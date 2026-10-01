"""Dependency and system prerequisite checks for hardware runners."""

from __future__ import annotations

import grp
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .models import CheckItem, HardwareMode


def check_command(cmd: str) -> bool:
    """Return True if command is available on PATH."""
    return shutil.which(cmd) is not None


def check_python_version() -> CheckItem:
    """Verify running python is >= 3.10."""
    v = sys.version_info
    passed = v >= (3, 10)
    ver_str = f"{v.major}.{v.minor}.{v.micro}"
    return CheckItem(
        name="Python version (>= 3.10)",
        passed=passed,
        message=f"Python {ver_str}",
        remediation="Install Python 3.10 or newer." if not passed else "",
    )


def check_dialout_group() -> CheckItem:
    """Verify current user has access to serial ports via dialout/uucp group."""
    try:
        current_groups = [grp.getgrgid(g).gr_name for g in os.getgroups()]
    except Exception:
        current_groups = []

    passed = "dialout" in current_groups or "uucp" in current_groups
    return CheckItem(
        name="Serial port group (dialout/uucp)",
        passed=passed,
        message="user in " + (", ".join(set(current_groups) & {"dialout", "uucp"}) or "none"),
        remediation="Run: sudo usermod -aG dialout $USER (and log out / log back in)."
        if not passed
        else "",
    )


def check_ser2net_version() -> CheckItem:
    """Check ser2net presence and detect buggy 4.6.0 version."""
    ser2net_path = shutil.which("ser2net")
    if not ser2net_path:
        return CheckItem(
            name="ser2net (>= 4.6.1)",
            passed=False,
            message="not installed on PATH",
            remediation="ser2net 4.6.1+ is required for exporter mode. Build from source into $HOME/opt/ser2net-4.6.1.",
        )

    try:
        proc = subprocess.run(
            [ser2net_path, "-v"], capture_output=True, text=True, timeout=5, check=False
        )
        out = (proc.stdout + " " + proc.stderr).strip()
        m = re.search(r"(\d+\.\d+(\.\d+)?)", out)
        ver_str = m.group(1) if m else "unknown"
    except Exception:
        ver_str = "unknown"

    if ver_str == "4.6.0":
        return CheckItem(
            name="ser2net (>= 4.6.1)",
            passed=False,
            message=f"found ser2net {ver_str} at {ser2net_path} (BROKEN: hangs on RFC2217 purge)",
            remediation="Replace ser2net 4.6.0 with 4.6.1 or newer built into $HOME/opt/ser2net-4.6.1/sbin.",
        )

    return CheckItem(
        name="ser2net (>= 4.6.1)",
        passed=True,
        message=f"found ser2net {ver_str} at {ser2net_path}",
    )


def check_pmount() -> CheckItem:
    """Check for pmount (needed by MassStorageDriver)."""
    passed = check_command("pmount")
    return CheckItem(
        name="pmount (mass storage)",
        passed=passed,
        message="installed" if passed else "missing",
        remediation="Run: sudo apt install pmount (or distro equivalent)." if not passed else "",
    )


def check_usbsdmux() -> CheckItem:
    """Check for usbsdmux command."""
    passed = check_command("usbsdmux")
    return CheckItem(
        name="usbsdmux (SD card multiplexer)",
        passed=passed,
        message="installed" if passed else "missing",
        remediation="Run: pip install usbsdmux (and ensure udev rules are installed)."
        if not passed
        else "",
    )


def check_gh_cli() -> CheckItem:
    """Check for GitHub CLI."""
    passed = check_command("gh")
    return CheckItem(
        name="GitHub CLI (gh)",
        passed=passed,
        message="installed" if passed else "not found",
        remediation="Install gh CLI: https://cli.github.com/ or provide manual runner token."
        if not passed
        else "",
    )


def build_ser2net_461(prefix: Path | None = None) -> Path:
    """Download, build, and install ser2net 4.6.1 into prefix (default: $HOME/opt/ser2net-4.6.1)."""
    if prefix is None:
        prefix = Path.home() / "opt" / "ser2net-4.6.1"

    prefix = prefix.resolve()
    prefix.mkdir(parents=True, exist_ok=True)

    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        tarball = Path(tmpdir) / "ser2net-4.6.1.tar.gz"
        subprocess.run(
            [
                "curl",
                "-sSL",
                "-o",
                str(tarball),
                "https://github.com/cminyard/ser2net/archive/refs/tags/v4.6.1.tar.gz",
            ],
            check=True,
        )
        subprocess.run(["tar", "-xzf", str(tarball), "-C", tmpdir], check=True)
        src_dir = Path(tmpdir) / "ser2net-4.6.1"
        subprocess.run(["./configure", f"--prefix={prefix}"], cwd=src_dir, check=True)
        subprocess.run(["make", "-j"], cwd=src_dir, check=True)
        subprocess.run(["make", "install"], cwd=src_dir, check=True)

    return prefix / "sbin" / "ser2net"


def run_dependency_checks(mode: HardwareMode) -> list[CheckItem]:
    """Run all prerequisite checks for the selected mode."""
    items = [
        check_python_version(),
        check_gh_cli(),
    ]

    for tool in ("curl", "tar", "git"):
        items.append(
            CheckItem(
                name=f"System tool: {tool}",
                passed=check_command(tool),
                message="installed" if check_command(tool) else "missing",
                remediation=f"Install {tool} via your system package manager."
                if not check_command(tool)
                else "",
            )
        )

    if mode == HardwareMode.EXPORTER:
        items.append(check_ser2net_version())
    elif mode == HardwareMode.DIRECT:
        items.append(check_dialout_group())
        items.append(check_pmount())
        items.append(check_usbsdmux())

    return items
