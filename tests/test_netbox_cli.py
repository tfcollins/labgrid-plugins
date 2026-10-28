"""Unit tests for `adi-lg netbox add-hardware` orchestration.

NetBox, SSH, and the coordinator are external services, so their client calls
are replaced with recorders; template rendering and validation run for real
against this repo's exporter_configs/. Most tests answer prompts through
`_stub_prompts`; `test_dry_run_through_the_real_prompts` types every answer into
the real prompts instead.
"""

from __future__ import annotations

import getpass
import json
import re
import stat
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
    for var in ("LG_COORDINATOR", "ADI_LG_COORDINATOR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("LG_API_PASSWORD", raising=False)


@pytest.fixture(autouse=True)
def saved_runs(monkeypatch, tmp_path):
    """Keep saved answers out of the real ~/.cache; returns where they go."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return tmp_path / "cache" / "adi-lg" / "netbox-add-hardware"


@pytest.fixture(autouse=True)
def _netbox_inventory(monkeypatch):
    """What NetBox holds, read before the plan: two sites, no power or console devices yet."""
    monkeypatch.setattr(cli.client, "sites", lambda nb: [("lab3", "Lab 3"), ("lab4", "Lab 4")])
    monkeypatch.setattr(cli.client, "power_devices", lambda nb, site: [])
    monkeypatch.setattr(cli.client, "console_devices", lambda nb, site: [])
    monkeypatch.setattr(cli.client, "device_exists", lambda nb, name, site: False)
    monkeypatch.setattr(cli.client, "connect_power", lambda nb, board, **kwargs: [])
    monkeypatch.setattr(cli.client, "connect_console", lambda nb, board, **kwargs: [])


# The real prompts, even after a test has replaced them with _stub_prompts.
_REAL_ASK = {Prompt: Prompt.ask, Confirm: Confirm.ask}


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

        def spy(prompt, *a, _real_ask=_REAL_ASK[cls], **k):
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
        max((q for q, _ in conversation if p.startswith(q)), key=len, default=p) for p in prompts
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


def _stub_services(monkeypatch, *, place=None, power_devices=(), consoles=(), taken=()):
    """Replace NetBox, the exporter host and the coordinator with recorders.

    ``place`` is what the coordinator already holds under the board's name;
    ``power_devices`` and ``consoles`` are NetBox's power devices and devices
    with console server ports at the site, ``taken`` the names of its other
    devices. Returns the calls made; ``calls["steps"]`` lists the changes in
    order, ``calls["power"]`` the power cabling and ``calls["UART"]`` /
    ``calls["JTAG"]`` the console cabling.
    """
    calls = {"steps": []}

    def connect_power(nb, board, **kwargs):
        calls["power"] = kwargs
        return [f"connected b1 power to {kwargs['device']} outlet {kwargs['outlets'][0]}"]

    def connect_console(nb, board, *, kind, **kwargs):
        calls[kind] = kwargs
        return [f"connected b1 {kind} to {kwargs['device']} {kwargs['port']}"]

    monkeypatch.setattr(cli.client, "power_devices", lambda nb, site: list(power_devices))
    monkeypatch.setattr(cli.client, "console_devices", lambda nb, site: list(consoles))
    monkeypatch.setattr(cli.client, "connect_console", connect_console)
    monkeypatch.setattr(cli.client, "device_exists", lambda nb, name, site: name in taken)
    monkeypatch.setattr(cli.client, "connect_power", connect_power)

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
        calls["api"] = api
        return "cookie"

    monkeypatch.setattr(cli.client, "connect", connect)
    monkeypatch.setattr(cli.client, "ensure_schema", lambda nb: None)
    monkeypatch.setattr(cli.client, "create_or_update_device", device)
    monkeypatch.setattr(cli.provision, "check_prerequisites", lambda host: "/usr/bin/lg-exp")
    monkeypatch.setattr(cli.provision, "deploy_exporter", deploy)
    monkeypatch.setattr(cli.provision, "verify_exporter_active", lambda host, name: None)
    monkeypatch.setattr(cli.provision, "missing_power_env", lambda host, power: [])
    monkeypatch.setattr(cli, "resolve_coordinator", lambda coord: coord or "coord:20408")
    monkeypatch.setattr(cli, "_resolve_api", lambda coord: coord.replace(":20408", ":8000"))
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
        ("GitHub Actions runner label", ""),
        ("NetBox site slug", "lab3"),  # typed: a dry run doesn't read NetBox
        ("Power category", "1"),
        ("Power type", "cyberpower"),  # by name
        ("  PDU hostname or IP", "10.0.0.20"),
        ("  Outlet number", "4"),
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


# A soc-ssh board typed in full, credentials included.
_BOARD = [
    ("Board template", "soc-ssh"),
    ("Board name", "b1"),
    ("Carrier board", "zcu102"),
    ("ADI daughter board or chip", "ad9081"),
    ("Boot strategy", ""),
    ("GitHub Actions runner label", ""),
    # NetBox is read from here on (sites, power devices); nothing is written before Proceed?.
    ("NetBox URL", "https://netbox.test"),
    ("NetBox API token", "  tok123  "),  # pasted with stray whitespace
    ("NetBox site slug", "1"),  # lab3, from NetBox's list
]
_SSH = [("Exporter host SSH login", "root@h")]
# No console servers in NetBox at lab3: the serial device is added, named after the exporter host.
_SERIAL = [
    ("Serial device name in NetBox", ""),  # the exporter host, h
    ("  Serial console device", ""),  # the template's /dev/ttyUSB0
]
_TEMPLATE_FIELDS = [
    ("  Board IP address", "10.0.0.5"),
    ("  BOOT.BIN", ""),
    ("  Device tree", ""),
    ("  Kernel image", ""),
    ("  Kuiper release", ""),
    ("  Board Linux SSH password", ""),
    ("  Board Linux SSH username", ""),
    ("\nProceed?", "y"),
    ("Coordinator API username", "admin"),
    ("Coordinator API password", "secret"),
]
_FIELDS = [*_SSH, *_SERIAL, *_TEMPLATE_FIELDS]
_FULL_RUN = [
    *_BOARD,
    # No power devices at lab3 yet, so a new one is described and named.
    ("Power category", "Network PDU"),
    ("Power type", "cyberpower"),
    ("  PDU hostname or IP", "10.0.0.20"),
    ("  Outlet number", "4"),
    ("Power device name in NetBox", ""),  # the suggested cyberpower-10.0.0.20
    *_FIELDS,
]


def test_full_run_through_the_real_prompts(monkeypatch):
    """Credentials too: NetBox's before the site, the coordinator's after Proceed?.

    Hidden ones go through getpass.
    """
    calls = _stub_services(monkeypatch)

    result, prompts = _type_into_real_prompts(monkeypatch, _FULL_RUN)

    assert result.exit_code == 0, result.output
    _assert_asked_in_order(_FULL_RUN, prompts)
    assert calls["url"] == "https://netbox.test"
    assert calls["token"] == "tok123"
    assert "received 6 characters" in result.output
    assert calls["login"] == ("admin", "secret")
    assert calls["tags"]["power-driver"] == "CyberPowerDriver"
    # The new power device is created in NetBox and cabled to the board.
    assert calls["power"] == {
        "site_slug": "lab3",
        "device": "cyberpower-10.0.0.20",
        "settings": {"type": "cyberpower", "address": "10.0.0.20"},
        "outlets": ["4"],
    }
    assert _rows(result.output)("Power in NetBox", "cyberpower-10.0.0.20 outlet 4", "new")
    assert "connected b1 power to cyberpower-10.0.0.20 outlet 4" in result.output
    # The credential questions explain themselves like the others.
    output = " ".join(result.output.split())
    assert "under your user profile in NetBox" in output
    assert "create places" in output


def _with_new_power(conversation):
    """``conversation`` with the questions describing a new CyberPower PDU."""
    i = conversation.index(("Power device name in NetBox", ""))
    return [*conversation[:i], *_NEW_POWER, *conversation[i:]]


_NEW_POWER = [
    ("Power category", "Network PDU"),
    ("Power type", "cyberpower"),
    ("  PDU hostname or IP", "10.0.0.20"),
    ("  Outlet number", "4"),
]


def _pdu(name, settings, *outlets, address=""):
    """A power device in NetBox; each outlet is a name, or (name, what it feeds)."""
    return cli.client.PowerDevice(
        name,
        settings,
        address,
        tuple(cli.client.PowerOutlet(*((o,) if isinstance(o, str) else o)) for o in outlets),
    )


_RACK3 = _pdu(
    "pdu-rack3",
    {"type": "cyberpower", "address": "10.0.0.20"},
    ("1", "zcu102-old PSU1"),
    "2",
    "3",
)


def _rendered(monkeypatch):
    """The template context the exporter config is rendered from, once it is."""
    rendered = {}
    real_render = cli.provision.render_and_validate

    def render(template_path, context, exporter_configs_dir):
        rendered.update(context)
        return real_render(template_path, context, exporter_configs_dir)

    monkeypatch.setattr(cli.provision, "render_and_validate", render)
    return rendered


def test_a_power_device_in_netbox_is_picked_and_configures_the_power(monkeypatch):
    calls = _stub_services(monkeypatch, power_devices=[_RACK3])
    rendered = _rendered(monkeypatch)
    conversation = [
        *_BOARD,
        ("Power device", "pdu-rack3"),
        ("Outlet on pdu-rack3", "1"),  # feeds another board: asked again
        ("Outlet on pdu-rack3", "2"),
        *_FIELDS,
    ]

    result, prompts = _type_into_real_prompts(monkeypatch, conversation)

    assert result.exit_code == 0, result.output
    _assert_asked_in_order(conversation, prompts)  # no type, host or outlet number asked
    row = _rows(result.output)
    assert row("pdu-rack3", "cyberpower", "10.0.0.20", "2 of 3")  # free outlets
    assert row("1", "zcu102-old PSU1")
    assert "already feeds zcu102-old PSU1" in result.output
    assert calls["tags"]["power-driver"] == "CyberPowerDriver"
    assert rendered["power_host"] == "10.0.0.20"
    assert rendered["power_outlet"] == "2"
    assert calls["power"] == {
        "site_slug": "lab3",
        "device": "pdu-rack3",
        "settings": {"type": "cyberpower", "address": "10.0.0.20"},
        "outlets": ["2"],
    }


def test_a_power_device_made_by_hand_is_described_once_with_its_address_offered(monkeypatch):
    hand_made = _pdu("pdu-x", {}, "Outlet 1", "Outlet 2", address="10.0.0.77")
    calls = _stub_services(monkeypatch, power_devices=[hand_made])
    rendered = _rendered(monkeypatch)
    conversation = [
        *_BOARD,
        ("Power device", "pdu-x"),
        ("Power category", "Network PDU"),
        ("Power type", "apc"),
        ("  PDU hostname or IP", ""),  # Enter: its primary IP in NetBox
        ("Outlet on pdu-x", "Outlet 2"),
        ("  Outlet number", ""),  # Enter: the 2 in its name
        *_FIELDS,
    ]

    result, prompts = _type_into_real_prompts(monkeypatch, conversation)

    assert result.exit_code == 0, result.output
    _assert_asked_in_order(conversation, prompts)
    row = _rows(result.output)
    assert row("pdu-x", "not set", "10.0.0.77")
    assert row("Power in NetBox", "b1 power port -> pdu-x Outlet 2")
    assert rendered["power_host"] == "10.0.0.77"
    assert rendered["power_outlet"] == "2"
    assert calls["power"]["settings"] == {"type": "apc", "address": "10.0.0.77"}
    assert calls["power"]["outlets"] == ["Outlet 2"]


def test_an_outlet_not_in_netbox_yet_is_added(monkeypatch):
    calls = _stub_services(monkeypatch, power_devices=[_RACK3])
    rendered = _rendered(monkeypatch)
    conversation = [
        *_BOARD,
        ("Power device", "pdu-rack3"),
        ("Outlet on pdu-rack3", "new"),
        ("  Outlet number", "8"),
        *_FIELDS,
    ]

    result, prompts = _type_into_real_prompts(monkeypatch, conversation)

    assert result.exit_code == 0, result.output
    _assert_asked_in_order(conversation, prompts)
    assert rendered["power_outlet"] == "8"
    assert calls["power"]["outlets"] == ["8"]


def test_a_new_power_device_is_offered_alongside_the_ones_in_netbox(monkeypatch):
    calls = _stub_services(monkeypatch, power_devices=[_RACK3], taken=["bench-switch"])
    conversation = [
        *_BOARD,
        ("Power device", "new"),
        ("Power category", "Smart plug / home automation"),
        ("Power type", "vesync"),
        ("  VeSync outlet name", "zcu102 plug"),
        ("Power device name in NetBox", "bench-switch"),  # another device has it
        ("Power device name in NetBox", ""),  # the suggestion, made a valid name
        *_FIELDS,
    ]

    result, prompts = _type_into_real_prompts(monkeypatch, conversation)

    assert result.exit_code == 0, result.output
    _assert_asked_in_order(conversation, prompts)
    assert "bench-switch is already a device" in " ".join(result.output.split())
    assert calls["power"] == {
        "site_slug": "lab3",
        "device": "vesync-zcu102-plug",
        "settings": {"type": "vesync", "outlet_names": "zcu102 plug"},
        "outlets": [cli.client.SINGLE_OUTLET],
    }


def test_a_single_switch_in_netbox_needs_no_outlet_question(monkeypatch):
    plug = _pdu("vesync-zcu102-plug", {"type": "vesync", "outlet_names": "zcu102 plug"}, "1")
    calls = _stub_services(monkeypatch, power_devices=[plug])
    rendered = _rendered(monkeypatch)
    conversation = [*_BOARD, ("Power device", "vesync-zcu102-plug"), *_FIELDS]

    result, prompts = _type_into_real_prompts(monkeypatch, conversation)

    assert result.exit_code == 0, result.output
    _assert_asked_in_order(conversation, prompts)  # its only outlet is used
    assert rendered["power_outlet"] == "zcu102 plug"
    assert calls["tags"]["power-driver"] == "VesyncPowerDriver"
    assert calls["power"]["device"] == "vesync-zcu102-plug"
    assert calls["power"]["outlets"] == ["1"]


def test_a_netbox_without_sites_stops_before_the_power_questions(monkeypatch, saved_runs):
    _stub_services(monkeypatch)
    monkeypatch.setattr(cli.client, "sites", lambda nb: [])

    result, prompts = _type_into_real_prompts(monkeypatch, _BOARD[:-1])

    assert result.exit_code == 1
    assert "NetBox has no sites" in result.output
    assert not [p for p in prompts if p.startswith(("NetBox site", "Power"))]
    assert "pick b1 to resume" in result.output


def _host(name, *ports, address=""):
    """A device with console server ports; each port is a name or ConsoleServerPort args."""
    return cli.client.ConsoleDevice(
        name,
        address,
        tuple(cli.client.ConsoleServerPort(*((p,) if isinstance(p, str) else p)) for p in ports),
    )


_BY_ID = "/dev/serial/by-id/usb-FTDI_Quad_RS232-HS-if01-port0"
_LAB_HOST = _host(
    "h",
    ("A", _BY_ID),  # path recorded in NetBox
    ("B", "", "zc706-old UART"),  # feeds another board
    ("JTAG 1", "", "zc706-old JTAG", True),  # a JTAG cable: not a serial port
    "ttyUSB2",  # made by hand: no path yet
)


def _serial_run(conversation):
    return [*_BOARD, ("Power device name in NetBox", ""), *_SSH, *conversation, *_TEMPLATE_FIELDS]


def test_the_exporter_host_in_netbox_is_offered_and_its_port_gives_the_serial_path(monkeypatch):
    calls = _stub_services(monkeypatch, consoles=[_LAB_HOST])
    rendered = _rendered(monkeypatch)
    conversation = _serial_run(
        [
            ("Serial device", ""),  # Enter: h, the exporter host
            ("Serial port on h", "B"),  # feeds another board: asked again
            ("Serial port on h", "A"),
        ]
    )

    result, prompts = _type_into_real_prompts(monkeypatch, _with_new_power(conversation))

    assert result.exit_code == 0, result.output
    _assert_asked_in_order(_with_new_power(conversation), prompts)  # no path question
    row = _rows(result.output)
    assert row("h", "2 of 4")  # free ports
    assert not row("JTAG 1", "zc706-old JTAG")  # not offered for the serial console
    assert "h B already feeds zc706-old UART" in result.output
    assert rendered["serial_port"] == _BY_ID
    assert row("Serial in NetBox", "b1 UART -> h A")
    assert calls["UART"] == {"site_slug": "lab3", "device": "h", "port": "A", "path": _BY_ID}


def test_a_port_without_a_path_asks_it_with_its_name_as_the_default(monkeypatch):
    calls = _stub_services(monkeypatch, consoles=[_LAB_HOST])
    rendered = _rendered(monkeypatch)
    conversation = _serial_run(
        [
            ("Serial device", "h"),
            ("Serial port on h", "ttyUSB2"),
            ("  Serial console device", ""),  # Enter: /dev/ttyUSB2
        ]
    )

    result, prompts = _type_into_real_prompts(monkeypatch, _with_new_power(conversation))

    assert result.exit_code == 0, result.output
    _assert_asked_in_order(_with_new_power(conversation), prompts)
    assert rendered["serial_port"] == "/dev/ttyUSB2"
    assert calls["UART"]["path"] == "/dev/ttyUSB2"  # recorded on the port


def test_a_new_port_is_named_after_its_serial_device(monkeypatch):
    by_id = "/dev/serial/by-id/usb-Silicon_Labs_CP2108_Quad_USB_to_UART_Bridge_Controller_0001-if02"
    calls = _stub_services(monkeypatch, consoles=[_LAB_HOST])
    conversation = _serial_run(
        [
            ("Serial device", "h"),
            ("Serial port on h", "new"),
            ("  Serial console device", by_id),
        ]
    )

    result, _ = _type_into_real_prompts(monkeypatch, _with_new_power(conversation))

    assert result.exit_code == 0, result.output
    port = calls["UART"]["port"]
    assert by_id.endswith(port) and len(port) == 64  # NetBox's limit for a port name
    assert calls["UART"]["path"] == by_id


def test_the_exporter_host_is_matched_by_its_address_too(monkeypatch):
    lab_host = _host("lab-host-03", ("A", _BY_ID), address="10.0.0.40")
    calls = _stub_services(monkeypatch, consoles=[lab_host])
    conversation = [
        *_BOARD,
        ("Power device name in NetBox", ""),
        ("Exporter host SSH login", "root@10.0.0.40"),
        ("Serial device", ""),  # Enter: lab-host-03
        ("Serial port on lab-host-03", "A"),
        *_TEMPLATE_FIELDS,
    ]

    result, _ = _type_into_real_prompts(monkeypatch, _with_new_power(conversation))

    assert result.exit_code == 0, result.output
    assert calls["UART"]["device"] == "lab-host-03"


def test_a_run_saved_before_serial_ports_asks_for_the_serial_device_and_redoes_netbox(
    monkeypatch, saved_runs
):
    _stub_services(monkeypatch)
    _fail_deploy(monkeypatch)
    _type_into_real_prompts(monkeypatch, _FULL_RUN)
    path = saved_runs / "b1.json"
    saved = json.loads(path.read_text())
    assert saved["done"] == ["plan", "netbox"]
    for key in ("serial_device", "serial_device_name", "serial_netbox_port"):
        del saved["answers"][key]
    saved["answers"]["field.serial_port"] = ""  # how a template field saved Enter
    path.write_text(json.dumps(saved))
    calls = _stub_services(monkeypatch)
    conversation = [
        ("Resume a saved run", ""),
        ("Use the saved answers", ""),
        ("NetBox URL", ""),
        ("NetBox API token", "tok123"),
        ("Serial device name in NetBox", ""),
        ("\nProceed?", "y"),
        ("Coordinator API username", ""),
        ("Coordinator API password", "secret"),
    ]

    result, prompts = _type_into_real_prompts(monkeypatch, conversation)

    assert result.exit_code == 0, result.output
    _assert_asked_in_order(conversation, prompts)
    assert calls["steps"] == ["netbox", "exporter", "place"]  # the cable is added
    assert calls["UART"]["path"] == "/dev/ttyUSB0"


def test_manual_power_is_not_recorded_in_netbox(monkeypatch):
    calls = _stub_services(monkeypatch)
    conversation = [
        *_BOARD,
        ("Power category", "Other"),
        ("Power type", "manual"),
        *_FIELDS,
    ]

    result, prompts = _type_into_real_prompts(monkeypatch, conversation)

    assert result.exit_code == 0, result.output
    _assert_asked_in_order(conversation, prompts)  # no power device name
    assert "power" not in calls
    assert _rows(result.output)("Power in NetBox", "not recorded")


def test_a_dry_run_does_not_read_netbox(monkeypatch):
    def unreachable(*a, **k):
        raise AssertionError("a dry run must not talk to NetBox")

    for name in ("connect", "sites", "power_devices"):
        monkeypatch.setattr(cli.client, name, unreachable)
    _stub_prompts(monkeypatch, _SOC_SSH)

    result = _invoke(*DRY_RUN)

    assert result.exit_code == 0, result.output
    assert _rows(result.output)("Power in NetBox", "chosen from NetBox when run without --dry-run")


def test_netbox_read_failure_before_the_plan_is_reported_and_answers_kept(monkeypatch, saved_runs):
    import pynetbox

    class _Forbidden:
        status_code, reason, url, text = 403, "Forbidden", "https://nb/api/", ""
        request = type("R", (), {"body": None})()

        def json(self):
            return {"detail": "Invalid authorization header"}

    def forbidden(nb):
        raise pynetbox.RequestError(_Forbidden())

    _stub_services(monkeypatch)
    monkeypatch.setattr(cli.client, "sites", forbidden)

    result, _ = _type_into_real_prompts(monkeypatch, _BOARD)

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "Invalid authorization header" in result.output
    assert "Bearer/Token" in result.output
    assert _saved(saved_runs)["answers"]["runner_label"] == "hw-zcu102"
    assert "pick b1 to resume" in result.output


def test_a_power_cabling_failure_leaves_the_netbox_step_to_do_again(monkeypatch, saved_runs):
    def occupied(nb, board, **kwargs):
        raise RuntimeError("outlet 4 on cyberpower-10.0.0.20 already feeds zc706 PSU1")

    _stub_services(monkeypatch)
    monkeypatch.setattr(cli.client, "connect_power", occupied)

    result, _ = _type_into_real_prompts(monkeypatch, _FULL_RUN)

    assert result.exit_code == 1
    assert "already feeds zc706 PSU1" in result.output
    assert _saved(saved_runs)["done"] == ["plan"]


def test_resuming_a_run_saved_before_power_devices_asks_only_for_the_power_device(
    monkeypatch, saved_runs
):
    """Runs saved by an earlier version have every answer but the NetBox power device."""
    _stub_prompts(monkeypatch, _SOC_SSH)
    _invoke(*DRY_RUN)
    path = saved_runs / "b1.json"
    old = json.loads(path.read_text())
    assert not [k for k in old["answers"] if k.startswith("power_device")]
    calls = _stub_services(monkeypatch)
    rendered = _rendered(monkeypatch)
    conversation = [
        ("Resume a saved run", ""),
        ("Use the saved answers", ""),
        ("NetBox URL", "https://netbox.test"),
        ("NetBox API token", "tok123"),
        ("Power device name in NetBox", ""),
        ("Serial device name in NetBox", ""),  # its path was answered in the dry run
        ("\nProceed?", "y"),
        ("Coordinator API username", "admin"),
        ("Coordinator API password", "secret"),
    ]

    result, prompts = _type_into_real_prompts(monkeypatch, conversation)

    assert result.exit_code == 0, result.output
    _assert_asked_in_order(conversation, prompts)  # NetBox asked once, before the plan
    assert calls["power"]["device"] == "cyberpower-10.0.0.20"
    assert calls["steps"] == ["netbox", "exporter", "place"]
    # Enter in the dry run meant the template's default, not an empty path.
    assert rendered["serial_port"] == "/dev/ttyUSB0"
    assert calls["UART"] == {
        "site_slug": "lab3",
        "device": "h",
        "port": "ttyUSB0",
        "path": "/dev/ttyUSB0",
    }


def test_answers_taken_from_netbox_are_saved_so_a_resume_does_not_ask_them(monkeypatch, saved_runs):
    _stub_services(monkeypatch, power_devices=[_RACK3])
    _fail_deploy(monkeypatch)
    conversation = [
        *_BOARD,
        ("Power device", "pdu-rack3"),
        ("Outlet on pdu-rack3", "2"),
        *_FIELDS,
    ]
    _type_into_real_prompts(monkeypatch, conversation)  # stops at the exporter step

    answers = _saved(saved_runs)["answers"]
    assert answers["power_device"] == "pdu-rack3"
    assert answers["power_netbox_outlet"] == "2"
    assert answers["power"] == "cyberpower"
    assert answers["power.power_host"] == "10.0.0.20"
    assert answers["power.power_outlet"] == "2"

    calls = _stub_services(monkeypatch, power_devices=[_RACK3])
    result, prompts = _type_into_real_prompts(monkeypatch, _RESUME_TO_COORDINATOR)

    assert result.exit_code == 0, result.output
    _assert_asked_in_order(_RESUME_TO_COORDINATOR, prompts)
    assert calls["steps"] == ["exporter", "place"]


def test_a_saved_new_power_device_without_its_name_asks_for_it(monkeypatch, saved_runs):
    _stub_prompts(monkeypatch, _SOC_SSH)
    _invoke(*DRY_RUN)
    path = saved_runs / "b1.json"
    saved = json.loads(path.read_text())
    saved["answers"]["power_device"] = "new"
    path.write_text(json.dumps(saved))
    calls = _stub_services(monkeypatch, taken=["cyberpower-10.0.0.20"])
    conversation = [
        ("Resume a saved run", ""),
        ("Use the saved answers", ""),
        ("NetBox URL", "https://netbox.test"),  # read before the plan, to check the name
        ("NetBox API token", "tok123"),
        ("Power device name in NetBox", ""),  # the suggestion is taken
        ("Power device name in NetBox", "pdu-bench"),
        ("Serial device name in NetBox", ""),
        ("\nProceed?", "y"),
        ("Coordinator API username", "admin"),
        ("Coordinator API password", "secret"),
    ]

    result, prompts = _type_into_real_prompts(monkeypatch, conversation)

    assert result.exit_code == 0, result.output
    _assert_asked_in_order(conversation, prompts)
    assert calls["power"]["device"] == "pdu-bench"


def test_a_saved_site_netbox_does_not_have_is_asked_again(monkeypatch, saved_runs):
    _stub_prompts(monkeypatch, {**_SOC_SSH, "NetBox site slug": "lab9"})
    _invoke(*DRY_RUN)
    calls = _stub_services(monkeypatch)
    conversation = [
        ("Resume a saved run", ""),
        ("Use the saved answers", ""),
        ("NetBox URL", "https://netbox.test"),
        ("NetBox API token", "tok123"),
        ("NetBox site slug", "lab4"),
        ("Power device name in NetBox", ""),
        ("Serial device name in NetBox", ""),
        ("\nProceed?", "y"),
        ("Coordinator API username", "admin"),
        ("Coordinator API password", "secret"),
    ]

    result, prompts = _type_into_real_prompts(monkeypatch, conversation)

    assert result.exit_code == 0, result.output
    _assert_asked_in_order(conversation, prompts)
    assert calls["power"]["site_slug"] == "lab4"


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


def _fail_deploy(monkeypatch):
    def deploy(*args, **kwargs):
        raise RuntimeError("failed to install/start labgrid-exporter-b1 on h: permission denied")

    monkeypatch.setattr(cli.provision, "deploy_exporter", deploy)


def _saved(saved_runs, name="b1"):
    return json.loads((saved_runs / f"{name}.json").read_text())


def test_a_failed_run_keeps_its_answers_but_not_the_credentials(monkeypatch, saved_runs):
    _stub_services(monkeypatch)
    _fail_deploy(monkeypatch)

    result, _ = _type_into_real_prompts(monkeypatch, _FULL_RUN)

    assert result.exit_code == 1
    path = saved_runs / "b1.json"
    saved = _saved(saved_runs)
    assert saved["answers"]["site_slug"] == "lab3"
    assert saved["answers"]["ssh_target"] == "root@h"
    assert saved["answers"]["netbox_url"] == "https://netbox.test"
    assert saved["done"] == ["plan", "netbox"]  # the exporter step failed
    assert "tok123" not in path.read_text()
    assert "secret" not in path.read_text()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert f"Answers saved to {path}" in result.output
    assert "pick b1 to resume" in result.output


def test_resume_goes_straight_to_the_plan_and_skips_finished_steps(monkeypatch, saved_runs):
    _stub_services(monkeypatch)
    _fail_deploy(monkeypatch)
    _type_into_real_prompts(monkeypatch, _FULL_RUN)
    calls = _stub_services(monkeypatch)  # the exporter host is fixed now
    conversation = [
        ("Resume a saved run", ""),  # the most recent: b1
        ("Use the saved answers", ""),  # as they are
        ("\nProceed?", "y"),
        ("Coordinator API username", ""),  # Enter: the saved one
        ("Coordinator API password", "secret"),  # never saved
    ]

    result, prompts = _type_into_real_prompts(monkeypatch, conversation)

    assert result.exit_code == 0, result.output
    _assert_asked_in_order(conversation, prompts)
    row = _rows(result.output)
    assert row("b1", "soc-ssh", "NetBox device done")
    assert row("NetBox site slug", "lab3")
    assert row("Board Linux SSH password", "(default)")
    assert "NetBox device: done in an earlier run" in result.output
    assert calls["steps"] == ["exporter", "place"]  # no second NetBox update
    assert calls["login"] == ("admin", "secret")
    assert not saved_runs.exists() or not list(saved_runs.iterdir())  # finished: nothing to resume


def _netbox_down(nb):
    raise RuntimeError("could not reach NetBox at https://netbox.test")


def test_resume_asks_again_for_the_netbox_url_and_coordinator_login(monkeypatch, saved_runs):
    """A wrong URL or login is what most often stops a run, so resume lets you fix it."""
    _stub_services(monkeypatch)
    monkeypatch.setattr(cli.client, "ensure_schema", _netbox_down)
    _type_into_real_prompts(monkeypatch, _FULL_RUN)
    calls = _stub_services(monkeypatch)
    conversation = [
        ("Resume a saved run", ""),
        ("Use the saved answers", ""),
        ("\nProceed?", "y"),
        ("NetBox URL", "https://netbox.fixed.test"),
        ("NetBox API token", "tok123"),
        ("Coordinator API username", ""),
        ("Coordinator API password", "secret"),
    ]

    result, prompts = _type_into_real_prompts(monkeypatch, conversation)

    assert result.exit_code == 0, result.output
    _assert_asked_in_order(conversation, prompts)
    assert "(https://netbox.test):" in result.output  # the saved URL is the default
    assert calls["url"] == "https://netbox.fixed.test"
    assert calls["login"] == ("admin", "secret")
    assert calls["steps"] == ["netbox", "exporter", "place"]


def _fail_coordinator_login(monkeypatch):
    def login(api, user, password):
        raise RuntimeError(f"login to http://{api}/api/auth/login failed: 401")

    monkeypatch.setattr(cli.coord_mod, "login", login)


_RESUME_TO_COORDINATOR = [
    ("Resume a saved run", ""),
    ("Use the saved answers", ""),
    ("\nProceed?", "y"),
    ("Coordinator API username", ""),
    ("Coordinator API password", "secret"),
]


def test_resume_uses_the_coordinator_the_saved_run_used(monkeypatch, saved_runs):
    """The exporter it deployed points at that coordinator; --coord isn't given again."""
    _stub_services(monkeypatch)
    _fail_coordinator_login(monkeypatch)
    _type_into_real_prompts(monkeypatch, _FULL_RUN, "--coord", "lab-coord:20408")
    calls = _stub_services(monkeypatch)

    result, prompts = _type_into_real_prompts(monkeypatch, _RESUME_TO_COORDINATOR)

    assert result.exit_code == 0, result.output
    _assert_asked_in_order(_RESUME_TO_COORDINATOR, prompts)
    assert calls["api"] == "lab-coord:8000"
    assert calls["steps"] == ["place"]  # NetBox and the exporter were done in the first run


def test_another_coordinator_runs_every_step_again(monkeypatch, saved_runs):
    _stub_services(monkeypatch)
    _fail_coordinator_login(monkeypatch)
    _type_into_real_prompts(monkeypatch, _FULL_RUN, "--coord", "lab-coord:20408")
    calls = _stub_services(monkeypatch)
    conversation = [
        *_RESUME_TO_COORDINATOR[:3],
        ("NetBox URL", ""),  # the saved one
        ("NetBox API token", "tok123"),
        *_RESUME_TO_COORDINATOR[3:],
    ]

    result, prompts = _type_into_real_prompts(
        monkeypatch, conversation, "--coord", "other-coord:20408"
    )

    assert result.exit_code == 0, result.output
    _assert_asked_in_order(conversation, prompts)
    assert calls["api"] == "other-coord:8000"
    assert calls["steps"] == ["netbox", "exporter", "place"]


def test_review_asks_each_question_again_with_the_saved_answer_as_default(monkeypatch, saved_runs):
    _stub_prompts(monkeypatch, _SOC_SSH)
    _invoke(*DRY_RUN)
    # Only the site changes; every other question is answered by its default,
    # which the stub can only do if it is the saved answer.
    asked = _stub_prompts(
        monkeypatch,
        {"Resume a saved run": "b1", "Use the saved answers": "review", "NetBox site slug": "lab4"},
    )

    result = _invoke(*DRY_RUN)

    assert result.exit_code == 0, result.output
    assert asked.kwargs["Board name (e.g. zcu102-ad9081-lab3)"]["default"] == "b1"
    assert asked.kwargs["PDU hostname or IP"]["default"] == "10.0.0.20"
    assert "b1 (site lab4)" in result.output
    assert _saved(saved_runs)["answers"]["site_slug"] == "lab4"


def test_a_changed_answer_reruns_the_steps_it_had_finished(monkeypatch, saved_runs):
    monkeypatch.setattr(cli.Confirm, "ask", staticmethod(lambda *a, **k: True))
    args = ["add-hardware", "--exporter-configs-dir", str(EXPORTER_CONFIGS_DIR), *CREDENTIALS]
    _stub_prompts(monkeypatch, _SOC_SSH)
    _stub_services(monkeypatch)
    _fail_deploy(monkeypatch)
    _invoke(*args)
    _stub_prompts(
        monkeypatch,
        {"Resume a saved run": "b1", "Use the saved answers": "review", "NetBox site slug": "lab4"},
    )
    calls = _stub_services(monkeypatch)

    result = _invoke(*args)

    assert result.exit_code == 0, result.output
    assert calls["steps"] == ["netbox", "exporter", "place"]


def test_a_saved_optional_answer_can_be_cleared_in_review(monkeypatch, saved_runs):
    _stub_prompts(monkeypatch, {**_SOC_SSH, "  BOOT.BIN": "release:zynq/BOOT.BIN"})
    _invoke(*DRY_RUN)
    asked = _stub_prompts(
        monkeypatch,
        {"Resume a saved run": "b1", "Use the saved answers": "review", "  BOOT.BIN": "-"},
    )
    rendered = {}
    real_render = cli.provision.render_and_validate

    def render(template_path, context, exporter_configs_dir):
        rendered.update(context)
        return real_render(template_path, context, exporter_configs_dir)

    monkeypatch.setattr(cli.provision, "render_and_validate", render)

    result = _invoke(*DRY_RUN)

    assert result.exit_code == 0, result.output
    bootbin = next(p for p in asked if p.startswith("  BOOT.BIN"))
    assert "Enter for release:zynq/BOOT.BIN, - to leave unset" in bootbin
    assert "kuiper_bootbin" not in rendered  # unset again, so the template's null applies


def test_a_dry_run_saves_its_answers_to_resume_from(monkeypatch, saved_runs):
    _stub_prompts(monkeypatch, _SOC_SSH)

    result = _invoke(*DRY_RUN)

    assert result.exit_code == 0, result.output
    assert _saved(saved_runs)["done"] == ["plan"]
    assert f"Answers saved to {saved_runs / 'b1.json'}" in result.output


def test_unreadable_saved_answers_are_ignored(monkeypatch, saved_runs):
    saved_runs.mkdir(parents=True)
    (saved_runs / "b0.json").write_text("{truncated")
    asked = _stub_prompts(monkeypatch, _SOC_SSH)

    result = _invoke(*DRY_RUN)

    assert result.exit_code == 0, result.output
    assert not [p for p in asked if p.startswith("Resume")]


def test_new_starts_over_and_keeps_the_saved_run(monkeypatch, saved_runs):
    _stub_prompts(monkeypatch, _SOC_SSH)
    _invoke(*DRY_RUN)
    asked = _stub_prompts(
        monkeypatch, {**_SOC_SSH, "Resume a saved run": "new", "Board name": "b2"}
    )

    result = _invoke(*DRY_RUN)

    assert result.exit_code == 0, result.output
    assert asked.kwargs["Board name (e.g. zcu102-ad9081-lab3)"].get("default") is None
    assert sorted(p.name for p in saved_runs.iterdir()) == ["b1.json", "b2.json"]


def test_options_win_over_saved_answers(monkeypatch, saved_runs):
    def netbox_down(nb):
        raise RuntimeError("NetBox is down")

    _stub_services(monkeypatch)
    monkeypatch.setattr(cli.client, "ensure_schema", netbox_down)
    _type_into_real_prompts(monkeypatch, _FULL_RUN)  # saves netbox_url https://netbox.test
    calls = _stub_services(monkeypatch)
    conversation = [
        ("Resume a saved run", ""),
        ("Use the saved answers", ""),
        ("\nProceed?", "y"),
        ("NetBox API token", "tok123"),
        ("Coordinator API username", ""),
        ("Coordinator API password", "secret"),
    ]

    result, prompts = _type_into_real_prompts(
        monkeypatch, conversation, "--netbox-url", "https://other.test"
    )

    assert result.exit_code == 0, result.output
    _assert_asked_in_order(conversation, prompts)
    assert calls["url"] == "https://other.test"


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

    _stub_prompts(monkeypatch, _SOC_SSH)
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


def test_a_pasted_bearer_header_is_reduced_to_the_token(monkeypatch):
    """NetBox shows "Bearer nbt_..." as the header to send; pynetbox adds the keyword itself."""
    seen = {}

    def connect(url, token, **kwargs):
        seen["token"] = token
        return object()

    result, asked = _run_until_netbox(
        monkeypatch,
        ["--netbox-url", "https://nb", "--coord-user", "u", "--coord-password", "p"],
        {"NetBox API token": "Bearer nbt_abc123.s3cret"},
        connect=connect,
    )

    assert seen == {"token": "nbt_abc123.s3cret"}
    assert "Bearer" in result.output and "removed" in result.output


def test_an_unusable_token_is_asked_for_again(monkeypatch):
    seen = {}

    def connect(url, token, **kwargs):
        seen["token"] = token
        return object()

    result, asked = _run_until_netbox(
        monkeypatch,
        ["--netbox-url", "https://nb", "--coord-user", "u", "--coord-password", "p"],
        {"NetBox API token": ["nbt_abc123", "nbt_abc123 s3cret", "nbt_abc123.s3cret"]},
        connect=connect,
    )

    assert seen == {"token": "nbt_abc123.s3cret"}
    assert sum(p.startswith("NetBox API token") for p in asked) == 3
    assert "only the key" in result.output


def test_a_bad_netbox_token_option_fails_before_any_question(monkeypatch):
    asked = _stub_prompts(monkeypatch, {})

    result = _invoke(
        "add-hardware",
        "--exporter-configs-dir",
        str(EXPORTER_CONFIGS_DIR),
        "--netbox-token",
        "nbt_abc123 s3cret",
    )

    assert result.exit_code == 1
    assert asked == []
    assert "--netbox-token / NETBOX_TOKEN" in result.output
    assert "space" in result.output


def test_netbox_token_option_is_cleaned_too(monkeypatch):
    monkeypatch.setenv("NETBOX_TOKEN", "Bearer nbt_abc123.s3cret")
    seen = {}

    def connect(url, token, **kwargs):
        seen["token"] = token
        return object()

    _run_until_netbox(
        monkeypatch,
        ["--netbox-url", "https://nb", "--coord-user", "u", "--coord-password", "p"],
        connect=connect,
    )

    assert seen == {"token": "nbt_abc123.s3cret"}


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
