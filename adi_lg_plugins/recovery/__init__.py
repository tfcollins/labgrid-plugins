"""Reusable building blocks for SD-recovery initramfs creation.

The ``BootZynq7000JTAGRecovery`` strategy consumes a recovery initramfs
hosted on a TFTP server. This subpackage provides the host-side tooling
to *build* that initramfs from a cross-compiled static busybox:

- :class:`~adi_lg_plugins.recovery.cpio.CpioBuilder` and
  :func:`~adi_lg_plugins.recovery.cpio.build_cpio` — newc-format cpio
  writer that includes device nodes without needing root.
- :func:`~adi_lg_plugins.recovery.initramfs.build_recovery_initramfs` —
  one-shot orchestrator: stages the rootfs tree, installs the bundled
  ``/init`` + udhcpc hook + applet symlinks, then wraps the cpio with
  ``mkimage`` for U-Boot to ``bootm``.

The same logic is exposed on the CLI:

.. code-block:: console

    adi-lg build-recovery-initramfs \\
        --busybox /path/to/static/busybox \\
        --out /var/lib/tftpboot/uInitrd.recovery
"""

from adi_lg_plugins.recovery.cpio import CpioBuilder, build_cpio
from adi_lg_plugins.recovery.initramfs import (
    DEFAULT_APPLETS,
    DEFAULT_DEV_NODES,
    build_recovery_initramfs,
    stage_recovery_rootfs,
)

__all__ = [
    "CpioBuilder",
    "DEFAULT_APPLETS",
    "DEFAULT_DEV_NODES",
    "build_cpio",
    "build_recovery_initramfs",
    "stage_recovery_rootfs",
]
