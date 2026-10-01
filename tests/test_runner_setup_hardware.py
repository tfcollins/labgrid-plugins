from unittest.mock import MagicMock, patch

from adi_lg_plugins.tools.runner_setup import hardware


@patch("glob.glob")
def test_scan_serial_devices(mock_glob):
    mock_glob.side_effect = lambda pat: (
        ["/dev/serial/by-id/usb-FTDI_FT232R-if00-port0"] if "by-id" in pat else []
    )
    devs = hardware.scan_serial_devices()
    assert devs == ["/dev/serial/by-id/usb-FTDI_FT232R-if00-port0"]


@patch("socket.create_connection")
def test_check_port_reachable(mock_conn):
    mock_conn.return_value.__enter__.return_value = MagicMock()
    assert hardware.check_port_reachable("127.0.0.1", 20408) is True


@patch("adi_lg_plugins.tools.runner_setup.hardware.check_port_reachable")
def test_check_coordinator_reachability(mock_check_port):
    mock_check_port.side_effect = lambda host, port, **kw: port == 20408
    res = hardware.check_coordinator_reachability("10.0.0.1:20408")
    assert res["grpc_reachable"] is True
    assert res["rest_reachable"] is False
    assert res["grpc_port"] == 20408
    assert res["rest_port"] == 8000


def test_validate_direct_env(tmp_path):
    env_file = tmp_path / "valid.yaml"
    env_file.write_text("targets:\n  main:\n    resources: {}\n")
    assert hardware.validate_direct_env(env_file) is True

    bad_file = tmp_path / "invalid.yaml"
    bad_file.write_text("foo: bar\n")
    assert hardware.validate_direct_env(bad_file) is False

    assert hardware.validate_direct_env(tmp_path / "nonexistent.yaml") is False
