"""Cloudsmith Downloader Driver for Labgrid.

Resolves and downloads boot artifacts (e.g. ``BOOT.BIN``) from a Cloudsmith
package repository (default ``adi/sdg-boot-partition``), mirroring the
KuiperDLDriver pattern. The downloaded file is exposed to the FPGA SoC boot
strategies through the same ``get_boot_files_from_release()`` /
``_boot_files`` contract used by KuiperDLDriver, so it drops into those
strategies in place of the Kuiper downloader.

The Cloudsmith API resolution logic is ported from a standalone reference
script; the streaming download + retry session is copied from
``kuiperdldriver.py`` (kept independent on purpose).
"""

import hashlib
import json
import logging
import os
import time

import attr
import requests
from labgrid.driver.common import Driver
from labgrid.factory import target_factory
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from tqdm import tqdm

logger = logging.getLogger(__name__)

CLOUDSMITH_API = "https://api.cloudsmith.io/packages/{owner}/{repo}/"

# Maps a Cloudsmith ``system`` segment prefix to the short FPGA carrier name
# used by the place-tag schema (carrier=zcu102, etc.).
CARRIER_PREFIXES = [
    ("zynqmp-zcu102-rev10-", "zcu102"),
    ("zynqmp-adrv9009-zu11eg-revb-", "zu11eg"),
    ("zynqmp-adrv9009-zu11eg-", "zu11eg"),
    ("zynqmp-jupiter-sdr", "jupiter-sdr"),
    ("zynq-zc706-adv7511-", "zc706"),
    ("zynq-zc702-adv7511-", "zc702"),
    ("zynq-zed-adv7511-", "zed"),
    ("zynq-coraz7s-", "coraz7s"),
    ("zynq-adrv9361-z7035-", "adrv9361-z7035"),
    ("zynq-adrv9364-z7020-", "adrv9364-z7020"),
    ("versal-vck190-reva-", "vck190"),
    ("versal-vpk180-reva-", "vpk180"),
    ("ad9081_fmca_ebz_vpk180", "vpk180"),
    ("ad9082_fmca_ebz_vpk180", "vpk180"),
]

# ``system`` segments that are not real carrier builds and must be skipped.
TO_IGNORE = [
    "zynq-zed-otg",
    "zynq-zed-adv7511",
    "pulsar_adc_zed",
    "pulsar_adc_zc706",
    "pulsar_adc_zc702",
    "zynq-zc702-adv7511",
    "zynq-zc706-adv7511",
]


class Downloader:
    """Streaming downloader with retry + sha256 verification.

    Copied from KuiperDLDriver's Downloader (kept independent). Only the
    pieces needed for individual-file downloads are retained: a retrying
    session and a streaming ``download`` that returns the sha256 digest.
    """

    def retry_session(
        self,
        retries=3,
        backoff_factor=0.3,
        status_forcelist=(429, 500, 502, 504),
        session=None,
    ):
        session = session or requests.Session()
        retry = Retry(
            total=retries,
            read=retries,
            connect=retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def download(self, url, fname, headers=None):
        """Stream ``url`` to ``fname`` and return the sha256 hexdigest."""
        resp = self.retry_session().get(url, stream=True, headers=headers)
        if not resp.ok:
            raise Exception(os.path.basename(fname) + " - File not found!")
        total = int(resp.headers.get("content-length", 0))
        sha256_hash = hashlib.sha256()
        with (
            open(fname, "wb") as file,
            tqdm(
                desc=fname,
                total=total,
                unit="iB",
                unit_scale=True,
                unit_divisor=1024,
            ) as bar,
        ):
            for data in resp.iter_content(chunk_size=1024):
                size = file.write(data)
                sha256_hash.update(data)
                bar.update(size)
        return sha256_hash.hexdigest()


def verify_sha256(fname, expected):
    """Raise if the sha256 of ``fname`` does not match ``expected``."""
    h = hashlib.sha256()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if expected and actual != expected:
        raise Exception(
            f"sha256 mismatch for {os.path.basename(fname)}: expected {expected}, got {actual}"
        )
    return actual


def search_cloudsmith_packages(owner, repo, query, token, page_size=100):
    """Query the Cloudsmith packages API, paging through all results."""
    url = CLOUDSMITH_API.format(owner=owner, repo=repo)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    all_packages = []
    page = 1
    while True:
        params = {"query": query, "page": page, "page_size": page_size}
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        packages = response.json()
        print(f"Cloudsmith API page {page}: {len(packages)} packages")
        if not packages:
            break
        all_packages.extend(packages)
        logger.debug("Fetched page %d with %d packages", page, len(packages))
        page += 1
        if len(packages) < page_size:
            break
    return all_packages


def parse_version_info(version_str, tags, repo=None):
    """Parse a Cloudsmith version string into structured metadata.

    Returns ``None`` (rather than raising) for unparseable strings,
    ignored systems, or unknown carriers, so one unexpected package never
    crashes resolution.
    """
    parts = [p for p in version_str.strip("/").split("/") if p]
    if len(parts) < 2:
        return None

    if repo == "sdg-hdl":
        # hdl/releases/hdl_2022_r2/hdl_output/2024_02_15-06_47_17/adrv9371x_kcu105/
        last = parts[-1]
        pparts = last.split("_")
        if len(pparts) < 2:
            return None
        project = pparts[0]
        branch = parts[2]

    else:
        project = parts[0]
        branch = parts[1]

    # kuiper_partition releases have no timestamp segment.
    if repo == "sdg-hdl":
        timestamp = parts[4]
        remaining = ModuleNotFoundError

    else:
        if branch.startswith("kuiper_partition"):
            remaining = parts[2:]
            timestamp = None
        else:
            if len(parts) < 3:
                return None
            timestamp = parts[2]
            remaining = parts[3:]

    # Skip a repeated "boot_partition" segment if present.
    if repo == "sdg-hdl":
        fpga_carrier = pparts[1]
        # system = f"{fpga_carrier}-{project}"
        system = None
        variant = None
        carrier = "Xilinx"
    else:
        if remaining and remaining[0] == "boot_partition":
            remaining = remaining[1:]

        # An "adi-" prefixed segment is the carrier family, not the system.
        carrier = None
        if remaining and remaining[0].startswith("adi-"):
            carrier = remaining[0]
            remaining = remaining[1:]

        system = remaining[0] if remaining else None
        remaining = remaining[1:] if remaining else []
        variant = remaining[0] if remaining else None

        if system:
            for ignore in TO_IGNORE:
                if system.startswith(ignore):
                    return None

        fpga_carrier = None

    if system:
        for prefix, carrier_name in CARRIER_PREFIXES:
            if system.startswith(prefix):
                fpga_carrier = carrier_name
                project = system[len(prefix) :] if len(system) > len(prefix) else system
                break
        else:
            logger.debug("Unknown carrier in version string, skipping: %s", system)
            return None

    hdl_sha = None
    linux_sha = None
    if tags:
        for tag in tags:
            if "hdl" in tag:
                hdl_sha = tag.split("-")[-1]
            if "linux" in tag:
                linux_sha = tag.split("-")[-1]

    return {
        "project": project,
        "branch": branch,
        "timestamp": timestamp,
        "carrier": fpga_carrier,
        "carrier_family": carrier,
        "system": system,
        "variant": variant,
        "hdl_git_sha": hdl_sha,
        "linux_git_sha": linux_sha,
    }


def get_latest_bootfiles(
    owner, repo, fpga_carrier=None, daughter_card=None, filename=None, token=None, pin=None
):
    """Resolve the matching Cloudsmith package, returning the raw package dict.

    Without ``pin`` the newest matching package (by ``uploaded_at``) is
    returned; with ``pin`` the package whose ``version`` equals ``pin`` is
    returned. The returned dict carries ``cdn_url``, ``checksums``
    ``version`` and ``uploaded_at`` plus a parsed ``_info`` entry.
    """
    # query = f"filename:{filename} AND version:*{fpga_carrier}*{daughter_card}*"
    # query = f"filename:{filename} AND version:*{daughter_card}*"
    query = f"filename:{filename}"
    if fpga_carrier:
        query += f" AND version:*{fpga_carrier}*"
    if daughter_card:
        query += f" AND version:*{daughter_card}*"
    packages = search_cloudsmith_packages(owner, repo, query, token, page_size=1000)
    if not packages:
        return None

    candidates = []
    for package in packages:
        tags = package.get("tags", {})
        if isinstance(tags, dict):
            tags = tags.get("info", [])
        info = parse_version_info(package.get("version", ""), tags, repo)
        if info is None:
            print(f"Skipping unparseable or ignored package version: {package.get('version')}")
            continue
        if info["carrier"] == fpga_carrier:
            candidates.append({**package, "_info": info})

    if not candidates:
        return None

    if pin is not None:
        for package in candidates:
            if package.get("version") == pin:
                return package
        raise Exception(
            f"Pinned version {pin!r} not found for carrier {fpga_carrier!r} / {daughter_card!r}"
        )

    candidates.sort(key=lambda p: p.get("uploaded_at", ""), reverse=True)
    return candidates[0]


@target_factory.reg_driver
@attr.s(eq=False)
class CloudsmithDLDriver(Driver):
    """Driver to resolve and download Cloudsmith boot artifacts.

    Exposes the same ``get_boot_files_from_release()`` / ``_boot_files``
    contract as KuiperDLDriver so it drops into the FPGA SoC boot strategies.
    """

    bindings = {"cloudsmith_resource": {"CloudsmithRelease"}}

    cache_datafile = "cache_info.json"

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self._boot_files = []

    def _cache_path(self):
        return os.path.expanduser(self.cloudsmith_resource.cache_path)

    def _resolve(self):
        """Resolve the matching Cloudsmith package from the resource config."""
        res = self.cloudsmith_resource
        token = res.api_token
        if not token:
            raise Exception("No Cloudsmith API token (set CLOUDSMITH_API_TOKEN or api_token).")
        package = get_latest_bootfiles(
            res.owner,
            res.repo,
            res.fpga_carrier,
            res.daughter_card,
            res.filename,
            token,
            pin=res.version,
        )
        if package is None:
            raise Exception(
                f"No {res.filename} found for carrier {res.fpga_carrier!r} / "
                f"daughter card {res.daughter_card!r}"
            )
        return package

    def check_cached(self, version):
        """Return the cached boot-file path for ``version`` if present, else None."""
        cache_path = self._cache_path()
        cache_file_path = os.path.join(cache_path, self.cache_datafile)
        if not os.path.exists(cache_file_path):
            return None
        with open(cache_file_path) as f:
            cache_data = json.load(f)
        entry = cache_data.get(version)
        if entry and os.path.exists(entry["boot_file_path"]):
            return entry["boot_file_path"]
        return None

    def download_release(self, version=None):
        """Resolve, download, and cache the boot artifact; return its local path."""
        res = self.cloudsmith_resource
        package = self._resolve()
        version = package.get("version")

        cached = self.check_cached(version)
        if cached:
            self.logger.info(f"Cloudsmith artifact {version} is already cached.")
            res.boot_file_path = cached
            return cached

        cache_path = self._cache_path()
        # Use a filesystem-safe subdirectory derived from the version string.
        safe_version = version.strip("/").replace("/", "_")
        dest_dir = os.path.join(cache_path, safe_version)
        os.makedirs(dest_dir, exist_ok=True)
        boot_file_path = os.path.join(dest_dir, res.filename)

        url = package.get("cdn_url")
        self.logger.info(f"Downloading {res.filename} {version} from {url}")
        headers = {"Authorization": f"Bearer {res.api_token}"}
        Downloader().download(url, boot_file_path, headers=headers)

        expected = (package.get("checksums") or {}).get("sha256")
        verify_sha256(boot_file_path, expected)

        cache_file_path = os.path.join(cache_path, self.cache_datafile)
        cache_data = {}
        if os.path.exists(cache_file_path):
            with open(cache_file_path) as f:
                cache_data = json.load(f)
        cache_data[version] = {
            "boot_file_path": boot_file_path,
            "cdn_url": url,
            "sha256": expected,
            "download_time": time.ctime(),
            "download_date": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        }
        with open(cache_file_path, "w") as f:
            json.dump(cache_data, f, indent=4)

        self.logger.info(f"Cloudsmith artifact {version} cached successfully.")
        res.boot_file_path = boot_file_path
        return boot_file_path

    def get_boot_file_path(self, version=None):
        """Ensure the artifact is downloaded and return its local path."""
        return self.download_release(version=version)

    def get_boot_files_from_release(self):
        """Strategy-facing contract: populate and return ``_boot_files``."""
        self._boot_files = [self.get_boot_file_path()]
        return self._boot_files
