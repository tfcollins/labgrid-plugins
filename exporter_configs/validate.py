#!/usr/bin/env python3
"""Validate a labgrid exporter YAML config against the standard schema.

Usage:
    python validate.py exporter.yaml
    python validate.py --schema schemas/exporter_schema.json exporter.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).parent
DEFAULT_SCHEMA = SCRIPT_DIR / "schemas" / "exporter_schema.json"

# Known resource classes from the adi-labgrid-plugins project
KNOWN_CLASSES = {
    "NetworkService",
    "RawSerialPort",
    "XilinxDeviceJTAG",
    "XilinxVivadoTool",
    "USBSDMuxDevice",
    "MassStorageDevice",
    "CyberPowerOutlet",
    "VesyncOutlet",
    "HomeAssistantOutlet",
    "TFTPServerResource",
    "KuiperRelease",
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


def validate_config(config_path: str, schema_path: str | None = None) -> list[str]:
    """Validate an exporter config YAML and return a list of issues."""
    issues: list[str] = []

    with open(config_path) as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            return [f"YAML parse error: {e}"]

    if not isinstance(data, dict):
        return ["Config must be a YAML mapping at the top level"]

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


def main():
    parser = argparse.ArgumentParser(description="Validate a labgrid exporter configuration")
    parser.add_argument("config", help="Path to the exporter YAML config")
    parser.add_argument(
        "--schema",
        default=None,
        help=f"Path to JSON schema (default: {DEFAULT_SCHEMA})",
    )
    args = parser.parse_args()

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
