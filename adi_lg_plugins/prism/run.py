"""Run a command and finalize Prism DUT artifacts inside its reservation."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import signal
import subprocess
import sys
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from .session_hook import LabgridSessionHook

PROCESS_GROUP_GRACE_SECONDS = 5.0
PROCESS_GROUP_KILL_SECONDS = 2.0
_PR_SET_CHILD_SUBREAPER = 36
_PR_GET_CHILD_SUBREAPER = 37


@contextmanager
def _child_subreaper():
    """On Linux, adopt orphaned pipeline descendants so they can be reaped."""
    previous = ctypes.c_int()
    prctl = None
    if sys.platform == "linux":
        try:
            candidate = ctypes.CDLL(None, use_errno=True).prctl
            if candidate(_PR_GET_CHILD_SUBREAPER, ctypes.byref(previous), 0, 0, 0) == 0:
                if candidate(_PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) == 0:
                    prctl = candidate
        except (AttributeError, OSError):
            pass
    try:
        yield
    finally:
        if prctl is not None:
            prctl(_PR_SET_CHILD_SUBREAPER, previous.value, 0, 0, 0)


def _wait_for_process_group(group: int) -> bool:
    """Wait for cancellation cleanup, then kill and reap remaining descendants."""
    deadline = time.monotonic() + PROCESS_GROUP_GRACE_SECONDS
    killed = False
    while True:
        try:
            while True:
                pid, _status = os.waitpid(-group, os.WNOHANG)
                if pid == 0:
                    break
        except ChildProcessError:
            pass

        try:
            os.killpg(group, 0)
        except ProcessLookupError:
            return True

        if time.monotonic() >= deadline:
            if killed:
                return False
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                return True
            killed = True
            deadline = time.monotonic() + PROCESS_GROUP_KILL_SECONDS
        time.sleep(0.02)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path(".prism-labgrid"))
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    ctx = SimpleNamespace(
        hook_dir=output / "hooks" / "labgrid",
        config=SimpleNamespace(
            labgrid_place=os.environ.get("LG_PLACE"),
            dmesg_via=os.environ.get("PRISM_DMESG_VIA", "auto"),
            dmesg_ssh_user=os.environ.get("PRISM_DMESG_SSH_USER", "root"),
            dmesg_ssh_key=os.environ.get("PRISM_DMESG_SSH_KEY"),
        ),
    )
    for name in ("hardware.json", "artifacts.zip"):
        (output / name).unlink(missing_ok=True)
    for pattern in ("dmesg_*.log", "console_*", "metadata.json"):
        for path in ctx.hook_dir.glob(pattern):
            if path.is_file() or path.is_symlink():
                path.unlink()

    hook = LabgridSessionHook()
    metadata: dict = {}
    collection_errors: list[str] = []

    def collect(stage: str) -> None:
        try:
            metadata.update(getattr(hook, f"session_{stage}")(ctx))
        except Exception as exc:  # Best-effort diagnostics must preserve the test result.
            collection_errors.append(f"session_{stage}: collection failed ({type(exc).__name__})")

    child = None
    interrupted_signal = None
    waiting_for_child = False

    def forward_signal(signum, frame) -> None:
        nonlocal interrupted_signal
        first_signal = interrupted_signal is None
        if first_signal:
            interrupted_signal = signum
        if child is not None:
            try:
                os.killpg(child.pid, signum)
            except ProcessLookupError:
                pass
            if first_signal and waiting_for_child:
                raise KeyboardInterrupt

    previous_handlers = {
        signum: signal.signal(signum, forward_signal) for signum in (signal.SIGTERM, signal.SIGINT)
    }
    status = 0
    group_quiet = True
    with _child_subreaper():
        try:
            collect("pre")
            try:
                if interrupted_signal is None:
                    waiting_for_child = True
                    child = subprocess.Popen(command, start_new_session=True)
                    # A signal can arrive between fork and assignment to child.
                    if interrupted_signal is not None:
                        forward_signal(interrupted_signal, None)
                        raise KeyboardInterrupt
                    status = child.wait()
            except KeyboardInterrupt:
                if interrupted_signal is None:
                    forward_signal(signal.SIGINT, None)
            finally:
                waiting_for_child = False
                if child is not None:
                    if interrupted_signal is not None or status < 0:
                        group_quiet = _wait_for_process_group(child.pid)
                    if group_quiet:
                        child.wait()
                    else:
                        child.poll()
                    child = None
                if group_quiet:
                    collect("post")
                else:
                    collection_errors.append(
                        "session_post: process group remained active after SIGKILL"
                    )
                metadata["collection_errors"] = [
                    *metadata.get("collection_errors", []),
                    *collection_errors,
                ]
                if interrupted_signal is not None:
                    metadata["interrupted_signal"] = interrupted_signal
                hardware = output / "hardware.json"
                hardware.write_text(
                    json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
                with zipfile.ZipFile(
                    output / "artifacts.zip", "w", zipfile.ZIP_DEFLATED
                ) as archive:
                    archive.write(hardware, "hardware.json")
                    for path in sorted(ctx.hook_dir.glob("*")):
                        if path.is_file() and not path.is_symlink():
                            archive.write(path, str(path.relative_to(output)))
        finally:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)

    if interrupted_signal is not None:
        return 128 + interrupted_signal
    return 128 - status if status < 0 else status


if __name__ == "__main__":
    raise SystemExit(main())
