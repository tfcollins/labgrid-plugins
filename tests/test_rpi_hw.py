import pytest

pytestmark = pytest.mark.hardware


@pytest.fixture(scope="module")
def in_shell(strategy):
    strategy.transition("shell")
    yield


def test_ssh_shell(target, in_shell):
    """Test basic SSH command execution."""
    ssh = target["SSHDriver"]
    stdout, stderr, returncode = ssh.run("cat /proc/version")
    assert returncode == 0
    assert stdout
    assert "Linux" in stdout[0]


def test_hostname(target, in_shell):
    """Test hostname retrieval."""
    ssh = target["SSHDriver"]
    stdout, stderr, returncode = ssh.run("hostname")
    assert returncode == 0
    assert stdout


def test_uptime(target, in_shell):
    """Test uptime command."""
    ssh = target["SSHDriver"]
    stdout, stderr, returncode = ssh.run("uptime")
    assert returncode == 0
    assert stdout


def test_disk_space(target, in_shell):
    """Test disk space check."""
    ssh = target["SSHDriver"]
    stdout, stderr, returncode = ssh.run("df -h /")
    assert returncode == 0
    assert len(stdout) >= 2  # header + at least one row


def test_network_interface(target, in_shell):
    """Test network interface is up."""
    ssh = target["SSHDriver"]
    stdout, stderr, returncode = ssh.run("ip addr show")
    assert returncode == 0
    assert stdout
