"""Unit tests for MassStorageDriver's use of RemoteExecMixin.

Construct the driver bypassing labgrid binding machinery (as test_xilinx_jtag
does) and assert mount/copy route through the mixin's remote-exec methods.
"""

import logging
import types
from unittest import mock

from adi_lg_plugins.drivers.massstoragedriver import MassStorageDriver


def _driver(resource):
    d = MassStorageDriver.__new__(MassStorageDriver)
    d.mass_storage = resource
    d.partition = None
    d.mount_label = "lg_mass_storage"
    d.mounted = True
    d.logger = logging.getLogger("test_massstorage")
    return d


def test_copy_file_remote_uses_remote_put(tmp_path):
    src = tmp_path / "boot.bin"
    src.write_text("payload")
    d = _driver(types.SimpleNamespace(path="/dev/sdb1", extra={"proxy": "exp.host"}))

    with (
        mock.patch.object(d, "_remote_check") as check,
        mock.patch.object(d, "_remote_put") as put,
    ):
        d.copy_file(str(src), "BOOT.BIN")

    check.assert_called_once()  # mkdir -p on the mount point
    assert check.call_args[0][0][0] == "mkdir"
    put.assert_called_once()
    local_arg, remote_arg = put.call_args[0]
    assert local_arg == str(src)
    assert remote_arg == "/media/lg_mass_storage/BOOT.BIN"
    d.mounted = False  # avoid __del__ -> real ssh unmount at GC time


def test_copy_file_local_uses_shutil(tmp_path):
    src = tmp_path / "boot.bin"
    src.write_text("payload")
    mount = tmp_path / "media"
    mount.mkdir()  # local copy needs the mount dir to exist (mkdir is mocked out)
    d = _driver(types.SimpleNamespace(path="/dev/sdb1", extra={}))

    with (
        mock.patch.object(d, "_remote_check"),
        mock.patch.object(d, "_mount_dir", return_value=str(mount)),
        mock.patch.object(d, "_remote_put") as put,
    ):
        d.copy_file(str(src), "BOOT.BIN")

    put.assert_not_called()
    assert (mount / "BOOT.BIN").read_text() == "payload"


def test_mount_partition_routes_through_remote_check():
    d = _driver(types.SimpleNamespace(path="/dev/sdb1", extra={"proxy": "exp.host"}))
    d.mounted = False
    calls = []

    def fake_run(cmd, check=False):
        calls.append(list(cmd))
        return mock.Mock(returncode=0)

    with (
        mock.patch.object(d, "_remote_run", side_effect=fake_run),
        mock.patch.object(d, "_remote_check", side_effect=lambda cmd: fake_run(cmd, check=True)),
        mock.patch("time.sleep"),
    ):
        # _is_mountpoint -> False first (not mounted), test -e -> True, then
        # after pmount _is_mountpoint -> True. Simplify by forcing mountpoint
        # checks via the real _is_mountpoint using fake_run returncodes.
        with (
            mock.patch.object(d, "_is_mountpoint", side_effect=[False, True]),
            mock.patch.object(d, "_path_exists", return_value=True),
        ):
            d.mount_partition()

    assert ["pmount", "/dev/sdb1", "lg_mass_storage"] in calls
    assert d.mounted is True
    d.mounted = False  # avoid __del__ -> real ssh unmount at GC time


def test_mount_partition_repairs_stale_mounted_state():
    d = _driver(types.SimpleNamespace(path="/dev/sdb1", extra={"proxy": "exp.host"}))
    calls = []

    def fake_check(cmd):
        calls.append(list(cmd))

    with (
        mock.patch.object(d, "_is_mountpoint", side_effect=[False, False, True]),
        mock.patch.object(d, "_path_exists", return_value=True),
        mock.patch.object(d, "_remote_check", side_effect=fake_check),
        mock.patch("time.sleep"),
    ):
        d.mount_partition()

    assert ["pmount", "/dev/sdb1", "lg_mass_storage"] in calls
    assert d.mounted is True
    d.mounted = False


def test_unmount_partition_accepts_already_unmounted_device():
    d = _driver(types.SimpleNamespace(path="/dev/sdb1", extra={"proxy": "exp.host"}))

    with (
        mock.patch.object(d, "_is_mountpoint", return_value=False),
        mock.patch.object(d, "_remote_run") as run,
        mock.patch.object(d, "_remote_check") as check,
    ):
        d.unmount_partition()

    run.assert_not_called()
    check.assert_not_called()
    assert d.mounted is False
