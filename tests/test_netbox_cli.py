"""Unit tests for `adi-lg netbox add-hardware` orchestration.

NetBox, SSH, and the coordinator are external services, so their client calls
are replaced with recorders; template rendering and validation run for real
against this repo's exporter_configs/. Most tests answer prompts through
`_stub_prompts`; `test_dry_run_through_the_real_prompts` types every answer into
the real prompts instead.
"""

from __future__ import annotations

import getpass
import re
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner
from rich.prompt import Confirm, Prompt

from adi_lg_plugins.tools.netbox import cli

EXPORTER_CONFIGS_DIR = Path(__file__).resolve().parents[1] / "exporter_configs"
DRY_RUN = ["add-hardware", "--dry-run", "--exporter-configs-dir", str(EXPORTER_CONFIGS_DIR)]
CREDENTIALS = [
    "--netbox-url",
    "https://nb",
    "--netbox-token",
    "t",
    "--coord-user",
    "u",
    "--coord-password",
    "p",
]


@pytest.fixture(autouse=True)
def _no_credentials_from_the_environment(monkeypatch):
    """These would skip the credential prompts the tests answer."""
    for var in ("NETBOX_URL", "NETBOX_TOKEN", "NETBOX_CA_BUNDLE", "LG_API_USERNAME"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("LG_API_PASSWORD", raising=False)


def _type_into_real_prompts(monkeypatch, conversation, *args):
    """Run add-hardware, typing each answer of ``conversation`` into the real prompts.

    Returns the result and every prompt shown, in order. Hidden answers go
    through getpass, which would otherwise read the real terminal.
    """
    monkeypatch.setattr(
        getpass, "getpass", lambda prompt="", stream=None: sys.stdin.readline().rstrip("\n")
    )
    prompts = []
    for cls in (Prompt, Confirm):
        real_ask = cls.ask

        def spy(prompt, *a, _real_ask=real_ask, **k):
            prompts.append(str(prompt))
            return _real_ask(prompt, *a, **k)

        monkeypatch.setattr(cls, "ask", staticmethod(spy))
    result = CliRunner().invoke(
        cli.netbox_group,
        ["add-hardware", "--exporter-configs-dir", str(EXPORTER_CONFIGS_DIR), *args],
        input="".join(f"{answer}\n" for _, answer in conversation),
        catch_exceptions=False,
    )
    return result, prompts


def _assert_asked_in_order(conversation, prompts):
    assert [q for q, _ in conversation] == [
        next((q for q, _ in conversation if p.startswith(q)), p) for p in prompts
    ]
    # Every question says what it is for, not a bare template variable name.
    assert not [p for p in prompts if re.match(r"\s*[a-z]+_[a-z_]+\b", p)]


class _Asked(list):
    """Prompts asked, in order; ``kwargs`` maps each stripped prompt to its keyword args."""

    def __init__(self):
        super().__init__()
        self.kwargs = {}


def _stub_prompts(monkeypatch, replies) -> _Asked:
    """Answer each prompt from the first ``replies`` key it starts with.

    A list answers successive asks (its last item repeats). A prompt matching no
    key gets its default; with no default the test fails at once, because a
    required prompt would otherwise be asked again forever.
    """
    asked = _Asked()
    replies = {k: list(v) if isinstance(v, list) else [v] for k, v in replies.items()}

    def _ask(prompt, *args, **kwargs):
        asked.append(prompt)
        asked.kwargs[prompt.strip()] = kwargs
        for prefix, answers in replies.items():
            if prompt.startswith(prefix):
                return answers.pop(0) if len(answers) > 1 else answers[0]
        if kwargs.get("default") is None:
            raise AssertionError(f"no answer for prompt {prompt!r}")
        return kwargs["default"]

    monkeypatch.setattr(Prompt, "ask", staticmethod(_ask))
    return asked


def _invoke(*args):
    # Unexpected exceptions (including a stub's AssertionError) fail the test
    # with their own traceback; click still turns ClickException into exit 1.
    return CliRunner().invoke(cli.netbox_group, list(args), catch_exceptions=False)


def _stub_services(monkeypatch, *, place=None):
    """Replace NetBox, the exporter host and the coordinator with recorders.

    ``place`` is what the coordinator already holds under the board's name.
    Returns the calls made; ``calls["steps"]`` lists the changes in order.
    """
    calls = {"steps": []}

    def connect(url, token, **kwargs):
        calls.update(url=url, token=token)
        return object()

    def device(nb, name, **kwargs):
        calls["steps"].append("netbox")
        return type("Device", (), {"id": 7})()

    def deploy(ssh_host, ssh_user, name, rendered, coord, **kwargs):
        calls["steps"].append("exporter")
        calls["exporter_name"] = name

    def login(api, user, password):
        calls["login"] = (user, password)
        return "cookie"

    monkeypatch.setattr(cli.client, "connect", connect)
    monkeypatch.setattr(cli.client, "ensure_schema", lambda nb: None)
    monkeypatch.setattr(cli.client, "create_or_update_device", device)
    monkeypatch.setattr(cli.provision, "check_prerequisites", lambda host: "/usr/bin/lg-exp")
    monkeypatch.setattr(cli.provision, "deploy_exporter", deploy)
    monkeypatch.setattr(cli.provision, "verify_exporter_active", lambda host, name: None)
    monkeypatch.setattr(cli.provision, "missing_power_env", lambda host, power: [])
    monkeypatch.setattr(cli, "resolve_coordinator", lambda coord: "coord:20408")
    monkeypatch.setattr(cli, "_resolve_api", lambda coord: "coord:8000")
    monkeypatch.setattr(cli.coord_mod, "login", login)
    monkeypatch.setattr(cli, "get_place", lambda api, name: place)
    monkeypatch.setattr(
        cli, "create_place", lambda api, cookie, name: calls["steps"].append("place")
    )
    monkeypatch.setattr(
        cli,
        "add_match",
        lambda api, cookie, name, pattern: calls.setdefault("patterns", []).append(pattern),
    )
    monkeypatch.setattr(
        cli, "set_place_tags", lambda api, cookie, name, tags: calls.update(tags=tags)
    )
    # A lab coordinator lists many places, not just the new one.
    monkeypatch.setattr(
        cli,
        "fetch_raw_places",
        lambda coord: [{"name": n, "tags": {}} for n in ("bq", "pluto", "zc706-lab3-001")],
    )
    return calls


# A soc-ssh board with a CyberPower PDU, keyed by prompt prefix.
_SOC_SSH = {
    "Board template": "soc-ssh",
    "Board name": "b1",
    "Carrier board": "zcu102",
    "ADI daughter board or chip": "ad9081",
    "Power category": "Network PDU",
    "Power type": "cyberpower",
    "  PDU hostname or IP": "10.0.0.20",
    "  Outlet number": "4",
    "NetBox site slug": "lab3",
    "Exporter host SSH login": "root@h",
    "  Board IP address": "10.0.0.5",
}

_SOC_SDMUX = {
    "Board template": "soc-sdmux",
    "Board name": "zc706-lab3-001",
    "Carrier board": "zc706",
    "ADI daughter board or chip": "adrv9009",
    "GitHub Actions runner label": "hw-zc706",
    "NetBox site slug": "lab3",
    "Exporter host SSH login": "labadmin@lab-host-03",
    "  Board IP address": "10.0.0.42",
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
    asked = _stub_prompts(
        monkeypatch,
        {"Power category": category, "Power type": power, **power_answers, **_SOC_SDMUX},
    )
    monkeypatch.setattr(cli.Confirm, "ask", staticmethod(lambda *a, **k: True))
    calls = _stub_services(monkeypatch)
    monkeypatch.setattr(
        cli.provision, "missing_power_env", lambda host, power: [missing] if missing else []
    )

    result = _invoke(
        "add-hardware", "--exporter-configs-dir", str(EXPORTER_CONFIGS_DIR), *CREDENTIALS
    )

    assert result.exit_code == 0, result.output
    assert calls["exporter_name"] == "zc706-lab3-001"
    # The group name comes from the Carrier / Daughter board answers ...
    assert calls["patterns"] == ["zc706-lab3-001/ZC706_ADRV9009/*"]
    # ... so they are not asked for again as template fields, nor are the power
    # answers or labgrid's own runtime `env`.
    assert not [p for p in asked if re.match(r"\s+(carrier|chip|power|env)\b", p)]
    # The strategy defaults to the one the template declares.
    assert asked.kwargs["Boot strategy"]["default"] == "BootFPGASoC"
    assert calls["tags"]["boot-strategy"] == "BootFPGASoC"
    # render-env picks the power driver from this tag.
    assert {k: v for k, v in calls["tags"].items() if k.startswith("power")} == expected_tags
    # A missing credential on the exporter host is reported, not fatal.
    if missing:
        assert missing in result.output


def test_dry_run_through_the_real_prompts(monkeypatch):
    """Type every answer into the real prompts: checks their order, wording and parsing."""
    conversation = [
        ("Board template", "3"),  # by row number: soc-sdmux
        ("Board name", "zcu102-lab3-001"),
        ("Carrier board", "zcu102"),
        ("ADI daughter board or chip", "ad9081"),
        ("Boot strategy", ""),  # the template's own, BootFPGASoC
        ("Power category", "1"),
        ("Power type", "cyberpower"),  # by name
        ("  PDU hostname or IP", "10.0.0.20"),
        ("  Outlet number", "4"),
        ("GitHub Actions runner label", ""),
        ("NetBox site slug", "lab3"),
        ("Exporter host SSH login", "labadmin@lab-host-03"),
        ("  Board IP address", "10.0.0.42"),
        ("  SD card boot partition", ""),
        ("  BOOT.BIN", "release:zynqmp-zcu102-rev10-ad9081/m8_l4/BOOT.BIN"),
        ("  Device tree", ""),
        ("  Kernel image", ""),
        ("  Kuiper release", ""),
        ("  SD mux control device", ""),
        ("  Serial console device", "/dev/ttyUSB2"),
        ("  Board Linux SSH password", ""),
        ("  Board Linux SSH username", ""),
    ]
    result, prompts = _type_into_real_prompts(monkeypatch, conversation, "--dry-run")

    assert result.exit_code == 0, result.output
    _assert_asked_in_order(conversation, prompts)
    plan = result.output[result.output.index("\nPlan") :]
    assert "ZCU102_AD9081" in plan
    assert "power-driver=CyberPowerDriver" in plan
    assert "Dry run" in result.output


def test_full_run_through_the_real_prompts(monkeypatch):
    """Credentials too: typed after Proceed?, hidden ones through getpass."""
    conversation = [
        ("Board template", "soc-ssh"),
        ("Board name", "b1"),
        ("Carrier board", "zcu102"),
        ("ADI daughter board or chip", "ad9081"),
        ("Boot strategy", ""),
        ("Power category", "Network PDU"),
        ("Power type", "cyberpower"),
        ("  PDU hostname or IP", "10.0.0.20"),
        ("  Outlet number", "4"),
        ("GitHub Actions runner label", ""),
        ("NetBox site slug", "lab3"),
        ("Exporter host SSH login", "root@h"),
        ("  Board IP address", "10.0.0.5"),
        ("  BOOT.BIN", ""),
        ("  Device tree", ""),
        ("  Kernel image", ""),
        ("  Kuiper release", ""),
        ("  Serial console device", ""),
        ("  Board Linux SSH password", ""),
        ("  Board Linux SSH username", ""),
        ("\nProceed?", "y"),
        ("NetBox URL", "https://netbox.test"),
        ("NetBox API token", "  tok123  "),  # pasted with stray whitespace
        ("Coordinator API username", "admin"),
        ("Coordinator API password", "secret"),
    ]
    calls = _stub_services(monkeypatch)

    result, prompts = _type_into_real_prompts(monkeypatch, conversation)

    assert result.exit_code == 0, result.output
    _assert_asked_in_order(conversation, prompts)
    assert calls["url"] == "https://netbox.test"
    assert calls["token"] == "tok123"
    assert "received 6 characters" in result.output
    assert calls["login"] == ("admin", "secret")
    assert calls["tags"]["power-driver"] == "CyberPowerDriver"
    # The credential questions explain themselves like the others.
    output = " ".join(result.output.split())
    assert "under your user profile in NetBox" in output
    assert "create places" in output


def test_rerun_for_an_onboarded_board_keeps_its_place_and_matches(monkeypatch):
    """The coordinator rejects a duplicate place or match, so a re-run must not send them."""
    _stub_prompts(monkeypatch, _SOC_SSH)
    monkeypatch.setattr(cli.Confirm, "ask", staticmethod(lambda *a, **k: True))
    match = {"exporter": "b1", "group": "ZCU102_AD9081", "cls": "*", "name": None, "rename": ""}
    calls = _stub_services(monkeypatch, place={"name": "b1", "matches": [match], "tags": {}})

    result = _invoke(
        "add-hardware", "--exporter-configs-dir", str(EXPORTER_CONFIGS_DIR), *CREDENTIALS
    )

    assert result.exit_code == 0, result.output
    assert calls["steps"] == ["netbox", "exporter"]  # no new place
    assert "patterns" not in calls  # nor a second copy of its match
    assert calls["tags"]["carrier"] == "zcu102"  # tags are still brought up to date


def test_coordinator_that_cannot_be_reached_is_reported_without_a_traceback(monkeypatch):
    import urllib.error

    _stub_prompts(monkeypatch, _SOC_SSH)
    monkeypatch.setattr(cli.Confirm, "ask", staticmethod(lambda *a, **k: True))
    _stub_services(monkeypatch)

    def refused(api, user, password):
        raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))

    monkeypatch.setattr(cli.coord_mod, "login", refused)

    result = _invoke(
        "add-hardware", "--exporter-configs-dir", str(EXPORTER_CONFIGS_DIR), *CREDENTIALS
    )

    assert result.exit_code == 1
    assert "Connection refused" in result.output


def test_required_answers_are_asked_again_until_given(monkeypatch):
    """A blank answer to a field with no default must not reach the render step."""
    asked = _stub_prompts(
        monkeypatch,
        {
            **_SOC_SSH,
            "Carrier board": ["", "adrv2crr-fmc"],
            "  PDU hostname or IP": ["", "10.68.152.20"],
            "  Outlet number": ["", "4"],
            "  Board IP address": ["", "10.68.152.140"],
        },
    )

    result = _invoke(*DRY_RUN)

    assert result.exit_code == 0, result.output
    assert "Dry run" in result.output
    for question in ("Carrier board", "  PDU hostname", "  Board IP address"):
        assert sum(p.startswith(question) for p in asked) == 2, question
    # Required template fields say so; optional ones say what Enter gives.
    assert "  Board IP address, for SSH to its Linux (required)" in asked
    assert "  Serial console device on the exporter host (Enter for /dev/ttyUSB0)" in asked


@pytest.mark.parametrize(
    ("question", "bad"),
    [
        ("Board name", "my board"),
        ("Board name", "lab3/b1"),
        ("Carrier board", "zcu 102"),
        ("ADI daughter board or chip", "ad9081/fmc"),
        ("NetBox site slug", "Lab 3"),
        ("Exporter host SSH login", "lab-host-03"),
        ("Exporter host SSH login", "@lab-host-03"),
    ],
)
def test_malformed_answers_are_asked_again(monkeypatch, question, bad):
    asked = _stub_prompts(monkeypatch, {**_SOC_SSH, question: [bad, _SOC_SSH[question]]})

    result = _invoke(*DRY_RUN)

    assert result.exit_code == 0, result.output
    assert sum(p.startswith(question) for p in asked) == 2


def test_each_fixed_question_explains_what_the_answer_is_for(monkeypatch):
    _stub_prompts(monkeypatch, _SOC_SSH)

    output = " ".join(_invoke(*DRY_RUN).output.split())  # explanations wrap at 80 columns

    assert "NetBox device, the coordinator place and the exporter service" in output
    assert "existing NetBox site" in output
    assert "passwordless sudo" in output


def test_missing_netbox_extra_fails_before_any_prompt(monkeypatch):
    """Without pynetbox the command must stop at once, not after every prompt."""
    monkeypatch.setitem(sys.modules, "pynetbox", None)  # `import pynetbox` -> ImportError
    asked = _stub_prompts(monkeypatch, {})

    result = _invoke("add-hardware", "--exporter-configs-dir", str(EXPORTER_CONFIGS_DIR))

    assert result.exit_code == 1
    assert asked == []
    assert 'pip install -e ".[netbox]"' in result.output


def test_dry_run_does_not_need_pynetbox(monkeypatch):
    monkeypatch.setitem(sys.modules, "pynetbox", None)
    _stub_prompts(monkeypatch, _SOC_SSH)

    result = _invoke(*DRY_RUN)

    assert result.exit_code == 0, result.output
    assert "Dry run" in result.output


def test_netbox_errors_are_reported_without_a_traceback(monkeypatch):
    """e.g. a site slug that doesn't exist in NetBox."""

    def no_site(*a, **k):
        raise RuntimeError("NetBox site 'nosuchsite' does not exist")

    _stub_prompts(monkeypatch, {**_SOC_SSH, "NetBox site slug": "nosuchsite"})
    monkeypatch.setattr(cli.Confirm, "ask", staticmethod(lambda *a, **k: True))
    monkeypatch.setattr(cli.client, "connect", lambda url, token, **k: object())
    monkeypatch.setattr(cli.client, "ensure_schema", lambda nb: None)
    monkeypatch.setattr(cli.client, "create_or_update_device", no_site)
    monkeypatch.setattr(cli, "resolve_coordinator", lambda coord: "coord:20408")

    result = _invoke(
        "add-hardware", "--exporter-configs-dir", str(EXPORTER_CONFIGS_DIR), *CREDENTIALS
    )

    assert result.exit_code == 1
    assert "does not exist" in result.output


def _run_until_netbox(monkeypatch, args, replies=None, *, connect=None, schema_error=None):
    """Answer every prompt, then stop the run at the NetBox schema step."""
    asked = _stub_prompts(monkeypatch, {**_SOC_SSH, **(replies or {})})

    def ensure_schema(nb):
        raise schema_error or RuntimeError("stop after connecting")

    monkeypatch.setattr(cli.Confirm, "ask", staticmethod(lambda *a, **k: True))
    monkeypatch.setattr(cli.client, "connect", connect or (lambda url, token, **k: object()))
    monkeypatch.setattr(cli.client, "ensure_schema", ensure_schema)
    monkeypatch.setattr(cli, "resolve_coordinator", lambda coord: "coord:20408")
    result = _invoke("add-hardware", "--exporter-configs-dir", str(EXPORTER_CONFIGS_DIR), *args)
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
    assert len(token_prompts) == 2  # blank answer asked again
    assert "hidden" in token_prompts[0]
    assert "received 6 characters" in result.output


def test_netbox_url_without_a_scheme_is_asked_again(monkeypatch):
    seen = {}

    def connect(url, token, **kwargs):
        seen["url"] = url
        return object()

    _, asked = _run_until_netbox(
        monkeypatch,
        ["--netbox-token", "t", "--coord-user", "u", "--coord-password", "p"],
        {"NetBox URL": ["netbox.test", "https://netbox.test"]},
        connect=connect,
    )

    assert seen == {"url": "https://netbox.test"}
    assert sum(p.startswith("NetBox URL") for p in asked) == 2


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

    result, _ = _run_until_netbox(monkeypatch, [*CREDENTIALS, *args], connect=connect)

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
        CREDENTIALS,
        schema_error=requests.exceptions.SSLError(
            "certificate verify failed: self-signed certificate in certificate chain"
        ),
    )

    assert result.exit_code == 1
    assert "--netbox-ca-bundle" in result.output


def test_rejected_token_is_reported_without_a_traceback(monkeypatch):
    import pynetbox

    class _Forbidden:
        status_code, reason, url, text = 403, "Forbidden", "https://nb/api/", ""
        request = type("R", (), {"body": None})()

        def json(self):
            return {"detail": "Invalid v1 token"}

    result, _ = _run_until_netbox(
        monkeypatch, CREDENTIALS, schema_error=pynetbox.RequestError(_Forbidden())
    )

    assert result.exit_code == 1
    assert "Invalid v1 token" in result.output
    assert "--netbox-token" in result.output


def test_unusable_ca_bundle_is_reported_without_a_traceback(monkeypatch):
    """requests raises a bare OSError for a CA bundle path that doesn't exist."""
    result, _ = _run_until_netbox(
        monkeypatch,
        [*CREDENTIALS, "--netbox-verify"],
        schema_error=OSError("Could not find a suitable TLS CA certificate bundle"),
    )

    assert result.exit_code == 1
    assert "Could not find a suitable TLS CA certificate bundle" in result.output


def _rows(text):
    lines = text.splitlines()
    return lambda *tokens: any(all(t in line for t in tokens) for line in lines)


def test_options_are_listed_one_per_row_not_run_together(monkeypatch):
    asked = _stub_prompts(monkeypatch, _SOC_SSH)

    result = _invoke(*DRY_RUN)

    assert result.exit_code == 0, result.output
    row = _rows(result.output)
    assert row("fabric-jtag", "BootFabric")  # template + the strategy it's written for
    assert row("soc-ssh", "BootFPGASoCSSH")
    assert not row("fabric-jtag", "rpi-ssh")
    assert row("BootZynqMPJTAG", "JTAG")  # strategy + its description
    assert row("Network PDU", "cyberpower")  # category + its types
    assert row("cyberpower", "CyberPower PDU")  # type + its label
    assert row("target_ip", "Board IP address", "required")  # field + question + default
    assert row("serial_port", "/dev/ttyUSB0")
    for prompt in ("Board template", "Boot strategy", "Power category", "Power type"):
        assert asked.kwargs[prompt]["show_choices"] is False, prompt
    # an empty default would otherwise print as "()" after the prompt
    optional = "Serial console device on the exporter host (Enter for /dev/ttyUSB0)"
    assert asked.kwargs[optional]["show_default"] is False


def test_plan_is_a_table_with_one_tag_per_line(monkeypatch):
    _stub_prompts(monkeypatch, _SOC_SSH)

    result = _invoke(*DRY_RUN)

    assert result.exit_code == 0, result.output
    plan = result.output[result.output.index("\nPlan") :]
    row = _rows(plan)
    assert row("Coordinator place", "b1")
    assert row("Systemd unit", "labgrid-exporter-b1")
    assert row("Place matches", "b1/ZCU102_AD9081/*")
    assert row("Power", "CyberPower PDU")
    for tag in (
        "daughter-board=ad9081",
        "carrier=zcu102",
        "boot-strategy=BootFPGASoCSSH",
        "runner=hw-zcu102",
        "power-driver=CyberPowerDriver",
    ):
        assert sum(tag in line for line in plan.splitlines()) == 1, tag
    assert not row("daughter-board=", "carrier=")  # not run together on one line


def test_optional_power_fields_do_not_print_an_empty_default(monkeypatch):
    asked = _stub_prompts(
        monkeypatch,
        {"Power category": "2", "Power type": "kasa", "  Kasa device": "10.0.0.60"},
    )

    power, _ = cli._ask_power()

    assert power == "kasa"
    sockets = next(p for p in asked.kwargs if p.startswith("Strip socket"))
    assert asked.kwargs[sockets]["show_default"] is False  # its default "" prints as "()"
    assert all(k.get("show_default", True) for p, k in asked.kwargs.items() if p != sockets)
