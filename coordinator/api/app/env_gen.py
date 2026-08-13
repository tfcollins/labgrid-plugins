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
    "NetworkService": [("SSHDriver", lambda _r: {})],
    "APCOutlet": [("APCDriver", lambda _r: {})],
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
    "BootFPGASoCSSH": {
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
    "BootZynq7000JTAGRecovery": {
        "prompt": "root@.*",
        "login_prompt": "analog login: ",
        "username": "root",
        "password": "analog",
    },
    "BootNoOSJTAG": {
        # no-os bare-metal firmware: no login prompt, no shell — the console
        # is only read for the validation banner. login is bypassed.
        "prompt": "",
        "login_prompt": "",
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
    "BootFPGASoCSSH": {
        "reached_linux_marker": "analog",
        "wait_for_linux_prompt_timeout": 180,
    },
    "BootFabric": {
        "reached_boot_marker": "login:",
        "trigger_dhcp_reset": True,
        "wait_for_boot_timeout": 700,
        "power_off_delay": 30,
    },
    # NOTE: BootZynq7000JTAGRecovery needs board-specific path params
    # (ps7_init_tcl, uboot_elf, bitstream_path, etc.) that env_gen can't
    # infer. Operator must extend the generated env yaml or stage the
    # paths at the strategy's defaults. Defaults here cover the
    # conventional bq/zc706 layout; override per-place via additional
    # tags or in the consumer's pytest fixture if they differ.
    "BootZynq7000JTAGRecovery": {
        "ps7_init_tcl": "/srv/recovery/zc706/ps7_init.tcl",
        "uboot_elf": "/srv/recovery/zc706/u-boot.elf",
        "bitstream_path": "/srv/recovery/zc706/system_top.bit",
        "a9_target_name": "*Cortex-A9 MPCore #0",
        "recovery_kernel": "uImage",
        "recovery_dtb": "devicetree.dtb",
        "recovery_initramfs": "uInitrd.recovery",
        "recovery_login_marker": "recovery login:",
        "uboot_prompt": "Zynq>.*",
        "kernel_addr": "0x3000000",
        "dtb_addr": "0x2A00000",
        "initramfs_addr": "0x10000000",
        "jtag_bootstrap_retries": 1,
        "wait_for_uboot_prompt_timeout": 90,
        "wait_for_recovery_linux_timeout": 240,
        "wait_for_sd_flash_timeout": 1800,
    },
    # no-os firmware flash via JTAG. The per-build path params (firmware_elf,
    # bitstream_path, ps7_init_tcl) come from the request (the built artifact),
    # not env_gen; only the static validation defaults live here.
    "BootNoOSJTAG": {
        "a9_target_name": "*Cortex-A9 MPCore #0",
        "boot_marker": "Successfully initialized",
        "boot_timeout": 60,
    },
}

# Strategy class names recognized as explicit boot-strategy tag overrides.
_KNOWN_STRATEGIES = frozenset(
    {
        "BootFPGASoC",
        "BootFabric",
        "BootFPGASoCSSH",
        "BootZynq7000JTAGRecovery",
        "BootNoOSJTAG",
    }
)


def infer_strategy(resource_classes: set[str]) -> str | None:
    """Return a labgrid strategy class name inferred from the set of resource
    classes a place has live, or None if the heuristic doesn't match any
    known pattern. Supported: "BootFPGASoC", "BootFPGASoCSSH", "BootFabric",
    "BootZynq7000JTAGRecovery"."""
    has_kuiper = "KuiperRelease" in resource_classes
    has_mass = "NetworkUSBMassStorage" in resource_classes
    has_sdmux = "NetworkUSBSDMuxDevice" in resource_classes
    has_jtag = "XilinxDeviceJTAG" in resource_classes
    has_vivado = "XilinxVivadoTool" in resource_classes
    has_net = "NetworkService" in resource_classes
    has_power = any(
        resource_class in resource_classes
        for resource_class in ("APCOutlet", "HomeAssistantOutlet", "VesyncOutlet")
    )
    has_tftp = "TFTPServerResource" in resource_classes

    # Zynq-7000 boards staged for JTAG-bootstrap + SD-boot have all of
    # JTAG, Vivado, TFTP, and KuiperRelease — match before plain JTAG
    # below so we don't mistakenly classify them as BootFabric.
    if has_kuiper and has_jtag and has_vivado and has_tftp:
        return "BootZynq7000JTAGRecovery"
    if has_kuiper and has_mass and has_sdmux:
        return "BootFPGASoC"
    # SSH-based variant: no SD-mux/mass-storage, but Kuiper + a power outlet
    # let the strategy power-cycle the board and push boot files over SSH.
    if has_kuiper and has_net and has_power and not has_mass and not has_sdmux:
        return "BootFPGASoCSSH"
    if has_jtag and has_vivado:
        return "BootFabric"
    return None


def resolve_strategy(place_tags: dict[str, str], resource_classes: set[str]) -> str | None:
    """Pick a strategy: explicit place tag wins, else fall back to inference.

    The `boot-strategy` tag on a place lets operators pin a specific
    strategy without depending on the resource-shape heuristic. Unknown
    tag values are ignored (defensive — never emit a typoed strategy
    class into the env yaml)."""
    tagged = place_tags.get("boot-strategy")
    if tagged and tagged in _KNOWN_STRATEGIES:
        return tagged
    return infer_strategy(resource_classes)


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
    strategy = resolve_strategy(place.tags, resource_classes) if tier == "boot" else None
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
            drivers[strategy] = dict(STRATEGY_CONFIGS.get(strategy, {}))

    # Expose the place's identity as labgrid `features` so consumers that
    # gate tests with `@pytest.mark.lg_feature(...)` (e.g. pyadi-dt's
    # per-board HW tests) are selected rather than skipped. Derived from the
    # daughter-board (chip) + carrier (FPGA board) tags, e.g. [ad9081, zcu102].
    features = [v for v in (place.tags.get("daughter-board"), place.tags.get("carrier")) if v]

    target: dict[str, Any] = {
        "resources": {
            "RemotePlace": {"name": place.name},
        },
        "drivers": drivers,
    }
    if features:
        target["features"] = features

    # `imports` registers the ADI plugin drivers/resources/strategies with
    # labgrid by name (upstream labgrid has no entry-point auto-discovery).
    doc = {"imports": ["adi_lg_plugins"], "targets": {"main": target}}

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
