import os
import tempfile
from unittest.mock import MagicMock, call

import pytest

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


def test_detect_package_manager_apt(driver, mock_command_protocol):
    mock_command_protocol.run.side_effect = [
        (None, None, 0),  # which apt-get -> success
        (None, None, 0),  # apt-get install foo -> success
    ]

    driver.install_package("foo")

    assert mock_command_protocol.run.call_count == 2
    mock_command_protocol.run.assert_has_calls(
        [call("which apt-get"), call("apt-get install -y foo")]
    )


def test_detect_package_manager_dnf(driver, mock_command_protocol):
    mock_command_protocol.run.side_effect = [
        (None, None, 1),  # which apt-get -> fail
        (None, None, 0),  # which dnf -> success
        (None, None, 0),  # dnf install foo -> success
    ]

    driver.install_package("foo")

    assert mock_command_protocol.run.call_count == 3
    mock_command_protocol.run.assert_has_calls(
        [call("which apt-get"), call("which dnf"), call("dnf install -y foo")]
    )


def test_detect_package_manager_opkg(driver, mock_command_protocol):
    mock_command_protocol.run.side_effect = [
        (None, None, 1),  # which apt-get
        (None, None, 1),  # which dnf
        (None, None, 0),  # which opkg
        (None, None, 0),  # opkg install foo
    ]

    driver.install_package("foo")

    assert mock_command_protocol.run.call_count == 4
    mock_command_protocol.run.assert_has_calls(
        [call("which apt-get"), call("which dnf"), call("which opkg"), call("opkg install foo")]
    )


def test_detect_package_manager_none(driver, mock_command_protocol):
    mock_command_protocol.run.return_value = (None, None, 1)  # All fail

    with pytest.raises(Exception, match="No supported package manager found"):
        driver.install_package("foo")


def test_install_package_update(driver, mock_command_protocol):
    mock_command_protocol.run.side_effect = [
        (None, None, 0),  # which apt-get
        (None, None, 0),  # apt-get update
        (None, None, 0),  # apt-get install foo
    ]

    driver.install_package("foo", update=True)

    mock_command_protocol.run.assert_has_calls(
        [call("which apt-get"), call("apt-get update"), call("apt-get install -y foo")]
    )


def test_install_package_fail(driver, mock_command_protocol):
    mock_command_protocol.run.side_effect = [
        (None, None, 0),  # which apt-get
        ("", "E: Unable to locate package", 100),  # install fail
    ]

    with pytest.raises(Exception, match="Failed to install package 'foo'"):
        driver.install_package("foo")


def test_clone_repo(driver, mock_command_protocol):
    mock_command_protocol.run.side_effect = [
        (None, None, 0),  # which git
        (None, None, 0),  # git clone
    ]

    driver.clone_repo("http://github.com/foo/bar", "/tmp/bar")

    mock_command_protocol.run.assert_has_calls(
        [call("which git"), call("git clone http://github.com/foo/bar /tmp/bar")]
    )


def test_clone_repo_no_git(driver, mock_command_protocol):
    # Simulate git missing, then apt-get install git success, then clone
    mock_command_protocol.run.side_effect = [
        (None, None, 1),  # which git -> fail
        (None, None, 0),  # which apt-get -> success (install_package)
        (None, None, 0),  # apt-get install git -> success
        (None, None, 0),  # git clone -> success
    ]

    driver.clone_repo("http://github.com/foo/bar", "/tmp/bar")

    # We expect recursive calls due to install_package('git')
    # Since install_package calls detect, we will see which apt-get again
    mock_command_protocol.run.assert_has_calls(
        [
            call("which git"),
            call("which apt-get"),
            call("apt-get install -y git"),
            call("git clone http://github.com/foo/bar /tmp/bar"),
        ]
    )


def test_clone_repo_branch(driver, mock_command_protocol):
    mock_command_protocol.run.side_effect = [
        (None, None, 0),  # which git
        (None, None, 0),  # git clone
    ]

    driver.clone_repo("http://github.com/foo/bar", "/tmp/bar", branch="dev")

    mock_command_protocol.run.assert_has_calls(
        [call("which git"), call("git clone http://github.com/foo/bar /tmp/bar --branch dev")]
    )


def test_clone_repo_fail(driver, mock_command_protocol):
    mock_command_protocol.run.side_effect = [
        (None, None, 0),  # which git
        ("", "fatal: repository not found", 128),  # git clone fail
    ]

    with pytest.raises(Exception, match="Failed to clone repo"):
        driver.clone_repo("http://foo", "/tmp/bar")


def test_run_build(driver, mock_command_protocol):
    mock_command_protocol.run.return_value = (None, None, 0)
    driver.run_build("make", "/tmp/build")
    mock_command_protocol.run.assert_called_with("cd /tmp/build && make", timeout=3600)


def test_run_build_fail(driver, mock_command_protocol):
    mock_command_protocol.run.return_value = ("", "make: *** No targets", 2)
    with pytest.raises(Exception, match="Build failed"):
        driver.run_build("make", "/tmp/build")


def test_run_binary(driver, mock_command_protocol):
    mock_command_protocol.run.return_value = (None, None, 0)
    driver.run_binary("/bin/ls", "-la", "/tmp")
    mock_command_protocol.run.assert_called_with("cd /tmp && /bin/ls -la")


def test_run_binary_fail(driver, mock_command_protocol):
    mock_command_protocol.run.return_value = ("", "Segmentation fault", 139)
    with pytest.raises(Exception, match="Binary execution failed"):
        driver.run_binary("/bin/ls", "", "/tmp")


def test_run_test(driver, mock_command_protocol):
    mock_command_protocol.run.return_value = (None, None, 0)
    driver.run_test("pytest", "/tmp/tests")
    mock_command_protocol.run.assert_called_with("cd /tmp/tests && pytest")


def test_run_test_fail(driver, mock_command_protocol):
    mock_command_protocol.run.return_value = ("", "AssertionError", 1)
    with pytest.raises(Exception, match="Test failed"):
        driver.run_test("pytest", "/tmp/tests")


def test_copy_directory(driver, mock_command_protocol, mock_file_transfer_protocol):
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


def test_copy_directory_fail_local_path(driver):
    with pytest.raises(ValueError, match="is not a directory"):
        driver.copy_directory("/non/existent/path", "/remote")


def test_copy_directory_fail_transfer(driver, mock_command_protocol, mock_file_transfer_protocol):
    mock_file_transfer_protocol.put.side_effect = Exception("Transfer failed")

    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(Exception, match="Transfer failed"):
            driver.copy_directory(tmpdir, "/remote")


def test_copy_directory_fail_extract(driver, mock_command_protocol, mock_file_transfer_protocol):
    with tempfile.TemporaryDirectory() as tmpdir:
        mock_command_protocol.run.side_effect = [
            (None, None, 0),  # mkdir
            ("", "tar: Error is not recoverable", 2),  # tar extract fail
            (None, None, 0),  # rm cleanup
        ]

        with pytest.raises(Exception, match="Failed to extract directory"):
            driver.copy_directory(tmpdir, "/remote")
