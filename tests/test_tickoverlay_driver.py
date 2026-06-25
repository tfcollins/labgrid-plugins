"""Unit tests for TickOverlayDriver."""

import logging
import types
from unittest import mock

import pytest
from labgrid.driver.exception import ExecutionError

from adi_lg_plugins.drivers.tickoverlaydriver import TickOverlayDriver


def _driver(run_check_returns):
    d = TickOverlayDriver.__new__(TickOverlayDriver)
    d.artifacts = types.SimpleNamespace(
        overlay_dtbo_path="/run/tick.dtbo", overlay_name="tick", remote_dir="/tmp/tick"
    )
    d.command = types.SimpleNamespace(
        run_check=mock.Mock(side_effect=run_check_returns), run=mock.Mock(return_value=([], [], 0))
    )
    d.fs = types.SimpleNamespace(put=mock.Mock())
    d.logger = logging.getLogger("test_tickoverlay")
    return d


def test_apply_stages_dtbo_and_applies_overlay():
    # run_check order: mkdir remote, mount-check, mkdir overlay, cat>dtbo, cat status
    d = _driver([[], [], [], [], ["applied"]])
    d.apply()

    d.fs.put.assert_called_once_with("/run/tick.dtbo", "/tmp/tick/tick.dtbo")
    cmds = [c.args[0] for c in d.command.run_check.call_args_list]
    assert any("/sys/kernel/config/device-tree/overlays/tick/dtbo" in c for c in cmds)
    assert any("/sys/kernel/config/device-tree/overlays/tick/status" in c for c in cmds)


def test_apply_raises_when_status_not_applied():
    d = _driver([[], [], [], [], ["unapplied"]])
    with pytest.raises(ExecutionError):
        d.apply()


def test_remove_rmdirs_overlay():
    d = _driver([])
    d.remove()
    assert any(
        "rmdir" in c.args[0] and "overlays/tick" in c.args[0] for c in d.command.run.call_args_list
    )
