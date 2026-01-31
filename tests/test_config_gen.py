import os
from unittest.mock import patch

import yaml
from click.testing import CliRunner

from adi_lg_plugins.tools.cli import cli


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
