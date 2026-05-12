"""newc-format cpio archive builder with explicit device-node support.

The Linux kernel opens ``/dev/console`` (char 5:1) for the init process's
stdio before exec'ing it. If that node isn't in the rootfs, init runs with
closed file descriptors and every ``echo`` vanishes silently — boot looks
like a kernel hang because no userspace output ever reaches the serial
port.

Standard ``find . | cpio -o -H newc`` can't create device nodes without
root privileges (``mknod`` fails). This module writes the newc bytes
directly so a regular user can produce a cpio that includes
``/dev/console``, ``/dev/null``, ``/dev/mmcblk0``, etc.

The cpio newc format is documented in the kernel tree at
``Documentation/early-userspace/buffer-format.rst``.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass, field

# stat S_IF* aren't exported as constants we can rely on; copy them in.
S_IFREG = 0o100000
S_IFDIR = 0o040000
S_IFLNK = 0o120000
S_IFCHR = 0o020000
S_IFBLK = 0o060000


@dataclass(frozen=True)
class DevNode:
    """A character or block device node to include in the cpio."""

    path: str  # archive-relative path, e.g. "dev/console"
    kind: str  # "c" (character) or "b" (block)
    major: int
    minor: int
    mode: int = 0o600


def _newc_header(
    name: str,
    body_len: int,
    mode: int,
    nlink: int = 1,
    mtime: int = 0,
    dev_major: int = 0,
    dev_minor: int = 0,
) -> bytes:
    """Emit a single newc-format cpio header + filename + padding.

    The newc layout: 6-byte ``070701`` magic, thirteen 8-byte hex fields,
    NUL-terminated filename, padded with NULs so the next byte is on a
    4-byte boundary.
    """
    name_bytes = name.encode() + b"\x00"
    namesize = len(name_bytes)
    # Use a stable per-path "inode" so repeated builds are deterministic.
    inode = abs(hash(name)) & 0xFFFFFFFF
    header = b"070701"
    header += b"%08x" % inode  # ino
    header += b"%08x" % mode  # mode
    header += b"%08x" % 0  # uid
    header += b"%08x" % 0  # gid
    header += b"%08x" % nlink  # nlink
    header += b"%08x" % mtime  # mtime
    header += b"%08x" % body_len  # filesize
    header += b"%08x" % 0  # devmajor (hosting fs, unused)
    header += b"%08x" % 0  # devminor (hosting fs, unused)
    header += b"%08x" % dev_major  # rdevmajor (char/block specials)
    header += b"%08x" % dev_minor  # rdevminor
    header += b"%08x" % namesize  # namesize
    header += b"%08x" % 0  # check (unused for newc)
    header += name_bytes
    return _pad4(header)


def _pad4(data: bytes) -> bytes:
    """Pad ``data`` with NULs so its length is a multiple of 4."""
    pad = (-len(data)) & 3
    return data + (b"\x00" * pad) if pad else data


@dataclass
class CpioBuilder:
    """Accumulates entries and serializes them into a newc cpio.

    Typical usage is via :func:`build_cpio`; instantiate directly only
    when you need fine-grained control over the entry order or want to
    add custom in-memory files.
    """

    chunks: list[bytes] = field(default_factory=list)
    _emitted_dirs: set[str] = field(default_factory=set)

    def add_dir(self, path: str, mode: int = 0o755) -> None:
        if path in self._emitted_dirs:
            return
        self.chunks.append(_newc_header(path, 0, S_IFDIR | mode))
        self._emitted_dirs.add(path)

    def add_file(self, path: str, body: bytes, mode: int = 0o644) -> None:
        self.chunks.append(_newc_header(path, len(body), S_IFREG | mode))
        self.chunks.append(_pad4(body))

    def add_symlink(self, path: str, target: str, mode: int = 0o777) -> None:
        body = target.encode()
        self.chunks.append(_newc_header(path, len(body), S_IFLNK | mode))
        self.chunks.append(_pad4(body))

    def add_dev_node(self, node: DevNode) -> None:
        if node.kind == "c":
            kind_bits = S_IFCHR
        elif node.kind == "b":
            kind_bits = S_IFBLK
        else:
            raise ValueError(f"invalid dev-node kind {node.kind!r}; expected 'c' or 'b'")
        self.chunks.append(
            _newc_header(
                node.path,
                0,
                kind_bits | node.mode,
                dev_major=node.major,
                dev_minor=node.minor,
            )
        )

    def add_tree(self, rootfs: str | os.PathLike[str]) -> None:
        """Walk a host directory and emit cpio entries for every file.

        Directories implied by file paths are emitted before their
        contents. Symlinks are preserved as-is (target string is kept;
        absolute vs. relative is the caller's responsibility).
        Regular files are read into memory and emitted with their host
        permission bits (mode & 0o777).

        Skips any path starting with ``dev/`` — device nodes must be
        added explicitly via :meth:`add_dev_node` since the host
        filesystem can't represent them without root.
        """
        rootfs = os.fspath(rootfs)
        for dirpath, dirnames, filenames in os.walk(rootfs, followlinks=False):
            rel_dir = os.path.relpath(dirpath, rootfs)
            arc_dir = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
            if arc_dir and not arc_dir.startswith("dev"):
                self.add_dir(arc_dir)
            for fn in sorted(dirnames + filenames):
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, rootfs).replace(os.sep, "/")
                if rel.startswith("dev/") or rel == "dev":
                    # Device nodes are added explicitly by the caller.
                    continue
                st = os.lstat(full)
                if stat.S_ISLNK(st.st_mode):
                    self.add_symlink(rel, os.readlink(full))
                elif stat.S_ISREG(st.st_mode):
                    with open(full, "rb") as f:
                        body = f.read()
                    self.add_file(rel, body, mode=st.st_mode & 0o777)
                # Directories handled by the outer loop; other special
                # files are skipped silently — callers should pass them
                # via add_dev_node.

    def _trailer(self) -> bytes:
        # cpio newc terminator: an entry named "TRAILER!!!" with nlink=1
        # and all other fields zero. mode=0 here matches GNU cpio output.
        return _newc_header("TRAILER!!!", 0, 0, nlink=1)

    def serialize(self) -> bytes:
        return b"".join(self.chunks) + self._trailer()


def build_cpio(
    rootfs: str | os.PathLike[str],
    out_path: str | os.PathLike[str],
    dev_nodes: list[DevNode] | None = None,
) -> int:
    """Build a newc cpio at ``out_path`` from ``rootfs`` + ``dev_nodes``.

    Args:
        rootfs: host directory containing the rootfs tree (without
            ``/dev`` populated — device nodes go in via ``dev_nodes``).
        out_path: destination cpio file.
        dev_nodes: list of device nodes to emit before walking the tree.
            ``None`` means no device nodes; callers building an
            initramfs almost certainly want at least
            :data:`~adi_lg_plugins.recovery.initramfs.DEFAULT_DEV_NODES`.

    Returns:
        Number of bytes written.
    """
    builder = CpioBuilder()
    if dev_nodes:
        builder.add_dir("dev")
        for node in dev_nodes:
            builder.add_dev_node(node)
    builder.add_tree(rootfs)
    payload = builder.serialize()
    out_path = os.fspath(out_path)
    with open(out_path, "wb") as f:
        f.write(payload)
    return len(payload)


def _cli(argv: list[str] | None = None) -> int:
    """Module-as-script entry point for ad-hoc cpio builds.

    Run via ``python -m adi_lg_plugins.recovery.cpio <rootfs> <out.cpio>``.
    Always includes the default recovery device-node set.
    """
    import argparse

    from adi_lg_plugins.recovery.initramfs import DEFAULT_DEV_NODES

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("rootfs", help="rootfs directory to archive")
    parser.add_argument("out", help="output cpio file path")
    parser.add_argument(
        "--no-default-devs",
        action="store_true",
        help="Skip the default /dev/{console,null,tty,zero,mmcblk0} entries.",
    )
    args = parser.parse_args(argv)
    devs = None if args.no_default_devs else DEFAULT_DEV_NODES
    n = build_cpio(args.rootfs, args.out, dev_nodes=devs)
    print(f"wrote {args.out} ({n} bytes)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_cli())
