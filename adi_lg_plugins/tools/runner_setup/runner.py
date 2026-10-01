"""Actions runner package management and configuration."""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

import requests

from .models import HardwareMode, RunnerConfig

FALLBACK_RUNNER_VERSION = "2.322.0"


def detect_architecture() -> str:
    """Return GitHub runner architecture name for the current machine."""
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x64"
    if machine in ("aarch64", "arm64"):
        return "arm64"
    if machine.startswith("arm"):
        return "arm"
    raise RuntimeError(f"unsupported processor architecture: {machine}")


def get_latest_runner_version() -> str:
    """Query GitHub releases API for latest runner version with fallback."""
    try:
        resp = requests.get(
            "https://api.github.com/repos/actions/runner/releases/latest",
            timeout=5,
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        if resp.status_code == 200:
            tag = resp.json().get("tag_name", "")
            return tag.lstrip("v") if tag else FALLBACK_RUNNER_VERSION
    except Exception:
        pass
    return FALLBACK_RUNNER_VERSION


def get_runner_download_url(version: str, arch: str) -> tuple[str, str]:
    """Return (download_url, tarball_filename)."""
    tarball = f"actions-runner-linux-{arch}-{version}.tar.gz"
    url = f"https://github.com/actions/runner/releases/download/v{version}/{tarball}"
    return url, tarball


def download_and_extract_runner(
    dest_dir: Path, version: str | None = None, dry_run: bool = False
) -> Path:
    """Download and extract GitHub Actions runner into dest_dir."""
    arch = detect_architecture()
    ver = version or get_latest_runner_version()
    url, tarball_name = get_runner_download_url(ver, arch)

    dest_dir = dest_dir.resolve()
    tarball_path = dest_dir / tarball_name

    if dry_run:
        return dest_dir

    dest_dir.mkdir(parents=True, exist_ok=True)

    if not tarball_path.is_file():
        subprocess.run(
            ["curl", "-fail", "-sSL", "-o", str(tarball_path), url],
            check=True,
        )

    config_sh = dest_dir / "config.sh"
    if not config_sh.is_file():
        subprocess.run(["tar", "xzf", str(tarball_path), "-C", str(dest_dir)], check=True)

    return dest_dir


def install_runner_dependencies(runner_dir: Path, dry_run: bool = False) -> None:
    """Run ./bin/installdependencies.sh if present."""
    dep_script = runner_dir / "bin" / "installdependencies.sh"
    if dry_run or not dep_script.is_file():
        return
    subprocess.run(["sudo", str(dep_script)], check=True)


def configure_runner(config: RunnerConfig) -> None:
    """Execute ./config.sh and configure environment variables in .env."""
    runner_dir = config.install_dir.resolve()
    config_script = runner_dir / "config.sh"

    labels_arg = ",".join(["self-hosted", *config.labels])

    cmd = [
        str(config_script),
        "--url",
        config.scope.url,
        "--token",
        config.token,
        "--name",
        config.name,
        "--labels",
        labels_arg,
        "--unattended",
        "--replace",
    ]

    if config.dry_run:
        return

    # If existing registration exists, remove first
    if (runner_dir / ".runner").is_file():
        subprocess.run(
            [str(config_script), "remove", "--token", config.token],
            cwd=runner_dir,
            check=False,
        )

    subprocess.run(cmd, cwd=runner_dir, check=True)

    # Write .env
    write_runner_env(config)


def write_runner_env(config: RunnerConfig) -> Path:
    """Write or update .env file in runner directory."""
    runner_dir = config.install_dir.resolve()
    env_file = runner_dir / ".env"

    env_vars: dict[str, str] = {}
    if env_file.is_file() and not config.dry_run:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip()

    if config.mode == HardwareMode.EXPORTER and config.coordinator:
        env_vars["LG_COORDINATOR"] = config.coordinator
    elif config.mode == HardwareMode.DIRECT and config.direct_env_file:
        env_vars["LG_DIRECT_ENV"] = str(config.direct_env_file.resolve())

    # Prepend custom ser2net path if installed
    ser2net_bin = Path.home() / "opt" / "ser2net-4.6.1" / "sbin"
    if ser2net_bin.is_dir():
        current_path = env_vars.get("PATH", os.environ.get("PATH", ""))
        if str(ser2net_bin) not in current_path:
            env_vars["PATH"] = f"{ser2net_bin}:{current_path}"

    if not config.dry_run:
        lines = [f"{k}={v}" for k, v in sorted(env_vars.items())]
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return env_file
