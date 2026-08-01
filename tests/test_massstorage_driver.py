"""Unit tests for MassStorageDriver's use of RemoteExecMixin.

Construct the driver bypassing labgrid binding machinery (as test_xilinx_jtag
does) and assert mount/copy route through the mixin's remote-exec methods.
"""

import logging
import subprocess
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
    d.unmount_retries = 3
    d.unmount_retry_delay = 0.0
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


def _busy_error():
    return subprocess.CalledProcessError(1, ["pumount", "lg_mass_storage"])


def test_unmount_retries_then_succeeds_when_busy_clears():
    d = _driver(types.SimpleNamespace(path="/dev/sdb1", extra={"proxy": "exp.host"}))
    # mountpoint: initial True; after 1st busy pumount still True; after
    # 2nd pumount succeeds -> not a mountpoint.
    with (
        mock.patch.object(d, "_is_mountpoint", side_effect=[True, True, False]),
        mock.patch.object(d, "_remote_run"),
        mock.patch.object(d, "_remote_check", side_effect=[_busy_error(), None]) as check,
        mock.patch("time.sleep"),
    ):
        d.unmount_partition()

    assert check.call_count == 2
    assert d.mounted is False


def test_unmount_falls_back_to_lazy_umount_when_persistently_busy():
    d = _driver(types.SimpleNamespace(path="/dev/sdb1", extra={"proxy": "exp.host"}))
    d.unmount_retries = 2
    lazy_calls = []

    def fake_run(cmd, check=False):
        lazy_calls.append(list(cmd))
        return mock.Mock(returncode=0)

    # _is_mountpoint calls: initial(True) + busy re-check x2 (True,True)
    # + post-lazy check (False).
    mp_states = [True, True, True, False]
    with (
        mock.patch.object(d, "_is_mountpoint", side_effect=mp_states),
        mock.patch.object(d, "_remote_run", side_effect=fake_run),
        mock.patch.object(d, "_remote_check", side_effect=_busy_error()),
        mock.patch("time.sleep"),
    ):
        d.unmount_partition()

    assert ["umount", "-l", "/media/lg_mass_storage"] in lazy_calls
    assert d.mounted is False


def test_unmount_raises_when_lazy_fallback_also_fails():
    d = _driver(types.SimpleNamespace(path="/dev/sdb1", extra={"proxy": "exp.host"}))
    d.unmount_retries = 1

    def fake_run(cmd, check=False):
        return mock.Mock(returncode=1)  # lazy umount fails too

    with (
        mock.patch.object(d, "_is_mountpoint", return_value=True),
        mock.patch.object(d, "_remote_run", side_effect=fake_run),
        mock.patch.object(d, "_remote_check", side_effect=_busy_error()),
        mock.patch("time.sleep"),
    ):
        try:
            d.unmount_partition()
        except subprocess.CalledProcessError:
            pass
        else:  # pragma: no cover
            raise AssertionError("expected CalledProcessError to propagate")


def test_unmount_returns_when_pumount_errors_but_already_gone():
    d = _driver(types.SimpleNamespace(path="/dev/sdb1", extra={"proxy": "exp.host"}))
    # initial mountpoint True; the busy re-check shows it's gone.
    with (
        mock.patch.object(d, "_is_mountpoint", side_effect=[True, False]),
        mock.patch.object(d, "_remote_run"),
        mock.patch.object(d, "_remote_check", side_effect=_busy_error()),
        mock.patch("time.sleep"),
    ):
        d.unmount_partition()

    assert d.mounted is False
