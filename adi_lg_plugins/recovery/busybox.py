"""On-demand busybox cross-compile + cache.

The recovery initramfs needs a static ARM ``busybox`` binary. Building it
is a 60–120 s one-time cost; subsequent runs reuse the cached binary. This
module hides the build and exposes a single entry point:

    from adi_lg_plugins.recovery.busybox import ensure_busybox_static
    bb = ensure_busybox_static()

``cache_dir`` defaults to ``$XDG_CACHE_HOME/labgrid-plugins/recovery``
(falls back to ``~/.cache/...``). Cross-compiler is autodetected by
walking common ``arm-*-gnueabihf-`` toolchain prefixes on ``PATH``; pass
``cross_compile=`` explicitly to override.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

log = logging.getLogger(__name__)


# Pinned to a stable upstream release. Tested against the kernel uImage
# format and ADIShellDriver's run/run_script paths.
DEFAULT_BUSYBOX_VERSION = "1.36.1"
DEFAULT_SOURCE_URL = f"https://busybox.net/downloads/busybox-{DEFAULT_BUSYBOX_VERSION}.tar.bz2"

# Toolchain prefixes to try when ``cross_compile`` isn't given. Order
# reflects what's typically already installed on lab hosts.
_DEFAULT_CROSS_PREFIXES: tuple[str, ...] = (
    "arm-none-linux-gnueabihf-",  # Linaro / ARM GNU
    "arm-linux-gnueabihf-",  # Debian/Ubuntu gcc-arm-linux-gnueabihf
    "arm-linux-musleabihf-",  # Alpine, musl-cross-make
)


class BusyboxBuildError(RuntimeError):
    """Raised when the cross-compile pipeline fails."""


def default_cache_dir() -> str:
    """Return the on-disk cache directory used for busybox artifacts."""
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "labgrid-plugins", "recovery")


def detect_cross_compile() -> str | None:
    """Find a usable ``arm-*-gnueabihf-`` toolchain prefix on PATH."""
    for prefix in _DEFAULT_CROSS_PREFIXES:
        if shutil.which(f"{prefix}gcc"):
            return prefix
    # Allow CROSS_COMPILE env var to act as a final fallback (matches the
    # convention every kernel/u-boot/busybox build expects).
    env = os.environ.get("CROSS_COMPILE")
    if env and shutil.which(f"{env}gcc"):
        return env
    return None


def _download(url: str, dest: str) -> None:
    log.info("downloading %s -> %s", url, dest)
    with urllib.request.urlopen(url, timeout=120) as src, open(dest, "wb") as out:
        shutil.copyfileobj(src, out)


def _extract(tarball: str, dest_dir: str) -> str:
    """Extract ``tarball`` into ``dest_dir``; return the top-level source dir."""
    with tarfile.open(tarball, "r:*") as tf:
        members = tf.getmembers()
        names = {m.name.split("/", 1)[0] for m in members if m.name}
        if len(names) != 1:
            raise BusyboxBuildError(
                f"unexpected tarball layout (multiple top-level entries): {names}"
            )
        top = names.pop()
        # `extractall` filter='data' is the safe default in Python 3.12+;
        # accept the no-filter ABI on older versions silently.
        try:
            tf.extractall(dest_dir, filter="data")
        except TypeError:
            tf.extractall(dest_dir)  # noqa: S202
    return os.path.join(dest_dir, top)


def _compile_busybox(source_dir: str, cross_compile: str) -> str:
    """Run ``make defconfig`` (+CONFIG_STATIC=y) and ``make busybox``.

    Returns the path to the built static busybox binary.
    """
    env = {**os.environ, "CROSS_COMPILE": cross_compile, "ARCH": "arm"}

    log.info("busybox: make defconfig (CROSS_COMPILE=%s)", cross_compile)
    subprocess.run(["make", "defconfig"], cwd=source_dir, env=env, check=True, capture_output=True)

    # Force a static build. busybox's defconfig leaves CONFIG_STATIC unset;
    # rewrite .config in place.
    config_path = os.path.join(source_dir, ".config")
    with open(config_path) as f:
        cfg = f.read()
    cfg = cfg.replace("# CONFIG_STATIC is not set", "CONFIG_STATIC=y")
    if "CONFIG_STATIC=y" not in cfg:
        # defconfig may already have it set, or the comment text changed
        # across versions. Append unconditionally as a safety net.
        cfg += "\nCONFIG_STATIC=y\n"
    with open(config_path, "w") as f:
        f.write(cfg)

    log.info("busybox: make -j%d busybox (this takes ~1 minute)", os.cpu_count() or 1)
    try:
        subprocess.run(
            ["make", "-j", str(os.cpu_count() or 1), "busybox"],
            cwd=source_dir,
            env=env,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        # Surface the actual build error — there are dozens of possible
        # failure modes (missing headers, stale toolchain, etc.).
        raise BusyboxBuildError(
            "busybox build failed:\n"
            f"  command: {' '.join(e.cmd)}\n"
            f"  stderr (tail): {e.stderr.decode(errors='replace')[-2000:]}"
        ) from e

    binary = os.path.join(source_dir, "busybox")
    if not os.path.isfile(binary):
        raise BusyboxBuildError(f"build claimed success but {binary} doesn't exist")
    return binary


def ensure_busybox_static(
    cache_dir: str | None = None,
    source_url: str = DEFAULT_SOURCE_URL,
    cross_compile: str | None = None,
) -> str:
    """Return the path to a static ARM busybox binary, building once if absent.

    Args:
        cache_dir: directory to cache the built binary in. Defaults to
            ``$XDG_CACHE_HOME/labgrid-plugins/recovery``.
        source_url: where to fetch busybox sources from when a build is
            needed. Defaults to the upstream 1.36.1 tarball.
        cross_compile: toolchain prefix (e.g.
            ``"arm-linux-gnueabihf-"``). Autodetected from PATH +
            ``$CROSS_COMPILE`` if None.

    Returns:
        Absolute path to the cached static binary.

    Raises:
        BusyboxBuildError: when no toolchain is found, the download
            fails, or the build itself errors out.
    """
    cache_dir = cache_dir or default_cache_dir()
    os.makedirs(cache_dir, exist_ok=True)

    # Cache key is the URL hash so callers can swap versions without
    # cross-contaminating the cache.
    url_hash = hashlib.sha256(source_url.encode()).hexdigest()[:12]
    binary_path = os.path.join(cache_dir, f"busybox-armv7-static-{url_hash}")
    if os.path.isfile(binary_path):
        log.debug("reusing cached busybox at %s", binary_path)
        return binary_path

    cc = cross_compile or detect_cross_compile()
    if cc is None:
        raise BusyboxBuildError(
            "no ARM cross-compiler found on PATH. Install one of "
            f"{', '.join(f'{p}gcc' for p in _DEFAULT_CROSS_PREFIXES)}, "
            "or pass cross_compile=... explicitly."
        )

    with tempfile.TemporaryDirectory(prefix="adi-recovery-bb-") as work:
        tarball = os.path.join(work, "busybox.tar.bz2")
        _download(source_url, tarball)
        source_dir = _extract(tarball, work)
        built = _compile_busybox(source_dir, cc)
        shutil.copyfile(built, binary_path)
    os.chmod(binary_path, 0o755)
    log.info("cached busybox at %s", binary_path)
    return binary_path
