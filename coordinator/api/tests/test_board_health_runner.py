"""Tests for HealthCheckRunner process stopping (timeout/cancel teardown)."""

from __future__ import annotations

import asyncio
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from app.board_health import runner as runner_mod
from app.board_health.runner import HealthCheckRunner
from app.board_health.store import BoardHealthStore

# A stand-in for `adi-lg health-check`: blocks, and on SIGINT runs its
# `finally` (the real CLI's teardown: power off + release) before exiting.
CHILD_GRACEFUL = """
import sys, time
print("started", flush=True)
try:
    time.sleep(60)
except KeyboardInterrupt:
    pass
finally:
    print("teardown ran", flush=True)
sys.exit(1)
"""

CHILD_STUBBORN = """
import signal, time
signal.signal(signal.SIGINT, signal.SIG_IGN)
print("started", flush=True)
time.sleep(60)
"""


async def _spawn(code: str) -> asyncio.subprocess.Process:
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", code, stdout=asyncio.subprocess.PIPE
    )
    assert (await proc.stdout.readline()).strip() == b"started"
    return proc


@pytest.mark.asyncio
async def test_stop_process_sigint_lets_child_run_teardown():
    proc = await _spawn(CHILD_GRACEFUL)
    await HealthCheckRunner._stop_process(proc, grace=10)
    rest = await proc.stdout.read()
    assert b"teardown ran" in rest
    assert proc.returncode == 1  # exited itself, not SIGKILLed


@pytest.mark.asyncio
async def test_stop_process_kills_child_that_ignores_sigint():
    proc = await _spawn(CHILD_STUBBORN)
    await HealthCheckRunner._stop_process(proc, grace=0.5)
    assert proc.returncode == -9


@pytest.mark.asyncio
async def test_stop_process_noop_when_already_exited():
    proc = await asyncio.create_subprocess_exec(sys.executable, "-c", "pass")
    await proc.wait()
    await HealthCheckRunner._stop_process(proc, grace=0.1)


@pytest_asyncio.fixture
async def runner_env(monkeypatch):
    with tempfile.NamedTemporaryFile(suffix=".db") as fh:
        db_path = fh.name
    store = BoardHealthStore(db_path)
    await store.initialize()
    client = MagicMock()
    client.allow_place = AsyncMock()
    runner = HealthCheckRunner(store, client)
    runner._release_place = AsyncMock()

    real_exec = asyncio.create_subprocess_exec

    async def fake_exec(*cmd, **kwargs):
        assert cmd[0] == "adi-lg"
        return await real_exec(sys.executable, "-c", CHILD_GRACEFUL, **kwargs)

    monkeypatch.setattr(runner_mod.asyncio, "create_subprocess_exec", fake_exec)
    return store, runner


@pytest.mark.asyncio
async def test_timeout_runs_cli_teardown_then_releases_place(runner_env):
    store, runner = runner_env
    run = await store.create_run(
        place_name="vpk180", trigger="manual", triggered_by="t", schedule_id=None, image=None
    )
    await runner._execute_check(
        run_id=run.id,
        place_name="vpk180",
        image=None,
        power_down=True,
        timeout=1.0,
    )
    r = await store.get_run(run.id)
    assert r.status == "failed"
    assert "timed out" in r.error_message
    assert "teardown ran" in r.log_output
    runner._release_place.assert_awaited_once()
    assert runner._release_place.await_args.args[0] == "vpk180"
    env = runner._release_place.await_args.args[1]
    assert env["LG_HOSTNAME"] == runner_mod.settings.api_name


@pytest.mark.asyncio
async def test_cancel_stops_child_and_releases_place(runner_env):
    store, runner = runner_env
    run = await store.create_run(
        place_name="vpk180", trigger="manual", triggered_by="t", schedule_id=None, image=None
    )
    runner.start_check(run_id=run.id, place_name="vpk180", timeout=60)
    for _ in range(100):
        if run.id in runner._active_processes:
            break
        await asyncio.sleep(0.05)
    await asyncio.sleep(0.3)  # let the child install its handlers
    assert await runner.cancel_run(run.id)
    r = await store.get_run(run.id)
    assert r.status == "cancelled"
    runner._release_place.assert_awaited_once()
