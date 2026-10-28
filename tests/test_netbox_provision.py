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
from labgrid.remote.config import ResourceConfig

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


TEMPLATES = EXPORTER_CONFIGS_DIR / "templates"


def test_stock_templates_are_named_by_boot_path():
    assert sorted(p.name for p in TEMPLATES.glob("*.yaml")) == [
        "fabric-jtag.yaml",
        "rpi-ssh.yaml",
        "soc-sdmux.yaml",
        "soc-ssh.yaml",
        "soc-tftp.yaml",
        "zynqmp-jtag.yaml",
    ]


@pytest.mark.parametrize(
    ("template", "required"),
    [
        ("soc-sdmux.yaml", {"target_ip"}),
        ("soc-ssh.yaml", {"target_ip"}),
        ("soc-tftp.yaml", {"target_ip"}),
        ("zynqmp-jtag.yaml", {"target_ip"}),
        ("fabric-jtag.yaml", {"target_ip", "bitstream_path", "kernel_path"}),
        ("rpi-ssh.yaml", {"target_ip"}),
    ],
)
def test_required_template_vars_are_the_fields_without_a_default(template, required):
    assert provision.required_template_vars(TEMPLATES / template) == required


def test_discover_template_vars_soc_sdmux():
    names = provision.discover_template_vars(TEMPLATES / "soc-sdmux.yaml")
    assert {"carrier", "chip", "target_ip", "serial_port", "sdmux_path"} <= names


@pytest.mark.parametrize(
    ("template", "context", "expected_group"),
    [
        ("soc-sdmux.yaml", {"target_ip": "10.0.0.5", "power_outlet": "Bench DUT"}, "ZCU102_AD9081"),
        (
            "soc-sdmux.yaml",
            {
                "target_ip": "10.0.0.5",
                "power_outlet": "Bench DUT",
                "carrier": "zc706",
                "chip": "adrv9009",
            },
            "ZC706_ADRV9009",
        ),
        (
            "fabric-jtag.yaml",
            {
                "target_ip": "10.0.0.5",
                "power_outlet": "Bench DUT",
                "bitstream_path": "/srv/a.bit",
                "kernel_path": "/srv/k.strip",
                "carrier": "vcu118",
                "chip": "ad9084",
            },
            "VCU118_AD9084",
        ),
    ],
)
def test_render_and_validate_group_name_from_carrier_and_chip(template, context, expected_group):
    path, groups = provision.render_and_validate(
        TEMPLATES / template, context, EXPORTER_CONFIGS_DIR
    )

    assert path.exists()
    assert groups == [expected_group]


def test_render_and_validate_missing_required_field_raises():
    with pytest.raises(RuntimeError, match="missing a required field"):
        provision.render_and_validate(TEMPLATES / "soc-sdmux.yaml", {}, EXPORTER_CONFIGS_DIR)


# Values for every template field without a default, so each template renders.
_REQUIRED_FIELDS = {
    "target_ip": "10.0.0.5",
    "power_outlet": "Bench DUT",
    "bitstream_path": "/srv/vcu118/system_top.bit",
    "kernel_path": "/srv/vcu118/simpleImage.strip",
}


@pytest.mark.parametrize(
    "template",
    sorted((EXPORTER_CONFIGS_DIR / "templates").glob("*.yaml")),
    ids=lambda p: p.stem,
)
def test_rendered_template_loads_in_labgrid_exporter(template):
    """The rendered file must load the way `labgrid-exporter` itself loads it.

    labgrid re-renders exporter configs as Jinja with ``#`` line statements and
    ``##`` line comments, then treats every top-level key as a resource group.
    """
    path, groups = provision.render_and_validate(template, _REQUIRED_FIELDS, EXPORTER_CONFIGS_DIR)

    data = ResourceConfig(str(path), {"env": {}, "isolated": False, "hostname": "h", "name": "n"})

    assert list(data.data) == groups
    known = provision._load_validate_module(EXPORTER_CONFIGS_DIR).KNOWN_CLASSES
    for group in data.data.values():
        for params in group.values():
            assert params["cls"] in known


def test_unit_text_shape():
    text = provision._unit_text("coord:20408", "rack1", "labuser", "/opt/lg/bin/labgrid-exporter")
    assert "ExecStart=/opt/lg/bin/labgrid-exporter -c coord:20408 -n rack1 " in text
    assert "User=labuser" in text
    assert "Restart=always" in text
    assert "WantedBy=multi-user.target" in text
    # Power credentials are read by labgrid from the exporter's environment.
    assert f"EnvironmentFile=-{provision.EXPORTER_ENV_FILE}" in text


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


def test_check_prerequisites_returns_resolved_exporter_path(monkeypatch):
    conn = _fake_conn()
    conn.run_check.return_value = ["/home/labuser/.local/bin/labgrid-exporter"]
    monkeypatch.setattr(ssh_mod.sshmanager, "get", lambda host: conn)

    assert provision.check_prerequisites("lab-host-03") == (
        "/home/labuser/.local/bin/labgrid-exporter"
    )


def test_check_prerequisites_rejects_non_path_resolution(monkeypatch):
    conn = _fake_conn()
    conn.run_check.return_value = ["alias labgrid-exporter='lg-exp'"]
    monkeypatch.setattr(ssh_mod.sshmanager, "get", lambda host: conn)

    with pytest.raises(RuntimeError, match="absolute path"):
        provision.check_prerequisites("lab-host-03")


def test_missing_power_env_reports_unset_variables(monkeypatch):
    conn = _fake_conn()

    def run_check(cmd):
        if "VESYNC_PASSWORD" in cmd:
            raise ExecutionError(cmd, [], [])
        return []

    conn.run_check.side_effect = run_check
    monkeypatch.setattr(ssh_mod.sshmanager, "get", lambda host: conn)

    assert provision.missing_power_env("lab-host-03", "vesync") == ["VESYNC_PASSWORD"]
    assert all(provision.EXPORTER_ENV_FILE in c.args[0] for c in conn.run_check.call_args_list)


def test_deploy_exporter_unit_runs_given_exporter_path(tmp_path, monkeypatch):
    conn = _fake_conn()
    monkeypatch.setattr(ssh_mod.sshmanager, "get", lambda host: conn)
    rendered = tmp_path / "resources.yaml"
    rendered.write_text("group: {}\n")

    provision.deploy_exporter(
        "lab-host-03",
        "labuser",
        "rack1",
        rendered,
        "coord:20408",
        exporter_bin="/home/labuser/.local/bin/labgrid-exporter",
    )

    unit_local_path = conn.put_file.call_args_list[1].args[0]
    assert (
        "ExecStart=/home/labuser/.local/bin/labgrid-exporter " in Path(unit_local_path).read_text()
    )


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


def test_template_field_defaults_are_read_from_the_template():
    defaults = provision.template_field_defaults(
        EXPORTER_CONFIGS_DIR / "templates" / "soc-sdmux.yaml"
    )

    assert defaults["serial_port"] == "/dev/ttyUSB0"
    assert defaults["kuiper_release"] == "2023_R2_P1"
    assert defaults["kuiper_bootbin"] is None  # default(none): left unset
    assert "target_ip" not in defaults  # required, no default
