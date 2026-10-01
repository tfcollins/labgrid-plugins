from unittest.mock import MagicMock, patch

import pytest

from adi_lg_plugins.tools.runner_setup import service


@patch("subprocess.run")
def test_install_and_start_runner_service(mock_run, tmp_path):
    svc_sh = tmp_path / "svc.sh"
    svc_sh.write_text("#!/bin/sh\n")

    service.install_and_start_runner_service(tmp_path, user="ciuser")

    assert mock_run.call_count == 2
    install_args = mock_run.call_args_list[0][0][0]
    assert install_args == ["sudo", str(svc_sh), "install", "ciuser"]

    start_args = mock_run.call_args_list[1][0][0]
    assert start_args == ["sudo", str(svc_sh), "start"]


def test_install_and_start_missing_script(tmp_path):
    with pytest.raises(FileNotFoundError, match="svc.sh not found"):
        service.install_and_start_runner_service(tmp_path)


@patch("subprocess.run")
def test_get_runner_service_status(mock_run, tmp_path):
    svc_sh = tmp_path / "svc.sh"
    svc_sh.write_text("#!/bin/sh\n")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "active (running)\n"
    mock_proc.stderr = ""
    mock_run.return_value = mock_proc

    rc, out = service.get_runner_service_status(tmp_path)
    assert rc == 0
    assert "active (running)" in out


def test_generate_exporter_service_unit(tmp_path):
    unit = service.generate_exporter_service_unit(
        coord="10.0.0.41:20408",
        exporter_name="mini2",
        resource_yaml=tmp_path / "resources.yaml",
        user="testuser",
    )
    assert "User=testuser" in unit
    assert "labgrid-exporter -c 10.0.0.41:20408 -n mini2" in unit
    assert "WantedBy=multi-user.target" in unit
