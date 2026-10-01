"""Systemd service installation and management for GitHub runner and exporter."""

from __future__ import annotations

import getpass
import subprocess
from pathlib import Path


def install_and_start_runner_service(
    runner_dir: Path, user: str | None = None, dry_run: bool = False
) -> None:
    """Install and start runner systemd service using ./svc.sh."""
    runner_dir = runner_dir.resolve()
    svc_sh = runner_dir / "svc.sh"
    if not svc_sh.is_file() and not dry_run:
        raise FileNotFoundError(f"svc.sh not found in {runner_dir}")

    target_user = user or getpass.getuser()

    if dry_run:
        return

    # Install service
    subprocess.run(["sudo", str(svc_sh), "install", target_user], cwd=runner_dir, check=True)
    # Start service
    subprocess.run(["sudo", str(svc_sh), "start"], cwd=runner_dir, check=True)


def get_runner_service_status(runner_dir: Path) -> tuple[int, str]:
    """Check service status via ./svc.sh status. Returns (exit_code, output)."""
    runner_dir = runner_dir.resolve()
    svc_sh = runner_dir / "svc.sh"
    if not svc_sh.is_file():
        return 1, "svc.sh not found"

    res = subprocess.run(
        ["sudo", str(svc_sh), "status"],
        cwd=runner_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    return res.returncode, (res.stdout + " " + res.stderr).strip()


def generate_exporter_service_unit(
    coord: str,
    exporter_name: str,
    resource_yaml: Path,
    user: str | None = None,
) -> str:
    """Generate systemd service unit text for labgrid-exporter."""
    target_user = user or getpass.getuser()
    resource_path = resource_yaml.resolve()

    ser2net_bin = Path.home() / "opt" / "ser2net-4.6.1" / "sbin"
    path_line = f'Environment="PATH={ser2net_bin}:/usr/local/bin:/usr/bin:/bin"'

    return f"""[Unit]
Description=Labgrid Exporter ({exporter_name})
After=network.target

[Service]
Type=simple
User={target_user}
{path_line}
WorkingDirectory={resource_path.parent}
ExecStart=/usr/local/bin/labgrid-exporter -c {coord} -n {exporter_name} {resource_path}
Restart=always
RestartSec=5s

[Install]
WantedBy=multi-user.target
"""
