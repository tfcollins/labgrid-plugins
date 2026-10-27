"""The power-type registry covers labgrid's power options and drives every consumer.

Consumers checked here: the generated template fragments, labgrid's own driver
binding, ``render-env``, the coordinator's ``env_gen``, ``validate.py`` and the
exporter-setup docs.
"""

from __future__ import annotations

import importlib
import json
import logging
import sys
import textwrap
from pathlib import Path

import attr
import pytest
import yaml
from labgrid.factory import target_factory
from labgrid.protocol import DigitalOutputProtocol, PowerProtocol
from labgrid.strategy import Strategy

import adi_lg_plugins  # noqa: F401 - registers the ADI drivers/resources
from adi_lg_plugins.hw_ci import power
from adi_lg_plugins.hw_ci.render_env import render_env
from adi_lg_plugins.hw_ci.schema import Place
from adi_lg_plugins.tools.netbox import provision

logging.getLogger("adi_lg_plugins").setLevel(logging.ERROR)

ROOT = Path(__file__).resolve().parents[1]
EXPORTER_CONFIGS_DIR = ROOT / "exporter_configs"
FRAGMENTS = EXPORTER_CONFIGS_DIR / "templates" / "power"
TYPES = list(power.POWER_TYPES.values())
EXPORTED = [t for t in TYPES if t.exporter_cls]

# Power-capable drivers that have no exporter resource to describe (see power.py).
NOT_OFFERED = {
    "ExternalPowerDriver",
    "DockerDriver",
    "QEMUDriver",
    "FileDigitalOutputDriver",
    "SerialPortDigitalOutputDriver",
    "ManualSwitchDriver",
}


def _ids(t):
    return t.key


def sample_context(t: power.PowerType) -> dict[str, str]:
    """An operator's answers for every field of ``t``."""
    values = {
        "int": "3",
        "bool": "false",
        "match": "pci-0000:00:14.0-usb-0:2",
        "pairs": "5v:on, 12v:on",
    }
    ctx = {"power": t.key}
    for f in t.fields:
        if f.choices:
            ctx[f.var] = power.choices_for(f.choices)[0]
        else:
            ctx[f.var] = values.get(f.kind, f"{f.param}-value")
    return ctx


def _dummy(a: attr.Attribute):
    text = repr(a.validator)
    for typ, val in (("int", 1), ("list", ["x"]), ("dict", {}), ("bool", False)):
        if f"<class '{typ}'>" in text:
            return val
    return "x"


def _client_params(t: power.PowerType, exporter_params: dict) -> dict:
    """Params a client would hold for ``t``'s exported resource."""
    cls = target_factory.resources[t.client_cls]
    fields = {a.name: a for a in attr.fields(cls) if a.init and a.name not in ("target", "name")}
    params = {k: v for k, v in exporter_params.items() if k in fields and k != "match"}
    for name, a in fields.items():
        if name not in params and a.default is attr.NOTHING:
            params[name] = _dummy(a)
    return params


# --- coverage -----------------------------------------------------------------


def test_every_labgrid_power_driver_is_offered_or_documented_as_excluded():
    offered = {t.driver for t in TYPES} | {t.output_driver for t in TYPES}
    candidates = {
        name
        for name, cls in target_factory.drivers.items()
        if isinstance(cls, type)
        and (issubclass(cls, PowerProtocol) or issubclass(cls, DigitalOutputProtocol))
        and not issubclass(cls, Strategy)
    }
    assert candidates - offered - NOT_OFFERED == set()


def test_categories_are_all_used():
    assert {t.category for t in TYPES} == set(power.CATEGORIES)


@pytest.mark.parametrize("t", EXPORTED, ids=_ids)
def test_client_class_is_what_the_driver_binds(t):
    assert t.exporter_cls in target_factory.resources
    assert t.client_cls in target_factory.resources
    binder = target_factory.drivers[t.output_driver or t.driver]
    accepted = set()
    for spec in binder.bindings.values():
        cands = spec if isinstance(spec, (set, frozenset, list, tuple)) else {spec}
        accepted |= {c if isinstance(c, str) else getattr(c, "__name__", "") for c in cands if c}
    assert t.client_cls in accepted


def test_network_power_models_come_from_installed_labgrid():
    models = power.choices_for("network_power_models")
    assert {"gude", "netio", "raritan", "rest"} <= set(models)


# --- fragments ------------------------------------------------------------------


def test_fragment_files_match_the_registry():
    on_disk = {p.stem: p.read_text() for p in FRAGMENTS.glob("*.yaml")}
    assert on_disk == {t.key: power.fragment(t) for t in TYPES}


@pytest.mark.parametrize("t", EXPORTED, ids=_ids)
def test_fragment_renders_valid_resource_parameters(t, tmp_path):
    import jinja2

    rendered = jinja2.Environment(undefined=jinja2.StrictUndefined).from_string(
        "g:\n" + power.fragment(t)
    )
    env = {c.env: f"{c.env.lower()}-value" for c in t.credentials}
    data = yaml.safe_load(rendered.render(env=env, **sample_context(t)))
    params = dict(data["g"][t.exporter_cls])
    assert params.pop("cls") == t.exporter_cls
    cls = target_factory.resources[t.exporter_cls]
    assert set(params) <= {a.name for a in attr.fields(cls) if a.init}
    for c in t.credentials:
        assert params[c.param] == f"{c.env.lower()}-value"
    if t.exporter_cls == t.client_cls:  # no udev lookup: build it as the client would
        from labgrid import Target

        try:
            cls(Target(f"t-{t.key}"), name=None, **params)
        except ModuleNotFoundError as e:
            pytest.skip(f"optional labgrid dependency {e.name!r} is not installed")


# --- client side ------------------------------------------------------------------


def _resource(target, t: power.PowerType):
    """Build ``t``'s client resource on ``target`` as a RemotePlace would provide it."""
    import jinja2

    frag = jinja2.Environment().from_string("g:\n" + power.fragment(t))
    exported = yaml.safe_load(frag.render(env={}, **sample_context(t)))["g"][t.exporter_cls]
    cls = target_factory.resources[t.client_cls]
    try:
        return cls(target, name=None, **_client_params(t, exported))
    except ModuleNotFoundError as e:
        pytest.skip(f"optional labgrid dependency {e.name!r} is not installed")


def _bind(target, driver_name):
    """Bind a driver with labgrid's own resolver, without its connect-on-create code."""
    from labgrid.binding import BindingState

    cls = target_factory.drivers[driver_name]
    driver = object.__new__(cls)
    driver.name, driver.target, driver.state = None, None, BindingState.idle
    driver.clients, driver.suppliers = set(), set()
    target.bind_driver(driver)
    return driver


@pytest.mark.parametrize("t", TYPES, ids=_ids)
def test_labgrid_binds_the_power_driver_from_its_client_resource(t):
    from labgrid import Target

    target = Target(f"bind-{t.key}")
    resource = _resource(target, t) if t.client_cls else None
    drivers = [_bind(target, name) for name in t.drivers]
    power_driver = drivers[-1]
    assert isinstance(power_driver, PowerProtocol)
    if t.output_driver:
        # DigitalOutputPowerDriver binds the relay driver, which binds the resource.
        assert power_driver.output is drivers[0]
        assert resource in drivers[0].suppliers
    elif resource is not None:
        assert resource in power_driver.suppliers


@pytest.mark.parametrize("t", TYPES, ids=_ids)
def test_render_env_emits_the_power_drivers_in_binding_order(t):
    tags = {"power-driver": t.driver}
    if t.output_driver:
        tags["power-output-driver"] = t.output_driver
    place = Place(
        name="p",
        carrier="zcu102",
        daughter_board="ad9081",
        boot_strategy="BootFPGASoC",
        hdl_config="m8_l4",
        extra_tags=tags,
    )
    drivers = list(yaml.safe_load(render_env(place))["targets"]["main"]["drivers"])
    positions = [drivers.index(d) for d in t.drivers]
    assert positions == sorted(positions)


def test_render_env_without_output_tag_keeps_the_legacy_single_driver():
    place = Place(
        name="p",
        carrier="zcu102",
        daughter_board="ad9081",
        boot_strategy="BootFPGASoC",
        hdl_config="m8_l4",
        extra_tags={"power-driver": "HomeAssistantPowerDriver"},
    )
    drivers = list(yaml.safe_load(render_env(place))["targets"]["main"]["drivers"])
    assert drivers[0] == "HomeAssistantPowerDriver"


def _env_gen():
    sys.path.insert(0, str(ROOT / "coordinator" / "api"))
    try:
        return importlib.import_module("app.env_gen")
    finally:
        sys.path.pop(0)


@pytest.mark.parametrize("t", EXPORTED, ids=_ids)
def test_coordinator_env_gen_maps_every_power_resource(t):
    env_gen = _env_gen()
    assert [d for d, _ in env_gen.RESOURCE_DRIVER_MAP[t.client_cls]] == list(t.drivers)
    # ...and counts it as a power outlet when inferring the SSH boot strategy.
    shape = {"KuiperRelease", "NetworkService", t.client_cls}
    assert env_gen.infer_strategy(shape) == "BootFPGASoCSSH"


# --- validation and docs ---------------------------------------------------------


def test_validate_py_knows_every_exported_power_class():
    validate = provision._load_validate_module(EXPORTER_CONFIGS_DIR)
    assert {t.exporter_cls for t in EXPORTED} <= validate.KNOWN_CLASSES
    schema = json.loads((EXPORTER_CONFIGS_DIR / "schemas" / "exporter_schema.json").read_text())
    assert set(schema["$defs"]["known_resource_classes"]["enum"]) == validate.KNOWN_CLASSES


def test_exporter_setup_docs_list_every_power_type():
    text = (ROOT / "docs" / "source" / "user-guide" / "exporter-setup.rst").read_text()
    assert [t.key for t in TYPES if f"``{t.key}``" not in text] == []


def test_missing_power_env_ignores_optional_credentials(monkeypatch):
    from unittest.mock import MagicMock

    import labgrid.util.ssh as ssh_mod
    from labgrid.driver.exception import ExecutionError

    conn = MagicMock()
    conn.run_check.side_effect = ExecutionError("grep", [], [])
    monkeypatch.setattr(ssh_mod.sshmanager, "get", lambda host: conn)

    assert provision.missing_power_env("h", "kasa") == []
    assert provision.missing_power_env("h", "homeassistant") == [
        "HOMEASSISTANT_URL",
        "HOMEASSISTANT_TOKEN",
    ]


def test_module_docstring_lists_the_exclusions():
    doc = textwrap.dedent(power.__doc__ or "")
    assert all(name in doc for name in NOT_OFFERED)
