"""Tests for adi_lg_plugins.hw_ci.render_env."""

from __future__ import annotations

import pytest

from adi_lg_plugins.hw_ci.render_env import (
    RenderError,
    list_strategy_templates,
    render_env,
    render_env_to,
)
from adi_lg_plugins.hw_ci.schema import KNOWN_STRATEGIES, Place


def _place(strat, place="mini2"):
    return Place(
        name=place,
        carrier="zcu102",
        daughter_board="ad9081",
        boot_strategy=strat,
        hdl_config="m8_l4",
    )


def test_every_known_strategy_has_a_template():
    """Discoverable strategies and discoverable templates must match.

    If this fails it means someone added a Boot* class under
    adi_lg_plugins.strategies/ without a matching .yaml template
    under adi_lg_plugins/hw_ci/templates/, OR vice versa.
    """
    templates = set(list_strategy_templates())
    strategies = set(KNOWN_STRATEGIES)
    # SoftwareProvisioningStrategy isn't a boot strategy; it shouldn't be
    # in either set, but defend explicitly.
    missing_templates = strategies - templates
    assert not missing_templates, (
        f"strategies missing render templates: {sorted(missing_templates)}"
    )


def test_render_substitutes_place_name():
    out = render_env(_place("BootFPGASoC"))
    assert "name: mini2" in out
    assert "${place_name}" not in out
    assert "${carrier}" not in out


def test_render_includes_strategy_driver():
    """Every template should mention its own strategy class name."""
    for strat in KNOWN_STRATEGIES:
        out = render_env(_place(strat))
        assert strat in out, f"template for {strat} doesn't reference it"


def test_render_unknown_strategy_raises():
    p = Place(
        name="x",
        carrier="zcu102",
        daughter_board="ad9081",
        boot_strategy="BootMadeUp",
    )
    with pytest.raises(RenderError, match="no env-yaml template"):
        render_env(p)


def test_render_env_to_writes_file(tmp_path):
    out = tmp_path / "env" / "mini2.yaml"
    written = render_env_to(_place("BootFPGASoC"), out)
    assert written == out
    text = out.read_text()
    assert "RemotePlace" in text
    assert "mini2" in text


def test_extra_subs_override_builtins(tmp_path):
    out = render_env(
        _place("BootFPGASoC"),
        extra_subs={"place_name": "override"},
    )
    assert "name: override" in out
    assert "name: mini2" not in out


def test_power_driver_defaults_to_vesync():
    """Places with no power-driver tag default to VesyncPowerDriver."""
    out = render_env(_place("BootFPGASoC"))
    assert "VesyncPowerDriver:" in out
    assert "HomeAssistantDriver:" not in out


def test_power_driver_tag_overrides():
    """A `power-driver=HomeAssistantDriver` tag swaps the power driver."""
    p = Place(
        name="bq",
        carrier="zc706",
        daughter_board="adrv9371",
        boot_strategy="BootFPGASoC",
        extra_tags={"power-driver": "HomeAssistantDriver"},
    )
    out = render_env(p)
    assert "HomeAssistantDriver:" in out
    assert "VesyncPowerDriver:" not in out
