"""ADI labgrid boot/provisioning strategies.

Importing this subpackage imports every strategy module so the
``@target_factory.reg_driver`` decorators run and the strategies register
with labgrid (see :mod:`adi_lg_plugins.drivers` for the rationale).
"""

from __future__ import annotations

import importlib
import logging

logger = logging.getLogger(__name__)

_MODULES = (
    "bootfabric",
    "bootfpgasoc",
    "bootfpgasocssh",
    "bootfpgasoctftp",
    "bootrpi",
    "bootselmap",
    "bootvpk180",
    "bootzynq7000recovery",
    "reflashvpk180sd",
    "software_provisioning",
)

for _m in _MODULES:
    try:
        importlib.import_module(f"{__name__}.{_m}")
    except Exception as exc:  # noqa: BLE001 - optional deps may be absent
        logger.warning("adi_lg_plugins: strategy %r not registered (%s)", _m, exc)
