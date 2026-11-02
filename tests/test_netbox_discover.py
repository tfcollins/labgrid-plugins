"""Unit tests for the read-only hardware probe `adi-lg netbox add-hardware` runs on the exporter host.

The probe runs for real, against a fake sysfs, /dev and /etc tree laid out the
way the kernel and udev lay them out (relative links included), so no test
needs the hardware.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from labgrid.driver.exception import ExecutionError

from adi_lg_plugins.tools.netbox import discover

_USB = "sys/devices/pci0000:00/0000:00:14.0/usb1"
_CP2108 = "usb-Silicon_Labs_CP2108_Quad_USB_to_UART_Bridge_Controller_BCA68DE8-if00-port0"
_DIGILENT = "usb-Digilent_Digilent_USB_Device_210299A567FE-if00-port0"
_FT232R = "usb-FTDI_FT232R_USB_UART_A10KZ9QX-if00-port0"
_ZCU102_UART = "usb-Xilinx_JTAG+3Serial_43211-if01-port0"
_MUX_DISK = "usb-LinuxAut_sdmux_HS-SD_MMC_000000001234-0:0"


def _write(root: Path, path: str, text: str = "") -> Path:
    p = root / path.lstrip("/")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def _link(root: Path, link: str, target: str) -> None:
    """A relative symlink, as udev and sysfs make them."""
    p = root / link.lstrip("/")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.symlink_to(os.path.relpath(root / target.lstrip("/"), p.parent))


def _usb_device(root, port, vendor, product, manufacturer, name, serial=""):
    d = f"{_USB}/{port}"
    for attr, value in (
        ("idVendor", vendor),
        ("idProduct", product),
        ("manufacturer", manufacturer),
        ("product", name),
        ("serial", serial),
    ):
        if value:
            _write(root, f"{d}/{attr}", f"{value}\n")
    return d


def _usb_tty(root, device, interface, tty, by_id=None):
    """A USB serial interface's tty, with its /sys/class/tty entry and /dev nodes."""
    iface = f"{device}/{device.rsplit('/', 1)[1]}:1.{int(interface)}"
    _write(root, f"{iface}/bInterfaceNumber", f"{interface}\n")
    _write(root, f"{iface}/{tty}/uevent")
    _link(root, f"/sys/class/tty/{tty}/device", f"{iface}/{tty}")
    _write(root, f"/dev/{tty}")
    if by_id:
        _link(root, f"/dev/serial/by-id/{by_id}", f"/dev/{tty}")


def _usb_disk(root, device, sg, disk, model, by_id=None):
    """A USB mass-storage device's SCSI disk, with its sg node and /dev nodes."""
    iface = f"{device}/{device.rsplit('/', 1)[1]}:1.0"
    scsi = f"{iface}/host2/target2:0:0/2:0:0:0"
    _write(root, f"{iface}/bInterfaceNumber", "00\n")
    _write(root, f"{scsi}/model", f"{model}\n")
    _write(root, f"{scsi}/block/{disk}/size", "0\n")
    _write(root, f"{scsi}/block/{disk}/{disk}1/partition", "1\n")
    _write(root, f"/dev/{disk}1")
    _link(root, f"/sys/class/scsi_generic/{sg}/device", scsi)
    _write(root, f"/dev/{sg}")
    _write(root, f"/dev/{disk}")
    if by_id:
        _link(root, f"/dev/disk/by-id/{by_id}", f"/dev/{disk}")


@pytest.fixture
def lab_host(tmp_path):
    """An exporter host with serial adapters, JTAG cables, an SD mux and Vivado.

    One exporter config (deployed by add-hardware) uses the CP2108's first
    port, the SD mux and a JTAG cable; another, named by a systemd unit, uses
    the ZCU102's UART; a third matches the FT232R by its udev serial.
    """
    root = tmp_path / "host"
    cp2108 = _usb_device(
        root, "1-2", "10c4", "ea71", "Silicon Labs", "CP2108 Quad USB to UART", "BCA68DE8"
    )
    _usb_tty(root, cp2108, "00", "ttyUSB0", _CP2108)
    _usb_tty(root, cp2108, "01", "ttyUSB1", _CP2108.replace("if00", "if01"))
    digilent = _usb_device(
        root, "1-3", "0403", "6014", "Digilent", "Digilent USB Device", "210299A567FE"
    )
    _usb_tty(root, digilent, "00", "ttyUSB2", _DIGILENT)  # its JTAG channel
    zcu102 = _usb_device(root, "1-4", "0403", "6011", "Xilinx", "JTAG+3Serial", "43211")
    _usb_tty(root, zcu102, "00", "ttyUSB3", _ZCU102_UART.replace("if01", "if00"))
    _usb_tty(root, zcu102, "01", "ttyUSB4", _ZCU102_UART)
    ft232r = _usb_device(root, "1-5", "0403", "6001", "FTDI", "FT232R USB UART", "A10KZ9QX")
    _usb_tty(root, ft232r, "00", "ttyUSB5", _FT232R)
    _usb_device(root, "1-6", "03fd", "0008", "Xilinx", "Platform Cable USB II")
    mux = _usb_device(root, "1-7", "0424", "4041", "Microchip", "USB2642", "000000001234")
    _usb_disk(root, mux, "sg0", "sda", "sdmux HS-SD/MMC", _MUX_DISK)
    kvm = _usb_device(root, "1-8", "0525", "a4a5", "Glinet", "Flash Drive", "0123456789")
    _usb_disk(root, kvm, "sg1", "sdb", "Flash Drive", "usb-Glinet_Flash_Drive_0123456789-0:0")
    _usb_device(root, "usb1-root", "1d6b", "0002", "Linux", "xHCI Host Controller")
    for port in ("1-2", "1-3", "1-4", "1-5", "1-6", "1-7", "1-8"):
        _link(root, f"/sys/bus/usb/devices/{port}", f"{_USB}/{port}")
        _link(root, f"/sys/bus/usb/devices/{port}:1.0", f"{_USB}/{port}/{port}:1.0")

    _write(root, "/tools/Xilinx/2025.1/Vivado/settings64.sh")
    _write(root, "/tools/Xilinx/2025.1/Vitis/bin/xsdb")
    _write(root, "/tools/Xilinx/2025.2/Vivado/settings64.sh")  # no Vitis beside it
    _write(root, "/opt/Xilinx/2024.2/Vivado_Lab/settings64.sh")
    _write(root, "/tools/Xilinx/Vivado/2023.2/settings64.sh")  # the layout before 2024.2
    _write(root, "/tools/Xilinx/Vivado/scripts/init.tcl")  # not an install

    _write(
        root,
        "/etc/labgrid/exporters/zcu102-old/resources.yaml",
        "ZCU102_OLD:\n"
        "  RawSerialPort:\n"
        f'    port: "/dev/serial/by-id/{_CP2108}"\n'
        "  USBSDMuxDevice:\n"
        '    control_path: "/dev/sg0"\n'
        "  XilinxDeviceJTAG:\n"
        "    root_target: 1\n"
        "  NetworkService:\n"
        '    password: "analog"\n',
    )
    _write(
        root,
        "/etc/systemd/system/labgrid-exporter.service",
        "[Service]\nExecStart=/home/lab/venv/bin/labgrid-exporter -n tron /home/lab/lg_tron.yaml\n",
    )
    _write(root, "/home/lab/lg_tron.yaml", "TRON:\n  RawSerialPort:\n    port: /dev/ttyUSB4\n")
    _write(
        root,
        "/etc/labgrid/rpi.yaml",
        "RPI:\n  USBSerialPort:\n    match:\n      ID_SERIAL_SHORT: A10KZ9QX\n",
    )
    return root


def _probe(root) -> str:
    out = subprocess.run(
        [sys.executable, "-c", discover.PROBE, str(root)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return out.stdout


def _found(root) -> discover.HostHardware:
    return discover.parse(_probe(root))


def test_serial_adapters_are_listed_by_their_by_id_link(lab_host):
    adapters = {a.tty: a for a in _found(lab_host).serial}

    assert adapters["/dev/ttyUSB1"] == discover.SerialAdapter(
        f"/dev/serial/by-id/{_CP2108.replace('if00', 'if01')}",
        "/dev/ttyUSB1",
        "Silicon Labs CP2108 Quad USB to UART",
        "BCA68DE8",
    )
    assert [a.link for a in _found(lab_host).serial] == sorted(a.link for a in adapters.values())


def test_jtag_cables_are_found_by_xilinx_s_vendor_id_digilent_or_jtag_in_the_product(lab_host):
    cables = _found(lab_host).jtag

    assert {(c.name, c.usb_id, c.serial) for c in cables} == {
        ("Digilent Digilent USB Device", "0403:6014", "210299A567FE"),
        ("Xilinx JTAG+3Serial", "0403:6011", "43211"),
        ("Xilinx Platform Cable USB II", "03fd:0008", ""),
    }


def test_a_jtag_cable_s_jtag_channel_is_not_a_serial_adapter_but_its_uarts_are(lab_host):
    ttys = {a.tty for a in _found(lab_host).serial}

    assert ttys == {"/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyUSB4", "/dev/ttyUSB5"}


def test_usb_sd_muxes_are_found_with_their_control_device_and_card(lab_host):
    (mux,) = _found(lab_host).sdmuxes  # the KVM's virtual drive (sg1) is not one

    assert (mux.serial, mux.sg, mux.disk) == (
        "000000001234",
        "/dev/sg0",
        f"/dev/disk/by-id/{_MUX_DISK}",
    )
    assert mux.partition == f"/dev/disk/by-id/{_MUX_DISK}-part1"


def test_a_mux_card_without_a_by_id_link_is_named_by_its_block_device(tmp_path):
    mux = _usb_device(tmp_path, "1-7", "0424", "4041", "Microchip", "USB2642", "000000001234")
    _usb_disk(tmp_path, mux, "sg2", "sdc", "sdmux HS-SD/MMC")

    (found,) = _found(tmp_path).sdmuxes

    assert (found.sg, found.disk, found.partition) == ("/dev/sg2", "/dev/sdc", "/dev/sdc1")


def test_vivado_installs_are_listed_newest_first_with_whether_xsdb_is_beside_them(lab_host):
    assert _found(lab_host).vivado == (
        discover.VivadoInstall("/tools/Xilinx/2025.2/Vivado", xsdb=False),
        discover.VivadoInstall("/tools/Xilinx/2025.1/Vivado", xsdb=True),
        discover.VivadoInstall("/opt/Xilinx/2024.2/Vivado_Lab", xsdb=False),
        discover.VivadoInstall("/tools/Xilinx/Vivado/2023.2", xsdb=False),
    )
    # The one a template's vivado_path can use as it is: XilinxVivadoTool runs the
    # xsdb in the Vitis beside it.
    assert _found(lab_host).vivado_path == "/tools/Xilinx/2025.1/Vivado"


def test_devices_exporter_configs_name_are_in_use(lab_host):
    found = _found(lab_host)
    used = {a.tty: a.used_by for a in found.serial}

    assert used == {
        # by its by-id link, in a config add-hardware deployed
        "/dev/ttyUSB0": "/etc/labgrid/exporters/zcu102-old/resources.yaml",
        "/dev/ttyUSB1": "",
        # by its tty, in the config a systemd unit runs the exporter with
        "/dev/ttyUSB4": "/home/lab/lg_tron.yaml",
        # by its USB serial number, in a udev match
        "/dev/ttyUSB5": "/etc/labgrid/rpi.yaml",
    }
    assert found.sdmuxes[0].used_by == "/etc/labgrid/exporters/zcu102-old/resources.yaml"
    assert [a.tty for a in found.free_serial] == ["/dev/ttyUSB1"]
    assert found.free_sdmuxes == ()


def test_a_udev_match_on_the_usb_port_marks_that_port_in_use(tmp_path):
    # labgrid resources often match ID_PATH; a multi-port adapter's ports differ by interface.
    cp2108 = _usb_device(tmp_path, "1-2", "10c4", "ea71", "Silicon Labs", "CP2108", "BCA68DE8")
    _usb_tty(tmp_path, cp2108, "00", "ttyUSB0", _CP2108)
    _usb_tty(tmp_path, cp2108, "01", "ttyUSB1", _CP2108.replace("if00", "if01"))
    mux = _usb_device(tmp_path, "1-14.1.1", "0424", "4041", "Microchip", "USB2642", "1143")
    _usb_disk(tmp_path, mux, "sg0", "sda", "sdmux HS-SD/MMC", _MUX_DISK)
    _write(
        tmp_path,
        "/etc/labgrid/exporter.yaml",
        "ADRV9002:\n"
        "  USBSerialPort:\n    match:\n      ID_PATH: pci-0000:00:14.0-usb-0:2:1.1\n"
        "  USBMassStorage:\n    match:\n"
        '      ID_PATH: "pci-0000:00:14.0-usb-0:14.1.1:1.0-scsi-0:0:0:0"\n',
    )

    found = _found(tmp_path)

    assert {a.tty: a.used_by for a in found.serial} == {
        "/dev/ttyUSB0": "",
        "/dev/ttyUSB1": "/etc/labgrid/exporter.yaml",
    }
    assert found.sdmuxes[0].used_by == "/etc/labgrid/exporter.yaml"


def test_a_config_exporting_an_sd_mux_it_doesn_t_name_takes_one(tmp_path):
    # labgrid's USBSDMuxDevice with no match uses whichever mux udev finds.
    for port, serial, sg in (("1-7", "000000001234", "sg0"), ("1-8", "000000005678", "sg1")):
        mux = _usb_device(tmp_path, port, "0424", "4041", "Microchip", "USB2642", serial)
        _usb_disk(tmp_path, mux, sg, f"sd{sg[-1]}", "sdmux HS-SD/MMC")
    _write(tmp_path, "/etc/labgrid/exporter.yaml", "ADRV9002:\n  USBSDMuxDevice:\n    {}\n")

    found = _found(tmp_path)

    assert found.sdmux_users == ("/etc/labgrid/exporter.yaml",)
    assert len(found.free_sdmuxes) == 1
    assert found.without("/etc/labgrid/exporter.yaml").free_sdmuxes == found.sdmuxes


def test_a_config_naming_the_mux_it_exports_takes_only_that_one(tmp_path):
    for port, serial, sg in (("1-7", "000000001234", "sg0"), ("1-8", "000000005678", "sg1")):
        mux = _usb_device(tmp_path, port, "0424", "4041", "Microchip", "USB2642", serial)
        _usb_disk(tmp_path, mux, sg, f"sd{sg[-1]}", "sdmux HS-SD/MMC")
    _write(tmp_path, "/etc/labgrid/a.yaml", 'A:\n  USBSDMuxDevice:\n    control_path: "/dev/sg0"\n')

    assert [m.sg for m in _found(tmp_path).free_sdmuxes] == ["/dev/sg1"]


def test_a_user_unit_s_exporter_config_is_found_through_its_home(tmp_path):
    cp2108 = _usb_device(tmp_path, "1-2", "10c4", "ea71", "Silicon Labs", "CP2108", "BCA68DE8")
    _usb_tty(tmp_path, cp2108, "00", "ttyUSB0", _CP2108)
    _write(
        tmp_path,
        "/home/lab/.config/systemd/user/labgrid-exporter.service",
        "[Service]\nExecStart=%h/venv/bin/labgrid-exporter %h/lg.yaml\n",
    )
    _write(tmp_path, "/home/lab/lg.yaml", "RPI:\n  RawSerialPort:\n    port: /dev/ttyUSB0\n")

    (adapter,) = _found(tmp_path).serial

    assert adapter.used_by == "/home/lab/lg.yaml"


def test_a_config_naming_another_link_to_a_device_marks_it_in_use(tmp_path):
    cp2108 = _usb_device(tmp_path, "1-2", "10c4", "ea71", "Silicon Labs", "CP2108", "BCA68DE8")
    _usb_tty(tmp_path, cp2108, "00", "ttyUSB0", _CP2108)
    by_path = "/dev/serial/by-path/pci-0000:00:14.0-usb-0:2:1.0-port0"
    _link(tmp_path, by_path, "/dev/ttyUSB0")
    _write(tmp_path, "/etc/labgrid/a.yaml", f"A:\n  RawSerialPort:\n    port: {by_path}\n")

    (adapter,) = _found(tmp_path).serial

    assert adapter.used_by == "/etc/labgrid/a.yaml"


def test_a_config_naming_a_partition_of_the_mux_s_card_marks_the_mux_in_use(tmp_path):
    mux = _usb_device(tmp_path, "1-7", "0424", "4041", "Microchip", "USB2642", "000000001234")
    _usb_disk(tmp_path, mux, "sg0", "sda", "sdmux HS-SD/MMC")
    _link(tmp_path, "/dev/disk/by-partuuid/a22286d2-01", "/dev/sda1")
    _write(
        tmp_path,
        "/etc/labgrid/a.yaml",
        'A:\n  MassStorageDevice:\n    path: "/dev/disk/by-partuuid/a22286d2-01"\n',
    )

    (found,) = _found(tmp_path).sdmuxes

    assert found.used_by == "/etc/labgrid/a.yaml"


def test_configs_that_export_a_jtag_device_are_counted(lab_host):
    found = _found(lab_host)

    assert found.jtag_users == ("/etc/labgrid/exporters/zcu102-old/resources.yaml",)
    # Three cables, one board using one: there is a free one.
    assert found.free_jtag


def test_no_cable_is_free_when_as_many_boards_use_jtag(tmp_path):
    _usb_device(tmp_path, "1-3", "0403", "6014", "Digilent", "Digilent USB Device", "2102")
    _link(tmp_path, "/sys/bus/usb/devices/1-3", f"{_USB}/1-3")
    _write(
        tmp_path, "/etc/labgrid/zu11eg.yaml", "ZU11EG:\n  XilinxDeviceJTAG:\n    root_target: 1\n"
    )

    found = _found(tmp_path)

    assert len(found.jtag) == 1
    assert not found.free_jtag


def test_this_board_s_own_config_doesn_t_make_its_devices_in_use(lab_host):
    own = "/etc/labgrid/exporters/zcu102-old/resources.yaml"

    found = _found(lab_host).without(own)

    assert {a.tty for a in found.free_serial} == {"/dev/ttyUSB0", "/dev/ttyUSB1"}
    assert found.free_sdmuxes == found.sdmuxes
    assert found.jtag_users == ()


def test_the_probe_prints_no_config_text(lab_host):
    # Exporter configs hold passwords; only paths and file names come back.
    assert "analog" not in _probe(lab_host)


def test_the_probe_never_opens_a_device_node(lab_host):
    # Opening a serial port toggles DTR/RTS, which resets some boards. A FIFO
    # blocks whoever opens it, so a probe that did would time out.
    for tty in ("ttyUSB0", "sg0", "sda"):
        (lab_host / "dev" / tty).unlink()
        os.mkfifo(lab_host / "dev" / tty)

    assert _found(lab_host).serial


def test_a_host_with_none_of_it_finds_nothing(tmp_path):
    assert _found(tmp_path) == discover.HostHardware()


class _FakeSSH:
    """sshmanager.get(host) -> a connection that runs commands here, through a shell."""

    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.hosts = reply, error, []

    def get(self, host):
        self.hosts.append(host)
        if self.error:
            raise self.error
        return self

    def run(self, command):
        if self.reply is not None:
            return self.reply
        out = subprocess.run(["sh", "-c", command], capture_output=True, text=True, timeout=60)
        return out.stdout.splitlines(), out.stderr.splitlines(), out.returncode


@pytest.fixture
def ssh(monkeypatch):
    def use(**kwargs):
        fake = _FakeSSH(**kwargs)
        monkeypatch.setattr("labgrid.util.ssh.sshmanager", fake)
        return fake

    return use


def test_the_probe_runs_on_the_exporter_host_over_ssh(lab_host, ssh):
    fake = ssh()

    found = discover.discover_host("lab-host-03", root=str(lab_host))

    assert fake.hosts == ["lab-host-03"]
    assert found == _found(lab_host)


def test_a_banner_printed_before_the_report_is_skipped(lab_host, ssh):
    ssh(reply=(["Welcome to lab-host-03!", _probe(lab_host).strip()], [], 0))

    assert discover.discover_host("lab-host-03") == _found(lab_host)


def test_a_host_that_can_t_be_reached_says_why(ssh):
    ssh(error=ExecutionError("ssh: connect to host lab-host-03 port 22: No route to host"))

    with pytest.raises(RuntimeError, match="No route to host"):
        discover.discover_host("lab-host-03")


def test_a_failed_ssh_connection_is_reported_by_ssh_s_own_reason(ssh):
    # labgrid's message lists every ssh argument before the reason.
    ssh(
        error=ExecutionError(
            "failed to connect to nohost with args ['ssh', '-x', '-o', 'LogLevel=ERROR', "
            "'nohost'], returncode=255 b'',b'ssh: Could not resolve hostname nohost: Name or "
            "service not known\\r\\n'"
        )
    )

    with pytest.raises(RuntimeError) as e:
        discover.discover_host("nohost")

    assert str(e.value) == "ssh: Could not resolve hostname nohost: Name or service not known"


def test_a_host_without_python3_says_so(ssh):
    ssh(reply=([], ["sh: 1: python3: not found"], 127))

    with pytest.raises(RuntimeError, match="python3: not found"):
        discover.discover_host("lab-host-03")


def test_output_that_is_not_the_probe_s_says_so(ssh):
    ssh(reply=(["Welcome to lab-host-03!"], [], 0))

    with pytest.raises(RuntimeError, match="unexpected output"):
        discover.discover_host("lab-host-03")
