"""End-to-end recovery initramfs builder.

Takes a cross-compiled static busybox + a destination uImage path and
produces an initramfs ready for ``BootZynq7000JTAGRecovery`` to TFTP-load.
The busybox binary itself is the caller's responsibility (the toolchain
varies by host). Everything else — applet symlinks, ``/init`` script,
udhcpc hook, device nodes, cpio packaging, and U-Boot uImage wrapping —
is bundled here.

Public API:

- :func:`build_recovery_initramfs` — one-shot orchestrator.
- :func:`stage_recovery_rootfs` — lower-level: populate a directory with
  busybox + applets + ``/init`` + ``/etc/udhcpc/default.script``. Useful
  when you want to customize the rootfs before packaging.
- :data:`DEFAULT_APPLETS` — the busybox applet set ``/init`` and
  ADIShellDriver actually need.
- :data:`DEFAULT_DEV_NODES` — minimal /dev set the kernel + recovery
  script rely on.
"""

from __future__ import annotations

import gzip
import logging
import os
import shutil
import subprocess
from collections.abc import Iterable
from importlib import resources

from adi_lg_plugins.recovery.cpio import DevNode, build_cpio

log = logging.getLogger(__name__)


DEFAULT_DEV_NODES: list[DevNode] = [
    # /dev/console (char 5:1) — kernel uses it for init stdio. The
    # whole reason this builder exists rather than `find | cpio`.
    DevNode("dev/console", "c", 5, 1, 0o600),
    DevNode("dev/null", "c", 1, 3, 0o666),
    DevNode("dev/tty", "c", 5, 0, 0o666),
    DevNode("dev/zero", "c", 1, 5, 0o666),
    # /dev/mmcblk0 is the SD device the recovery script dd's into.
    DevNode("dev/mmcblk0", "b", 179, 0, 0o660),
]


# Busybox applets needed by:
#   - /init (sh, mount, ifconfig, udhcpc, hostname, echo, …)
#   - ADIShellDriver's file-transfer + run paths (mktemp, rx, dd, base64,
#     tee, sed, grep, find, head, tail, wc, …)
#   - the recovery one-liner the strategy sends (wget, dd, sync, test).
# Add to taste; missing applets surface as ``sh: <name>: not found`` at
# runtime and fail the relevant transition.
DEFAULT_APPLETS: tuple[str, ...] = (
    # core shell + control flow
    "sh",
    "ash",
    "init",
    "echo",
    "printf",
    "true",
    "false",
    "test",
    "[",
    "env",
    "hostname",
    "sleep",
    "exec",
    # filesystem ops
    "cat",
    "ls",
    "mkdir",
    "mknod",
    "ln",
    "rm",
    "cp",
    "mv",
    "chmod",
    "chown",
    "mount",
    "umount",
    "blockdev",
    "partprobe",
    "mktemp",
    "touch",
    "stat",
    "readlink",
    "dirname",
    "basename",
    "find",
    "du",
    "df",
    "rmdir",
    # text processing
    "sed",
    "grep",
    "cut",
    "awk",
    "tr",
    "head",
    "tail",
    "wc",
    "sort",
    "uniq",
    "md5sum",
    "sha256sum",
    "od",
    "hexdump",
    "tee",
    "xargs",
    "expr",
    "seq",
    # storage + network
    "dd",
    "sync",
    "ifconfig",
    "ip",
    "route",
    "udhcpc",
    "wget",
    "ping",
    "nc",
    "ftpget",
    "ftpput",
    # power
    "poweroff",
    "halt",
    "reboot",
    # misc utilities ADIShellDriver may invoke
    "base64",
    "dmesg",
    "mdev",
    "uname",
    "id",
    "which",
    "whoami",
    "date",
    "tar",
    "gunzip",
    "gzip",
    "stty",
    # XMODEM receivers (ADIShellDriver's run_script fallback chain).
    "rx",
    "rz",
)

# /sbin applets that need a direct ../bin/busybox symlink so the kernel
# can find them via the standard init search path even before $PATH is
# set up.
SBIN_APPLETS: tuple[str, ...] = (
    "init",
    "halt",
    "poweroff",
    "reboot",
    "ifconfig",
    "mdev",
    "udhcpc",
)


def _read_template(name: str) -> bytes:
    """Read a packaged template (init script, udhcpc hook) as bytes."""
    return resources.files("adi_lg_plugins.recovery.templates").joinpath(name).read_bytes()


def stage_recovery_rootfs(
    busybox: str | os.PathLike[str],
    rootfs_dir: str | os.PathLike[str],
    applets: Iterable[str] = DEFAULT_APPLETS,
    sbin_applets: Iterable[str] = SBIN_APPLETS,
) -> None:
    """Lay out a recovery rootfs tree at ``rootfs_dir``.

    Creates the standard directories (``bin``, ``sbin``, ``etc/udhcpc``,
    ``proc``, ``sys``, ``dev``, ``tmp``), copies ``busybox`` into
    ``bin/``, makes one symlink per applet, and writes the bundled
    ``/init`` + udhcpc hook with execute bits set.

    Does *not* create device nodes — those go into the cpio archive
    directly via :data:`DEFAULT_DEV_NODES`.

    Args:
        busybox: host path to a static ARM busybox binary.
        rootfs_dir: destination directory. Created if missing; reused
            if already populated (overwrites collisions).
        applets: busybox applet names to symlink into ``bin/``.
        sbin_applets: subset that also needs a ``sbin/`` symlink.
    """
    busybox = os.fspath(busybox)
    rootfs_dir = os.fspath(rootfs_dir)
    if not os.path.isfile(busybox):
        raise FileNotFoundError(f"busybox binary not found: {busybox}")

    for sub in ("bin", "sbin", "etc/udhcpc", "proc", "sys", "dev", "tmp"):
        os.makedirs(os.path.join(rootfs_dir, sub), exist_ok=True)

    target_busybox = os.path.join(rootfs_dir, "bin", "busybox")
    shutil.copyfile(busybox, target_busybox)
    os.chmod(target_busybox, 0o755)

    for applet in applets:
        link = os.path.join(rootfs_dir, "bin", applet)
        if os.path.lexists(link):
            os.unlink(link)
        os.symlink("busybox", link)

    for applet in sbin_applets:
        link = os.path.join(rootfs_dir, "sbin", applet)
        if os.path.lexists(link):
            os.unlink(link)
        os.symlink("../bin/busybox", link)

    init_path = os.path.join(rootfs_dir, "init")
    with open(init_path, "wb") as f:
        f.write(_read_template("init"))
    os.chmod(init_path, 0o755)

    udhcpc_path = os.path.join(rootfs_dir, "etc", "udhcpc", "default.script")
    with open(udhcpc_path, "wb") as f:
        f.write(_read_template("udhcpc-default.script"))
    os.chmod(udhcpc_path, 0o755)


def _have_mkimage() -> str | None:
    """Locate the ``mkimage`` binary; return None if absent."""
    return shutil.which("mkimage")


def build_recovery_initramfs(
    busybox: str | os.PathLike[str],
    output: str | os.PathLike[str],
    work_dir: str | os.PathLike[str] | None = None,
    image_name: str = "ZC706-recovery",
    applets: Iterable[str] = DEFAULT_APPLETS,
    dev_nodes: list[DevNode] = DEFAULT_DEV_NODES,
    wrap_uimage: bool = True,
) -> dict[str, int]:
    """Build a recovery initramfs uImage end-to-end.

    Pipeline: stage rootfs → cpio (with device nodes) → gzip → mkimage.

    Args:
        busybox: host path to a static ARM busybox binary.
        output: destination path for the final image. If ``wrap_uimage``
            is True (the default), this is a U-Boot legacy uImage that
            ``bootm`` can load. If False, this is a raw cpio.gz.
        work_dir: directory used to stage the rootfs tree + intermediate
            cpio. If None, a sibling of ``output`` is used. Caller is
            responsible for cleaning it up.
        image_name: ``Image Name`` field embedded in the uImage header.
        applets: busybox applets to symlink into ``bin/``.
        dev_nodes: device nodes to bake into the cpio.
        wrap_uimage: if False, skip the ``mkimage`` step and write the
            raw cpio.gz to ``output``. Lets callers use a different
            ramdisk format.

    Returns:
        Sizes dict with keys ``cpio``, ``gz``, ``uimage`` (the last
        omitted when ``wrap_uimage=False``).
    """
    busybox = os.fspath(busybox)
    output = os.fspath(output)
    if work_dir is None:
        work_dir = output + ".workdir"
    work_dir = os.fspath(work_dir)

    rootfs_dir = os.path.join(work_dir, "rootfs")
    os.makedirs(rootfs_dir, exist_ok=True)
    log.info("staging recovery rootfs at %s", rootfs_dir)
    stage_recovery_rootfs(busybox, rootfs_dir, applets=applets)

    cpio_path = os.path.join(work_dir, "initramfs.cpio")
    cpio_size = build_cpio(rootfs_dir, cpio_path, dev_nodes=dev_nodes)
    log.info("wrote cpio %s (%d bytes)", cpio_path, cpio_size)

    gz_path = cpio_path + ".gz"
    with open(cpio_path, "rb") as src, gzip.open(gz_path, "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)
    gz_size = os.path.getsize(gz_path)
    log.info("compressed cpio.gz %s (%d bytes)", gz_path, gz_size)

    sizes = {"cpio": cpio_size, "gz": gz_size}

    if not wrap_uimage:
        shutil.copyfile(gz_path, output)
        return sizes

    mkimage = _have_mkimage()
    if mkimage is None:
        raise RuntimeError(
            "mkimage not found on PATH; install u-boot-tools or pass "
            "wrap_uimage=False to skip the uImage wrap step"
        )
    cmd = [
        mkimage,
        "-A", "arm",
        "-O", "linux",
        "-T", "ramdisk",
        "-C", "gzip",
        "-n", image_name,
        "-d", gz_path,
        output,
    ]  # fmt: skip
    log.info("wrapping with mkimage: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True)
    sizes["uimage"] = os.path.getsize(output)
    log.info("wrote uImage %s (%d bytes)", output, sizes["uimage"])
    return sizes
