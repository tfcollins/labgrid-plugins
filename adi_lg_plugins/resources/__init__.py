"""ADI labgrid resources.

Importing this subpackage imports every resource module so the
``@target_factory.reg_resource`` decorators run and the resources register
with labgrid (see :mod:`adi_lg_plugins.drivers` for the rationale).
"""

from __future__ import annotations

import importlib
import logging

logger = logging.getLogger(__name__)

_MODULES = (
    "cloudsmithrelease",
    "cyberpowerpdu",
    "homeassistant",
    "kuiperrelease",
    "massstorage",
    "tftpserver",
    "vesync",
    "xilinxdevice",
    "xilinxtool",
)

for _m in _MODULES:
    try:
        importlib.import_module(f"{__name__}.{_m}")
    except Exception as exc:  # noqa: BLE001 - optional deps may be absent
        logger.warning("adi_lg_plugins: resource %r not registered (%s)", _m, exc)
