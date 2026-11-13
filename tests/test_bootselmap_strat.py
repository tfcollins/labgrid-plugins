"""Unit tests for BootSelMap: rebooting to apply freshly staged boot files.

update_zynq_boot_files SCPs a kernel/devicetree to the board's /boot/ over SSH.
Without an explicit reboot, those files only take effect on some later boot —
this run's own pre_load_commands / SelMap boot would proceed against whatever
was already running, not what was just staged.
"""

import logging
import threading
from types import SimpleNamespace
from unittest import mock

import pytest
from labgrid.remote.common import ResourceEntry
from labgrid.resource.networkservice import NetworkService
from labgrid.resource.remote import RemotePlaceManager
from labgrid.strategy import StrategyError

from adi_lg_plugins.strategies.bootselmap import BootSelMap, Status


@pytest.fixture(autouse=True)
def _no_real_sleep():
    with mock.patch("adi_lg_plugins.strategies.bootselmap.time.sleep"):
        yield


def _strategy(tmp_path, *, kernel=True, devicetree=True, initial_status=Status.unknown):
    s = BootSelMap.__new__(BootSelMap)
    s.status = initial_status
    s.target = mock.MagicMock()
    s.logger = logging.getLogger("test_bootselmap")
    s.power = mock.MagicMock()
    s.shell = mock.MagicMock()
    s.ssh = mock.MagicMock()
    s.reached_linux_marker = "analog"
    s.ethernet_interface = "eth0"
    s.pre_load_commands = None
    s.target_dut_folder = "/boot/ci"
    s.selmap_boot_script_name = "selmap_dtbo.sh"
    s.boot_log = ""
    s._copied_pre_boot_files = False
    s._copied_post_boot_files = False
    s._rebooted_after_boot_file_update = False

    kernel_file = tmp_path / "Image"
    kernel_file.write_text("kernel")
    dt_file = tmp_path / "system.dtb"
    dt_file.write_text("dt")

    s.local_kernel_filename = str(kernel_file) if kernel else None
    s.local_device_tree_filename = str(dt_file) if devicetree else None
    s.local_bitstream_filename = None
    s.local_overlay_filename = None
    s.pre_boot_boot_files = None
    s.post_boot_boot_files = None

    addr = mock.MagicMock()
    addr.ip = "10.0.0.5"
    s.shell.get_ip_addresses.return_value = [addr]
    s.ssh.networkservice.address = "10.0.0.5"
    s.shell.console.expect.return_value = (0, b"", b"", b"")

    return s


def test_update_zynq_boot_files_reboots_when_kernel_and_dt_staged(tmp_path):
    s = _strategy(tmp_path)

    s.transition(Status.update_zynq_boot_files)

    s.ssh.put.assert_any_call(s.local_kernel_filename, "/boot/Image")
    s.ssh.put.assert_any_call(s.local_device_tree_filename, "/boot/system.dtb")
    s.power.off.assert_called()
    s.power.on.assert_called()
    # Reboot left in progress (early return) for the caller's chain to continue from.
    assert s.status == Status.powered_off
    assert s._rebooted_after_boot_file_update is True


def test_power_activation_deadline_leaves_stage_incomplete(tmp_path, monkeypatch):
    s = _strategy(tmp_path)
    monkeypatch.setenv("LG_SM_STAGE_TIMEOUT", "0.05")
    s.target.activate.side_effect = lambda driver: threading.Event().wait()
    with pytest.raises(StrategyError, match="activate power"):
        s.transition(Status.powered_off)
    s.power.off.assert_not_called()
    assert s.status == Status.unknown


@pytest.mark.parametrize("live_address", ["192.0.2.1", "10.0.0.5"])
def test_discovered_ssh_address_survives_real_resource_refresh(tmp_path, live_address):
    s = _strategy(tmp_path, devicetree=False, initial_status=Status.booted_zynq)
    resource = NetworkService(
        target=None,
        name=None,
        address=live_address,
        port=22,
        username="root",
        password="test-password",
    )
    entry = ResourceEntry(
        {
            "cls": "NetworkService",
            "params": {
                "address": "192.0.2.1",
                "port": 22,
                "username": "root",
                "password": "test-password",
            },
            "avail": True,
        }
    )
    resource._remote_entry = entry
    manager = RemotePlaceManager.__new__(RemotePlaceManager)
    manager.resources = []
    manager.unmanaged_resources = [resource]
    manager.loop = SimpleNamespace(is_running=lambda: True)
    manager.logger = logging.getLogger("test_remote_refresh")
    s.ssh.networkservice = resource
    destinations = []

    def activate(driver):
        if driver is s.ssh:
            manager.poll()  # Real labgrid poll rewrites fields from ResourceEntry.
            destinations.append(resource.address)

    s.target.activate.side_effect = activate
    s.transition(Status.update_zynq_boot_files)
    assert destinations and set(destinations) == {"10.0.0.5"}
    assert entry.args["address"] == "10.0.0.5"
    assert entry.args["password"] == "test-password"
    assert entry.args["port"] == 22


def test_update_zynq_boot_files_no_reboot_without_staged_files(tmp_path):
    # Start already booted so the only power activity possible is the
    # reboot-to-apply-new-files path under test.
    s = _strategy(tmp_path, kernel=False, devicetree=False, initial_status=Status.booted_zynq)

    s.transition(Status.update_zynq_boot_files)

    s.power.off.assert_not_called()
    s.power.on.assert_not_called()
    assert s.status == Status.update_zynq_boot_files


def test_update_zynq_boot_files_reboots_only_once(tmp_path):
    s = _strategy(tmp_path)

    s.transition(Status.update_zynq_boot_files)
    assert s.status == Status.powered_off

    s.power.reset_mock()
    s.transition(Status.update_zynq_boot_files)

    s.power.off.assert_not_called()
    assert s.status == Status.update_zynq_boot_files
