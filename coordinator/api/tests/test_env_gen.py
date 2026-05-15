"""Unit tests for the env-yaml generator — pure function, no FastAPI."""

import pytest
import yaml

from app.env_gen import generate_env_yaml
from app.models import PlaceModel, ResourceMatchModel, ResourceModel


def _place(name="test", matches=None):
    return PlaceModel(
        name=name,
        matches=matches or [ResourceMatchModel(exporter="lab", group="tlab", cls="*")],
    )


def _res(cls, name=None, params=None):
    return ResourceModel(
        exporter="lab",
        group="tlab",
        cls=cls,
        name=name or cls,
        params=params or {},
        avail=True,
    )


SOC_RESOURCES = [
    _res("NetworkSerialPort"),
    _res("VesyncOutlet"),
    _res("NetworkUSBSDMuxDevice"),
    _res("NetworkUSBMassStorage", params={"path": "/dev/disk/by-partuuid/a22286d2-01"}),
    _res("KuiperRelease"),
]

FABRIC_RESOURCES = [
    _res("NetworkSerialPort"),
    _res("VesyncOutlet"),
    _res("XilinxDeviceJTAG"),
    _res("XilinxVivadoTool"),
]

# SSH-boot variant: NetworkService + power outlet + Kuiper, no SD-mux/mass-storage.
SOC_SSH_RESOURCES = [
    _res("NetworkSerialPort"),
    _res("NetworkService", params={"address": "10.0.0.50", "username": "root"}),
    _res("HomeAssistantOutlet"),
    _res("KuiperRelease"),
]

SERIAL_ONLY = [_res("NetworkSerialPort")]


class TestShellTier:
    def test_contains_only_remote_place_and_shell_drivers(self):
        out = generate_env_yaml(_place(), SOC_RESOURCES, "shell")
        doc = yaml.safe_load(out)
        drivers = doc["targets"]["main"]["drivers"]
        assert "SerialDriver" in drivers
        assert "ADIShellDriver" in drivers
        assert len(drivers) == 2
        assert doc["targets"]["main"]["resources"]["RemotePlace"]["name"] == "test"

    def test_no_strategy_block(self):
        out = generate_env_yaml(_place(), SOC_RESOURCES, "shell")
        doc = yaml.safe_load(out)
        drivers = doc["targets"]["main"]["drivers"]
        assert "BootFPGASoC" not in drivers
        assert "BootFabric" not in drivers


class TestDriversTier:
    def test_one_driver_per_resource_kind(self):
        out = generate_env_yaml(_place(), SOC_RESOURCES, "drivers")
        doc = yaml.safe_load(out)
        drivers = doc["targets"]["main"]["drivers"]
        assert "SerialDriver" in drivers
        assert "ADIShellDriver" in drivers
        assert "VesyncPowerDriver" in drivers
        assert "USBSDMuxDriver" in drivers
        assert "MassStorageDriver" in drivers
        assert "KuiperDLDriver" in drivers

    def test_no_strategy(self):
        out = generate_env_yaml(_place(), SOC_RESOURCES, "drivers")
        doc = yaml.safe_load(out)
        drivers = doc["targets"]["main"]["drivers"]
        assert "BootFPGASoC" not in drivers

    def test_mass_storage_picks_up_partition_from_params(self):
        out = generate_env_yaml(_place(), SOC_RESOURCES, "drivers")
        doc = yaml.safe_load(out)
        ms = doc["targets"]["main"]["drivers"]["MassStorageDriver"]
        assert ms["partition"] == "/dev/disk/by-partuuid/a22286d2-01"


class TestBootTierSoC:
    def test_infers_boot_fpga_soc(self):
        out = generate_env_yaml(_place(), SOC_RESOURCES, "boot")
        doc = yaml.safe_load(out)
        drivers = doc["targets"]["main"]["drivers"]
        assert "BootFPGASoC" in drivers
        assert drivers["BootFPGASoC"]["reached_linux_marker"] == "analog"
        assert drivers["BootFPGASoC"]["wait_for_linux_prompt_timeout"] == 180

    def test_shell_defaults_for_soc(self):
        out = generate_env_yaml(_place(), SOC_RESOURCES, "boot")
        doc = yaml.safe_load(out)
        shell = doc["targets"]["main"]["drivers"]["ADIShellDriver"]
        assert shell["login_prompt"] == "analog login: "
        assert shell["prompt"] == "root@.*"


class TestBootTierSoCSSH:
    def test_infers_boot_fpga_soc_ssh(self):
        out = generate_env_yaml(_place(), SOC_SSH_RESOURCES, "boot")
        doc = yaml.safe_load(out)
        drivers = doc["targets"]["main"]["drivers"]
        assert "BootFPGASoCSSH" in drivers
        assert "BootFPGASoC" not in drivers
        assert drivers["BootFPGASoCSSH"]["reached_linux_marker"] == "analog"

    def test_includes_ssh_and_power_drivers(self):
        out = generate_env_yaml(_place(), SOC_SSH_RESOURCES, "boot")
        doc = yaml.safe_load(out)
        drivers = doc["targets"]["main"]["drivers"]
        # Strategy bindings: power (PowerProtocol), shell (ADIShellDriver),
        # ssh (SSHDriver), kuiper (KuiperDLDriver).
        assert "SSHDriver" in drivers
        assert "HomeAssistantPowerDriver" in drivers
        assert "KuiperDLDriver" in drivers
        assert "ADIShellDriver" in drivers

    def test_shell_defaults_for_soc_ssh(self):
        out = generate_env_yaml(_place(), SOC_SSH_RESOURCES, "boot")
        doc = yaml.safe_load(out)
        shell = doc["targets"]["main"]["drivers"]["ADIShellDriver"]
        assert shell["login_prompt"] == "analog login: "
        assert shell["prompt"] == "root@.*"


class TestBootTierFabric:
    def test_infers_boot_fabric(self):
        out = generate_env_yaml(_place(), FABRIC_RESOURCES, "boot")
        doc = yaml.safe_load(out)
        drivers = doc["targets"]["main"]["drivers"]
        assert "BootFabric" in drivers
        assert drivers["BootFabric"]["reached_boot_marker"] == "login:"
        assert drivers["BootFabric"]["trigger_dhcp_reset"] is True

    def test_shell_defaults_for_fabric(self):
        out = generate_env_yaml(_place(), FABRIC_RESOURCES, "boot")
        doc = yaml.safe_load(out)
        shell = doc["targets"]["main"]["drivers"]["ADIShellDriver"]
        assert shell["login_prompt"] == "buildroot login: "
        assert shell["prompt"] == "#.*"


class TestBootTierNoStrategy:
    def test_falls_back_to_drivers_with_comment(self):
        out = generate_env_yaml(_place(), SERIAL_ONLY, "boot")
        doc = yaml.safe_load(out)
        drivers = doc["targets"]["main"]["drivers"]
        assert "BootFPGASoC" not in drivers
        assert "BootFabric" not in drivers
        assert "# No boot strategy" in out

    def test_shell_defaults_when_no_strategy(self):
        out = generate_env_yaml(_place(), SERIAL_ONLY, "boot")
        doc = yaml.safe_load(out)
        shell = doc["targets"]["main"]["drivers"]["ADIShellDriver"]
        assert shell["login_prompt"] == "login: "


class TestEdgeCases:
    def test_no_resources_returns_minimal(self):
        out = generate_env_yaml(_place(), [], "shell")
        doc = yaml.safe_load(out)
        assert doc["targets"]["main"]["resources"]["RemotePlace"]["name"] == "test"
        drivers = doc["targets"]["main"]["drivers"]
        assert "SerialDriver" in drivers
        assert "ADIShellDriver" in drivers

    def test_invalid_tier_raises(self):
        with pytest.raises(ValueError, match="tier"):
            generate_env_yaml(_place(), [], "bogus")


class TestInferStrategy:
    def test_soc_when_kuiper_mass_sdmux_all_present(self):
        from app.env_gen import infer_strategy

        assert (
            infer_strategy({"KuiperRelease", "NetworkUSBMassStorage", "NetworkUSBSDMuxDevice"})
            == "BootFPGASoC"
        )

    def test_fabric_when_jtag_and_vivado_present(self):
        from app.env_gen import infer_strategy

        assert infer_strategy({"XilinxDeviceJTAG", "XilinxVivadoTool"}) == "BootFabric"

    def test_none_when_no_pattern_matches(self):
        from app.env_gen import infer_strategy

        assert infer_strategy({"NetworkSerialPort", "VesyncOutlet"}) is None
