"""Safe, bounded capture helpers for Prism labgrid reports."""

from __future__ import annotations

import ipaddress
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

MAX_LOG_BYTES = 4 * 1024 * 1024
MAX_CONSOLE_FILES = 16
MAX_CONSOLE_TOTAL_BYTES = 16 * 1024 * 1024
SSH_CAPTURE_TIMEOUT = 30.0
_HOSTNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")


@dataclass(frozen=True)
class CaptureResult:
    ok: bool
    output: bytes
    method: str
    error: str | None = None


def bounded(data: bytes | str | None) -> bytes:
    if data is None:
        return b""
    if isinstance(data, str):
        data = data.encode("utf-8", errors="replace")
    return data[-MAX_LOG_BYTES:]


def iio_host(uri: str | None) -> str | None:
    """Return a validated host from a libiio ``ip:HOST`` URI."""
    if not uri or not uri.startswith("ip:"):
        return None
    parsed = urlsplit(f"ip://{uri[3:]}")
    try:
        host = parsed.hostname
    except ValueError:
        return None
    if not host or host.startswith("-"):
        return None
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not _HOSTNAME.fullmatch(host):
            return None
    return host


def safe_iio_uri(uri: str | None) -> str | None:
    host = iio_host(uri)
    if host is None:
        return None
    return f"ip:{host}"


def capture_dmesg_ssh(
    uri: str | None,
    *,
    user: str = "root",
    key: str | None = None,
    timeout: float = SSH_CAPTURE_TIMEOUT,
) -> CaptureResult:
    host = iio_host(uri)
    executable = shutil.which("ssh")
    if host is None:
        return CaptureResult(False, b"", "ssh", "IIO_URI is not an ip: URI")
    if executable is None:
        return CaptureResult(False, b"", "ssh", "ssh not found")
    if not user or user.startswith("-") or not re.fullmatch(r"[A-Za-z0-9._-]+", user):
        return CaptureResult(False, b"", "ssh", "invalid SSH user")

    argv = [
        executable,
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
    ]
    if key:
        argv.extend(["-i", key])
    argv.extend([f"{user}@{host}", "dmesg", "--color=never"])
    try:
        completed = subprocess.run(
            argv,
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return CaptureResult(False, bounded(exc.stdout), "ssh", "timed out")
    except OSError:
        return CaptureResult(False, b"", "ssh", "ssh could not be started")
    output = bounded(completed.stdout)
    if completed.returncode != 0:
        return CaptureResult(False, output, "ssh", f"exit {completed.returncode}")
    return CaptureResult(True, output, "ssh")


def dmesg_delta(before: bytes, after: bytes) -> bytes:
    """Return ordered new lines, preserving duplicates and ring-wrap output."""
    before_lines = before.replace(b"\r\n", b"\n").splitlines(keepends=True)
    after_lines = after.replace(b"\r\n", b"\n").splitlines(keepends=True)
    overlap = 0
    for size in range(min(len(before_lines), len(after_lines)), 0, -1):
        if before_lines[-size:] == after_lines[:size]:
            overlap = size
            break
    return b"".join(after_lines[overlap:])


def _read_tail(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(max(0, size - limit))
        return stream.read(limit)


def copy_console_logs(source: Path | None, destination: Path) -> list[str]:
    """Copy bounded regular files produced by labgrid's ``--lg-log`` reporter."""
    if source is None or not source.is_dir() or source.is_symlink():
        return []
    copied: list[str] = []
    total = 0
    destination.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.glob("console_*")):
        if len(copied) >= MAX_CONSOLE_FILES or total >= MAX_CONSOLE_TOTAL_BYTES:
            break
        if path.is_symlink() or not path.is_file():
            continue
        remaining = min(MAX_LOG_BYTES, MAX_CONSOLE_TOTAL_BYTES - total)
        data = _read_tail(path, remaining)
        name = f"{path.name}.log" if path.suffix != ".log" else path.name
        (destination / name).write_bytes(data)
        copied.append(name)
        total += len(data)
    return copied
