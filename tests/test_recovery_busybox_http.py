"""Unit tests for ``adi_lg_plugins.recovery.busybox`` and ``...http``."""

from __future__ import annotations

import os
import urllib.request

import pytest

from adi_lg_plugins.recovery import busybox as bb_mod
from adi_lg_plugins.recovery import http as http_mod

# ---------- busybox helpers ------------------------------------------------


def test_detect_cross_compile_returns_known_prefix(monkeypatch):
    """When ``arm-linux-gnueabihf-gcc`` is on PATH, the matching prefix wins."""
    found = {"arm-linux-gnueabihf-gcc": "/usr/bin/arm-linux-gnueabihf-gcc"}
    monkeypatch.setattr(bb_mod.shutil, "which", lambda name: found.get(name))
    assert bb_mod.detect_cross_compile() == "arm-linux-gnueabihf-"


def test_detect_cross_compile_returns_none_when_absent(monkeypatch):
    monkeypatch.setattr(bb_mod.shutil, "which", lambda _name: None)
    monkeypatch.delenv("CROSS_COMPILE", raising=False)
    assert bb_mod.detect_cross_compile() is None


def test_detect_cross_compile_honors_env_var(monkeypatch):
    """``$CROSS_COMPILE`` fallback when no standard prefix is on PATH."""
    monkeypatch.setattr(
        bb_mod.shutil,
        "which",
        lambda name: "/opt/toolchain/bin/" + name if name == "my-custom-gcc" else None,
    )
    monkeypatch.setenv("CROSS_COMPILE", "my-custom-")
    assert bb_mod.detect_cross_compile() == "my-custom-"


def test_ensure_busybox_static_returns_cached_path(tmp_path, monkeypatch):
    """Pre-existing cache short-circuits the download + build entirely."""
    cache = tmp_path / "cache"
    cache.mkdir()

    # Match the SHA-based filename the module computes.
    import hashlib

    digest = hashlib.sha256(bb_mod.DEFAULT_SOURCE_URL.encode()).hexdigest()[:12]
    cached = cache / f"busybox-armv7-static-{digest}"
    cached.write_bytes(b"\x7fELF cached")

    # If the function tried to build, it would call _download — fail loudly.
    monkeypatch.setattr(
        bb_mod, "_download", lambda *_a, **_kw: pytest.fail("should not redownload")
    )
    monkeypatch.setattr(
        bb_mod, "_compile_busybox", lambda *_a, **_kw: pytest.fail("should not rebuild")
    )

    result = bb_mod.ensure_busybox_static(cache_dir=str(cache))
    assert result == str(cached)


def test_ensure_busybox_static_raises_without_toolchain(tmp_path, monkeypatch):
    monkeypatch.setattr(bb_mod, "detect_cross_compile", lambda: None)
    with pytest.raises(bb_mod.BusyboxBuildError, match="no ARM cross-compiler"):
        bb_mod.ensure_busybox_static(cache_dir=str(tmp_path), cross_compile=None)


def test_ensure_busybox_static_full_pipeline(tmp_path, monkeypatch):
    """Download → extract → compile → cache. Each step is stubbed."""
    cache = tmp_path / "cache"

    monkeypatch.setattr(bb_mod, "detect_cross_compile", lambda: "fake-cc-")

    # Skip the real download; tarball contents are read by _extract.
    def fake_download(url, dest):
        assert url == bb_mod.DEFAULT_SOURCE_URL
        # Build a synthetic tarball with a single top-level dir.
        import tarfile

        with tarfile.open(dest, "w:bz2") as tf:
            info = tarfile.TarInfo(name="busybox-X.Y.Z/")
            info.type = tarfile.DIRTYPE
            tf.addfile(info)

    monkeypatch.setattr(bb_mod, "_download", fake_download)

    captured = {}

    def fake_compile(source_dir, cross_compile):
        captured["source_dir"] = source_dir
        captured["cross_compile"] = cross_compile
        # Drop a fake binary where the module expects it.
        binary = os.path.join(source_dir, "busybox")
        with open(binary, "wb") as f:
            f.write(b"\x7fELF fake binary")
        return binary

    monkeypatch.setattr(bb_mod, "_compile_busybox", fake_compile)

    result = bb_mod.ensure_busybox_static(cache_dir=str(cache))

    assert captured["cross_compile"] == "fake-cc-"
    assert os.path.isfile(result)
    assert open(result, "rb").read().startswith(b"\x7fELF")

    # Second call must hit the cache and not rebuild.
    monkeypatch.setattr(bb_mod, "_download", lambda *a, **kw: pytest.fail("re-download"))
    monkeypatch.setattr(bb_mod, "_compile_busybox", lambda *a, **kw: pytest.fail("rebuild"))
    again = bb_mod.ensure_busybox_static(cache_dir=str(cache))
    assert again == result


# ---------- http helpers ---------------------------------------------------


def test_serve_directory_serves_files_and_releases_port(tmp_path):
    """Round-trip: start server, GET a file, exit context, port is freed."""
    f = tmp_path / "hello.txt"
    f.write_bytes(b"hello recovery")

    with http_mod.serve_directory(str(tmp_path)) as (_host, port):
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/hello.txt", timeout=5) as r:
            body = r.read()
    assert body == b"hello recovery"

    # Once the context exits, the port should be reusable. Bind a fresh
    # listener as the strongest possible "actually freed" assertion.
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("127.0.0.1", port))
    finally:
        s.close()


def test_local_ip_for_returns_valid_address():
    ip = http_mod.local_ip_for("8.8.8.8")
    # Should be a dotted-quad IPv4 string; for an unrouted environment
    # the fallback ``127.0.0.1`` is also valid.
    assert ip.count(".") == 3
    for octet in ip.split("."):
        assert 0 <= int(octet) <= 255


def test_local_ip_for_fallback_on_resolve_failure(monkeypatch):
    import socket as _socket

    class _BrokenSocket:
        def __init__(self, *_a, **_kw):
            pass

        def connect(self, *_a, **_kw):
            raise OSError("simulated")

        def getsockname(self):  # pragma: no cover - never reached
            return ("0.0.0.0", 0)

        def close(self):
            pass

    monkeypatch.setattr(_socket, "socket", lambda *_a, **_kw: _BrokenSocket())
    assert http_mod.local_ip_for("8.8.8.8", fallback="127.5.5.5") == "127.5.5.5"
