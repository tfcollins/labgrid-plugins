"""Unit tests for TickFpgaManagerDriver (constructed without labgrid binding)."""

import logging
import types
from unittest import mock

import pytest
from labgrid.driver.exception import ExecutionError

from adi_lg_plugins.drivers.tickfpgamanagerdriver import TickFpgaManagerDriver


def _driver(run_check_returns):
    d = TickFpgaManagerDriver.__new__(TickFpgaManagerDriver)
    d.artifacts = types.SimpleNamespace(bitstream_path="/run/tick.bit", firmware_name="tick.bit")
    d.command = types.SimpleNamespace(run_check=mock.Mock(side_effect=run_check_returns))
    d.fs = types.SimpleNamespace(put=mock.Mock())
    d.logger = logging.getLogger("test_tickfpga")
    return d


def test_load_bitstream_puts_and_writes_firmware_sysfs():
    d = _driver([[], ["operating"]])  # echo -> empty, cat state -> operating
    d.load_bitstream()

    d.fs.put.assert_called_once_with("/run/tick.bit", "/lib/firmware/tick.bit")
    cmds = [c.args[0] for c in d.command.run_check.call_args_list]
    assert any("/sys/class/fpga_manager/fpga0/firmware" in c and "tick.bit" in c for c in cmds)
    assert any("cat /sys/class/fpga_manager/fpga0/state" in c for c in cmds)


def test_load_bitstream_raises_when_not_operating():
    d = _driver([[], ["unknown"]])
    with pytest.raises(ExecutionError):
        d.load_bitstream()
