from unittest.mock import patch

from adi_lg_plugins.tools.runner_setup import runner
from adi_lg_plugins.tools.runner_setup.models import (
    GitHubScope,
    HardwareMode,
    RunnerConfig,
)


@patch("platform.machine")
def test_detect_architecture(mock_machine):
    mock_machine.return_value = "x86_64"
    assert runner.detect_architecture() == "x64"

    mock_machine.return_value = "aarch64"
    assert runner.detect_architecture() == "arm64"

    mock_machine.return_value = "armv7l"
    assert runner.detect_architecture() == "arm"


def test_get_runner_download_url():
    url, tarball = runner.get_runner_download_url("2.322.0", "x64")
    assert tarball == "actions-runner-linux-x64-2.322.0.tar.gz"
    assert "releases/download/v2.322.0/actions-runner-linux-x64-2.322.0.tar.gz" in url


def test_write_runner_env_exporter(tmp_path):
    scope = GitHubScope.parse("repo:owner/repo")
    cfg = RunnerConfig(
        mode=HardwareMode.EXPORTER,
        scope=scope,
        install_dir=tmp_path,
        coordinator="10.0.0.41:20408",
    )
    env_file = runner.write_runner_env(cfg)
    content = env_file.read_text(encoding="utf-8")
    assert "LG_COORDINATOR=10.0.0.41:20408" in content


def test_write_runner_env_direct(tmp_path):
    scope = GitHubScope.parse("repo:owner/repo")
    dummy_yaml = tmp_path / "env.yaml"
    dummy_yaml.write_text("targets: {}")
    cfg = RunnerConfig(
        mode=HardwareMode.DIRECT,
        scope=scope,
        install_dir=tmp_path,
        direct_env_file=dummy_yaml,
    )
    env_file = runner.write_runner_env(cfg)
    content = env_file.read_text(encoding="utf-8")
    assert f"LG_DIRECT_ENV={dummy_yaml.resolve()}" in content


@patch("subprocess.run")
def test_configure_runner(mock_run, tmp_path):
    scope = GitHubScope.parse("repo:owner/repo")
    cfg = RunnerConfig(
        mode=HardwareMode.EXPORTER,
        scope=scope,
        name="test-runner",
        labels=["hw-lab"],
        install_dir=tmp_path,
        token="DUMMY_TOKEN",
        coordinator="10.0.0.41:20408",
    )
    config_sh = tmp_path / "config.sh"
    config_sh.write_text("#!/bin/sh\n")

    runner.configure_runner(cfg)

    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == str(config_sh)
    assert "--url" in args
    assert "https://github.com/owner/repo" in args
    assert "--token" in args
    assert "DUMMY_TOKEN" in args
    assert "--name" in args
    assert "test-runner" in args
    assert "--labels" in args
    assert "self-hosted,hw-lab" in args
