import logging
import socket
from pathlib import Path
from unittest import mock

import pytest
from labgrid.util.agentwrapper import AgentException

from adi_lg_plugins.drivers import tftpserverdriver
from adi_lg_plugins.drivers.tftpserverdriver import TFTPServerDriver
from adi_lg_plugins.resources.tftpserver import TFTPServerResource


class DummyTarget:
    def __init__(self):
        self.name = "dummy"
        self.logger = logging.getLogger("dummy")

    def bind(self, item):
        item.target = self


def _make_driver(root: Path, *, address="127.0.0.1", port=0, proxy=None):
    target = DummyTarget()
    resource = TFTPServerResource(
        target,
        "tftp_res",
        address=address,
        port=port,
        root=str(root),
    )
    if proxy:
        resource.extra = {"proxy": proxy}
    driver = TFTPServerDriver(target, "tftp")
    driver.resource = resource
    return driver


def _download(address, filename):
    host, port = address.rsplit(":", 1)
    server_addr = (host, int(port))
    client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_sock.settimeout(2.0)
    try:
        rrq = b"\x00\x01" + filename.encode() + b"\x00octet\x00"
        client_sock.sendto(rrq, server_addr)
        received = b""
        block = 1
        while True:
            data, addr = client_sock.recvfrom(1024)
            opcode = data[:2]
            if opcode == b"\x00\x05":
                return opcode, data[4:]
            assert opcode == b"\x00\x03"
            assert int.from_bytes(data[2:4], "big") == block
            received += data[4:]
            client_sock.sendto(b"\x00\x04" + data[2:4], addr)
            if len(data[4:]) < 512:
                return opcode, received
            block = (block + 1) % 65536
    finally:
        client_sock.close()


def test_local_lifecycle_publish_and_real_udp_transfer(tmp_path):
    root = tmp_path / "tftpboot"
    source = tmp_path / "client" / "test.txt"
    source.parent.mkdir()
    content = b"Hello TFTP World!" * 100
    source.write_bytes(content)
    driver = _make_driver(root)

    driver.on_activate()
    try:
        published = driver.publish(str(source), "images/./test.txt")
        assert published == {
            "filename": "images/test.txt",
            "address": driver.get_server_address.__wrapped__(driver),
        }
        assert (root / "images/test.txt").read_bytes() == content
        opcode, received = _download(published["address"], published["filename"])
        assert opcode == b"\x00\x03"
        assert received == content
    finally:
        driver.on_deactivate()

    assert driver.wrapper is None
    assert driver.proxy is None


@pytest.mark.parametrize("destination", ["../escape", "a/../../escape", "/absolute", r"..\escape"])
def test_publish_rejects_traversal_and_absolute_destinations(tmp_path, destination):
    source = tmp_path / "source"
    source.write_bytes(b"payload")
    driver = _make_driver(tmp_path / "root")
    driver.on_activate()
    try:
        with pytest.raises((AgentException, ValueError), match="destination|relative|traversal"):
            driver.publish(str(source), destination)
        assert not (tmp_path / "escape").exists()
    finally:
        driver.on_deactivate()


def test_tftp_rrq_rejects_traversal(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "secret").write_bytes(b"not served")
    driver = _make_driver(root)
    driver.on_activate()
    try:
        opcode, message = _download(
            driver.get_server_address.__wrapped__(driver),
            "../secret",
        )
        assert opcode == b"\x00\x05"
        assert b"Access violation" in message
    finally:
        driver.on_deactivate()


def test_deactivation_releases_udp_port_for_immediate_reactivation(tmp_path):
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    first = _make_driver(tmp_path / "first", port=port)
    second = _make_driver(tmp_path / "second", port=port)
    first.on_activate()
    first.on_deactivate()
    second.on_activate()
    second.on_deactivate()


def test_remote_place_uses_agentwrapper_on_exporter_and_exporter_auto_address(tmp_path):
    source = tmp_path / "kernel"
    source.write_bytes(b"kernel")
    driver = _make_driver(tmp_path / "exporter-root", address="auto", proxy="exporter.local")
    wrapper = mock.Mock()
    proxy = mock.Mock()
    wrapper.load.return_value = proxy
    proxy.start.return_value = {
        "address": "192.0.2.10",
        "port": 3069,
        "root": str(tmp_path / "exporter-root"),
    }
    proxy.begin_upload.return_value = "upload-token"
    proxy.finish_upload.return_value = "boot/kernel"

    with mock.patch.object(tftpserverdriver, "AgentWrapper", return_value=wrapper) as wrapper_cls:
        driver.on_activate()
        result = driver.publish(str(source), "boot/kernel")
        driver.on_deactivate()

    wrapper_cls.assert_called_once_with("exporter.local")
    wrapper.load.assert_called_once()
    proxy.start.assert_called_once_with("auto", 0, str(tmp_path / "exporter-root"))
    proxy.begin_upload.assert_called_once_with("boot/kernel")
    proxy.write_upload.assert_called_once()
    proxy.finish_upload.assert_called_once_with("upload-token")
    proxy.stop.assert_called_once_with()
    wrapper.close.assert_called_once_with()
    assert result == {"filename": "boot/kernel", "address": "192.0.2.10:3069"}
    assert driver.wrapper is None
    assert driver.proxy is None


def test_stage_file_is_publish_alias(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"payload")
    driver = _make_driver(tmp_path / "root")
    driver.on_activate()
    try:
        result = driver.stage_file(source)
        assert result["filename"] == "source.bin"
        assert (tmp_path / "root" / "source.bin").read_bytes() == b"payload"
    finally:
        driver.on_deactivate()


def test_remote_auto_resource_refuses_client_side_address_discovery(tmp_path):
    driver = _make_driver(tmp_path / "root", address="auto", proxy="exporter.local")
    with pytest.raises(RuntimeError, match="exporter-side"):
        driver.resource.get_ip()


def test_activation_bind_failure_closes_agent(tmp_path):
    driver = _make_driver(tmp_path / "root", proxy="exporter.local")
    wrapper = mock.Mock()
    proxy = mock.Mock()
    wrapper.load.return_value = proxy
    proxy.start.side_effect = AgentException("OSError(98, 'Address already in use')")

    with mock.patch.object(tftpserverdriver, "AgentWrapper", return_value=wrapper):
        with pytest.raises(AgentException, match="Address already in use"):
            driver.on_activate()

    wrapper.close.assert_called_once_with()
    assert driver.wrapper is None
    assert driver.proxy is None


def test_auto_address_derivation_failure_does_not_advertise_client(tmp_path):
    driver = _make_driver(tmp_path / "root", address="auto", proxy="exporter.local")
    wrapper = mock.Mock()
    proxy = mock.Mock()
    wrapper.load.return_value = proxy
    proxy.start.side_effect = AgentException("RuntimeError('cannot derive exporter address')")

    with mock.patch.object(tftpserverdriver, "AgentWrapper", return_value=wrapper):
        with pytest.raises(AgentException, match="cannot derive exporter address"):
            driver.on_activate()

    assert driver.resource.address == "auto"
    wrapper.close.assert_called_once_with()
