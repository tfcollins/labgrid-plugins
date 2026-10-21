"""Unit tests for XilinxUSBJTAG and NetworkXilinxUSBJTAG resources."""

from types import SimpleNamespace

from labgrid import Target

from adi_lg_plugins.resources.xilinxusb import NetworkXilinxUSBJTAG, XilinxUSBJTAG


def test_xilinx_usb_jtag_defaults():
    target = Target("test")
    res = XilinxUSBJTAG(target, "xilinxusb")
    assert res.hw_server_cmd == "hw_server"
    assert res.serial == ""
    assert res.agent_url == ""
    assert res.gdb_port == 0
    assert res.log_level == []
    assert res.extra_args == []


def test_network_xilinx_usb_jtag_defaults():
    target = Target("test")
    res = NetworkXilinxUSBJTAG(target, "net_xilinxusb", host="192.168.1.100")
    assert res.host == "192.168.1.100"
    assert res.hw_server_cmd == "hw_server"
    assert res.serial == ""
    assert res.agent_url == ""
    assert res.gdb_port == 0
    assert res.log_level == []
    assert res.extra_args == []
    assert res.timeout == 10.0


def test_xilinx_usb_jtag_filter_match():
    target = Target("test")
    res = XilinxUSBJTAG(target, "xilinxusb")

    def make_device(vid, pid):
        return SimpleNamespace(properties={"ID_VENDOR_ID": vid, "ID_MODEL_ID": pid})

    # Trenz Electronic TE0790-03
    assert res.filter_match(make_device("0403", "6010")) is True
    # Digilent JTAG-SMT2 / JTAG-HS3
    assert res.filter_match(make_device("0403", "6014")) is True
    # Xilinx Platform Cable USB
    assert res.filter_match(make_device("03fd", "0013")) is True
    # Xilinx Platform Cable USB II
    assert res.filter_match(make_device("03fd", "0008")) is True
    # Wildcard / None match
    assert res.filter_match(make_device(None, None)) is True
    # Unknown USB vendor/device
    assert res.filter_match(make_device("1234", "5678")) is False
    assert res.filter_match(make_device("0403", "9999")) is False
