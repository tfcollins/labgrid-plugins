"""Mocked unit tests for the Cloudsmith download stack (no network)."""

from __future__ import annotations

import hashlib
import json
from unittest.mock import MagicMock

import pytest

from adi_lg_plugins.drivers import cloudsmithdldriver as csd
from adi_lg_plugins.drivers.cloudsmithdldriver import (
    CloudsmithDLDriver,
    get_latest_bootfiles,
    parse_version_info,
    verify_sha256,
)

# --- parse_version_info -----------------------------------------------------


def test_parse_version_info_known_carrier():
    info = parse_version_info(
        "boot_partition/main/2025_06_14-07_18_12/zynqmp-zcu102-rev10-adrv9009/boot_bin_LVDS/",
        tags=["hdl_git_sha-d146370c1", "linux_git_sha-e2573a4dfe1a"],
    )
    assert info is not None
    assert info["carrier"] == "zcu102"
    assert info["variant"] == "boot_bin_LVDS"
    assert info["timestamp"] == "2025_06_14-07_18_12"
    assert info["hdl_git_sha"] == "d146370c1"
    assert info["linux_git_sha"] == "e2573a4dfe1a"


def test_parse_version_info_unknown_carrier_returns_none():
    # Downgraded from a raise: an unknown carrier must skip, not crash.
    info = parse_version_info(
        "boot_partition/main/2025_06_14-07_18_12/zynqmp-someboard-rev1-foo/boot_bin_LVDS/",
        tags=[],
    )
    assert info is None


def test_parse_version_info_ignored_system_returns_none():
    info = parse_version_info(
        "boot_partition/main/2025_06_14-07_18_12/zynq-zed-adv7511-something/",
        tags=[],
    )
    assert info is None


# --- get_latest_bootfiles ---------------------------------------------------


def _pkg(version, uploaded_at, sha):
    return {
        "version": version,
        "uploaded_at": uploaded_at,
        "tags": {"info": []},
        "cdn_url": f"https://cdn/{version}/BOOT.BIN",
        "checksums": {"sha256": sha},
    }


_FAKE_PACKAGES = [
    _pkg(
        "boot_partition/main/2025_01_01-00_00_00/zynqmp-zcu102-rev10-adrv9009/", "2025-01-01", "aaa"
    ),
    _pkg(
        "boot_partition/main/2025_06_14-07_18_12/zynqmp-zcu102-rev10-adrv9009/", "2025-06-14", "bbb"
    ),
    _pkg(
        "boot_partition/main/2025_03_03-00_00_00/zynqmp-zcu102-rev10-adrv9009/", "2025-03-03", "ccc"
    ),
]


def test_get_latest_bootfiles_picks_newest(monkeypatch):
    monkeypatch.setattr(csd, "search_cloudsmith_packages", lambda *a, **k: list(_FAKE_PACKAGES))
    pkg = get_latest_bootfiles("adi", "sdg-boot-partition", "zcu102", "adrv9009", "BOOT.BIN", "tok")
    assert pkg["uploaded_at"] == "2025-06-14"
    assert pkg["checksums"]["sha256"] == "bbb"
    assert pkg["cdn_url"].endswith("BOOT.BIN")


def test_get_latest_bootfiles_pin_selects_exact(monkeypatch):
    monkeypatch.setattr(csd, "search_cloudsmith_packages", lambda *a, **k: list(_FAKE_PACKAGES))
    pin = "boot_partition/main/2025_03_03-00_00_00/zynqmp-zcu102-rev10-adrv9009/"
    pkg = get_latest_bootfiles(
        "adi", "sdg-boot-partition", "zcu102", "adrv9009", "BOOT.BIN", "tok", pin=pin
    )
    assert pkg["version"] == pin
    assert pkg["checksums"]["sha256"] == "ccc"


def test_get_latest_bootfiles_pin_not_found_raises(monkeypatch):
    monkeypatch.setattr(csd, "search_cloudsmith_packages", lambda *a, **k: list(_FAKE_PACKAGES))
    with pytest.raises(Exception, match="Pinned version"):
        get_latest_bootfiles(
            "adi", "sdg-boot-partition", "zcu102", "adrv9009", "BOOT.BIN", "tok", pin="nope"
        )


def test_get_latest_bootfiles_no_match_returns_none(monkeypatch):
    monkeypatch.setattr(csd, "search_cloudsmith_packages", lambda *a, **k: [])
    pkg = get_latest_bootfiles("adi", "sdg-boot-partition", "zcu102", "adrv9009", "BOOT.BIN", "tok")
    assert pkg is None


# --- query construction (vfilter / vnot, single + multiple) -----------------


def _capture_query(monkeypatch):
    """Patch the packages search to record the query string it receives."""
    captured = {}

    def fake_search(owner, repo, query, token, page_size=100):
        captured["query"] = query
        return []

    monkeypatch.setattr(csd, "search_cloudsmith_packages", fake_search)
    return captured


def test_query_no_filters(monkeypatch):
    captured = _capture_query(monkeypatch)
    get_latest_bootfiles("adi", "r", filename="BOOT.BIN", token="tok")
    assert captured["query"] == "filename:BOOT.BIN"


def test_query_single_vfilter_and_vnot_strings(monkeypatch):
    captured = _capture_query(monkeypatch)
    get_latest_bootfiles("adi", "r", filename="BOOT.BIN", vfilter="x", vnot="a", token="tok")
    assert captured["query"] == "filename:BOOT.BIN AND version:*x* AND version:~a"


def test_query_multiple_vfilter_and_vnot(monkeypatch):
    captured = _capture_query(monkeypatch)
    get_latest_bootfiles(
        "adi", "r", filename="BOOT.BIN", vfilter=["x", "y"], vnot=["a", "b"], token="tok"
    )
    assert captured["query"] == (
        "filename:BOOT.BIN AND version:*x* AND version:*y* AND version:~a AND version:~b"
    )


def test_query_empty_tuples_add_no_clauses(monkeypatch):
    captured = _capture_query(monkeypatch)
    get_latest_bootfiles("adi", "r", filename="BOOT.BIN", vfilter=(), vnot=(), token="tok")
    assert captured["query"] == "filename:BOOT.BIN"


# --- CloudsmithRelease resource validators ----------------------------------


def test_resource_accepts_str_and_iterable_for_vfilter_vnot():
    from labgrid import Target

    from adi_lg_plugins.resources.cloudsmithrelease import CloudsmithRelease

    # Single string (back-compat) and a tuple of strings must both validate.
    str_res = CloudsmithRelease(Target("t-str"), name=None, vfilter="x", vnot="a")
    assert str_res.vfilter == "x"
    assert str_res.vnot == "a"

    list_res = CloudsmithRelease(Target("t-list"), name=None, vfilter=["x", "y"], vnot=("a", "b"))
    assert list(list_res.vfilter) == ["x", "y"]
    assert list(list_res.vnot) == ["a", "b"]


# --- verify_sha256 ----------------------------------------------------------


def test_verify_sha256_mismatch_raises(tmp_path):
    f = tmp_path / "BOOT.BIN"
    f.write_bytes(b"hello")
    with pytest.raises(Exception, match="sha256 mismatch"):
        verify_sha256(str(f), "deadbeef")


# --- driver download / cache / contract -------------------------------------


def _driver(tmp_path, version, sha):
    res = MagicMock()
    res.cache_path = str(tmp_path)
    res.filename = "BOOT.BIN"
    res.api_token = "tok"
    res.version = None
    drv = CloudsmithDLDriver.__new__(CloudsmithDLDriver)
    drv.cloudsmith_resource = res
    drv._boot_files = []
    # MagicMock for logger so info() calls are no-ops.
    drv.logger = MagicMock()
    return drv, res


def test_download_release_verifies_and_caches(tmp_path, monkeypatch):
    payload = b"boot-bin-bytes"
    sha = hashlib.sha256(payload).hexdigest()
    version = "boot_partition/main/2025_06_14-07_18_12/zynqmp-zcu102-rev10-adrv9009/"
    drv, res = _driver(tmp_path, version, sha)

    monkeypatch.setattr(
        drv,
        "_resolve",
        lambda: {
            "version": version,
            "cdn_url": "https://cdn/BOOT.BIN",
            "checksums": {"sha256": sha},
        },
    )

    def fake_download(self, url, fname, headers=None):
        with open(fname, "wb") as f:
            f.write(payload)
        return sha

    monkeypatch.setattr(csd.Downloader, "download", fake_download)

    path = drv.download_release()
    assert path.endswith("BOOT.BIN")
    assert res.boot_file_path == path

    cache_file = tmp_path / "cache_info.json"
    data = json.loads(cache_file.read_text())
    assert data[version]["sha256"] == sha
    assert data[version]["boot_file_path"] == path

    # Second call short-circuits to the cached path without re-downloading.
    monkeypatch.setattr(
        csd.Downloader,
        "download",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not download")),
    )
    assert drv.download_release() == path


def test_download_release_sha_mismatch_raises(tmp_path, monkeypatch):
    version = "boot_partition/main/2025_06_14-07_18_12/zynqmp-zcu102-rev10-adrv9009/"
    drv, res = _driver(tmp_path, version, "expected")
    monkeypatch.setattr(
        drv,
        "_resolve",
        lambda: {
            "version": version,
            "cdn_url": "https://cdn/BOOT.BIN",
            "checksums": {"sha256": "expectedsha"},
        },
    )

    def fake_download(self, url, fname, headers=None):
        with open(fname, "wb") as f:
            f.write(b"wrong")
        return "wrongsha"

    monkeypatch.setattr(csd.Downloader, "download", fake_download)
    with pytest.raises(Exception, match="sha256 mismatch"):
        drv.download_release()


def test_get_boot_files_from_release_populates_list(tmp_path, monkeypatch):
    payload = b"x"
    sha = hashlib.sha256(payload).hexdigest()
    version = "boot_partition/main/2025_06_14-07_18_12/zynqmp-zcu102-rev10-adrv9009/"
    drv, res = _driver(tmp_path, version, sha)
    monkeypatch.setattr(
        drv,
        "_resolve",
        lambda: {"version": version, "cdn_url": "u", "checksums": {"sha256": sha}},
    )

    def fake_download(self, url, fname, headers=None):
        with open(fname, "wb") as f:
            f.write(payload)
        return sha

    monkeypatch.setattr(csd.Downloader, "download", fake_download)

    out = drv.get_boot_files_from_release()
    assert out == drv._boot_files
    assert len(out) == 1 and out[0].endswith("BOOT.BIN")


# --- tools/cloudsmithdl helper ------------------------------------------------


def test_download_cloudsmith_boot_file_returns_path(monkeypatch):
    from adi_lg_plugins.tools import cloudsmithdl

    monkeypatch.setattr(
        CloudsmithDLDriver,
        "get_boot_file_path",
        lambda self, version=None: "/tmp/cache/v1/BOOT.BIN",
    )
    path = cloudsmithdl.download_cloudsmith_boot_file(
        fpga_carrier="zcu102",
        daughter_card="adrv9009",
        vfilter=("LVDS", "boot_bin"),
        vnot=("debug", "test"),
        filename="BOOT.BIN",
        owner="adi",
        repo="sdg-boot-partition",
        version=None,
        cache_path="/tmp/cloudsmith_cache",
    )
    assert path == "/tmp/cache/v1/BOOT.BIN"
