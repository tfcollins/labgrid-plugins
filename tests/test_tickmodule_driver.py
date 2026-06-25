"""Unit tests for TickModuleDriver."""

import logging
import types
from unittest import mock

import pytest
from labgrid.driver.exception import ExecutionError

from adi_lg_plugins.drivers.tickmoduledriver import TickModuleDriver


def _driver(*, run_returns, run_check_returns, restart_iiod=True, force=True):
    d = TickModuleDriver.__new__(TickModuleDriver)
    d.artifacts = types.SimpleNamespace(
        module_ko_path="/run/axi_timed_command_scheduler.ko", remote_dir="/tmp/tick"
    )
    d.restart_iiod = restart_iiod
    d.force_on_vermagic_mismatch = force
    d.command = types.SimpleNamespace(
        run=mock.Mock(side_effect=run_returns),
        run_check=mock.Mock(side_effect=run_check_returns),
    )
    d.fs = types.SimpleNamespace(put=mock.Mock())
    d.logger = logging.getLogger("test_tickmodule")
    return d


def test_load_inserts_module_and_restarts_iiod():
    # run: rmmod (ok), insmod (ok); run_check: mkdir, modinfo, uname, restart iiod
    d = _driver(
        run_returns=[([], [], 0), ([], [], 0)],
        run_check_returns=[[], ["6.1.0-xilinx SMP mod_unload"], ["6.1.0-xilinx"], []],
    )
    d.load()

    d.fs.put.assert_called_once_with(
        "/run/axi_timed_command_scheduler.ko", "/tmp/tick/axi_timed_command_scheduler.ko"
    )
    run_cmds = [c.args[0] for c in d.command.run.call_args_list]
    assert any(c.startswith("insmod ") for c in run_cmds)
    check_cmds = [c.args[0] for c in d.command.run_check.call_args_list]
    assert any("systemctl restart iiod" in c for c in check_cmds)


def test_load_skips_iiod_when_disabled():
    d = _driver(
        run_returns=[([], [], 0), ([], [], 0)],
        run_check_returns=[[], ["6.1.0-xilinx"], ["6.1.0-xilinx"]],
        restart_iiod=False,
    )
    d.load()
    check_cmds = [c.args[0] for c in d.command.run_check.call_args_list]
    assert not any("iiod" in c for c in check_cmds)


def test_load_force_inserts_on_insmod_failure():
    # insmod fails (rc=1) -> force=y via run_check
    d = _driver(
        run_returns=[([], [], 0), ([], ["bad"], 1)],
        run_check_returns=[[], ["5.0-foo"], ["6.1.0-xilinx"], [], []],
        force=True,
    )
    d.load()
    check_cmds = [c.args[0] for c in d.command.run_check.call_args_list]
    assert any("force=y" in c for c in check_cmds)


def test_load_raises_without_force_on_insmod_failure():
    d = _driver(
        run_returns=[([], [], 0), ([], ["bad"], 1)],  # rmmod ok, insmod fails
        run_check_returns=[[], ["6.1.0-xilinx"], ["6.1.0-xilinx"]],  # mkdir, modinfo, uname
        restart_iiod=True,
        force=False,
    )
    with pytest.raises(ExecutionError):
        d.load()


def test_unload_rmmods_module():
    d = _driver(run_returns=[([], [], 0)], run_check_returns=[])
    d.unload()
    run_cmds = [c.args[0] for c in d.command.run.call_args_list]
    assert any("rmmod" in c and "axi_timed_command_scheduler" in c for c in run_cmds)
