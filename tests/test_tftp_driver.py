import logging
import socket

import pytest

from adi_lg_plugins.drivers.tftpserverdriver import TFTPServerDriver
from adi_lg_plugins.resources.tftpserver import TFTPServerResource


class DummyTarget:
    def __init__(self):
        self.name = "dummy"
        self.logger = logging.getLogger("dummy")

    def bind(self, item):
        item.target = self


def test_tftp_driver_basic_transfer(tmp_path):
    # Setup
    port = 10069
    root_dir = tmp_path / "tftpboot"
    root_dir.mkdir()

    test_file = root_dir / "test.txt"
    content = b"Hello TFTP World!" * 100
    test_file.write_bytes(content)

    target = DummyTarget()
    res = TFTPServerResource(target, "tftp_res", address="127.0.0.1", port=port, root=str(root_dir))
    driver = TFTPServerDriver(target, "tftp")
    driver.resource = res

    # Activate
    driver.on_activate()

    try:
        # Client download
        client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client_sock.settimeout(2.0)
        server_addr = ("127.0.0.1", port)

        # RRQ: \x00\x01 + filename + \x00 + mode + \x00
        rrq = b"\x00\x01test.txt\x00octet\x00"
        client_sock.sendto(rrq, server_addr)

        received = b""
        block = 1

        while True:
            try:
                data, addr = client_sock.recvfrom(1024)
            except TimeoutError:
                pytest.fail("Timeout waiting for data")

            opcode = data[:2]
            if opcode == b"\x00\x03":  # DATA
                block_num = int.from_bytes(data[2:4], "big")
                if block_num == block:
                    received += data[4:]
                    # Send ACK
                    ack = b"\x00\x04" + data[2:4]
                    client_sock.sendto(ack, addr)
                    block += 1

                    if len(data[4:]) < 512:
                        break

                    # Handle wrap around for test if needed, but 100*len is small.
                    if block > 65535:
                        block = 0
                else:
                    # Ignore duplicates
                    pass
            elif opcode == b"\x00\x05":  # ERROR
                pytest.fail(f"TFTP Error: {data[4:].decode(errors='replace')}")
            else:
                pytest.fail(f"Unexpected opcode: {opcode}")

        assert received == content

    finally:
        driver.on_deactivate()
        client_sock.close()
