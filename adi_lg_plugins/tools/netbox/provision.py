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
import re
import tempfile
import time
from pathlib import Path
from types import ModuleType

import yaml

from adi_lg_plugins.hw_ci.power import POWER_TYPES

logger = logging.getLogger(__name__)

STAGE_DIR = "/tmp/adi-lg-netbox-stage"
DEFAULT_EXPORTER_BIN = "/usr/local/bin/labgrid-exporter"
# Read by systemd into the exporter's environment; templates reference these
# variables as `{{ env["NAME"] }}`, which labgrid resolves when it starts.
EXPORTER_ENV_FILE = "/etc/labgrid/exporter.env"

# Power types (template `power` value -> resource, client driver(s), fields,
# credentials) live in adi_lg_plugins.hw_ci.power.


def power_tags(power: str) -> dict[str, str]:
    """Place tags that make render-env emit this power type's client driver(s)."""
    t = POWER_TYPES[power]
    tags = {"power-driver": t.driver}
    if t.output_driver:
        tags["power-output-driver"] = t.output_driver
    return tags


# Provided by labgrid-exporter when it renders the file - never prompted for.
EXPORTER_RUNTIME_VARS = frozenset({"env", "hostname", "name", "isolated"})

# The question asked for each template field. Every variable a template uses
# needs an entry (tests/test_exporter_templates.py checks), so add-hardware never
# asks for a bare variable name. Kuiper boot files take `release:<path>` (inside
# the release image's boot partition) or a file on the test runner.
TEMPLATE_FIELDS = {
    "target_ip": "Board IP address, for SSH to its Linux",
    "target_username": "Board Linux SSH username",
    "target_password": "Board Linux SSH password",
    "serial_port": "Serial console device on the exporter host",
    "sdmux_path": "SD mux control device (/dev/sg*) on the exporter host",
    "boot_partition": "SD card boot partition on the exporter host, through the SD mux",
    "kuiper_release": "Kuiper release to take the boot files from",
    "kuiper_bootbin": "BOOT.BIN, as release:<path> or a file on the test runner",
    "kuiper_devicetree": "Device tree, as release:<path> or a file on the test runner",
    "kuiper_kernel": "Kernel image, as release:<path> or a file on the test runner",
    "root_target": "xsdb JTAG target ID of the device (see xsdb `targets`)",
    "microblaze_target": "xsdb JTAG target ID of the MicroBlaze CPU (see xsdb `targets`)",
    "bitstream_path": "Bitstream (.bit) on the test runner, or exporter:<path> on the exporter host",
    "kernel_path": "MicroBlaze kernel (.strip) on the test runner, or exporter:<path>",
    "vivado_path": "Vivado install directory on the exporter host",
    "xsdb_path": "xsdb executable on the exporter host (unset: Vitis/bin/xsdb beside Vivado)",
    "variant": "Raspberry Pi model, naming the resource group RPI_<model> (e.g. CM4, PI4)",
}


class _ExporterEnv(dict):
    """Re-emit ``env["NAME"]`` lookups so labgrid resolves them on the exporter."""

    def __missing__(self, key):
        return f'{{{{ env["{key}"] }}}}'


def _require_jinja2():
    try:
        import jinja2
    except ImportError as e:
        raise RuntimeError(
            "jinja2 is required for `adi-lg netbox` commands; "
            'run `pip install -e ".[netbox]"` in your labgrid-plugins checkout'
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


_STRATEGY_HEADER = re.compile(r"^##\s*boot-strategy:\s*(\S+)\s*$", re.M)


def template_strategy(template_path: Path) -> str | None:
    """Boot strategy a template is written for, from its ``## boot-strategy:`` line."""
    match = _STRATEGY_HEADER.search(template_path.read_text())
    return match.group(1) if match else None


_TITLE_HEADER = re.compile(r"^##\s*Exporter template:\s*(.+?)\s*$", re.M)


def template_title(template_path: Path) -> str:
    """One-line description of a template, from its ``## Exporter template:`` line."""
    match = _TITLE_HEADER.search(template_path.read_text())
    return match.group(1) if match else ""


_RESOURCE_CLASS = re.compile(r"^\s*cls:\s*([A-Za-z_][A-Za-z0-9_]*)\s*$", re.M)


def template_resources(template_path: Path) -> set[str]:
    """Resource classes a template exports, from its ``cls:`` lines."""
    return set(_RESOURCE_CLASS.findall(template_path.read_text()))


def discover_template_vars(template_path: Path) -> set[str]:
    """Undeclared Jinja2 variables referenced by the template."""
    jinja2 = _require_jinja2()
    from jinja2 import meta

    env = jinja2.Environment()
    ast = env.parse(template_path.read_text())
    return meta.find_undeclared_variables(ast)


def required_template_vars(template_path: Path) -> set[str]:
    """Template variables used at least once without a ``| default(...)`` filter.

    These have no fallback, so rendering fails unless the operator supplies them.
    """
    jinja2 = _require_jinja2()
    from jinja2 import nodes

    ast = jinja2.Environment().parse(template_path.read_text())
    defaulted = {id(f.node) for f in ast.find_all(nodes.Filter) if f.name == "default"}
    return {
        n.name for n in ast.find_all(nodes.Name) if n.ctx == "load" and id(n) not in defaulted
    } & discover_template_vars(template_path)


def template_field_defaults(template_path: Path) -> dict[str, object]:
    """Each template variable's ``| default(...)`` value (``None`` for ``default(none)``)."""
    jinja2 = _require_jinja2()
    from jinja2 import nodes

    ast = jinja2.Environment().parse(template_path.read_text())
    defaults = {}
    for f in ast.find_all(nodes.Filter):
        if f.name == "default" and isinstance(f.node, nodes.Name) and f.args:
            arg = f.args[0]
            defaults.setdefault(f.node.name, arg.value if isinstance(arg, nodes.Const) else None)
    return defaults


def render_and_validate(
    template_path: Path, context: dict, exporter_configs_dir: Path
) -> tuple[Path, list[str]]:
    """Render + schema-validate the template.

    Returns the path to the rendered file and the list of resource-group
    names it defines (e.g. ``["ZCU102_AD9081"]``) - the caller needs these
    verbatim to build a correct `add-match` pattern, and they vary per
    template (some bake the chip into the group name, some templatize it),
    so they're read back from the actual rendered YAML rather than guessed
    from the template's filename.
    """
    jinja2 = _require_jinja2()

    # A file loader so templates can `{% include "power/<type>.yaml" %}`, the same
    # way labgrid-exporter resolves includes relative to the config file.
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_path.parent)),
        undefined=jinja2.StrictUndefined,
    )
    try:
        rendered = env.get_template(template_path.name).render(**{"env": _ExporterEnv(), **context})
    except jinja2.UndefinedError as e:
        raise RuntimeError(f"template {template_path.name} is missing a required field: {e}") from e
    except jinja2.TemplateNotFound as e:
        raise RuntimeError(f"template {template_path.name}: unknown power type ({e.name})") from e

    out_dir = Path(tempfile.mkdtemp(prefix="adi-lg-netbox-"))
    out_path = out_dir / template_path.name
    out_path.write_text(rendered)

    validate = _load_validate_module(exporter_configs_dir)
    issues = validate.validate_config(str(out_path))
    if issues:
        detail = "\n".join(f"  - {i}" for i in issues)
        raise RuntimeError(f"rendered exporter config failed validation:\n{detail}")

    # labgrid's exporter format: {group_name: {resource: params}}. The
    # exporter's own name comes from `labgrid-exporter -n`, not the file.
    data = yaml.safe_load(rendered)
    return out_path, list(data.keys())


def _unit_text(coord: str, name: str, user: str, exporter_bin: str) -> str:
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
EnvironmentFile=-{EXPORTER_ENV_FILE}
ExecStart={exporter_bin} -c {coord} -n {name} {resource_path}
Restart=always
RestartSec=5s

[Install]
WantedBy=multi-user.target
"""


def check_prerequisites(ssh_host: str) -> str:
    """Fail fast if `labgrid-exporter` isn't installed on the exporter host.

    Returns its absolute path as the SSH user's PATH resolves it, so the
    systemd unit runs the same install (venv, ``~/.local/bin``, ...).
    """
    from labgrid.driver.exception import ExecutionError
    from labgrid.util.ssh import sshmanager

    try:
        conn = sshmanager.get(ssh_host)
    except ExecutionError as e:
        raise RuntimeError(
            f"cannot SSH to {ssh_host} - check the exporter host login and that its key is "
            f"accepted without a password: {e}"
        ) from e
    try:
        out = conn.run_check("command -v labgrid-exporter")
    except ExecutionError as e:
        raise RuntimeError(
            f"labgrid-exporter not found on {ssh_host} - install it there "
            f"(pip install labgrid on that host) before running this command: {e}"
        ) from e
    lines = out if isinstance(out, list) else str(out).splitlines()
    path = lines[0].strip() if lines else ""
    if not path.startswith("/"):
        raise RuntimeError(
            f"`command -v labgrid-exporter` on {ssh_host} returned {path!r}, not an "
            "absolute path - make labgrid-exporter an executable on that user's PATH"
        )
    return path


def missing_power_env(ssh_host: str, power: str) -> list[str]:
    """Return the required power-credential variables not set in the host's exporter env file.

    An unset variable renders as an empty string, so the exporter still starts
    and the place only fails at its first power operation - worth a warning.
    """
    from labgrid.driver.exception import ExecutionError
    from labgrid.util.ssh import sshmanager

    conn = sshmanager.get(ssh_host)
    missing = []
    for name in (c.env for c in POWER_TYPES[power].credentials if c.required):
        try:
            conn.run_check(f"sudo grep -qE '^{name}=.' {EXPORTER_ENV_FILE}")
        except ExecutionError:
            missing.append(name)
    return missing


def deploy_exporter(
    ssh_host: str,
    ssh_user: str,
    name: str,
    rendered_yaml: Path,
    coord: str,
    *,
    exporter_bin: str = DEFAULT_EXPORTER_BIN,
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
    unit_path.write_text(_unit_text(coord, name, ssh_user, exporter_bin))

    try:
        conn.run_check(f"mkdir -p {stage}")
        conn.put_file(str(rendered_yaml), f"{stage}/resources.yaml")
        conn.put_file(str(unit_path), f"{stage}/{unit_name}")
        conn.run_check(
            f"sudo mkdir -p /etc/labgrid/exporters/{name} && "
            f"sudo mv {stage}/resources.yaml /etc/labgrid/exporters/{name}/resources.yaml && "
            f"sudo mv {stage}/{unit_name} /etc/systemd/system/{unit_name} && "
            f"sudo systemctl daemon-reload && "
            # restart, not `enable --now`, so a re-run loads the new config into a
            # unit that is already running
            f"sudo systemctl enable labgrid-exporter-{name} && "
            f"sudo systemctl restart labgrid-exporter-{name}"
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
