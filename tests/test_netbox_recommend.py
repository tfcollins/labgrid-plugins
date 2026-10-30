"""Unit tests for adi_lg_plugins.tools.netbox.recommend.

Which boot strategies a template's exported resources can run is read from the
real render-env configs (adi_lg_plugins/hw_ci/templates) and the real labgrid
driver bindings, so these tests check it against this repo's own exporter
templates.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from labgrid.factory import target_factory

from adi_lg_plugins.tools.netbox import cli, provision, recommend

TEMPLATES = Path(__file__).resolve().parents[1] / "exporter_configs" / "templates"


def _exported(template: str) -> set[str]:
    return provision.template_resources(TEMPLATES / f"{template}.yaml")


@pytest.mark.parametrize("template", sorted(p.stem for p in TEMPLATES.glob("*.yaml")))
def test_each_template_runs_the_strategy_it_is_written_for(template):
    strategy = provision.template_strategy(TEMPLATES / f"{template}.yaml")

    assert recommend.missing(strategy, _exported(template)) == []


def test_the_sd_mux_template_also_runs_the_ssh_strategy():
    # soc-sdmux's header says it serves BootFPGASoCSSH too.
    assert recommend.missing("BootFPGASoCSSH", _exported("soc-sdmux")) == []


def test_a_jtag_template_cannot_run_the_sd_mux_strategy():
    assert recommend.missing("BootFPGASoC", _exported("zynqmp-jtag")) == [
        "KuiperRelease",
        "MassStorageDevice",
        "USBSDMuxDevice",
    ]


def test_an_exported_class_meets_a_need_for_its_base_class():
    # SerialDriver binds a SerialPort; the templates export a RawSerialPort.
    assert recommend.missing("BootSelMap", {"RawSerialPort", "NetworkService"}) == []
    assert recommend.missing("BootSelMap", {"NetworkService"}) == ["SerialPort"]


def test_a_resource_the_render_config_defines_itself_is_not_needed_from_the_exporter():
    # BootFPGASoCTFTP's config runs its own TFTP server; BootZynq7000JTAGRecovery's doesn't.
    assert "TFTPServerResource" not in recommend.missing("BootFPGASoCTFTP", set())
    assert recommend.missing("BootZynq7000JTAGRecovery", _exported("soc-tftp")) == [
        "TFTPServerResource"
    ]


def test_a_need_met_by_any_of_several_classes_is_named_once():
    # USBStorageDriver takes any of eight storage classes, a USB SD mux among them;
    # without one, BootFPGASoC names only the SD mux it needs anyway.
    missing = recommend.missing("BootFPGASoC", {"RawSerialPort", "KuiperRelease"})

    assert missing == ["MassStorageDevice", "USBSDMuxDevice"]


def test_an_optional_binding_is_not_a_need(monkeypatch):
    class OptionalDriver:
        bindings = {"port": {"SerialPort", None}}

    monkeypatch.setitem(target_factory.drivers, "OptionalDriver", OptionalDriver)

    assert recommend._needs({"drivers": {"OptionalDriver": {}}}) == frozenset()


def test_every_strategy_add_hardware_offers_is_read_from_its_render_config():
    for strategy in cli.KNOWN_BOOT_STRATEGIES:
        assert recommend.strategy_needs(strategy), strategy
