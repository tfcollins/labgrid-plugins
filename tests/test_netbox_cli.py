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
    monkeypatch.setattr(cli.client, "connect", lambda url, token, **k: object())
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
    monkeypatch.setattr(cli.client, "connect", lambda url, token, **k: object())
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


_SOC_SSH_REPLIES = {
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


def _run_until_netbox(monkeypatch, args, replies=None, *, connect=None, schema_error=None):
    """Answer every prompt, then stop the run at the NetBox schema step."""
    replies = {**_SOC_SSH_REPLIES, **(replies or {})}
    asked = []

    def _ask(prompt, *a, **k):
        asked.append(prompt)
        for key, value in replies.items():
            if prompt.startswith(key):
                return value.pop(0) if isinstance(value, list) else value
        return k.get("default")

    def ensure_schema(nb):
        raise schema_error or RuntimeError("stop after connecting")

    monkeypatch.setattr(cli.Prompt, "ask", staticmethod(_ask))
    monkeypatch.setattr(cli.Confirm, "ask", staticmethod(lambda *a, **k: True))
    monkeypatch.setattr(cli.client, "connect", connect or (lambda url, token, **k: object()))
    monkeypatch.setattr(cli.client, "ensure_schema", ensure_schema)
    monkeypatch.setattr(cli, "resolve_coordinator", lambda coord: "coord:20408")
    result = CliRunner().invoke(
        cli.netbox_group,
        ["add-hardware", "--exporter-configs-dir", str(EXPORTER_CONFIGS_DIR), *args],
    )
    return result, asked


def test_netbox_token_prompt_says_input_is_hidden_and_confirms_what_it_read(monkeypatch):
    """A pasted token doesn't echo, so the operator needs proof it arrived."""
    seen = {}

    def connect(url, token, **kwargs):
        seen.update(url=url, token=token)
        return object()

    result, asked = _run_until_netbox(
        monkeypatch,
        ["--coord-user", "u", "--coord-password", "p"],
        {"NetBox URL": "https://netbox.test", "NetBox API token": ["", "  tok123\n"]},
        connect=connect,
    )

    assert seen == {"url": "https://netbox.test", "token": "tok123"}
    token_prompts = [p for p in asked if p.startswith("NetBox API token")]
    assert len(token_prompts) == 2  # blank answer re-asked
    assert "hidden" in token_prompts[0]
    assert "received 6 characters" in result.output


@pytest.mark.parametrize(
    ("args", "expected"),
    [([], False), (["--netbox-verify"], True), (["--netbox-ca-bundle", "CA"], "CA")],
)
def test_tls_options_reach_the_netbox_client(monkeypatch, tmp_path, args, expected):
    ca = tmp_path / "ca.pem"
    ca.write_text("")
    args = [str(ca) if a == "CA" else a for a in args]
    expected = str(ca) if expected == "CA" else expected
    seen = {}

    def connect(url, token, *, verify):
        seen["verify"] = verify
        return object()

    result, _ = _run_until_netbox(
        monkeypatch,
        [
            "--netbox-url",
            "https://nb",
            "--netbox-token",
            "t",
            "--coord-user",
            "u",
            "--coord-password",
            "p",
            *args,
        ],
        connect=connect,
    )

    assert seen == {"verify": expected}
    assert ("not verified" in result.output) == (expected is False)


def test_connect_applies_tls_verification_to_the_session(tmp_path):
    from adi_lg_plugins.tools.netbox import client

    assert client.connect("https://nb", "t").http_session.verify is True
    assert client.connect("https://nb", "t", verify=False).http_session.verify is False
    ca = str(tmp_path / "ca.pem")
    assert client.connect("https://nb", "t", verify=ca).http_session.verify == ca


@pytest.mark.parametrize("verify", [False, "/etc/netbox-ca.pem"])
def test_tls_choice_wins_over_ca_bundle_env_vars(monkeypatch, verify):
    """requests lets REQUESTS_CA_BUNDLE override session.verify; the CLI choice must not lose."""
    from adi_lg_plugins.tools.netbox import client

    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/elsewhere/ca.pem")
    session = client.connect("https://nb", "t", verify=verify).http_session

    settings = session.merge_environment_settings("https://nb/api/", {}, None, None, None)

    assert settings["verify"] == verify


def test_verification_on_still_honors_ca_bundle_env_vars(monkeypatch):
    from adi_lg_plugins.tools.netbox import client

    monkeypatch.setenv("REQUESTS_CA_BUNDLE", "/elsewhere/ca.pem")
    session = client.connect("https://nb", "t", verify=True).http_session

    settings = session.merge_environment_settings("https://nb/api/", {}, None, None, None)

    assert settings["verify"] == "/elsewhere/ca.pem"


def test_tls_failure_suggests_a_ca_bundle(monkeypatch):
    import requests

    result, _ = _run_until_netbox(
        monkeypatch,
        [
            "--netbox-url",
            "https://nb",
            "--netbox-token",
            "t",
            "--coord-user",
            "u",
            "--coord-password",
            "p",
        ],
        schema_error=requests.exceptions.SSLError(
            "certificate verify failed: self-signed certificate in certificate chain"
        ),
    )

    assert result.exit_code == 1
    assert not isinstance(result.exception, requests.exceptions.SSLError)
    assert "--netbox-ca-bundle" in result.output


def test_rejected_token_is_reported_without_a_traceback(monkeypatch):
    import pynetbox

    class _Forbidden:
        status_code, reason, url, text = 403, "Forbidden", "https://nb/api/", ""
        request = type("R", (), {"body": None})()

        def json(self):
            return {"detail": "Invalid v1 token"}

    result, _ = _run_until_netbox(
        monkeypatch,
        [
            "--netbox-url",
            "https://nb",
            "--netbox-token",
            "t",
            "--coord-user",
            "u",
            "--coord-password",
            "p",
        ],
        schema_error=pynetbox.RequestError(_Forbidden()),
    )

    assert result.exit_code == 1
    assert not isinstance(result.exception, pynetbox.RequestError)
    assert "Invalid v1 token" in result.output
    assert "--netbox-token" in result.output


def test_unusable_ca_bundle_is_reported_without_a_traceback(monkeypatch):
    """requests raises a bare OSError for a CA bundle path that doesn't exist."""
    result, _ = _run_until_netbox(
        monkeypatch,
        [
            "--netbox-url",
            "https://nb",
            "--netbox-token",
            "t",
            "--coord-user",
            "u",
            "--coord-password",
            "p",
            "--netbox-verify",
        ],
        schema_error=OSError("Could not find a suitable TLS CA certificate bundle"),
    )

    assert result.exit_code == 1
    assert not isinstance(result.exception, OSError)
    assert "Could not find a suitable TLS CA certificate bundle" in result.output


def test_options_are_listed_one_per_row_not_run_together(monkeypatch):
    kwargs_by_prompt = {}

    def _ask(prompt, *args, **kwargs):
        kwargs_by_prompt[prompt.strip()] = kwargs
        return next(
            (v for k, v in _SOC_SSH_REPLIES.items() if prompt.startswith(k)), kwargs.get("default")
        )

    monkeypatch.setattr(cli.Prompt, "ask", staticmethod(_ask))

    result = CliRunner().invoke(
        cli.netbox_group,
        ["add-hardware", "--dry-run", "--exporter-configs-dir", str(EXPORTER_CONFIGS_DIR)],
    )

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()

    def row(*tokens):
        return any(all(t in line for t in tokens) for line in lines)

    assert row("fabric-jtag", "BootFabric")  # template + the strategy it's written for
    assert row("soc-ssh", "BootFPGASoCSSH")
    assert not row("fabric-jtag", "rpi-ssh")
    assert row("BootZynqMPJTAG", "JTAG")  # strategy + its description
    assert row("Network PDU", "cyberpower")  # category + its types
    assert row("cyberpower", "CyberPower PDU")  # type + its label
    assert row("target_ip", "required")
    assert not row("Template fields", ", ")
    for prompt in ("Board template", "Boot strategy", "Power category", "Power type"):
        assert kwargs_by_prompt[prompt]["show_choices"] is False, prompt
    # an empty default would otherwise print as "()" after the prompt
    assert kwargs_by_prompt["serial_port (blank = template default)"]["show_default"] is False
