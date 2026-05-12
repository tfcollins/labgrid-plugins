"""Thin wrapper around :mod:`adi_lg_plugins.recovery.cpio`.

Kept for backwards compatibility with the original example README and as
a copy-paste-able single file. New code should call the module API directly:

.. code-block:: python

    from adi_lg_plugins.recovery import build_cpio, DEFAULT_DEV_NODES
    build_cpio("rootfs", "initramfs.cpio", dev_nodes=DEFAULT_DEV_NODES)

Run:
    python3 examples/zynq7000_recovery/build_cpio.py <rootfs> <out.cpio>
"""

import sys

from adi_lg_plugins.recovery import DEFAULT_DEV_NODES, build_cpio


def main(rootfs: str, out_path: str) -> None:
    n = build_cpio(rootfs, out_path, dev_nodes=DEFAULT_DEV_NODES)
    print(f"wrote {out_path} ({n} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: build_cpio.py <rootfs_dir> <out.cpio>", file=sys.stderr)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2])
