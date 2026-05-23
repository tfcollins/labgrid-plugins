"""Tests for adi_lg_plugins.matlab_ci.run."""

from __future__ import annotations

import subprocess

from adi_lg_plugins.matlab_ci.run import (
    build_matlab_command,
    default_matlab_command,
    matlab_env,
    resolve_uri,
    run_matlab_tests,
)

# --- fakes for the labgrid surface --------------------------------------


class _FakeResource:
    def __init__(self, address):
        self.address = address


class _FakeStrategy:
    def __init__(self):
        self.transitions = []

    def transition(self, state):
        self.transitions.append(state)


class _FakeTarget:
    def __init__(self, address="10.0.0.57"):
        self.strategy = _FakeStrategy()
        self._resource = _FakeResource(address)
        self.driver_requested = None

    def get_driver(self, name):
        self.driver_requested = name
        return self.strategy

    def get_resource(self, name):
        self.resource_requested = name
        return self._resource


class _FakeEnv:
    def __init__(self, config):
        self.config = config
        self.target = _FakeTarget()

    def get_target(self, name):
        self.target_requested = name
        return self.target


# --- pure helpers --------------------------------------------------------


def test_resolve_uri_prefixes_ip():
    assert resolve_uri(_FakeTarget(address="10.0.0.57")) == "ip:10.0.0.57"


def test_build_matlab_command():
    cmd = build_matlab_command("matlab", "disp('hi')")
    assert cmd == ["matlab", "-nodisplay", "-nosplash", "-batch", "disp('hi')"]


def test_matlab_env_sets_uri_and_board_without_mutating_base():
    base = {"PATH": "/bin", "HOME": "/h"}
    env = matlab_env(base, "ip:10.0.0.57", "zynqmp-zcu102-rev10-adrv9002-vcmos")
    assert env["IIO_URI"] == "ip:10.0.0.57"
    assert env["board"] == "zynqmp-zcu102-rev10-adrv9002-vcmos"
    assert env["PATH"] == "/bin"
    assert "IIO_URI" not in base  # base dict untouched


def test_default_matlab_command_runs_runhwtests():
    cmd = default_matlab_command()
    assert "runHWTests" in cmd
    assert "addpath(genpath('test'))" in cmd


# --- orchestrator --------------------------------------------------------


def _runner_ok(captured):
    def runner(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(cmd, 0)

    return runner


def test_run_boots_resolves_and_launches(tmp_path):
    captured = {}
    env = _FakeEnv("ignored")
    result = run_matlab_tests(
        config=tmp_path / "env.yaml",
        matlab_board="zynqmp-zcu102-rev10-adrv9002-vcmos",
        boot_strategy="BootFPGASoC",
        repo_dir=tmp_path,
        matlab_bin="matlab",
        reached_state="shell",
        env_factory=lambda c: env,
        runner=_runner_ok(captured),
        base_env={"PATH": "/bin"},
    )
    # booted via the place's strategy to the requested state
    assert env.target.driver_requested == "BootFPGASoC"
    assert env.target.strategy.transitions == ["shell"]
    # URI resolved and handed to MATLAB
    assert result.uri == "ip:10.0.0.57"
    assert captured["kwargs"]["env"]["IIO_URI"] == "ip:10.0.0.57"
    assert captured["kwargs"]["env"]["board"] == "zynqmp-zcu102-rev10-adrv9002-vcmos"
    assert captured["kwargs"]["cwd"] == str(tmp_path)
    assert captured["cmd"][0] == "matlab"
    assert result.returncode == 0


def test_run_copies_junit_when_requested(tmp_path):
    # MATLAB writes <board>_HWTestResults.xml into repo_dir
    board = "zynqmp-zcu102-rev10-adrv9002-vcmos"

    def runner(cmd, **kwargs):
        (tmp_path / f"{board}_HWTestResults.xml").write_text("<testsuite/>", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0)

    dest = tmp_path / "out" / "junit.xml"
    result = run_matlab_tests(
        config=tmp_path / "env.yaml",
        matlab_board=board,
        boot_strategy="BootFPGASoC",
        repo_dir=tmp_path,
        env_factory=lambda c: _FakeEnv("x"),
        runner=runner,
        junit_dest=dest,
    )
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == "<testsuite/>"
    assert result.junit_dest == dest


def test_run_propagates_nonzero_exit(tmp_path):
    def runner(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 2)

    result = run_matlab_tests(
        config=tmp_path / "env.yaml",
        matlab_board="b",
        boot_strategy="BootFPGASoC",
        repo_dir=tmp_path,
        env_factory=lambda c: _FakeEnv("x"),
        runner=runner,
    )
    assert result.returncode == 2


def test_run_missing_junit_source_is_not_fatal(tmp_path):
    # runner exits 0 but never writes the XML; copy is best-effort
    def runner(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0)

    dest = tmp_path / "junit.xml"
    result = run_matlab_tests(
        config=tmp_path / "env.yaml",
        matlab_board="b",
        boot_strategy="BootFPGASoC",
        repo_dir=tmp_path,
        env_factory=lambda c: _FakeEnv("x"),
        runner=runner,
        junit_dest=dest,
    )
    assert result.returncode == 0
    assert result.junit_dest is None  # nothing copied
    assert not dest.exists()


def test_run_skip_boot_does_not_transition(tmp_path):
    """With skip_boot=True the strategy is never touched (used when the
    board is already up / acquired out-of-band)."""
    captured = {}
    env = _FakeEnv("x")
    result = run_matlab_tests(
        config=tmp_path / "env.yaml",
        matlab_board="b",
        boot_strategy="BootFPGASoC",
        repo_dir=tmp_path,
        env_factory=lambda c: env,
        runner=_runner_ok(captured),
        skip_boot=True,
    )
    # no driver lookup, no transition
    assert env.target.driver_requested is None
    assert env.target.strategy.transitions == []
    # URI was still resolved from NetworkService
    assert result.uri == "ip:10.0.0.57"
    assert captured["kwargs"]["env"]["IIO_URI"] == "ip:10.0.0.57"


def test_run_resolves_custom_network_resource(tmp_path):
    captured = {}
    env = _FakeEnv("x")
    run_matlab_tests(
        config=tmp_path / "env.yaml",
        matlab_board="b",
        boot_strategy="BootFPGASoC",
        repo_dir=tmp_path,
        env_factory=lambda c: env,
        runner=_runner_ok(captured),
        network_resource="MyNetSvc",
    )
    assert env.target.resource_requested == "MyNetSvc"
