from unittest.mock import MagicMock, patch

from adi_lg_plugins.tools.runner_setup import deps
from adi_lg_plugins.tools.runner_setup.models import HardwareMode


def test_check_python_version():
    item = deps.check_python_version()
    assert item.passed is True
    assert "Python" in item.message


@patch("shutil.which")
def test_check_command(mock_which):
    mock_which.return_value = "/usr/bin/curl"
    assert deps.check_command("curl") is True

    mock_which.return_value = None
    assert deps.check_command("nonexistent") is False


@patch("os.getgroups")
@patch("grp.getgrgid")
def test_check_dialout_group(mock_getgrgid, mock_getgroups):
    mock_getgroups.return_value = [1000, 20]
    mock_group = MagicMock()
    mock_group.gr_name = "dialout"
    mock_getgrgid.return_value = mock_group

    item = deps.check_dialout_group()
    assert item.passed is True
    assert "dialout" in item.message


@patch("shutil.which")
@patch("subprocess.run")
def test_check_ser2net_version_broken(mock_run, mock_which):
    mock_which.return_value = "/usr/bin/ser2net"
    mock_proc = MagicMock()
    mock_proc.stdout = "ser2net version 4.6.0"
    mock_proc.stderr = ""
    mock_run.return_value = mock_proc

    item = deps.check_ser2net_version()
    assert item.passed is False
    assert "BROKEN" in item.message


@patch("shutil.which")
@patch("subprocess.run")
def test_check_ser2net_version_ok(mock_run, mock_which):
    mock_which.return_value = "/usr/local/bin/ser2net"
    mock_proc = MagicMock()
    mock_proc.stdout = "ser2net version 4.6.1"
    mock_proc.stderr = ""
    mock_run.return_value = mock_proc

    item = deps.check_ser2net_version()
    assert item.passed is True
    assert "4.6.1" in item.message


@patch("shutil.which")
def test_check_ser2net_version_missing(mock_which):
    mock_which.return_value = None
    item = deps.check_ser2net_version()
    assert item.passed is False
    assert "not installed" in item.message


def test_run_dependency_checks_exporter():
    checks = deps.run_dependency_checks(HardwareMode.EXPORTER)
    names = [c.name for c in checks]
    assert any("Python" in n for n in names)
    assert any("ser2net" in n for n in names)
    assert not any("dialout" in n for n in names)


def test_run_dependency_checks_direct():
    checks = deps.run_dependency_checks(HardwareMode.DIRECT)
    names = [c.name for c in checks]
    assert any("Python" in n for n in names)
    assert any("dialout" in n for n in names)
    assert not any("ser2net" in n for n in names)
