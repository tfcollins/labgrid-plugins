"""Tests for BootFabric strategy on VCU118+AD9081 platform."""

import pytest
from labgrid import Environment


# @pytest.fixture(scope="module")
# def env():
#     """Load test environment for VCU118."""
#     env_path = "tests/test_fabric_vcu118.yaml"
#     env = Environment(env_path)
#     env.get_target("main")
#     return env


# @pytest.fixture(scope="module")
# def target(env):
#     """Get target from environment."""
#     return env.get_target("main")


# @pytest.fixture(scope="module")
# def strategy(target):
#     """Get BootFabric strategy."""
#     return target.get_driver("BootFabric")


@pytest.fixture(scope="module")
def in_shell(strategy):
    """Boot to shell and cleanup after tests."""
    strategy.transition("shell")
    yield
    strategy.transition("soft_off")


def test_boot_to_shell(target, in_shell):
    """Test boot sequence to shell."""
    shell = target.get_driver("ADIShellDriver")
    stdout, stderr, returncode = shell.run("uname -a")
    assert returncode == 0, f"Command failed with stderr: {stderr}"
    if isinstance(stdout, list):
        stdout = "\n".join(stdout)
    assert "Linux" in stdout, f"Linux not found in output: {stdout}"
    assert "microblaze" in stdout, f"microblaze not found in output: {stdout}"


def test_iio_device_available(target, in_shell):
    """Test AD9081 IIO device is available."""
    shell = target.get_driver("ADIShellDriver")
    stdout, stderr, returncode = shell.run("iio_attr -d axi-ad9081-rx-hpc name")
    assert returncode == 0, f"IIO device check failed with stderr: {stderr}"
    assert "could not find device" not in stdout, f"Device not found: {stdout}"


def test_bitstream_flash(target):
    """Test bitstream flashing."""
    strategy = target.get_driver("BootFabric")
    strategy.transition("powered_on")
    strategy.transition("bitstream_flashed")
    assert strategy.status.name == "bitstream_flashed"


def test_kernel_download(target):
    """Test kernel download."""
    strategy = target.get_driver("BootFabric")
    strategy.transition("bitstream_flashed")
    strategy.transition("kernel_downloaded")
    assert strategy.status.name == "kernel_downloaded"


@pytest.mark.parametrize(
    "marker",
    [
        "login:",  # Default Linux login prompt
        "root@",  # Root shell prompt
    ],
)
def test_custom_boot_marker(marker):
    """Test custom boot marker configuration."""
    # This test demonstrates how to use custom boot markers
    # In practice, you would create a new target with custom marker
    assert marker in ["login:", "root@", "# "]
