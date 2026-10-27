"""Contract test: each stock exporter template serves its boot strategy.

For every ``exporter_configs/templates/*.yaml`` and each supported power type,
render the template the way ``adi-lg netbox add-hardware`` does, load it the
way ``labgrid-exporter`` does, then render the strategy's client env with
``adi-lg-hw-ci render-env`` and check every driver's resource bindings are
satisfied exactly once (labgrid refuses both a missing and an ambiguous
binding).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest
import yaml
from labgrid.factory import target_factory
from labgrid.remote.config import ResourceConfig
from labgrid.remote.exporter import SerialPortExport, USBGenericExport, exports

import adi_lg_plugins  # noqa: F401 - registers the ADI drivers/resources
from adi_lg_plugins.hw_ci.render_env import render_env
from adi_lg_plugins.hw_ci.schema import KNOWN_STRATEGIES, Place
from adi_lg_plugins.tools.netbox import provision

logging.getLogger("adi_lg_plugins").setLevel(logging.ERROR)

EXPORTER_CONFIGS_DIR = Path(__file__).resolve().parents[1] / "exporter_configs"
TEMPLATES = sorted((EXPORTER_CONFIGS_DIR / "templates").glob("*.yaml"))
POWER_DRIVERS = {"vesync": "VesyncPowerDriver", "homeassistant": "HomeAssistantPowerDriver"}
# Fields without a template default.
REQUIRED_FIELDS = {
    "target_ip": "10.0.0.5",
    "power_outlet": "Bench DUT",
    "bitstream_path": "/srv/fabric/system_top.bit",
    "kernel_path": "/srv/fabric/simpleImage.strip",
}
EXPORTER_ENV = {
    "VESYNC_USERNAME": "lab@example.com",
    "VESYNC_PASSWORD": "vesync-secret",
    "HOMEASSISTANT_URL": "http://ha.example.test:8123",
    "HOMEASSISTANT_TOKEN": "ha-secret",
}


def _client_cls(exported_cls: str) -> str:
    """Class name a client sees for a resource exported as ``exported_cls``."""
    export = exports.get(exported_cls)
    if export is not None and issubclass(export, SerialPortExport):
        return "NetworkSerialPort"
    if export is not None and issubclass(export, USBGenericExport):
        return f"Network{exported_cls}"
    return exported_cls


def _load_as_exporter(template: Path, power: str):
    path, groups = provision.render_and_validate(
        template, {**REQUIRED_FIELDS, "power": power}, EXPORTER_CONFIGS_DIR
    )
    env = {"env": EXPORTER_ENV, "isolated": False, "hostname": "h", "name": "n"}
    return path, groups, ResourceConfig(str(path), env).data


def _client_env(strategy: str, power: str) -> dict:
    place = Place(
        name="lab-place",
        carrier="zcu102",
        daughter_board="ad9081",
        boot_strategy=strategy,
        hdl_config="m8_l4",
        extra_tags={"power-driver": POWER_DRIVERS[power]},
    )
    return yaml.safe_load(render_env(place))["targets"]["main"]


def _resource_bindings(driver_cls):
    """Yield (binding name, candidate resource class names, optional)."""
    for name, spec in driver_cls.bindings.items():
        cands = spec if isinstance(spec, (set, frozenset, list, tuple)) else {spec}
        optional = None in cands
        names = {c if isinstance(c, str) else getattr(c, "__name__", "") for c in cands if c}
        resources = {n for n in names if n in target_factory.resources}
        if resources:
            yield name, resources, optional


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.stem)
def test_template_declares_a_known_boot_strategy(template):
    assert provision.template_strategy(template) in KNOWN_STRATEGIES


@pytest.mark.parametrize("power", sorted(POWER_DRIVERS))
@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.stem)
def test_template_exports_everything_its_strategy_binds(template, power):
    strategy = provision.template_strategy(template)
    _, groups, data = _load_as_exporter(template, power)
    assert len(groups) == 1
    exported = [_client_cls(params["cls"]) for params in data[groups[0]].values()]

    target = _client_env(strategy, power)
    declared = [cls for cls in target["resources"] if cls != "RemotePlace"]
    available = exported + declared

    problems = []
    for drv_name, drv_cfg in target["drivers"].items():
        explicit = ((drv_cfg or {}).get("bindings") or {}) if isinstance(drv_cfg, dict) else {}
        for binding, candidates, optional in _resource_bindings(target_factory.drivers[drv_name]):
            if binding in explicit:
                continue  # bound by name to a resource the client env declares
            matches = [cls for cls in available if cls in candidates]
            if len(matches) > 1 or (not matches and not optional):
                problems.append(f"{drv_name}.{binding}: {sorted(candidates)} matched {matches}")
    assert not problems, f"{template.name} ({power}) for {strategy}: {problems}"


@pytest.mark.parametrize("power", sorted(POWER_DRIVERS))
@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.stem)
def test_exported_adi_resources_accept_their_rendered_parameters(template, power):
    """The client builds ADI resources from these exact params; bad fields fail there."""
    from labgrid import Target

    _, groups, data = _load_as_exporter(template, power)
    for name, params in data[groups[0]].items():
        params = dict(params)
        cls = target_factory.resources[params.pop("cls")]
        if cls.__module__.startswith("adi_lg_plugins"):
            cls(Target(f"t-{template.stem}-{power}-{name}"), name=None, **params)


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.stem)
def test_power_credentials_come_from_the_exporter_environment(template):
    """Secrets are not written into the deployed file; labgrid reads them at start."""
    path, groups, data = _load_as_exporter(template, "vesync")
    rendered = path.read_text()
    assert "vesync-secret" not in rendered
    assert re.search(r"""\{\{ env\["VESYNC_PASSWORD"\] \}\}""", rendered)
    outlet = data[groups[0]]["VesyncOutlet"]
    assert (outlet["username"], outlet["password"], outlet["outlet_names"]) == (
        "lab@example.com",
        "vesync-secret",
        "Bench DUT",
    )

    _, groups, data = _load_as_exporter(template, "homeassistant")
    outlet = data[groups[0]]["HomeAssistantOutlet"]
    assert (outlet["url"], outlet["token"], outlet["entity_id"]) == (
        "http://ha.example.test:8123",
        "ha-secret",
        "Bench DUT",
    )
