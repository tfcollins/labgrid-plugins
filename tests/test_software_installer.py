import pytest
from unittest.mock import MagicMock, call, ANY
from adi_lg_plugins.drivers.softwareinstaller import SoftwareInstallerDriver

class DummyTarget:
    def __init__(self):
        self.name = "dummy"

    def bind(self, item):
        item.target = self

@pytest.fixture
def mock_command_protocol():
    return MagicMock()

@pytest.fixture
def mock_file_transfer_protocol():
    return MagicMock()

@pytest.fixture
def driver(mock_command_protocol, mock_file_transfer_protocol):
    target = DummyTarget()
    drv = SoftwareInstallerDriver(target=target, name="installer")
    drv.command = mock_command_protocol
    drv.file_transfer = mock_file_transfer_protocol
    return drv

def test_install_package_apt(driver, mock_command_protocol):
    # Mock detection
    mock_command_protocol.run.side_effect = [
        (None, None, 0), # which apt-get -> success
        (None, None, 0), # apt-get install foo -> success
    ]
    
    driver.install_package("foo")
    
    assert mock_command_protocol.run.call_count == 2
    mock_command_protocol.run.assert_has_calls([
        call("which apt-get"),
        call("apt-get install -y foo")
    ])

def test_install_package_update(driver, mock_command_protocol):
    mock_command_protocol.run.side_effect = [
        (None, None, 0), # which apt-get
        (None, None, 0), # apt-get update
        (None, None, 0), # apt-get install foo
    ]
    
    driver.install_package("foo", update=True)
    
    mock_command_protocol.run.assert_has_calls([
        call("which apt-get"),
        call("apt-get update"),
        call("apt-get install -y foo")
    ])

def test_install_package_fail(driver, mock_command_protocol):
    mock_command_protocol.run.side_effect = [
        (None, None, 0), # which apt-get
        ("", "E: Unable to locate package", 100), # install fail
    ]
    
    with pytest.raises(Exception, match="Failed to install package 'foo'"):
        driver.install_package("foo")

def test_clone_repo(driver, mock_command_protocol):
    mock_command_protocol.run.side_effect = [
        (None, None, 0), # which git
        (None, None, 0), # git clone
        (None, None, 0), # Extra for debug
    ]
    
    driver.clone_repo("http://github.com/foo/bar", "/tmp/bar")
    
    mock_command_protocol.run.assert_has_calls([
        call("which git"),
        call("git clone http://github.com/foo/bar /tmp/bar")
    ])

def test_clone_repo_branch(driver, mock_command_protocol):
    mock_command_protocol.run.side_effect = [
        (None, None, 0), # which git
        (None, None, 0), # git clone
        (None, None, 0), # Extra for debug
    ]
    
    driver.clone_repo("http://github.com/foo/bar", "/tmp/bar", branch="dev")
    
    mock_command_protocol.run.assert_has_calls([
        call("which git"),
        call("git clone http://github.com/foo/bar /tmp/bar --branch dev")
    ])

def test_run_build(driver, mock_command_protocol):
    mock_command_protocol.run.return_value = (None, None, 0)
    
    driver.run_build("make", "/tmp/build")
    
    mock_command_protocol.run.assert_called_with("cd /tmp/build && make", timeout=3600)

def test_run_binary(driver, mock_command_protocol):
    mock_command_protocol.run.return_value = (None, None, 0)
    
    driver.run_binary("/bin/ls", "-la", "/tmp")
    
    mock_command_protocol.run.assert_called_with("cd /tmp && /bin/ls -la")

def test_run_test(driver, mock_command_protocol):
    mock_command_protocol.run.return_value = (None, None, 0)
    
    driver.run_test("pytest", "/tmp/tests")
    
    mock_command_protocol.run.assert_called_with("cd /tmp/tests && pytest")

def test_copy_directory(driver, mock_command_protocol, mock_file_transfer_protocol):
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # create dummy file
        with open(os.path.join(tmpdir, "test.txt"), "w") as f:
            f.write("hello")
            
        mock_command_protocol.run.return_value = (None, None, 0)
        
        driver.copy_directory(tmpdir, "/remote/dest")
        
        # Verify file transfer
        assert mock_file_transfer_protocol.put.called
        
        # Verify remote commands
        calls = mock_command_protocol.run.mock_calls
        assert any("mkdir -p /remote/dest" in str(c) for c in calls)
        assert any("tar -xzf" in str(c) for c in calls)
        assert any("rm " in str(c) for c in calls)
