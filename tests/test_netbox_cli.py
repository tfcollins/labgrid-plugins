"""Unit tests for `adi-lg netbox add-hardware` orchestration.

NetBox, SSH, and the coordinator are external services, so their client calls
are replaced with recorders; template rendering and validation run for real
against this repo's exporter_configs/.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from adi_lg_plugins.tools.netbox import cli

EXPORTER_CONFIGS_DIR = Path(__file__).resolve().parents[1] / "exporter_configs"

_ANSWERS = {
    "Board template": "soc-sdmux",
    "Hardware / place / exporter name": "zc706-lab3-001",
    "Carrier": "zc706",
    "Daughter board / chip": "adrv9009",
    "Power control": "homeassistant",
    "Power outlet": "switch.zc706_bench",
    "GitHub runner label": "hw-zc706",
    "NetBox site slug": "lab3",
    "Exporter host SSH target": "labadmin@lab-host-03",
    "  target_ip": "10.0.0.42",
}


def test_add_hardware_matches_resources_under_the_deployed_exporter_name(monkeypatch):
    calls = {}
    asked = []

    def _ask(prompt, *args, **kwargs):
        asked.append(prompt)
        calls.setdefault("defaults", {})[prompt] = kwargs.get("default")
        for prefix, answer in _ANSWERS.items():
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
        cli.provision, "missing_power_env", lambda host, power: ["HOMEASSISTANT_TOKEN"]
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
    assert calls["tags"]["power-driver"] == "HomeAssistantPowerDriver"
    # A missing credential on the exporter host is reported, not fatal.
    assert "HOMEASSISTANT_TOKEN" in result.output
