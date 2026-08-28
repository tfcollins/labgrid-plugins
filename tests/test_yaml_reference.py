"""Executable checks for the copy/paste YAML reference."""

from __future__ import annotations

import importlib
from pathlib import Path

import attr
import labgrid.strategy
import tomli
import yaml

ROOT = Path(__file__).parents[1]
REFERENCE = ROOT / "docs" / "source" / "yaml-reference"
GROUP_PAGES = {
    "labgrid.resources": REFERENCE / "resources.rst",
    "labgrid.drivers": REFERENCE / "drivers.rst",
    "labgrid.strategies": REFERENCE / "strategies.rst",
}
IGNORED_ATTRS = {"target", "name", "bindings", "status"}


class UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader variant which rejects duplicate mapping keys."""


def _construct_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _entrypoint_classes():
    # BootZynqMPJTAG still supports the labgrid fork's never_retry decorator.
    # Supply an identity shim when inspecting the classes with upstream labgrid.
    if not hasattr(labgrid.strategy, "never_retry"):
        labgrid.strategy.__dict__["never_retry"] = lambda function: function

    project = tomli.loads((ROOT / "pyproject.toml").read_text())["project"]
    result = {}
    for group in GROUP_PAGES:
        classes = {}
        for spec in project["entry-points"][group].values():
            module_name, class_name = spec.split(":")
            cls = getattr(importlib.import_module(module_name), class_name)
            classes[class_name] = cls
        result[group] = classes
    return result


def _yaml_blocks(text):
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        if lines[index].strip() != ".. code-block:: yaml":
            index += 1
            continue
        index += 1
        while index < len(lines) and not lines[index].strip():
            index += 1
        block = []
        while index < len(lines):
            line = lines[index]
            if line.startswith("    ") or not line.strip():
                block.append(line[4:] if line.startswith("    ") else "")
                index += 1
                continue
            break
        yield "\n".join(block).rstrip()


def _component_configs(document, section):
    for target in (document.get("targets") or {}).values():
        for class_name, config in (target.get(section) or {}).items():
            yield class_name, config or {}


def test_reference_covers_every_registered_component_and_argument():
    classes = _entrypoint_classes()
    for group, page in GROUP_PAGES.items():
        text = page.read_text()
        class_items = list(classes[group].items())
        for index, (class_name, cls) in enumerate(class_items):
            heading = f"{class_name}\n{'~' * len(class_name)}"
            assert heading in text, f"{page.name} does not document {class_name}"
            start = text.index(heading)
            if index + 1 < len(class_items):
                next_name = class_items[index + 1][0]
                end = text.index(f"{next_name}\n{'~' * len(next_name)}", start)
            else:
                end = len(text)
            section = text[start:end]
            for field in attr.fields(cls):
                if field.init and field.name not in IGNORED_ATTRS:
                    assert f"``{field.name}``" in section, (
                        f"{page.name} does not document {class_name}.{field.name}"
                    )
            assert list(_yaml_blocks(section)), f"{page.name} has no example for {class_name}"


def test_reference_yaml_is_unique_parseable_and_uses_real_arguments():
    classes = _entrypoint_classes()
    resources = classes["labgrid.resources"]
    drivers = {
        **classes["labgrid.drivers"],
        **classes["labgrid.strategies"],
    }
    strategy_names = set(classes["labgrid.strategies"])

    for page in GROUP_PAGES.values():
        blocks = list(_yaml_blocks(page.read_text()))
        assert blocks, f"{page.name} has no YAML examples"
        for number, block in enumerate(blocks, 1):
            document = yaml.load(block, Loader=UniqueKeyLoader)
            assert isinstance(document, dict), f"{page.name} block {number} is not a mapping"
            assert document.get("imports") == ["adi_lg_plugins"], (
                f"{page.name} block {number} must import adi_lg_plugins"
            )
            assert "strategies" not in document, (
                f"{page.name} block {number}: strategies belong under target drivers"
            )
            for target in (document.get("targets") or {}).values():
                assert "strategies" not in target, (
                    f"{page.name} block {number}: strategies belong under target drivers"
                )

            for class_name, config in _component_configs(document, "resources"):
                if class_name not in resources:
                    continue
                valid = {field.name for field in attr.fields(resources[class_name]) if field.init}
                required = {
                    field.name
                    for field in attr.fields(resources[class_name])
                    if field.init
                    and field.default is attr.NOTHING
                    and field.name not in IGNORED_ATTRS
                }
                unknown = set(config) - valid - {"name", "cls"}
                missing = required - set(config)
                assert not unknown, (
                    f"{page.name} block {number}: unknown {class_name} arguments {sorted(unknown)}"
                )
                assert not missing, (
                    f"{page.name} block {number}: missing {class_name} arguments {sorted(missing)}"
                )

            for class_name, config in _component_configs(document, "drivers"):
                if class_name not in drivers:
                    continue
                valid = {field.name for field in attr.fields(drivers[class_name]) if field.init}
                required = {
                    field.name
                    for field in attr.fields(drivers[class_name])
                    if field.init
                    and field.default is attr.NOTHING
                    and field.name not in IGNORED_ATTRS
                }
                unknown = set(config) - valid - {"name", "cls", "bindings"}
                missing = required - set(config)
                assert not unknown, (
                    f"{page.name} block {number}: unknown {class_name} arguments {sorted(unknown)}"
                )
                assert not missing, (
                    f"{page.name} block {number}: missing {class_name} arguments {sorted(missing)}"
                )
                if class_name in strategy_names:
                    assert class_name not in (document.get("strategies") or {})
