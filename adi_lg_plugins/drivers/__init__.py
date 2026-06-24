"""ADI labgrid drivers.

Importing this subpackage imports every driver module so that the
``@target_factory.reg_driver`` decorators run and the drivers register
with labgrid. This is what makes ``import adi_lg_plugins`` (or a labgrid
``imports: [adi_lg_plugins]`` config key) enough to use these drivers by
name — replacing the entry-point auto-discovery that only existed in the
old labgrid fork.

Each import is guarded: a driver whose optional/system dependency is
missing on this host (e.g. ``pysnmp``, ``pyvesync``, ``usbsdmux``) logs a
warning and is skipped rather than breaking the whole import.
"""

from __future__ import annotations

import importlib
import logging

logger = logging.getLogger(__name__)

_MODULES = (
    "cloudsmithdldriver",
    "cyberpowerdriver",
    "homeassistantdriver",
    "kuiperdldriver",
    "massstoragedriver",
    "shelldriver",
    "softwareinstaller",
    "tftpserverdriver",
    "tickfpgamanagerdriver",
    "tickoverlaydriver",
    "vesyncdriver",
    "xilinxjtagdriver",
)

for _m in _MODULES:
    try:
        importlib.import_module(f"{__name__}.{_m}")
    except Exception as exc:  # noqa: BLE001 - optional deps may be absent
        logger.warning("adi_lg_plugins: driver %r not registered (%s)", _m, exc)
