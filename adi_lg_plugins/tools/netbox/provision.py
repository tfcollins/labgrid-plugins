"""Render + validate an exporter config, then deploy it as a systemd service
on the exporter host over SSH.

``exporter_configs/`` (templates, JSON schema, ``validate.py``) lives at the
labgrid-plugins repo root, outside the installed ``adi_lg_plugins`` package,
so it isn't necessarily importable/on-disk from an arbitrary install
location. This module locates it by walking up from the current directory,
consistent with how ``exporter_configs/validate.py`` is already only ever
run from within a checkout today (it has no console-script entry point).
"""

from __future__ import annotations

import importlib.util
import logging
import tempfile
import time
from pathlib import Path
from types import ModuleType

import yaml

logger = logging.getLogger(__name__)

STAGE_DIR = "/tmp/adi-lg-netbox-stage"


def _require_jinja2():
    try:
        import jinja2
    except ImportError as e:
        raise RuntimeError(
            "jinja2 is required for `adi-lg netbox` commands; "
            "install with: pip install adi-labgrid-plugins[netbox]"
        ) from e
    return jinja2


def find_exporter_configs_dir(start: Path | None = None) -> Path:
    """Walk upward from `start` (default: cwd) for an `exporter_configs/` dir."""
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "exporter_configs" / "validate.py").is_file():
            return candidate / "exporter_configs"
    raise RuntimeError(
        "could not find exporter_configs/validate.py above the current directory - "
        "run `adi-lg netbox add-hardware` from within a labgrid-plugins checkout, "
        "or pass --exporter-configs-dir explicitly"
    )


def _load_validate_module(exporter_configs_dir: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "adi_lg_plugins._exporter_configs_validate", exporter_configs_dir / "validate.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"could not load {exporter_configs_dir / 'validate.py'}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def discover_template_vars(template_path: Path) -> set[str]:
    """Undeclared Jinja2 variables referenced by the template."""
    jinja2 = _require_jinja2()
    from jinja2 import meta

    env = jinja2.Environment()
    ast = env.parse(template_path.read_text())
    return meta.find_undeclared_variables(ast)


def render_and_validate(
    template_path: Path, context: dict, exporter_configs_dir: Path
) -> tuple[Path, list[str]]:
    """Render + schema-validate the template.

    Returns the path to the rendered file and the list of resource-group
    names found under its exporter-name key (e.g. ``["ZCU102_AD9081"]``) -
    the caller needs these verbatim to build a correct `add-match` pattern,
    and they vary per template (some bake the chip into the group name,
    some templatize it), so they're read back from the actual rendered YAML
    rather than guessed from the template's filename.
    """
    jinja2 = _require_jinja2()

    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    try:
        rendered = env.from_string(template_path.read_text()).render(**context)
    except jinja2.UndefinedError as e:
        raise RuntimeError(f"template {template_path.name} is missing a required field: {e}") from e

    out_dir = Path(tempfile.mkdtemp(prefix="adi-lg-netbox-"))
    out_path = out_dir / template_path.name
    out_path.write_text(rendered)

    validate = _load_validate_module(exporter_configs_dir)
    # Deliberately no schema_path: exporter_schema.json only matches the flat
    # {group: {resource: params}} shape. Every exporter_configs/templates/
    # file renders to the *wrapped* {exporter_name: {group: {resource}}}
    # shape instead (exporter_name has to be the real per-deployment name,
    # so it can't be flattened away) - passing the schema here fails on
    # every real template (confirmed against zcu102.yaml). validate_config's
    # own per-resource `cls`/known-class check (always run, schema or not)
    # already understands both shapes and is the meaningful check for a
    # rendered file.
    issues = validate.validate_config(str(out_path))
    if issues:
        detail = "\n".join(f"  - {i}" for i in issues)
        raise RuntimeError(f"rendered exporter config failed validation:\n{detail}")

    data = yaml.safe_load(rendered)
    # {exporter_name: {group_name: {resource: params}}} - exactly one
    # top-level exporter-name key per rendered template, per convention.
    (groups,) = data.values()
    return out_path, list(groups.keys())


def _unit_text(coord: str, name: str, user: str) -> str:
    """Systemd unit text for `labgrid-exporter`, for remote-only paths.

    Deliberately not reusing
    `adi_lg_plugins.tools.runner_setup.service.generate_exporter_service_unit`:
    that helper calls `Path(resource_yaml).resolve()`, which assumes it's
    generating a unit for the *local* host it runs on (how the existing
    runner-setup wizard uses it). These paths only exist on the *remote*
    exporter host, so the unit text is built directly from known remote
    path strings instead - same [Unit]/[Service]/[Install] shape otherwise.
    """
    resource_path = f"/etc/labgrid/exporters/{name}/resources.yaml"
    return f"""[Unit]
Description=Labgrid Exporter ({name})
After=network.target

[Service]
Type=simple
User={user}
WorkingDirectory=/etc/labgrid/exporters/{name}
ExecStart=/usr/local/bin/labgrid-exporter -c {coord} -n {name} {resource_path}
Restart=always
RestartSec=5s

[Install]
WantedBy=multi-user.target
"""


def check_prerequisites(ssh_host: str) -> None:
    """Fail fast if `labgrid-exporter` isn't installed on the exporter host."""
    from labgrid.driver.exception import ExecutionError
    from labgrid.util.ssh import sshmanager

    conn = sshmanager.get(ssh_host)
    try:
        conn.run_check("command -v labgrid-exporter")
    except ExecutionError as e:
        raise RuntimeError(
            f"labgrid-exporter not found on {ssh_host} - install it there "
            f"(pip install labgrid on that host) before running this command: {e}"
        ) from e


def deploy_exporter(
    ssh_host: str, ssh_user: str, name: str, rendered_yaml: Path, coord: str
) -> None:
    """SSH-deploy the rendered exporter config as a systemd service and start it.

    Requires passwordless sudo for the connecting SSH user on `ssh_host` (for
    the /etc writes + systemctl) - see `check_prerequisites` for the other
    prerequisite (labgrid-exporter already installed). Neither is
    auto-provisioned; both are documented in
    docs/source/user-guide/netbox-onboarding.rst.
    """
    from labgrid.driver.exception import ExecutionError
    from labgrid.util.ssh import sshmanager

    conn = sshmanager.get(ssh_host)
    stage = f"{STAGE_DIR}/{name}"
    unit_name = f"labgrid-exporter-{name}.service"

    unit_path = Path(tempfile.mkdtemp(prefix="adi-lg-netbox-unit-")) / unit_name
    unit_path.write_text(_unit_text(coord, name, ssh_user))

    try:
        conn.run_check(f"mkdir -p {stage}")
        conn.put_file(str(rendered_yaml), f"{stage}/resources.yaml")
        conn.put_file(str(unit_path), f"{stage}/{unit_name}")
        conn.run_check(
            f"sudo mkdir -p /etc/labgrid/exporters/{name} && "
            f"sudo mv {stage}/resources.yaml /etc/labgrid/exporters/{name}/resources.yaml && "
            f"sudo mv {stage}/{unit_name} /etc/systemd/system/{unit_name} && "
            f"sudo systemctl daemon-reload && "
            f"sudo systemctl enable --now labgrid-exporter-{name}"
        )
    except ExecutionError as e:
        raise RuntimeError(
            f"failed to install/start labgrid-exporter-{name} on {ssh_host}: {e}\n"
            "(requires passwordless sudo for the connecting SSH user)"
        ) from e


def verify_exporter_active(
    ssh_host: str, name: str, *, retries: int = 10, delay: float = 2.0
) -> None:
    """Poll `systemctl is-active` with backoff; pull journal logs on failure."""
    from labgrid.driver.exception import ExecutionError
    from labgrid.util.ssh import sshmanager

    conn = sshmanager.get(ssh_host)
    unit = f"labgrid-exporter-{name}"
    last_error: Exception | None = None
    for _ in range(retries):
        try:
            conn.run_check(f"systemctl is-active --quiet {unit}")
            return
        except ExecutionError as e:
            last_error = e
            time.sleep(delay)

    try:
        logs = conn.run_check(f"journalctl -u {unit} -n 50 --no-pager")
        logs_text = logs if isinstance(logs, str) else "\n".join(logs)
    except ExecutionError:
        logs_text = "(could not fetch journal logs)"
    raise RuntimeError(
        f"{unit} did not become active on {ssh_host} after {retries} attempts "
        f"({last_error}); last journal lines:\n{logs_text}"
    )
