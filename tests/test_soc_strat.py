import pytest
import iio

# @pytest.fixture(scope="function")
# def in_bootloader(strategy, capsys):
#     with capsys.disabled():
#         strategy.transition("barebox")

@pytest.fixture(scope="module")
def in_shell(strategy):
    # with capsys.disabled():
    strategy.transition("shell")
    addresses = strategy.target["ADIShellDriver"].get_ip_addresses()

    yield
    # with capsys.disabled():
    strategy.transition("soft_off")
    
@pytest.fixture(scope="module")
def iio_context(target, in_shell):
    shell = target.get_driver("ADIShellDriver")
    addresses = shell.get_ip_addresses()
    ip_address = addresses[0]
    # ip_address is of type IPv4Interface
    ip_address = str(ip_address.ip)
    print(f"Using IP address for IIO context: {ip_address}")
    # Remove /24 suffix if present
    if '/' in ip_address:
        ip_address = ip_address.split('/')[0]
    ctx = iio.Context(f"ip:{ip_address}")
    assert ctx is not None, "Failed to create IIO context"
    return ctx




# def test_shell(command, in_shell):
def test_shell(target, in_shell):
    command = target["ADIShellDriver"]

    stdout, stderr, returncode = command.run("cat /proc/version")
    assert returncode == 0
    assert stdout
    assert not stderr
    assert "Linux" in stdout[0]

    stdout, stderr, returncode = command.run("false")
    assert returncode != 0
    assert not stdout
    assert not stderr

    addresses = command.get_ip_addresses()
    print(f"IP addresses on eth0: {addresses}")
    assert addresses, "No IP addresses found on eth0"


def test_check_drivers(target, iio_context):

    drivers = ["axi-ad9081-rx-hpc"]
    for device in iio_context.devices:
        print(f"Found IIO device: {device.name}")
        if device.name in drivers:
            drivers.remove(device.name)

    assert not drivers, f"Expected IIO drivers not found: {drivers}"