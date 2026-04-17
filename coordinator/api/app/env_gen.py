"""Pure env-yaml generator: maps place resources to a labgrid client env yaml."""

from __future__ import annotations

from collections.abc import Callable
from io import StringIO
from typing import Any

import yaml

from .models import PlaceModel, ResourceModel

VALID_TIERS = ("shell", "drivers", "boot")

DriverConfigFactory = Callable[[ResourceModel], dict[str, Any]]

# Resource class (coordinator view) -> list of (driver_name, config_factory).
# config_factory(resource) returns the driver's yaml dict, or {} for no config.
RESOURCE_DRIVER_MAP: dict[str, list[tuple[str, DriverConfigFactory]]] = {
    "NetworkSerialPort": [("SerialDriver", lambda _r: {})],
    "VesyncOutlet": [("VesyncPowerDriver", lambda _r: {})],
    "HomeAssistantOutlet": [("HomeAssistantPowerDriver", lambda _r: {})],
    "NetworkUSBSDMuxDevice": [("USBSDMuxDriver", lambda _r: {})],
    "NetworkUSBMassStorage": [
        (
            "MassStorageDriver",
            lambda r: {"partition": r.params["path"]} if r.params.get("path") else {},
        ),
    ],
    "KuiperRelease": [("KuiperDLDriver", lambda _r: {})],
    "XilinxDeviceJTAG": [("XilinxJTAGDriver", lambda _r: {})],
    "XilinxVivadoTool": [],  # consumed by XilinxJTAGDriver, no standalone driver
    "TFTPServerResource": [("TFTPServerDriver", lambda _r: {})],
}

SHELL_DEFAULTS: dict[str, dict[str, str]] = {
    "BootFPGASoC": {
        "prompt": "root@.*",
        "login_prompt": "analog login: ",
        "username": "root",
        "password": "analog",
    },
    "BootFabric": {
        "prompt": "#.*",
        "login_prompt": "buildroot login: ",
        "username": "root",
        "password": "analog",
    },
    "_default": {
        "prompt": "root@.*",
        "login_prompt": "login: ",
        "username": "root",
        "password": "analog",
    },
}

STRATEGY_CONFIGS: dict[str, dict[str, Any]] = {
    "BootFPGASoC": {
        "reached_linux_marker": "analog",
        "wait_for_linux_prompt_timeout": 180,
    },
    "BootFabric": {
        "reached_boot_marker": "login:",
        "trigger_dhcp_reset": True,
        "wait_for_boot_timeout": 700,
        "power_off_delay": 30,
    },
}


def infer_strategy(resource_classes: set[str]) -> str | None:
    """Return a labgrid strategy class name inferred from the set of resource
    classes a place has live, or None if the heuristic doesn't match any
    known pattern. Supported: "BootFPGASoC", "BootFabric"."""
    has_kuiper = "KuiperRelease" in resource_classes
    has_mass = "NetworkUSBMassStorage" in resource_classes
    has_sdmux = "NetworkUSBSDMuxDevice" in resource_classes
    has_jtag = "XilinxDeviceJTAG" in resource_classes
    has_vivado = "XilinxVivadoTool" in resource_classes

    if has_kuiper and has_mass and has_sdmux:
        return "BootFPGASoC"
    if has_jtag and has_vivado:
        return "BootFabric"
    return None


def generate_env_yaml(
    place: PlaceModel,
    resources: list[ResourceModel],
    tier: str,
) -> str:
    """Generate a labgrid client env yaml string for `place`.

    Args:
        place: the PlaceModel (name is used for the RemotePlace binding).
        resources: the live resources currently matched by the place.
        tier: one of VALID_TIERS ("shell" | "drivers" | "boot").

    Returns the yaml as a string with a commented header. Raises ValueError
    for an unknown tier.
    """
    if tier not in VALID_TIERS:
        raise ValueError(f"Invalid tier '{tier}'; expected one of {VALID_TIERS}")

    resource_classes = {r.cls for r in resources}
    strategy = infer_strategy(resource_classes) if tier == "boot" else None
    shell_key = strategy or "_default"
    shell_cfg = dict(SHELL_DEFAULTS.get(shell_key, SHELL_DEFAULTS["_default"]))

    drivers: dict[str, Any] = {}

    if tier == "shell":
        drivers["SerialDriver"] = {}
        drivers["ADIShellDriver"] = shell_cfg
    else:
        drivers["SerialDriver"] = {}
        drivers["ADIShellDriver"] = shell_cfg
        for r in resources:
            for driver_name, config_fn in RESOURCE_DRIVER_MAP.get(r.cls, []):
                if driver_name not in drivers:
                    drivers[driver_name] = config_fn(r) or {}

        if strategy:
            drivers[strategy] = dict(STRATEGY_CONFIGS[strategy])

    doc = {
        "targets": {
            "main": {
                "resources": {
                    "RemotePlace": {"name": place.name},
                },
                "drivers": drivers,
            },
        },
    }

    buf = StringIO()
    buf.write(f"## Generated labgrid env yaml for place '{place.name}'\n")
    buf.write(f"## Tier: {tier}\n")
    if tier == "boot" and not strategy:
        buf.write(
            "## No boot strategy could be inferred from the place's resources.\n"
            "## Add a strategy block manually if needed.\n"
        )
    buf.write("\n")
    yaml.dump(doc, buf, default_flow_style=False, sort_keys=False)
    return buf.getvalue()
