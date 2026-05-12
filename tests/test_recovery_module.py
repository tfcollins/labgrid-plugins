"""Unit tests for ``adi_lg_plugins.recovery`` — pure host-side, no hardware."""

from __future__ import annotations

import gzip
import os
import shutil
import struct
import subprocess

import pytest

from adi_lg_plugins.recovery import (
    DEFAULT_APPLETS,
    DEFAULT_DEV_NODES,
    build_cpio,
    build_recovery_initramfs,
    stage_recovery_rootfs,
)
from adi_lg_plugins.recovery.cpio import CpioBuilder, DevNode

# ---------------------------------------------------------------------------
# CpioBuilder
# ---------------------------------------------------------------------------


def _parse_cpio(blob: bytes) -> list[dict]:
    """Tiny newc-cpio parser sufficient for asserting our builder output.

    Returns one dict per entry: ``{name, mode, body, dev_major, dev_minor}``.
    Stops at the TRAILER!!! sentinel.
    """
    entries = []
    off = 0
    while off < len(blob):
        assert blob[off : off + 6] == b"070701", f"bad magic at {off}: {blob[off : off + 6]!r}"
        # 13 hex fields, each 8 bytes
        ino, mode, uid, gid, nlink, mtime, fsize, dmaj, dmin, rmaj, rmin, nlen, _check = (
            int(blob[off + 6 + i * 8 : off + 6 + (i + 1) * 8], 16) for i in range(13)
        )
        name_start = off + 6 + 13 * 8
        name_end = name_start + nlen
        name = blob[name_start : name_end - 1].decode()
        # Pad header+name to 4 bytes
        header_block_end = name_end + ((-name_end) & 3)
        body = blob[header_block_end : header_block_end + fsize]
        body_block_end = header_block_end + fsize + ((-fsize) & 3)
        if name == "TRAILER!!!":
            return entries
        entries.append(
            {
                "name": name,
                "mode": mode,
                "body": body,
                "dev_major": rmaj,
                "dev_minor": rmin,
            }
        )
        off = body_block_end
    raise AssertionError("cpio blob missing TRAILER!!! sentinel")


def test_cpio_builder_file_and_symlink(tmp_path):
    cb = CpioBuilder()
    cb.add_dir("bin")
    cb.add_file("bin/hello", b"#!/bin/sh\necho hi\n", mode=0o755)
    cb.add_symlink("bin/sh", "hello", mode=0o777)
    blob = cb.serialize()

    entries = _parse_cpio(blob)
    by_name = {e["name"]: e for e in entries}
    assert set(by_name) == {"bin", "bin/hello", "bin/sh"}

    # File: regular bits set, exec mode preserved
    assert by_name["bin/hello"]["mode"] & 0o170000 == 0o100000
    assert by_name["bin/hello"]["mode"] & 0o777 == 0o755
    assert by_name["bin/hello"]["body"] == b"#!/bin/sh\necho hi\n"

    # Symlink: body is the target string
    assert by_name["bin/sh"]["mode"] & 0o170000 == 0o120000
    assert by_name["bin/sh"]["body"] == b"hello"

    # Dir: mode bits indicate directory
    assert by_name["bin"]["mode"] & 0o170000 == 0o040000


def test_cpio_builder_dev_nodes_carry_major_minor():
    cb = CpioBuilder()
    cb.add_dir("dev")
    cb.add_dev_node(DevNode("dev/console", "c", 5, 1, 0o600))
    cb.add_dev_node(DevNode("dev/mmcblk0", "b", 179, 0, 0o660))
    entries = {e["name"]: e for e in _parse_cpio(cb.serialize())}

    console = entries["dev/console"]
    assert console["mode"] & 0o170000 == 0o020000  # S_IFCHR
    assert console["mode"] & 0o777 == 0o600
    assert (console["dev_major"], console["dev_minor"]) == (5, 1)

    mmc = entries["dev/mmcblk0"]
    assert mmc["mode"] & 0o170000 == 0o060000  # S_IFBLK
    assert (mmc["dev_major"], mmc["dev_minor"]) == (179, 0)


def test_cpio_builder_rejects_unknown_dev_kind():
    cb = CpioBuilder()
    with pytest.raises(ValueError, match="invalid dev-node kind"):
        cb.add_dev_node(DevNode("dev/bad", "p", 1, 2))


def test_build_cpio_skips_host_dev_dir(tmp_path):
    """A populated ``dev/`` in the rootfs must not leak into the archive.

    The /dev tree on the host has nothing useful to a recovery cpio, and
    real device nodes can't even be represented there without root. The
    builder must ignore the host ``dev/`` and rely on the explicit
    ``dev_nodes=`` list.
    """
    rootfs = tmp_path / "rootfs"
    (rootfs / "dev").mkdir(parents=True)
    (rootfs / "dev" / "stray-file").write_text("should not appear")
    (rootfs / "bin").mkdir()
    (rootfs / "bin" / "busybox").write_text("fake")

    cpio = tmp_path / "out.cpio"
    nbytes = build_cpio(rootfs, cpio, dev_nodes=[DevNode("dev/console", "c", 5, 1, 0o600)])
    assert nbytes == cpio.stat().st_size

    names = {e["name"] for e in _parse_cpio(cpio.read_bytes())}
    assert "dev/console" in names
    assert "dev/stray-file" not in names
    assert "bin/busybox" in names


def test_build_cpio_payload_starts_with_dev_nodes(tmp_path):
    """Dev nodes are emitted before the walked tree so they're guaranteed."""
    rootfs = tmp_path / "rootfs"
    (rootfs / "bin").mkdir(parents=True)
    (rootfs / "bin" / "x").write_text("x")

    cpio = tmp_path / "out.cpio"
    build_cpio(rootfs, cpio, dev_nodes=DEFAULT_DEV_NODES)

    names = [e["name"] for e in _parse_cpio(cpio.read_bytes())]
    # /dev directory + dev/console must precede any non-dev file
    assert names[0] == "dev"
    dev_console_idx = names.index("dev/console")
    bin_x_idx = names.index("bin/x")
    assert dev_console_idx < bin_x_idx


# ---------------------------------------------------------------------------
# stage_recovery_rootfs
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_busybox(tmp_path):
    """A 'busybox' binary stand-in (real cross-compile not needed for staging)."""
    p = tmp_path / "busybox"
    p.write_bytes(b"\x7fELF" + b"\x00" * 100)
    os.chmod(p, 0o755)
    return p


def test_stage_recovery_rootfs_creates_all_layout(fake_busybox, tmp_path):
    rootfs = tmp_path / "rootfs"
    stage_recovery_rootfs(fake_busybox, rootfs)

    # Standard pseudo-fs mountpoints
    for sub in ("bin", "sbin", "etc/udhcpc", "proc", "sys", "dev", "tmp"):
        assert (rootfs / sub).is_dir(), f"missing {sub}/"

    # busybox + applet symlinks
    assert (rootfs / "bin" / "busybox").read_bytes().startswith(b"\x7fELF")
    for applet in ("sh", "dd", "mktemp", "wget", "rx"):
        link = rootfs / "bin" / applet
        assert link.is_symlink(), f"{applet} not symlinked"
        assert os.readlink(link) == "busybox"

    # sbin links use ../bin/busybox so the kernel's init search path works
    assert os.readlink(rootfs / "sbin" / "init") == "../bin/busybox"
    assert os.readlink(rootfs / "sbin" / "udhcpc") == "../bin/busybox"

    # Templates present and executable
    init = rootfs / "init"
    assert init.read_bytes().startswith(b"#!/bin/sh"), "init template not installed"
    assert os.access(init, os.X_OK), "init not executable"
    udhcpc = rootfs / "etc" / "udhcpc" / "default.script"
    assert udhcpc.read_bytes().startswith(b"#!/bin/sh"), "udhcpc hook not installed"
    assert os.access(udhcpc, os.X_OK)


def test_stage_recovery_rootfs_missing_busybox_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="busybox"):
        stage_recovery_rootfs(tmp_path / "nope", tmp_path / "rootfs")


def test_stage_recovery_rootfs_overwrites_stale_symlinks(fake_busybox, tmp_path):
    rootfs = tmp_path / "rootfs"
    # Pre-create a stale link pointing somewhere wrong.
    (rootfs / "bin").mkdir(parents=True)
    os.symlink("not-busybox", rootfs / "bin" / "sh")
    stage_recovery_rootfs(fake_busybox, rootfs)
    assert os.readlink(rootfs / "bin" / "sh") == "busybox"


# ---------------------------------------------------------------------------
# build_recovery_initramfs (full pipeline, mkimage optional)
# ---------------------------------------------------------------------------


def test_build_recovery_initramfs_raw_cpio_gz(fake_busybox, tmp_path):
    """Without mkimage we still get a valid gzipped cpio."""
    out = tmp_path / "initramfs.cpio.gz"
    sizes = build_recovery_initramfs(
        busybox=fake_busybox,
        output=out,
        work_dir=tmp_path / "work",
        wrap_uimage=False,
    )
    assert out.exists()
    assert sizes["cpio"] > 0
    assert sizes["gz"] > 0
    assert "uimage" not in sizes

    # File header is the gzip magic; payload decompresses to valid cpio
    raw = gzip.decompress(out.read_bytes())
    assert raw.startswith(b"070701"), "decompressed payload is not a newc cpio"
    names = {e["name"] for e in _parse_cpio(raw)}
    # Standard rootfs entries
    assert "init" in names
    assert "bin/busybox" in names
    assert "bin/sh" in names
    # And the device nodes
    assert "dev/console" in names
    assert "dev/mmcblk0" in names


@pytest.mark.skipif(shutil.which("mkimage") is None, reason="mkimage not installed")
def test_build_recovery_initramfs_uimage(fake_busybox, tmp_path):
    out = tmp_path / "uInitrd.recovery"
    sizes = build_recovery_initramfs(
        busybox=fake_busybox,
        output=out,
        work_dir=tmp_path / "work",
        image_name="unit-test",
    )
    assert out.exists()
    assert sizes["uimage"] == out.stat().st_size

    # U-Boot legacy uImage starts with magic 0x27051956 big-endian
    magic = struct.unpack(">I", out.read_bytes()[:4])[0]
    assert magic == 0x27051956, f"unexpected uImage magic 0x{magic:08x}"

    # And mkimage -l agrees about the type
    result = subprocess.run(["mkimage", "-l", str(out)], capture_output=True, text=True, check=True)
    assert "ARM Linux RAMDisk Image" in result.stdout
    assert "gzip compressed" in result.stdout
    assert "unit-test" in result.stdout


def test_build_recovery_initramfs_missing_mkimage_raises(monkeypatch, fake_busybox, tmp_path):
    """If mkimage is unavailable, wrap_uimage=True must error clearly."""
    from adi_lg_plugins.recovery import initramfs as ifs

    monkeypatch.setattr(ifs, "_have_mkimage", lambda: None)
    with pytest.raises(RuntimeError, match="mkimage not found"):
        build_recovery_initramfs(
            busybox=fake_busybox,
            output=tmp_path / "out.img",
            work_dir=tmp_path / "work",
        )


# ---------------------------------------------------------------------------
# Defaults sanity
# ---------------------------------------------------------------------------


def test_default_applets_include_strategy_dependencies():
    """The default applet set must cover everything the strategy invokes."""
    # /init script
    for required in ("sh", "mount", "ifconfig", "udhcpc", "hostname", "echo"):
        assert required in DEFAULT_APPLETS, f"DEFAULT_APPLETS missing {required}"
    # ADIShellDriver file transfer (mktemp + xmodem) + run() path
    for required in ("mktemp", "rx", "base64", "tee", "dd", "wget", "sync"):
        assert required in DEFAULT_APPLETS, f"DEFAULT_APPLETS missing {required}"


def test_default_dev_nodes_include_console_and_target():
    paths = {n.path for n in DEFAULT_DEV_NODES}
    # /dev/console is the one that makes init's stdio reach the serial console.
    assert "dev/console" in paths
    # /dev/mmcblk0 is what the recovery dd writes to.
    assert "dev/mmcblk0" in paths
