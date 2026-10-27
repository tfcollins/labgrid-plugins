"""Unit tests for adi_lg_plugins.tools.netbox.provision.

The rendering/validation tests run against this repo's own real
exporter_configs/ (templates + validate.py) - that's exactly the artifact
under test, nothing to mock there. The SSH-deploy tests mock
`labgrid.util.ssh.sshmanager` so no real network/subprocess call is made.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import labgrid.util.ssh as ssh_mod
import pytest
from labgrid.driver.exception import ExecutionError

from adi_lg_plugins.tools.netbox import provision

REPO_ROOT = Path(__file__).resolve().parents[1]
EXPORTER_CONFIGS_DIR = REPO_ROOT / "exporter_configs"


def test_find_exporter_configs_dir_from_repo_root():
    assert provision.find_exporter_configs_dir(REPO_ROOT) == EXPORTER_CONFIGS_DIR


def test_find_exporter_configs_dir_walks_upward(tmp_path):
    nested = tmp_path / "a" / "b" / "c"
    nested.mkdir(parents=True)
    (tmp_path / "exporter_configs").mkdir()
    (tmp_path / "exporter_configs" / "validate.py").write_text("")

    assert provision.find_exporter_configs_dir(nested) == tmp_path / "exporter_configs"


def test_find_exporter_configs_dir_raises_when_missing(tmp_path):
    with pytest.raises(RuntimeError, match="exporter_configs"):
        provision.find_exporter_configs_dir(tmp_path)


def test_discover_template_vars_zcu102():
    template = EXPORTER_CONFIGS_DIR / "templates" / "zcu102.yaml"
    names = provision.discover_template_vars(template)
    assert {"exporter_name", "target_ip", "chip", "serial_port", "sdmux_path"} <= names


def test_render_and_validate_zcu102_round_trips_group_name():
    template = EXPORTER_CONFIGS_DIR / "templates" / "zcu102.yaml"
    context = {"exporter_name": "lab-host-03", "target_ip": "10.0.0.5"}

    path, groups = provision.render_and_validate(template, context, EXPORTER_CONFIGS_DIR)

    assert path.exists()
    assert groups == ["ZCU102_AD9081"]


def test_render_and_validate_missing_required_field_raises():
    template = EXPORTER_CONFIGS_DIR / "templates" / "zcu102.yaml"
    with pytest.raises(RuntimeError, match="missing a required field"):
        provision.render_and_validate(template, {"exporter_name": "h"}, EXPORTER_CONFIGS_DIR)


def test_unit_text_shape():
    text = provision._unit_text("coord:20408", "rack1", "labuser")
    assert "ExecStart=/usr/local/bin/labgrid-exporter -c coord:20408 -n rack1 " in text
    assert "User=labuser" in text
    assert "Restart=always" in text
    assert "WantedBy=multi-user.target" in text


def _fake_conn():
    conn = MagicMock()
    conn.run_check.return_value = []
    return conn


def test_check_prerequisites_raises_when_exporter_missing(monkeypatch):
    conn = _fake_conn()
    conn.run_check.side_effect = ExecutionError("command -v labgrid-exporter", [], ["not found"])
    monkeypatch.setattr(ssh_mod.sshmanager, "get", lambda host: conn)

    with pytest.raises(RuntimeError, match="not found on"):
        provision.check_prerequisites("lab-host-03")


def test_deploy_exporter_stages_and_installs(tmp_path, monkeypatch):
    conn = _fake_conn()
    monkeypatch.setattr(ssh_mod.sshmanager, "get", lambda host: conn)

    rendered = tmp_path / "resources.yaml"
    rendered.write_text("exporter: {}\n")

    provision.deploy_exporter("lab-host-03", "labuser", "rack1", rendered, "coord:20408")

    put_calls = [c.args for c in conn.put_file.call_args_list]
    assert put_calls[0][0] == str(rendered)
    assert put_calls[0][1].endswith("/resources.yaml")
    assert put_calls[1][1].endswith("labgrid-exporter-rack1.service")

    install_cmd = conn.run_check.call_args_list[-1].args[0]
    assert "systemctl enable --now labgrid-exporter-rack1" in install_cmd
    assert "sudo mv" in install_cmd


def test_deploy_exporter_wraps_execution_error(tmp_path, monkeypatch):
    conn = _fake_conn()
    conn.run_check.side_effect = ExecutionError("sudo systemctl ...", [], ["permission denied"])
    monkeypatch.setattr(ssh_mod.sshmanager, "get", lambda host: conn)

    rendered = tmp_path / "resources.yaml"
    rendered.write_text("exporter: {}\n")

    with pytest.raises(RuntimeError, match="passwordless sudo"):
        provision.deploy_exporter("lab-host-03", "labuser", "rack1", rendered, "coord:20408")


def test_verify_exporter_active_succeeds_immediately(monkeypatch):
    conn = _fake_conn()
    monkeypatch.setattr(ssh_mod.sshmanager, "get", lambda host: conn)
    monkeypatch.setattr(provision.time, "sleep", lambda s: None)

    provision.verify_exporter_active("lab-host-03", "rack1", retries=1, delay=0)

    conn.run_check.assert_called_once_with("systemctl is-active --quiet labgrid-exporter-rack1")


def test_verify_exporter_active_raises_after_retries_with_logs(monkeypatch):
    conn = MagicMock()

    def run_check(cmd):
        if cmd.startswith("systemctl is-active"):
            raise ExecutionError(cmd, [], ["inactive"])
        return ["line1", "line2"]

    conn.run_check.side_effect = run_check
    monkeypatch.setattr(ssh_mod.sshmanager, "get", lambda host: conn)
    monkeypatch.setattr(provision.time, "sleep", lambda s: None)

    with pytest.raises(RuntimeError, match="did not become active"):
        provision.verify_exporter_active("lab-host-03", "rack1", retries=2, delay=0)
