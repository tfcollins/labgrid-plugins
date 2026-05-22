"""Boot a labgrid place, resolve its URI, and launch MATLAB against it.

The core of the MATLAB HW-CI bridge. Given a labgrid env yaml (rendered
from a place's tags, or supplied directly) it:

1. loads the labgrid :class:`~labgrid.Environment` and transitions the
   place's boot strategy to a reached state (e.g. Linux shell),
2. resolves the booted board's address from its ``NetworkService``
   resource into a libIIO URI (``ip:<addr>``),
3. launches MATLAB with ``IIO_URI`` (and ``board``) exported, so the
   toolbox's existing ``runHWTests`` picks the URI up unchanged
   (TransceiverToolbox ``test/HardwareTests.m`` honours ``IIO_URI``),
4. copies MATLAB's JUnit output to a requested path.

The labgrid ``Environment`` and the subprocess launcher are injected
(``env_factory`` / ``runner``) so the orchestration is unit-tested
without hardware or a MATLAB install. Place reservation (acquire /
release) is handled one layer up in the CLI, not here.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Default MATLAB batch body: add the toolbox test/ dir to the path and run
# the existing hardware test entry point. `board` is read from the env
# (set by matlab_env) so this string stays board-agnostic.
_DEFAULT_MATLAB_BODY = "addpath(genpath('test')); runHWTests(getenv('board'))"

# MATLAB's JUnit file name is derived from the board name in runHWTests.m
# (`board + "_HWTestResults.xml"`).
_JUNIT_NAME_TMPL = "{board}_HWTestResults.xml"


@dataclass(frozen=True)
class MatlabRunResult:
    """Outcome of a MATLAB HW test launch."""

    uri: str
    matlab_board: str
    returncode: int
    junit_dest: Path | None = None


def resolve_uri(target: Any, *, network_resource: str = "NetworkService") -> str:
    """Resolve a target's network address into a libIIO ``ip:`` URI."""
    address = target.get_resource(network_resource).address
    return f"ip:{address}"


def default_matlab_command() -> str:
    """The default MATLAB ``-batch`` body (runs ``runHWTests``)."""
    return _DEFAULT_MATLAB_BODY


def build_matlab_command(matlab_bin: str, body: str) -> list[str]:
    """Build the MATLAB argv for a headless ``-batch`` run."""
    return [matlab_bin, "-nodisplay", "-nosplash", "-batch", body]


def matlab_env(
    base_env: Mapping[str, str],
    uri: str,
    matlab_board: str,
) -> dict[str, str]:
    """Return a copy of ``base_env`` with ``IIO_URI`` and ``board`` set."""
    env = dict(base_env)
    env["IIO_URI"] = uri
    env["board"] = matlab_board
    return env


def run_matlab_tests(
    *,
    config: str | Path,
    matlab_board: str,
    boot_strategy: str,
    repo_dir: str | Path,
    matlab_bin: str = "matlab",
    target_name: str = "main",
    reached_state: str = "shell",
    network_resource: str = "NetworkService",
    matlab_command: str | None = None,
    junit_dest: str | Path | None = None,
    env_factory: Callable[[str], Any] = None,  # type: ignore[assignment]
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    base_env: Mapping[str, str] | None = None,
) -> MatlabRunResult:
    """Boot the place, resolve its URI, and run MATLAB HW tests.

    ``env_factory`` defaults to :class:`labgrid.Environment` (imported
    lazily so importing this module never requires labgrid). ``runner``
    defaults to :func:`subprocess.run`. Both are injected in tests.

    Returns a :class:`MatlabRunResult`; the caller maps ``returncode``
    to its own exit status. Releasing the place is the caller's job.
    """
    if env_factory is None:
        from labgrid import Environment  # lazy: only needed for real runs

        env_factory = Environment

    repo_dir = Path(repo_dir)

    env = env_factory(str(config))
    target = env.get_target(target_name)
    strategy = target.get_driver(boot_strategy)
    strategy.transition(reached_state)

    uri = resolve_uri(target, network_resource=network_resource)

    body = matlab_command if matlab_command is not None else default_matlab_command()
    cmd = build_matlab_command(matlab_bin, body)
    run_env = matlab_env(base_env if base_env is not None else os.environ, uri, matlab_board)

    proc = runner(cmd, cwd=str(repo_dir), env=run_env)

    copied: Path | None = None
    if junit_dest is not None:
        src = repo_dir / _JUNIT_NAME_TMPL.format(board=matlab_board)
        if src.is_file():
            dest = Path(junit_dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            copied = dest

    return MatlabRunResult(
        uri=uri,
        matlab_board=matlab_board,
        returncode=proc.returncode,
        junit_dest=copied,
    )
