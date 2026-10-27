#!/usr/bin/env python3
"""Validate a labgrid exporter YAML config (or hw-nodes manifest) against its schema.

Usage:
    python validate.py exporter.yaml
    python validate.py --schema schemas/exporter_schema.json exporter.yaml
    python validate.py --hw-nodes .github/hw-nodes.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).parent
DEFAULT_SCHEMA = SCRIPT_DIR / "schemas" / "exporter_schema.json"
HW_NODES_SCHEMA = SCRIPT_DIR / "schemas" / "hw-nodes.schema.json"

# Resource classes the stock templates and lab configs export. Power classes
# mirror adi_lg_plugins/hw_ci/power.py (kept in sync by tests/test_power_types.py).
KNOWN_CLASSES = {
    "NetworkService",
    "RawSerialPort",
    "XilinxDeviceJTAG",
    "XilinxVivadoTool",
    "USBSDMuxDevice",
    "USBMassStorage",
    "MassStorageDevice",
    "TFTPServerResource",
    "KuiperRelease",
    "TickArtifacts",
    # power control
    "APCOutlet",
    "CyberPowerOutlet",
    "DeditecRelais8",
    "Eth008DigitalOutput",
    "HIDRelay",
    "HomeAssistantOutlet",
    "HttpDigitalOutput",
    "KasaOutlet",
    "LAAPowerPort",
    "LXAIOBusPIO",
    "MatchedSysfsGPIO",
    "ModbusTCPCoil",
    "NetworkPowerPort",
    "OneWirePIO",
    "PDUDaemonPort",
    "SiSPMPowerPort",
    "SigrokUSBSerialDevice",
    "SysfsGPIO",
    "TasmotaPowerPort",
    "USBPowerPort",
    "VesyncOutlet",
    "WaveshareModbusTCPCoil",
    "YKUSHPowerPort",
}


def _detect_format(data: dict) -> str:
    """Detect whether the YAML uses exporter-wrapped or flat group format.

    Exporter-wrapped: {exporter_name: {group: {resource: params}}}
    Flat (labgrid exporter format): {group: {resource: params}}
    """
    for value in data.values():
        if not isinstance(value, dict):
            return "flat"
        for inner in value.values():
            if isinstance(inner, dict) and "cls" in inner:
                return "flat"
            return "wrapped"
    return "flat"


def _validate_group(prefix: str, group_name: str, resources: dict, issues: list[str]):
    """Validate a single resource group."""
    for resource_name, params in resources.items():
        if resource_name == "location":
            continue
        if params is None:
            issues.append(f"{prefix}/{group_name}/{resource_name}: resource has no parameters")
            continue
        if not isinstance(params, dict):
            issues.append(f"{prefix}/{group_name}/{resource_name}: expected a mapping")
            continue

        cls = params.get("cls", resource_name)
        if cls not in KNOWN_CLASSES:
            issues.append(
                f"{prefix}/{group_name}/{resource_name}: "
                f"unknown resource class '{cls}' "
                f"(known: {', '.join(sorted(KNOWN_CLASSES))})"
            )


def _check_labgrid_template(text: str) -> list[str]:
    """Parse the file the way labgrid-exporter does before it reads the YAML.

    labgrid renders exporter configs as a Jinja template with ``#`` as the
    line-statement prefix and ``##`` as the line-comment prefix, so a plain
    YAML ``# comment`` line is a template statement there. jinja2 ships with
    labgrid; without it this check is skipped.
    """
    try:
        import jinja2
    except ImportError:
        return []
    env = jinja2.Environment(line_statement_prefix="#", line_comment_prefix="##")
    try:
        env.parse(text)
    except jinja2.TemplateSyntaxError as e:
        return [
            f"line {e.lineno}: labgrid loads exporter configs as a Jinja template, where a "
            f"line starting with '#' is a template statement ({e.message}); "
            "use '##' for comments"
        ]
    return []


def validate_config(config_path: str, schema_path: str | None = None) -> list[str]:
    """Validate an exporter config YAML and return a list of issues."""
    with open(config_path) as f:
        text = f.read()

    issues: list[str] = _check_labgrid_template(text)

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return issues + [f"YAML parse error: {e}"]

    if not isinstance(data, dict):
        return issues + ["Config must be a YAML mapping at the top level"]

    fmt = _detect_format(data)

    if fmt == "wrapped":
        # {exporter_name: {group: {resource: params}}}
        for exporter_name, groups in data.items():
            if not isinstance(groups, dict):
                issues.append(f"Exporter '{exporter_name}': expected a mapping of groups")
                continue
            for group_name, resources in groups.items():
                if not isinstance(resources, dict):
                    issues.append(f"{exporter_name}/{group_name}: expected a mapping of resources")
                    continue
                _validate_group(exporter_name, group_name, resources, issues)
    else:
        # Flat format: {group: {resource: params}}
        for group_name, resources in data.items():
            if not isinstance(resources, dict):
                issues.append(f"{group_name}: expected a mapping of resources")
                continue
            _validate_group("(root)", group_name, resources, issues)

    # JSON Schema validation (optional, requires jsonschema)
    if schema_path:
        try:
            import jsonschema

            with open(schema_path) as f:
                schema = json.load(f)
            jsonschema.validate(data, schema)
        except ImportError:
            issues.append(
                "jsonschema not installed; skipping schema validation. "
                "Install with: pip install jsonschema"
            )
        except jsonschema.ValidationError as e:
            issues.append(f"Schema validation error: {e.message}")

    return issues


def validate_hw_nodes(manifest_path: str) -> list[str]:
    """Validate a hw-nodes.json manifest against its JSON schema."""
    issues: list[str] = []

    try:
        with open(manifest_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [f"JSON parse error: {e}"]
    except FileNotFoundError:
        return [f"Manifest not found: {manifest_path}"]

    try:
        import jsonschema
    except ImportError:
        return ["jsonschema not installed; install with: pip install jsonschema"]

    with open(HW_NODES_SCHEMA) as f:
        schema = json.load(f)

    validator = jsonschema.Draft202012Validator(schema)
    for err in validator.iter_errors(data):
        loc = "/".join(str(p) for p in err.absolute_path) or "(root)"
        issues.append(f"{loc}: {err.message}")

    # Cross-entry sanity checks not expressible in the schema.
    if isinstance(data, list):
        places = [entry.get("place") for entry in data if isinstance(entry, dict)]
        seen: set[str] = set()
        for p in places:
            if p in seen:
                issues.append(f"duplicate place '{p}'")
            elif p is not None:
                seen.add(p)

    return issues


def main():
    parser = argparse.ArgumentParser(description="Validate a labgrid exporter configuration")
    parser.add_argument("config", help="Path to the YAML config or hw-nodes.json manifest")
    parser.add_argument(
        "--schema",
        default=None,
        help=f"Path to JSON schema (default: {DEFAULT_SCHEMA})",
    )
    parser.add_argument(
        "--hw-nodes",
        action="store_true",
        help="Treat config as a hw-nodes.json manifest and validate against hw-nodes.schema.json",
    )
    args = parser.parse_args()

    if args.hw_nodes:
        issues = validate_hw_nodes(args.config)
    else:
        schema = args.schema or str(DEFAULT_SCHEMA)
        issues = validate_config(args.config, schema)

    if issues:
        print(f"Validation FAILED for {args.config}:")
        for issue in issues:
            print(f"  - {issue}")
        sys.exit(1)
    else:
        print(f"Validation PASSED for {args.config}")


if __name__ == "__main__":
    main()
