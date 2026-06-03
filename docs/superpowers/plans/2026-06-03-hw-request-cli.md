# Hardware Request — `adi-lg request` CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `adi-lg request --part <P> [--carrier <C>] [--bootfile <V>] [--wait <S>] [--power-down] --run '<cmd>'` — a generic CLI that acquires+boots a board by part, exports its interfaces (`IIO_URI`/`LG_PLACE`/`LG_CARRIER`) into a child command's environment, runs the command, and releases the board, with stable exit codes and signal-safe cleanup.

**Architecture:** A thin Click command in a new `adi_lg_plugins/tools/request_cli.py`, registered onto the existing `adi-lg` group in `tools/cli.py`. It is a pure wrapper over the Plan-2 `adi_lg_plugins.request.request()` context manager: build the request, enter its context, run the child, let the context manager release on exit. Request-layer exceptions map to dedicated exit codes; a SIGTERM handler converts a CI job-timeout into the same `KeyboardInterrupt` that Ctrl-C already raises, so the context manager's `finally` (release) always runs.

**Tech Stack:** Python 3.10+, Click (existing CLI lib), `rich` for output, stdlib `subprocess`/`signal`. ruff line length 100, double quotes, `from __future__ import annotations`. Tests use `click.testing.CliRunner` + monkeypatch. Run `pytest`/`ruff` from repo root `/home/tcollins/dev/lg-test/labgrid-plugins`.

This is **Plan 3 of 5** of the first-cut increment (`docs/superpowers/specs/2026-06-03-low-config-hardware-request-fresh-design.md`). It depends on **Plan 2** (`adi_lg_plugins.request`: `request`, `Lease`, `NoMatchingBoard`/`BoardUnavailable`/`ProvisionError`, and `EXIT_NO_MATCH`/`EXIT_UNAVAILABLE`/`EXIT_PROVISION`), on PR #50.

---

## Grounding & reuse

A working `adi-lg request` command exists on the original track (`feat/hw-request-phase1`, commit `0f59a7e`, in `tools/cli.py`). This plan adapts it with three deliberate changes for the fresh design:

| Aspect | Original | This plan |
| --- | --- | --- |
| Location | inline in `tools/cli.py` | own module `tools/request_cli.py`, registered in `cli.py` (thinner `cli.py`, isolated/testable surface) |
| `--power-down` | absent | added (passes `power_down` to `request()`) |
| Signal handling | none (relied on `finally` only) | SIGTERM→`KeyboardInterrupt` handler + child-termination + `EXIT_INTERRUPTED=130`, per the spec's "Ctrl-C / CI job-timeout still releases the place" |
| exported env | `IIO_URI`, `LG_PLACE` | adds `LG_CARRIER` |

Exit-code constants (`EXIT_NO_MATCH=10`, `EXIT_UNAVAILABLE=11`, `EXIT_PROVISION=12`) come from `adi_lg_plugins.request.errors` (already built in Plan 2). The CLI defines `EXIT_INTERRUPTED=130` (the conventional 128+SIGINT code).

## File Structure

- Create: `adi_lg_plugins/tools/request_cli.py` — the `request_cmd` Click command + `_run_child` + signal helpers.
- Modify: `adi_lg_plugins/tools/cli.py` — import and register `request_cmd` (two lines).
- Modify: `docs/source/user-guide/cli.rst` — document the `request` command.
- Test: `tests/test_request_cli.py`.

`request_cli.py` must NOT import from `cli.py` (cli.py imports it — avoid a cycle); it has its own `Console`.

## Conventions

- Commands run from repo root. Test runner: `python3 -m pytest tests/test_request_cli.py -v`.
- Lint: `ruff check <files> && ruff format <files>` before each commit.
- `CliRunner().invoke(cli, [...])` turns `sys.exit(n)` into `result.exit_code == n` and captures `console.print` output in `result.output`.

---

### Task 1: The `request_cmd` command (functional, no signals yet)

**Files:**
- Create: `adi_lg_plugins/tools/request_cli.py`
- Modify: `adi_lg_plugins/tools/cli.py`
- Test: `tests/test_request_cli.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_request_cli.py`:

```python
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

from click.testing import CliRunner

from adi_lg_plugins.request import BoardUnavailable, NoMatchingBoard, ProvisionError
from adi_lg_plugins.request.errors import EXIT_NO_MATCH, EXIT_PROVISION, EXIT_UNAVAILABLE
from adi_lg_plugins.tools import request_cli as rc_mod
from adi_lg_plugins.tools.cli import cli


def _fake_lease(uri="ip:10.0.0.57", place="adrv9002-zcu102", carrier="zcu102"):
    return MagicMock(uri=uri, place=place, carrier=carrier)


def _fake_request_yielding(lease):
    @contextmanager
    def fake_request(**kwargs):
        fake_request.kwargs = kwargs
        yield lease

    return fake_request


def test_request_registered_and_help():
    result = CliRunner().invoke(cli, ["request", "--help"])
    assert result.exit_code == 0
    assert "--part" in result.output
    assert "--power-down" in result.output


def test_request_flash_mode_rejected():
    result = CliRunner().invoke(cli, ["request", "--part", "adrv9002", "--mode", "flash"])
    assert result.exit_code != 0
    assert "flash" in result.output.lower()


def test_request_no_run_prints_uri(monkeypatch):
    monkeypatch.setattr(rc_mod, "request", _fake_request_yielding(_fake_lease()))
    result = CliRunner().invoke(cli, ["request", "--part", "adrv9002"])
    assert result.exit_code == 0
    assert "ip:10.0.0.57" in result.output


def test_request_runs_command_with_exported_env(monkeypatch):
    monkeypatch.setattr(rc_mod, "request", _fake_request_yielding(_fake_lease()))
    captured = {}

    def fake_run_child(run_cmd, env):
        captured["cmd"] = run_cmd
        captured["uri"] = env.get("IIO_URI")
        captured["place"] = env.get("LG_PLACE")
        captured["carrier"] = env.get("LG_CARRIER")
        return 0

    monkeypatch.setattr(rc_mod, "_run_child", fake_run_child)
    result = CliRunner().invoke(cli, ["request", "--part", "adrv9002", "--run", "echo hi"])
    assert result.exit_code == 0
    assert captured == {
        "cmd": "echo hi",
        "uri": "ip:10.0.0.57",
        "place": "adrv9002-zcu102",
        "carrier": "zcu102",
    }


def test_request_propagates_child_exit_code(monkeypatch):
    monkeypatch.setattr(rc_mod, "request", _fake_request_yielding(_fake_lease()))
    monkeypatch.setattr(rc_mod, "_run_child", lambda c, e: 3)
    result = CliRunner().invoke(cli, ["request", "--part", "adrv9002", "--run", "false"])
    assert result.exit_code == 3


def test_request_power_down_flag_passed(monkeypatch):
    fake = _fake_request_yielding(_fake_lease())
    monkeypatch.setattr(rc_mod, "request", fake)
    monkeypatch.setattr(rc_mod, "_run_child", lambda c, e: 0)

    CliRunner().invoke(cli, ["request", "--part", "adrv9002", "--power-down", "--run", "true"])
    assert fake.kwargs["power_down"] is True

    CliRunner().invoke(cli, ["request", "--part", "adrv9002", "--run", "true"])
    assert fake.kwargs["power_down"] is False


def test_request_no_match_exit_code(monkeypatch):
    @contextmanager
    def fake_request(**kwargs):
        raise NoMatchingBoard("no such board")
        yield  # pragma: no cover

    monkeypatch.setattr(rc_mod, "request", fake_request)
    result = CliRunner().invoke(cli, ["request", "--part", "nope", "--run", "true"])
    assert result.exit_code == EXIT_NO_MATCH


def test_request_unavailable_exit_code(monkeypatch):
    @contextmanager
    def fake_request(**kwargs):
        raise BoardUnavailable("all busy")
        yield  # pragma: no cover

    monkeypatch.setattr(rc_mod, "request", fake_request)
    result = CliRunner().invoke(cli, ["request", "--part", "adrv9002", "--run", "true"])
    assert result.exit_code == EXIT_UNAVAILABLE


def test_request_provision_error_exit_code_and_tail(monkeypatch):
    @contextmanager
    def fake_request(**kwargs):
        raise ProvisionError("boot failed", console_tail="kernel panic xyz")
        yield  # pragma: no cover

    monkeypatch.setattr(rc_mod, "request", fake_request)
    result = CliRunner().invoke(cli, ["request", "--part", "adrv9002", "--run", "true"])
    assert result.exit_code == EXIT_PROVISION
    assert "kernel panic xyz" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_request_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: ...tools.request_cli` (and the `request` subcommand isn't registered).

- [ ] **Step 3: Write minimal implementation** — create `adi_lg_plugins/tools/request_cli.py`:

```python
"""``adi-lg request`` — the generic hardware-request CLI surface.

A thin wrapper over :func:`adi_lg_plugins.request.request`: acquire + boot a
board by part, export its interfaces (``IIO_URI`` / ``LG_PLACE`` /
``LG_CARRIER``) into a child command's environment, run the command, and
release the board. Request-layer exceptions map to stable exit codes so CI can
tell an infra problem from a real test failure.
"""

from __future__ import annotations

import os
import subprocess
import sys

import click
from rich.console import Console

from adi_lg_plugins.request import (
    BoardUnavailable,
    NoMatchingBoard,
    ProvisionError,
    request,
)
from adi_lg_plugins.request.errors import (
    EXIT_NO_MATCH,
    EXIT_PROVISION,
    EXIT_UNAVAILABLE,
)

console = Console()


def _run_child(run_cmd: str, env: dict) -> int:
    """Run the user command with the board's interfaces in its environment."""
    return subprocess.call(run_cmd, shell=True, env=env)  # noqa: S602 - user cmd by design


@click.command(name="request")
@click.option("--part", required=True, help="Part / daughter-board, e.g. adrv9002")
@click.option("--carrier", default=None, help="Optional carrier filter, e.g. zcu102")
@click.option(
    "--mode",
    type=click.Choice(["uri", "flash"]),
    default="uri",
    help="uri: boot Linux and export IIO_URI (default). flash: not yet available.",
)
@click.option("--bootfile", default=None, help="Pin an image version (default: catalog default)")
@click.option(
    "--wait", default=1800, type=int, help="Seconds to wait for a free board (0=fail fast)"
)
@click.option(
    "--power-down",
    "power_down",
    is_flag=True,
    default=False,
    help="Power the board off after release (default: leave powered for the next user)",
)
@click.option("--coord", default=None, help="Coordinator host:port (default: $LG_COORDINATOR)")
@click.option(
    "--run",
    "run_cmd",
    default=None,
    help="Command to run with IIO_URI / LG_PLACE / LG_CARRIER exported",
)
def request_cmd(part, carrier, mode, bootfile, wait, power_down, coord, run_cmd):
    """Request a board by part, boot it, run a command against it, and release it."""
    if mode == "flash":
        raise click.ClickException("flash mode is not available yet (uri mode only)")

    try:
        with request(
            part=part,
            carrier=carrier,
            mode=mode,
            bootfile=bootfile,
            wait=wait,
            coord=coord,
            power_down=power_down,
        ) as board:
            if not run_cmd:
                console.print(board.uri or board.place)
                return
            env = os.environ.copy()
            if board.uri:
                env["IIO_URI"] = board.uri
            env["LG_PLACE"] = board.place
            if board.carrier:
                env["LG_CARRIER"] = board.carrier
            console.print(f"[green]Booted {board.place} -> {board.uri}[/green]")
            rc = _run_child(run_cmd, env)
            sys.exit(rc)
    except NoMatchingBoard as e:
        console.print(f"[bold red]No matching board: {e}[/bold red]")
        sys.exit(EXIT_NO_MATCH)
    except BoardUnavailable as e:
        console.print(f"[bold red]Board unavailable: {e}[/bold red]")
        sys.exit(EXIT_UNAVAILABLE)
    except ProvisionError as e:
        console.print(f"[bold red]Provisioning failed: {e}[/bold red]")
        if getattr(e, "console_tail", ""):
            console.print(e.console_tail)
        sys.exit(EXIT_PROVISION)
```

Then register it in `adi_lg_plugins/tools/cli.py`. Add the import alongside the existing `from adi_lg_plugins.tools.config_gen import generate_config`:

```python
from adi_lg_plugins.tools.config_gen import generate_config
from adi_lg_plugins.tools.request_cli import request_cmd
```

and register it next to the existing `cli.add_command(generate_config)`:

```python
cli.add_command(generate_config)
cli.add_command(request_cmd)
```

(Note: `sys.exit(rc)` inside the `with` raises `SystemExit`, which is not caught by the `except NoMatchingBoard/...` clauses, so `request()`'s context manager releases the board and the process exits with the child's code. The three `except` clauses only catch request-layer failures.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_request_cli.py -v`
Expected: PASS (9 passed).

- [ ] **Step 5: Lint and commit**

```bash
cd /home/tcollins/dev/lg-test/labgrid-plugins
ruff check adi_lg_plugins/tools/request_cli.py adi_lg_plugins/tools/cli.py tests/test_request_cli.py && \
  ruff format adi_lg_plugins/tools/request_cli.py adi_lg_plugins/tools/cli.py tests/test_request_cli.py
git add adi_lg_plugins/tools/request_cli.py adi_lg_plugins/tools/cli.py tests/test_request_cli.py
git commit -m "feat(cli): add 'adi-lg request' command (uri mode)"
```

---

### Task 2: Signal-safe cleanup (SIGINT/SIGTERM + child termination)

**Files:**
- Modify: `adi_lg_plugins/tools/request_cli.py`
- Test: `tests/test_request_cli.py`

The spec requires Ctrl-C and a CI job-timeout to still release the board. SIGINT already raises `KeyboardInterrupt` (which triggers `request()`'s `finally`); SIGTERM does not, so we install a handler that converts it. `_run_child` switches to `Popen` so we can terminate the child before re-raising. A new `EXIT_INTERRUPTED=130` distinguishes an interrupted run.

- [ ] **Step 1: Write the failing test** — append to `tests/test_request_cli.py`:

```python
import signal

import pytest


def test_install_term_handler_makes_sigterm_raise(monkeypatch):
    installed = {}

    def fake_signal(signum, handler):
        installed[signum] = handler
        return signal.SIG_DFL  # previous handler

    monkeypatch.setattr(rc_mod.signal, "signal", fake_signal)
    rc_mod._install_term_handler()
    handler = installed[signal.SIGTERM]
    with pytest.raises(KeyboardInterrupt):
        handler(signal.SIGTERM, None)


def test_run_child_terminates_child_on_interrupt(monkeypatch):
    events = []

    class FakeProc:
        def __init__(self):
            self._first = True

        def wait(self, timeout=None):
            if self._first:
                self._first = False
                raise KeyboardInterrupt
            events.append("waited")
            return 0

        def terminate(self):
            events.append("terminated")

        def kill(self):
            events.append("killed")

    monkeypatch.setattr(rc_mod.subprocess, "Popen", lambda *a, **k: FakeProc())
    with pytest.raises(KeyboardInterrupt):
        rc_mod._run_child("sleep 100", {})
    assert "terminated" in events


def test_request_interrupt_releases_and_exits_130(monkeypatch):
    monkeypatch.setattr(rc_mod, "request", _fake_request_yielding(_fake_lease()))

    def interrupt(run_cmd, env):
        raise KeyboardInterrupt

    monkeypatch.setattr(rc_mod, "_run_child", interrupt)
    result = CliRunner().invoke(cli, ["request", "--part", "adrv9002", "--run", "sleep 100"])
    assert result.exit_code == rc_mod.EXIT_INTERRUPTED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_request_cli.py -k "interrupt or term_handler" -v`
Expected: FAIL — `_install_term_handler`/`EXIT_INTERRUPTED` don't exist; `_run_child` doesn't use `Popen`.

- [ ] **Step 3: Write the implementation** — edit `adi_lg_plugins/tools/request_cli.py`:

(a) Add `import signal` to the imports (keep alphabetical: after `import os`).

(b) Add the interrupt exit code constant next to the imports (after `console = Console()`):

```python
EXIT_INTERRUPTED = 130  # SIGINT / SIGTERM during the run (128 + SIGINT)

# Sentinel: SIGTERM handler could not be installed (e.g. not on the main thread).
_NOT_INSTALLED = object()


def _install_term_handler():
    """Make SIGTERM raise KeyboardInterrupt so a CI job-timeout triggers
    request()'s cleanup (release), exactly as Ctrl-C (SIGINT) already does.

    Returns the previous handler so the caller can restore it, or the
    ``_NOT_INSTALLED`` sentinel if installation failed (signal handlers can
    only be set from the main thread).
    """

    def _raise(signum, frame):
        raise KeyboardInterrupt(f"received signal {signum}")

    try:
        return signal.signal(signal.SIGTERM, _raise)
    except ValueError:
        return _NOT_INSTALLED


def _restore_term_handler(previous) -> None:
    if previous is _NOT_INSTALLED:
        return
    try:
        signal.signal(signal.SIGTERM, previous)
    except ValueError:
        pass
```

(c) Replace `_run_child` with the `Popen`-based version that terminates the child on interrupt:

```python
def _run_child(run_cmd: str, env: dict) -> int:
    """Run the user command with the board's interfaces in its environment.

    Uses Popen so an interrupt (Ctrl-C / SIGTERM) stops the child before
    re-raising, letting request()'s context manager release the board.
    """
    proc = subprocess.Popen(run_cmd, shell=True, env=env)  # noqa: S602 - user cmd by design
    try:
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        raise
```

(d) Wrap the command body to install/restore the handler and map the interrupt. The full `request_cmd` body becomes:

```python
def request_cmd(part, carrier, mode, bootfile, wait, power_down, coord, run_cmd):
    """Request a board by part, boot it, run a command against it, and release it."""
    if mode == "flash":
        raise click.ClickException("flash mode is not available yet (uri mode only)")

    previous = _install_term_handler()
    try:
        with request(
            part=part,
            carrier=carrier,
            mode=mode,
            bootfile=bootfile,
            wait=wait,
            coord=coord,
            power_down=power_down,
        ) as board:
            if not run_cmd:
                console.print(board.uri or board.place)
                return
            env = os.environ.copy()
            if board.uri:
                env["IIO_URI"] = board.uri
            env["LG_PLACE"] = board.place
            if board.carrier:
                env["LG_CARRIER"] = board.carrier
            console.print(f"[green]Booted {board.place} -> {board.uri}[/green]")
            rc = _run_child(run_cmd, env)
            sys.exit(rc)
    except KeyboardInterrupt:
        console.print("[bold red]Interrupted — board released[/bold red]")
        sys.exit(EXIT_INTERRUPTED)
    except NoMatchingBoard as e:
        console.print(f"[bold red]No matching board: {e}[/bold red]")
        sys.exit(EXIT_NO_MATCH)
    except BoardUnavailable as e:
        console.print(f"[bold red]Board unavailable: {e}[/bold red]")
        sys.exit(EXIT_UNAVAILABLE)
    except ProvisionError as e:
        console.print(f"[bold red]Provisioning failed: {e}[/bold red]")
        if getattr(e, "console_tail", ""):
            console.print(e.console_tail)
        sys.exit(EXIT_PROVISION)
    finally:
        _restore_term_handler(previous)
```

(`KeyboardInterrupt` is raised either by Ctrl-C, by the SIGTERM handler, or re-raised out of `_run_child`. In every case `request()`'s `finally` has already released the board by the time we catch it here; the handler is restored in our own `finally`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_request_cli.py -v`
Expected: PASS (12 passed — 9 from Task 1 + 3 new). The Task-1 tests still pass because `_install_term_handler` installs then restores the SIGTERM handler around each invocation, leaving global state clean.

- [ ] **Step 5: Lint and commit**

```bash
cd /home/tcollins/dev/lg-test/labgrid-plugins
ruff check adi_lg_plugins/tools/request_cli.py tests/test_request_cli.py && \
  ruff format adi_lg_plugins/tools/request_cli.py tests/test_request_cli.py
git add adi_lg_plugins/tools/request_cli.py tests/test_request_cli.py
git commit -m "feat(cli): signal-safe cleanup for 'adi-lg request' (SIGINT/SIGTERM -> release)"
```

---

### Task 3: Document the `request` command

**Files:**
- Modify: `docs/source/user-guide/cli.rst`

The spec calls for the CLI to be "well documented and easy to use." Add a `request` subsection to the existing CLI reference, before the `boot-fabric` subsection (it is the recommended entry point for running tests against a board).

- [ ] **Step 1: Add the documentation**

In `docs/source/user-guide/cli.rst`, immediately before the `boot-fabric` subsection (the line `boot-fabric` followed by its `~~~~~~~~~~~` underline), insert:

```rst
request
~~~~~~~

Request a board **by part** — labgrid selects a free matching board, boots it,
hands over its libIIO URI, runs your command, and releases the board. No
strategy/driver/resource config and no place name required.

.. code-block:: bash

    # Boot an ADRV9002 (on any free carrier) and run a pytest selection against it
    adi-lg request --part adrv9002 --run 'pytest test/ -k adrv9002'

    # Narrow to a carrier and pin an image version
    adi-lg request --part adrv9002 --carrier zcu102 --bootfile 2023_R2_P1 \
        --run 'pytest test/ -k adrv9002'

    # Print just the URI (no command) — useful for scripting
    adi-lg request --part adrv9002

Options:

* ``--part`` (required): part / daughter-board, e.g. ``adrv9002``.
* ``--carrier``: optional FPGA carrier filter, e.g. ``zcu102``. Omit to match any free carrier.
* ``--bootfile``: pin an image version. Defaults to the coordinator catalog's default image.
* ``--wait`` (default ``1800``): seconds to queue for a free matching board. ``0`` fails fast.
* ``--power-down``: power the board off after release (default: leave it powered for the next user).
* ``--coord``: coordinator ``host:port`` (default: ``$LG_COORDINATOR``).
* ``--run '<cmd>'``: run ``<cmd>`` with ``IIO_URI``, ``LG_PLACE`` and ``LG_CARRIER`` exported into
  its environment. The command's own exit code is propagated.

Exit codes (so CI can tell an infra problem from a real test failure):

* ``0`` / child's code — success, or the ``--run`` command's own exit code.
* ``10`` — no matching board exists for the part/filters.
* ``11`` — matching boards exist but none became free within ``--wait``.
* ``12`` — the board failed to boot (the console tail is printed for triage).
* ``130`` — interrupted (Ctrl-C or CI job-timeout); the board is still released.

```

- [ ] **Step 2: Sanity-check the RST renders (no broken syntax)**

Run: `python3 -c "from docutils.core import publish_doctree; publish_doctree(open('docs/source/user-guide/cli.rst').read())" 2>&1 | grep -iE "severe|error" || echo "no RST errors"`
Expected: `no RST errors` (warnings about unknown directives like `code-block` are fine — Sphinx provides them; only `severe`/`error` matter). If `docutils` is not installed, skip this step and instead visually confirm the inserted block matches the surrounding subsections' `~~~~` underline style.

- [ ] **Step 3: Commit**

```bash
cd /home/tcollins/dev/lg-test/labgrid-plugins
git add docs/source/user-guide/cli.rst
git commit -m "docs(cli): document the 'adi-lg request' command"
```

---

## Self-Review (completed during plan authoring)

**Spec coverage** — implements the spec's "Surface A — generic CLI (`adi-lg request`)":
- `adi-lg request --part … [--carrier] [--bootfile] [--wait] [--power-down] --run '<cmd>'` ✓ (Task 1/2).
- Exports interfaces into the child env (`IIO_URI`, `LG_PLACE`, `LG_CARRIER`) ✓ (Task 1).
- Stratified exit codes: child code passes through; dedicated `10`/`11`/`12`; provision prints console tail ✓ (Task 1).
- SIGINT/SIGTERM handlers so Ctrl-C / CI job-timeout still releases ✓ (Task 2), plus `130` for interrupted.
- "the single entry point everything else shells out to" — it is a thin wrapper over `request()`; Plan 4 (pytest) and Plan 5 (GHA) reuse `request()`/this CLI. ✓
- Well documented ✓ (Task 3).

Deliberately out of scope (later plans / increments): flash mode (gated with a clear error), the `--adi-part`/`adi_board` pytest fixture (Plan 4), the GHA workflow (Plan 5).

**Placeholder scan** — no TBD/TODO; every code/step is complete.

**Type/name consistency** — `request_cmd` option dests (`part`, `carrier`, `mode`, `bootfile`, `wait`, `power_down`, `coord`, `run_cmd`) match the `request(...)` keyword arguments from Plan 2 (`part`, `carrier`, `mode`, `bootfile`, `wait`, `coord`, `power_down`). `_run_child(run_cmd, env)` and `_install_term_handler()`/`_restore_term_handler(previous)` signatures match their call sites and the monkeypatched fakes in the tests. `EXIT_NO_MATCH`/`EXIT_UNAVAILABLE`/`EXIT_PROVISION` are imported from `adi_lg_plugins.request.errors` (defined in Plan 2); `EXIT_INTERRUPTED` is defined here.

## Open Questions / notes for implementation

- **Main-thread caveat:** `signal.signal` only works on the main thread; `_install_term_handler` guards `ValueError` and degrades to no-op (relying on `request()`'s `finally` + SIGINT's default `KeyboardInterrupt`). The CLI runs on the main thread in normal use, so the handler installs.
- **Child signal forwarding:** `_run_child` terminates the child on interrupt but does not forward arbitrary signals; `terminate()` (SIGTERM) then `kill()` after 10s is sufficient for the "release the board" guarantee. Richer process-group handling is out of scope.
- **`rich` output in CI:** `console.print` markup (e.g. `[green]`) renders as plain text when stdout is not a TTY, so CI logs stay clean. No change needed.
