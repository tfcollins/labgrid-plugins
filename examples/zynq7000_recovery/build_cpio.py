"""Build a newc-format cpio archive from a directory tree + an explicit list
of device nodes. Without /dev/console in the archive, the kernel's init
process starts with closed file descriptors and any output vanishes.

The cpio newc format is documented in linux/Documentation/early-userspace/buffer-format.rst.
"""

import os
import stat
import struct
import sys

S_IFREG = 0o100000
S_IFDIR = 0o040000
S_IFLNK = 0o120000
S_IFCHR = 0o020000
S_IFBLK = 0o060000


def cpio_header(name, body_len, mode, nlink=1, mtime=0, dev_major=0, dev_minor=0):
    # newc magic + 13 8-byte hex fields + filename
    name_bytes = name.encode() + b"\x00"
    namesize = len(name_bytes)
    inode = abs(hash(name)) & 0xFFFFFFFF
    h = b"070701"
    h += b"%08x" % inode  # ino
    h += b"%08x" % mode  # mode
    h += b"%08x" % 0  # uid
    h += b"%08x" % 0  # gid
    h += b"%08x" % nlink  # nlink
    h += b"%08x" % mtime  # mtime
    h += b"%08x" % body_len  # filesize
    h += b"%08x" % 0  # devmajor (the device hosting the file)
    h += b"%08x" % 0  # devminor
    h += b"%08x" % dev_major  # rdevmajor (only for char/block specials)
    h += b"%08x" % dev_minor  # rdevminor
    h += b"%08x" % namesize  # namesize
    h += b"%08x" % 0  # check
    h += name_bytes
    # Pad header+name to 4-byte boundary
    while len(h) % 4:
        h += b"\x00"
    return h


def pad4(data):
    while len(data) % 4:
        data += b"\x00"
    return data


def walk_and_emit(root, out):
    """Emit cpio entries for every file under root (skipping root itself)."""
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir != ".":
            arc_name = rel_dir.replace(os.sep, "/")
            mode = S_IFDIR | 0o755
            out.write(cpio_header(arc_name, 0, mode))
        for fn in sorted(dirnames + filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if fn in dirnames:
                continue  # handled by next iteration
            st = os.lstat(full)
            if stat.S_ISLNK(st.st_mode):
                target = os.readlink(full).encode()
                mode = S_IFLNK | (st.st_mode & 0o777 or 0o777)
                out.write(cpio_header(rel, len(target), mode))
                out.write(pad4(target))
            elif stat.S_ISREG(st.st_mode):
                with open(full, "rb") as f:
                    body = f.read()
                mode = S_IFREG | (st.st_mode & 0o777)
                out.write(cpio_header(rel, len(body), mode))
                out.write(pad4(body))


def emit_dev_node(out, path, ch_or_blk, major, minor, mode=0o600):
    """Emit a char or block device node entry."""
    if ch_or_blk == "c":
        m = S_IFCHR | mode
    elif ch_or_blk == "b":
        m = S_IFBLK | mode
    else:
        raise ValueError(ch_or_blk)
    out.write(cpio_header(path, 0, m, dev_major=major, dev_minor=minor))


def trailer(out):
    out.write(cpio_header("TRAILER!!!", 0, 0, nlink=1))


def main(rootfs, out_path):
    with open(out_path, "wb") as out:
        # Dev nodes first so they're guaranteed even if walk skips /dev
        out.write(cpio_header("dev", 0, S_IFDIR | 0o755))
        emit_dev_node(out, "dev/console", "c", 5, 1, 0o600)
        emit_dev_node(out, "dev/null", "c", 1, 3, 0o666)
        emit_dev_node(out, "dev/tty", "c", 5, 0, 0o666)
        emit_dev_node(out, "dev/zero", "c", 1, 5, 0o666)
        emit_dev_node(out, "dev/mmcblk0", "b", 179, 0, 0o660)
        walk_and_emit(rootfs, out)
        trailer(out)
    print(f"wrote {out_path} ({os.path.getsize(out_path)} bytes)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
