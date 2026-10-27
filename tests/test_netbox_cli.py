"""Unit tests for `adi-lg netbox add-hardware` orchestration.

NetBox, SSH, and the coordinator are external services, so their client calls
are replaced with recorders; template rendering and validation run for real
against this repo's exporter_configs/.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from adi_lg_plugins.tools.netbox import cli

EXPORTER_CONFIGS_DIR = Path(__file__).resolve().parents[1] / "exporter_configs"

_ANSWERS = {
    "Board template": "soc-sdmux",
    "Hardware / place / exporter name": "zc706-lab3-001",
    "Carrier": "zc706",
    "Daughter board / chip": "adrv9009",
    "GitHub runner label": "hw-zc706",
    "NetBox site slug": "lab3",
    "Exporter host SSH target": "labadmin@lab-host-03",
    "  target_ip": "10.0.0.42",
}


# Per power type: (category, answers to that type's own prompts, expected tags,
# credential the stubbed host reports missing).
_POWER_CASES = {
    "homeassistant": (
        "Smart plug / home automation",
        {"  Home Assistant entity_id": "switch.zc706_bench"},
        {"power-driver": "HomeAssistantPowerDriver"},
        "HOMEASSISTANT_TOKEN",
    ),
    "modbus": (
        "Relay / digital output",
        {"  Device hostname": "10.0.0.50", "  Coil number": "2"},
        {"power-driver": "DigitalOutputPowerDriver", "power-output-driver": "ModbusCoilDriver"},
        None,
    ),
}


@pytest.mark.parametrize("power", sorted(_POWER_CASES))
def test_add_hardware_matches_resources_under_the_deployed_exporter_name(monkeypatch, power):
    category, power_answers, expected_tags, missing = _POWER_CASES[power]
    answers = {
        "Power category": category,
        "Power type": power,
        **power_answers,
        **_ANSWERS,
    }
    calls = {}
    asked = []

    def _ask(prompt, *args, **kwargs):
        asked.append(prompt)
        calls.setdefault("defaults", {})[prompt] = kwargs.get("default")
        for prefix, answer in answers.items():
            if prompt.startswith(prefix):
                return answer
        return kwargs.get("default", "")

    monkeypatch.setattr(cli.Prompt, "ask", staticmethod(_ask))
    monkeypatch.setattr(cli.Confirm, "ask", staticmethod(lambda *a, **k: True))
    monkeypatch.setattr(cli.client, "connect", lambda url, token: object())
    monkeypatch.setattr(cli.client, "ensure_schema", lambda nb: None)
    monkeypatch.setattr(
        cli.client, "create_or_update_device", lambda nb, name, **kw: type("D", (), {"id": 7})()
    )
    monkeypatch.setattr(cli.provision, "check_prerequisites", lambda host: "/usr/bin/lg-exp")

    def deploy(ssh_host, ssh_user, name, rendered, coord, **kw):
        calls["exporter_name"] = name

    monkeypatch.setattr(cli.provision, "deploy_exporter", deploy)
    monkeypatch.setattr(
        cli.provision, "missing_power_env", lambda host, power: [missing] if missing else []
    )
    monkeypatch.setattr(cli.provision, "verify_exporter_active", lambda host, name: None)
    monkeypatch.setattr(cli, "resolve_coordinator", lambda coord: "coord:20408")
    monkeypatch.setattr(cli, "_resolve_api", lambda coord: "http://coord:8000/api")
    monkeypatch.setattr(cli.coord_mod, "login", lambda api, user, password: "cookie")
    monkeypatch.setattr(cli, "create_place", lambda api, cookie, name: None)
    monkeypatch.setattr(
        cli,
        "add_match",
        lambda api, cookie, name, pattern: calls.setdefault("patterns", []).append(pattern),
    )
    monkeypatch.setattr(
        cli, "set_place_tags", lambda api, cookie, name, tags: calls.update(tags=tags)
    )
    monkeypatch.setattr(cli, "fetch_raw_places", lambda coord: ([], []))

    result = CliRunner().invoke(
        cli.netbox_group,
        [
            "add-hardware",
            "--exporter-configs-dir",
            str(EXPORTER_CONFIGS_DIR),
            "--netbox-url",
            "https://netbox.test",
            "--netbox-token",
            "t",
            "--coord-user",
            "u",
            "--coord-password",
            "p",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls["exporter_name"] == "zc706-lab3-001"
    # The group name comes from the Carrier / Daughter board answers ...
    assert calls["patterns"] == ["zc706-lab3-001/ZC706_ADRV9009/*"]
    # ... so they are not asked for again as template fields, nor are the power
    # answers or labgrid's own runtime `env`.
    assert not [p for p in asked if p.startswith(("  carrier", "  chip", "  power", "  env"))]
    # The strategy defaults to the one the template declares.
    assert calls["defaults"]["Boot strategy"] == "BootFPGASoC"
    assert calls["tags"]["boot-strategy"] == "BootFPGASoC"
    # render-env picks the power driver from this tag.
    assert {k: v for k, v in calls["tags"].items() if k.startswith("power")} == expected_tags
    # A missing credential on the exporter host is reported, not fatal.
    if missing:
        assert missing in result.output


def test_required_fields_are_re_asked_until_answered(monkeypatch):
    """A blank answer to a field with no default must not reach the render step."""
    replies = {
        "Board template": ["soc-ssh"],
        "Hardware / place / exporter name": ["adrv9009zu11eg"],
        "Carrier": ["adrv2crr-fmc"],
        "Daughter board / chip": ["adrv9009zu11eg"],
        "Power category": ["Network PDU"],
        "Power type": ["cyberpower"],
        "  PDU hostname or IP": ["", "10.68.152.20"],
        "  Outlet number": ["", "4"],
        "NetBox site slug": ["chelm"],
        "Exporter host SSH target": ["root@10.68.152.131"],
        "  target_ip": ["", "10.68.152.140"],
    }
    asked = []

    def _ask(prompt, *args, **kwargs):
        asked.append(prompt)
        for prefix, answers in replies.items():
            if prompt.startswith(prefix):
                return answers.pop(0) if len(answers) > 1 else answers[0]
        return kwargs.get("default")

    monkeypatch.setattr(cli.Prompt, "ask", staticmethod(_ask))

    result = CliRunner().invoke(
        cli.netbox_group,
        ["add-hardware", "--dry-run", "--exporter-configs-dir", str(EXPORTER_CONFIGS_DIR)],
    )

    assert result.exit_code == 0, result.output
    assert "Dry run" in result.output
    assert sum(p.startswith("  target_ip") for p in asked) == 2
    assert sum(p.startswith("  PDU hostname") for p in asked) == 2
    # Required template fields are labelled as such, optional ones as defaulted.
    assert any(p.startswith("  target_ip (required)") for p in asked)
    assert any(p.startswith("  serial_port (blank = template default)") for p in asked)


def test_missing_netbox_extra_fails_before_any_prompt(monkeypatch):
    """Without pynetbox the command must stop at once, not after every prompt."""
    import sys

    monkeypatch.setitem(sys.modules, "pynetbox", None)  # `import pynetbox` -> ImportError
    asked = []
    monkeypatch.setattr(
        cli.Prompt, "ask", staticmethod(lambda prompt, *a, **k: asked.append(prompt))
    )

    result = CliRunner().invoke(
        cli.netbox_group, ["add-hardware", "--exporter-configs-dir", str(EXPORTER_CONFIGS_DIR)]
    )

    assert result.exit_code == 1
    assert asked == []
    assert not isinstance(result.exception, RuntimeError)  # a clean error, not a traceback
    assert 'pip install -e ".[netbox]"' in result.output


def test_dry_run_does_not_need_pynetbox(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "pynetbox", None)
    replies = {
        "Board template": "soc-ssh",
        "Hardware / place / exporter name": "b1",
        "Carrier": "zcu102",
        "Daughter board / chip": "ad9081",
        "Power category": "Network PDU",
        "Power type": "cyberpower",
        "  PDU hostname or IP": "10.0.0.20",
        "  Outlet number": "4",
        "NetBox site slug": "lab3",
        "Exporter host SSH target": "root@h",
        "  target_ip": "10.0.0.5",
    }

    def _ask(prompt, *args, **kwargs):
        return next((v for k, v in replies.items() if prompt.startswith(k)), kwargs.get("default"))

    monkeypatch.setattr(cli.Prompt, "ask", staticmethod(_ask))

    result = CliRunner().invoke(
        cli.netbox_group,
        ["add-hardware", "--dry-run", "--exporter-configs-dir", str(EXPORTER_CONFIGS_DIR)],
    )

    assert result.exit_code == 0, result.output
    assert "Dry run" in result.output


def test_netbox_errors_are_reported_without_a_traceback(monkeypatch):
    """e.g. a site slug that doesn't exist in NetBox."""
    replies = {
        "Board template": "soc-ssh",
        "Hardware / place / exporter name": "b1",
        "Carrier": "zcu102",
        "Daughter board / chip": "ad9081",
        "Power category": "Network PDU",
        "Power type": "cyberpower",
        "  PDU hostname or IP": "10.0.0.20",
        "  Outlet number": "4",
        "NetBox site slug": "nosuchsite",
        "Exporter host SSH target": "root@h",
        "  target_ip": "10.0.0.5",
    }

    def _ask(prompt, *args, **kwargs):
        return next((v for k, v in replies.items() if prompt.startswith(k)), kwargs.get("default"))

    def no_site(*a, **k):
        raise RuntimeError("NetBox site 'nosuchsite' does not exist")

    monkeypatch.setattr(cli.Prompt, "ask", staticmethod(_ask))
    monkeypatch.setattr(cli.Confirm, "ask", staticmethod(lambda *a, **k: True))
    monkeypatch.setattr(cli.client, "connect", lambda url, token: object())
    monkeypatch.setattr(cli.client, "ensure_schema", lambda nb: None)
    monkeypatch.setattr(cli.client, "create_or_update_device", no_site)
    monkeypatch.setattr(cli, "resolve_coordinator", lambda coord: "coord:20408")

    result = CliRunner().invoke(
        cli.netbox_group,
        [
            "add-hardware",
            "--exporter-configs-dir",
            str(EXPORTER_CONFIGS_DIR),
            "--netbox-url",
            "https://netbox.test",
            "--netbox-token",
            "t",
            "--coord-user",
            "u",
            "--coord-password",
            "p",
        ],
    )

    assert result.exit_code == 1
    assert not isinstance(result.exception, RuntimeError)
    assert "does not exist" in result.output
