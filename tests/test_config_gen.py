import getpass
import json
import os
import stat
import sys
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner
from rich.prompt import Confirm, IntPrompt, Prompt

from adi_lg_plugins.tools import config_gen
from adi_lg_plugins.tools.cli import cli


@pytest.fixture(autouse=True)
def saved_runs(monkeypatch, tmp_path):
    """Keep saved answers out of the real ~/.cache; returns where they go."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return tmp_path / "cache" / "adi-lg" / "generate-config"


def test_generate_config_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["generate-config", "--help"])
    assert result.exit_code == 0
    assert "Interactive tool to generate Labgrid YAML configuration" in result.output


@patch("adi_lg_plugins.tools.config_gen.scan_serial_ports")
@patch("adi_lg_plugins.tools.config_gen.Prompt.ask")
@patch("adi_lg_plugins.tools.config_gen.IntPrompt.ask")
@patch("adi_lg_plugins.tools.config_gen.Confirm.ask")
def test_generate_config_soc(mock_confirm, mock_int, mock_prompt, mock_scan):
    runner = CliRunner()

    # Mock System Discovery
    mock_scan.return_value = [("/dev/ttyUSB0", "Test Device")]

    # Define inputs
    # Strategy -> Target -> Power -> Shell -> SDMux -> MassStorage -> Kuiper -> ImageWriter -> Output

    # Prompt.ask calls:
    # 1. Select Strategy
    # 2. Target Name
    # 3. Select Power Driver
    # 4. Outlet Names
    # 5. Username (VeSync)
    # 6. Password (VeSync)
    # 7. Select Serial Port
    # 8. Prompt Regex
    # 9. Login Prompt
    # 10. Username (Shell)
    # 11. Password (Shell)
    # 12. SD Mux Path
    # 13. Block Device Path
    # 14. Default Release
    # 15. Cache Directory
    # 16. USB Device Path (ImageWriter - ONLY if confirmed)
    # 17. Output Filename

    mock_prompt.side_effect = [
        "BootFPGASoC",  # Strategy
        "zcu102",  # Target
        "VesyncPowerDriver",  # Power Driver
        "outlet1",  # Outlet Names
        "user",  # VeSync User
        "pass",  # VeSync Pass
        "/dev/ttyUSB0",  # Serial Port
        "root#",  # Shell Prompt
        "login:",  # Login Prompt
        "root",  # Shell User
        "analog",  # Shell Pass
        "/dev/mux",  # SD Mux
        "/dev/sdb",  # Block Device
        "2023_R2",  # Release
        "/tmp/cache",  # Cache
        # Image Writer path only if confirmed. Let's say False for Confirm.
        "config_zcu102.yaml",  # Output
    ]

    # IntPrompt.ask calls:
    # 1. Delay (Power)
    # 2. Baud Rate
    # 3. Partition
    mock_int.side_effect = [
        5,  # Power Delay
        115200,  # Baud
        1,  # Partition
    ]

    # Confirm.ask calls:
    # 1. Enable Image Writer
    mock_confirm.side_effect = [
        False  # Image Writer
    ]

    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["generate-config"])

        assert result.exit_code == 0, result.output
        assert "Configuration generated: config_zcu102.yaml" in result.output
        assert os.path.exists("config_zcu102.yaml")

        with open("config_zcu102.yaml") as f:
            config = yaml.safe_load(f)

        target = config["targets"]["zcu102"]
        drivers = target["drivers"]
        resources = target["resources"]

        # Verify Drivers
        assert "BootFPGASoC" in drivers
        assert "VesyncPowerDriver" in drivers
        assert "SerialDriver" in drivers
        assert "ADIShellDriver" in drivers
        assert "USBSDMuxDriver" in drivers
        assert "MassStorageDriver" in drivers
        assert "KuiperDLDriver" in drivers

        # Verify Resources
        assert resources["VesyncOutlet"]["username"] == "user"
        assert resources["SerialPort"]["port"] == "/dev/ttyUSB0"
        assert resources["SerialPort"]["speed"] == 115200
        assert resources["KuiperRelease"]["release"] == "2023_R2"


@patch("adi_lg_plugins.tools.config_gen.scan_serial_ports")
@patch("adi_lg_plugins.tools.config_gen.get_local_ip")
@patch("adi_lg_plugins.tools.config_gen.Prompt.ask")
@patch("adi_lg_plugins.tools.config_gen.IntPrompt.ask")
@patch("adi_lg_plugins.tools.config_gen.Confirm.ask")
def test_generate_config_tftp(mock_confirm, mock_int, mock_prompt, mock_ip, mock_scan):
    runner = CliRunner()

    mock_scan.return_value = [("/dev/ttyUSB0", "Test Device")]
    mock_ip.return_value = "10.0.0.5"

    # Strategy -> Target -> Power -> Shell -> TFTP -> Kuiper -> SSH (Optional) -> Output

    mock_prompt.side_effect = [
        "BootFPGASoCTFTP",  # Strategy
        "tftp_target",  # Target
        "CyberPowerDriver",  # Power
        "192.168.1.100",  # PDU IP
        "/dev/ttyUSB0",  # Serial
        "root#",  # Prompt
        "login:",  # Login
        "root",  # User
        "analog",  # Pass
        # TFTP Managed
        "10.0.0.5",  # Bind Addr
        "/var/lib/tftpboot",  # Root
        # Kuiper
        "2023_R2",
        "/tmp/cache",
        # SSH (Optional) - Confirm True
        "10.0.0.6",  # SSH IP
        "config_tftp.yaml",  # Output
    ]

    mock_int.side_effect = [
        3,  # Outlet Num
        5,  # Delay
        115200,  # Baud
        3069,  # TFTP Port
    ]

    mock_confirm.side_effect = [
        True,  # Managed TFTP
        True,  # Configure SSH
    ]

    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["generate-config"])

        assert result.exit_code == 0, result.output

        with open("config_tftp.yaml") as f:
            config = yaml.safe_load(f)

        target = config["targets"]["tftp_target"]
        drivers = target["drivers"]
        resources = target["resources"]

        assert "BootFPGASoCTFTP" in drivers
        assert "TFTPServerDriver" in drivers
        assert "SSHDriver" in drivers
        assert "CyberPowerDriver" in drivers

        assert resources["TFTPServerResource"]["port"] == 3069
        assert resources["NetworkService"]["address"] == "10.0.0.6"


# A BootFPGASoC config with a VeSync outlet, typed into the real prompts.
_SOC = [
    ("Select Strategy", "BootFPGASoC"),
    ("Target Name", "zcu102"),
    ("Select Power Driver", "VesyncPowerDriver"),
    ("Outlet Names", "ZCU102"),
    ("VeSync Username", "user@example.com"),
    ("VeSync Password", "vesync-secret"),
    ("Power Cycle Delay", ""),
    ("Select Serial Port", "1"),
    ("Baud Rate", ""),
    ("Shell Prompt Regex", ""),
    ("Login Prompt Regex", ""),
    ("Username", ""),
    ("Password", ""),
    ("SD Mux Device Path", "/dev/sg0"),
    ("Block Device Path", "/dev/disk/by-label/BOOT"),
    ("Partition Number", ""),
    ("Default Release Version", ""),
    ("Cache Directory", ""),
    ("Enable Image Writer", "n"),
    ("Output Filename", ""),
]
# Stopped (input ran out) at the baud rate.
_INTERRUPTED = _SOC[: [q for q, _ in _SOC].index("Baud Rate")]


def _type(monkeypatch, conversation, ports=(("/dev/ttyUSB0", "FTDI"),)):
    """Run generate-config, typing ``conversation``'s answers; returns the result and prompts."""
    monkeypatch.setattr(config_gen, "scan_serial_ports", lambda: list(ports))
    monkeypatch.setattr(
        getpass, "getpass", lambda prompt="", stream=None: sys.stdin.readline().rstrip("\n")
    )
    prompts = []
    for cls in (Prompt, IntPrompt, Confirm):

        def spy(prompt, *a, _real_ask=cls.ask, **k):
            prompts.append((str(prompt), k.get("default")))
            return _real_ask(prompt, *a, **k)

        monkeypatch.setattr(cls, "ask", staticmethod(spy))
    result = CliRunner().invoke(
        cli, ["generate-config"], input="".join(f"{answer}\n" for _, answer in conversation)
    )
    return result, prompts


def _asked(prompts):
    return [p for p, _ in prompts]


def _assert_asked_in_order(conversation, prompts):
    assert [q for q, _ in conversation] == [
        next((q for q, _ in conversation if p.startswith(q)), p) for p in _asked(prompts)
    ]


def _straight_through(monkeypatch, tmp_path):
    """The config a run typed in one go writes."""
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        result, _ = _type(monkeypatch, _SOC)
        assert result.exit_code == 0, result.output
        return yaml.safe_load(open("config_zcu102.yaml"))
    finally:
        os.chdir(cwd)


def test_an_interrupted_run_keeps_its_answers_but_not_the_vesync_password(monkeypatch, saved_runs):
    with CliRunner().isolated_filesystem():
        result, _ = _type(monkeypatch, _INTERRUPTED)

    assert result.exit_code == 1
    path = saved_runs / "zcu102.json"
    answers = json.loads(path.read_text())["answers"]
    assert answers["strategy"] == "BootFPGASoC"
    assert answers["vesync.username"] == "user@example.com"
    assert answers["serial_port"] == "/dev/ttyUSB0"
    assert "vesync-secret" not in path.read_text()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert f"Answers saved to {path}" in result.output
    assert "run `adi-lg generate-config` again and pick zcu102 to resume" in result.output


def test_resume_asks_only_what_is_missing_and_writes_the_same_config(
    monkeypatch, saved_runs, tmp_path
):
    expected = _straight_through(monkeypatch, tmp_path)
    with CliRunner().isolated_filesystem():
        _type(monkeypatch, _INTERRUPTED)
        conversation = [
            ("Resume a saved run", ""),
            ("Use the saved answers", ""),
            ("VeSync Password", "vesync-secret"),  # never saved
            *_SOC[len(_INTERRUPTED) :],
        ]

        result, prompts = _type(monkeypatch, conversation)

        assert result.exit_code == 0, result.output
        _assert_asked_in_order(conversation, prompts)
        assert "zcu102" in result.output and "BootFPGASoC" in result.output  # the saved run listed
        assert yaml.safe_load(open("config_zcu102.yaml")) == expected
    assert not list(saved_runs.iterdir())  # written: nothing left to resume


def test_a_file_that_cannot_be_written_is_asked_for_again_on_resume(monkeypatch, saved_runs):
    with CliRunner().isolated_filesystem():
        failed, _ = _type(monkeypatch, [*_SOC[:-1], ("Output Filename", "no/such/dir/c.yaml")])
        conversation = [
            ("Resume a saved run", ""),
            ("Use the saved answers", ""),
            ("VeSync Password", "vesync-secret"),
            ("Output Filename", "c.yaml"),
        ]

        result, prompts = _type(monkeypatch, conversation)

        assert result.exit_code == 0, result.output
        assert os.path.exists("c.yaml")
    assert failed.exit_code == 1
    assert "could not write no/such/dir/c.yaml" in failed.output
    assert "Traceback" not in failed.output
    assert "pick zcu102 to resume" in failed.output
    _assert_asked_in_order(conversation, prompts)
    assert prompts[-1] == ("Output Filename", "no/such/dir/c.yaml")  # the saved name, to fix


def test_review_asks_again_with_the_saved_answers_as_defaults(monkeypatch, saved_runs):
    with CliRunner().isolated_filesystem():
        _type(monkeypatch, _INTERRUPTED)
        # The saved serial port is no longer plugged in; Enter must still keep it.
        conversation = [
            ("Resume a saved run", ""),
            ("Use the saved answers", "review"),
            *((q, "") for q, _ in _INTERRUPTED if q != "VeSync Password"),
            *_SOC[len(_INTERRUPTED) :],
        ]
        conversation.insert(conversation.index(("VeSync Username", "")) + 1, _SOC[5])

        result, prompts = _type(monkeypatch, conversation, ports=[("/dev/ttyACM0", "other")])

        assert result.exit_code == 0, result.output
        _assert_asked_in_order(conversation, prompts)
        defaults = dict(prompts)
        assert defaults["Target Name"] == "zcu102"
        assert defaults["Outlet Names (comma separated)"] == "ZCU102"
        assert defaults["Select Serial Port"] == "/dev/ttyUSB0"
        config = yaml.safe_load(open("config_zcu102.yaml"))
    assert config["targets"]["zcu102"]["resources"]["SerialPort"]["port"] == "/dev/ttyUSB0"


def test_new_starts_over(monkeypatch, saved_runs):
    with CliRunner().isolated_filesystem():
        _type(monkeypatch, _INTERRUPTED)

        conversation = [("Resume a saved run", "new"), *_SOC]

        result, prompts = _type(monkeypatch, conversation)

        assert result.exit_code == 0, result.output
        _assert_asked_in_order(conversation, prompts)
        assert dict(prompts)["Target Name"] == "main"  # not the saved zcu102
