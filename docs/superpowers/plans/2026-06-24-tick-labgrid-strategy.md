# Tick labgrid drivers + `BootTickFPGASSH` strategy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Tick-specific labgrid classes to `adi_lg_plugins` so a pre-baked Kuiper ZCU102+AD9081 board can have the Tick scheduler deployed at runtime (FPGA program → DT overlay → kernel module → iiod) as one strategy transition.

**Architecture:** A `TickArtifacts` resource carries the three artifact paths. Three small drivers (`TickFpgaManagerDriver`, `TickOverlayDriver`, `TickModuleDriver`) act on the target over the bound `CommandProtocol` + `FileTransferProtocol`. `BootTickFPGASSH` subclasses the existing `BootFPGASoCSSH` boot strategy and extends it with Tick deploy states. All classes self-register via the package's `__init__` import lists and `pyproject.toml` entry points; unit tests bypass labgrid binding by constructing objects with `__new__` and mocking the protocols.

**Tech Stack:** Python ≥3.10, `labgrid>=25`, `attr`, pytest, ruff (100 cols), nox. Repo: `/home/tcollins/dev/labgrid-plugins`, branch `tick-labgrid-strategy`.

**Conventions (from the repo):** `@target_factory.reg_driver`/`reg_resource` + `@attr.s(eq=False)`; no per-file license header (module docstring only); tests construct via `Class.__new__(Class)` and set bindings to `types.SimpleNamespace`/`MagicMock`, asserting calls with `mock.patch.object`/`assert_called_once`. `nox -s tests` = `pytest tests/`; `nox -s lint` = `ruff check .` + `ruff format --check .`; `nox -s format` = `ruff format .` + `ruff check --fix .`. Run `nox -s format` before each commit.

**Protocol facts:** labgrid `CommandProtocol.run(cmd)` returns `(stdout_list, stderr_list, returncode)`; `run_check(cmd)` returns `stdout_list` and raises on non-zero. `FileTransferProtocol.put(local, remote)` uploads. Import them: `from labgrid.protocol import CommandProtocol, FileTransferProtocol`.

---

## File structure

| File | Responsibility | Action |
| --- | --- | --- |
| `adi_lg_plugins/resources/tickartifacts.py` | `TickArtifacts` resource (artifact paths + tunables) | Create |
| `adi_lg_plugins/drivers/_tickcommon.py` | `stdout_text()` helper shared by the drivers | Create |
| `adi_lg_plugins/drivers/tickfpgamanagerdriver.py` | `TickFpgaManagerDriver` | Create |
| `adi_lg_plugins/drivers/tickoverlaydriver.py` | `TickOverlayDriver` | Create |
| `adi_lg_plugins/drivers/tickmoduledriver.py` | `TickModuleDriver` | Create |
| `adi_lg_plugins/strategies/boottickfpgassh.py` | `BootTickFPGASSH` strategy | Create |
| `adi_lg_plugins/resources/__init__.py` | register resource module | Modify (`_MODULES`) |
| `adi_lg_plugins/drivers/__init__.py` | register driver modules | Modify (`_MODULES`) |
| `adi_lg_plugins/strategies/__init__.py` | register strategy module | Modify (`_MODULES`) |
| `pyproject.toml` | entry points | Modify (3 blocks) |
| `tests/test_tickartifacts_resource.py` | resource test | Create |
| `tests/test_tickfpgamanager_driver.py` | fpga driver test | Create |
| `tests/test_tickoverlay_driver.py` | overlay driver test | Create |
| `tests/test_tickmodule_driver.py` | module driver test | Create |
| `tests/test_boottickfpgassh_strategy.py` | strategy test | Create |
| `tests/test_tick_registration.py` | registration/import test | Create |
| `docs/source/tick.rst` + toctree | docs page | Create + Modify |

---

## Task 1: `TickArtifacts` resource

**Files:**
- Create: `adi_lg_plugins/resources/tickartifacts.py`
- Create: `tests/test_tickartifacts_resource.py`
- Modify: `adi_lg_plugins/resources/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tickartifacts_resource.py`:

```python
"""Unit tests for the TickArtifacts resource: defaults and field presence."""

from adi_lg_plugins.resources.tickartifacts import TickArtifacts


def _artifacts():
    # Resources accept target=None for unbound construction (as KuiperRelease tests do).
    return TickArtifacts(
        None,
        "tick",
        bitstream_path="/run/tick.bit",
        overlay_dtbo_path="/run/tick.dtbo",
        module_ko_path="/run/axi_timed_command_scheduler.ko",
    )


def test_required_paths_are_stored():
    a = _artifacts()
    assert a.bitstream_path == "/run/tick.bit"
    assert a.overlay_dtbo_path == "/run/tick.dtbo"
    assert a.module_ko_path == "/run/axi_timed_command_scheduler.ko"


def test_target_side_defaults():
    a = _artifacts()
    assert a.firmware_name == "tick.bit"
    assert a.overlay_name == "tick"
    assert a.remote_dir == "/tmp/tick"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_tickartifacts_resource.py -q`
Expected: FAIL — `ModuleNotFoundError: adi_lg_plugins.resources.tickartifacts`.

- [ ] **Step 3: Create the resource**

Create `adi_lg_plugins/resources/tickartifacts.py`:

```python
"""Resource describing the per-run Tick deploy artifacts.

Holds host paths to the bitstream, the prebuilt devicetree overlay (.dtbo),
and the kernel module, plus target-side naming used by the Tick deploy
drivers. Pure configuration; declared in a labgrid env config.
"""

import attr
from labgrid.factory import target_factory
from labgrid.resource.common import Resource

_str = attr.validators.instance_of(str)


@target_factory.reg_resource
@attr.s(eq=False)
class TickArtifacts(Resource):
    """Paths and names for the Tick runtime deploy.

    Args:
        bitstream_path (str): Host path to the FPGA ``.bit``.
        overlay_dtbo_path (str): Host path to the prebuilt ``.dtbo`` overlay.
        module_ko_path (str): Host path to ``axi_timed_command_scheduler.ko``.
        firmware_name (str): Name written under ``/lib/firmware`` on target.
        overlay_name (str): configfs overlay directory name.
        remote_dir (str): Scratch directory on the target for staged files.
    """

    bitstream_path = attr.ib(validator=_str)
    overlay_dtbo_path = attr.ib(validator=_str)
    module_ko_path = attr.ib(validator=_str)
    firmware_name = attr.ib(default="tick.bit", validator=_str)
    overlay_name = attr.ib(default="tick", validator=_str)
    remote_dir = attr.ib(default="/tmp/tick", validator=_str)
```

- [ ] **Step 4: Register the resource module**

In `adi_lg_plugins/resources/__init__.py`, add `"tickartifacts"` to the `_MODULES` tuple (keep it alphabetical / consistent with the existing entries). If `resources/__init__.py` does not use a `_MODULES` tuple, mirror the structure of `adi_lg_plugins/drivers/__init__.py` exactly (the `importlib.import_module` loop) and include `"tickartifacts"`.

- [ ] **Step 5: Add the entry point**

In `pyproject.toml`, under `[project.entry-points."labgrid.resources"]`, add:

```toml
tickartifacts = "adi_lg_plugins.resources.tickartifacts:TickArtifacts"
```

- [ ] **Step 6: Format, run the test**

Run: `nox -s format && python3 -m pytest tests/test_tickartifacts_resource.py -q`
Expected: PASS (2 tests). If the `TickArtifacts(None, "tick", ...)` construction raises because the labgrid `Resource` base rejects a `None` target, change `_artifacts()` to build via `TickArtifacts.__new__(TickArtifacts)` and assign the six attributes directly, then re-run.

- [ ] **Step 7: Commit**

```bash
git add adi_lg_plugins/resources/tickartifacts.py adi_lg_plugins/resources/__init__.py \
        pyproject.toml tests/test_tickartifacts_resource.py
git commit -m "feat: add TickArtifacts resource"
```

---

## Task 2: `stdout_text` helper + `TickFpgaManagerDriver`

**Files:**
- Create: `adi_lg_plugins/drivers/_tickcommon.py`
- Create: `adi_lg_plugins/drivers/tickfpgamanagerdriver.py`
- Create: `tests/test_tickfpgamanager_driver.py`
- Modify: `adi_lg_plugins/drivers/__init__.py`, `pyproject.toml`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tickfpgamanager_driver.py`:

```python
"""Unit tests for TickFpgaManagerDriver (constructed without labgrid binding)."""

import logging
import types
from unittest import mock

import pytest

from adi_lg_plugins.drivers.tickfpgamanagerdriver import TickFpgaManagerDriver


def _driver(run_check_returns):
    d = TickFpgaManagerDriver.__new__(TickFpgaManagerDriver)
    d.artifacts = types.SimpleNamespace(bitstream_path="/run/tick.bit", firmware_name="tick.bit")
    d.command = types.SimpleNamespace(run_check=mock.Mock(side_effect=run_check_returns))
    d.fs = types.SimpleNamespace(put=mock.Mock())
    d.logger = logging.getLogger("test_tickfpga")
    return d


def test_load_bitstream_puts_and_writes_firmware_sysfs():
    d = _driver([[], ["operating"]])  # echo -> empty, cat state -> operating
    d.load_bitstream()

    d.fs.put.assert_called_once_with("/run/tick.bit", "/lib/firmware/tick.bit")
    cmds = [c.args[0] for c in d.command.run_check.call_args_list]
    assert any("/sys/class/fpga_manager/fpga0/firmware" in c and "tick.bit" in c for c in cmds)
    assert any("cat /sys/class/fpga_manager/fpga0/state" in c for c in cmds)


def test_load_bitstream_raises_when_not_operating():
    d = _driver([[], ["unknown"]])
    with pytest.raises(Exception):
        d.load_bitstream()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_tickfpgamanager_driver.py -q`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Create the shared helper**

Create `adi_lg_plugins/drivers/_tickcommon.py`:

```python
"""Shared helpers for the Tick deploy drivers."""


def stdout_text(result):
    """Join a labgrid ``run_check`` stdout result (list[str]) into one string."""
    if isinstance(result, (list, tuple)):
        return "\n".join(str(x) for x in result)
    return str(result)
```

- [ ] **Step 4: Create the driver**

Create `adi_lg_plugins/drivers/tickfpgamanagerdriver.py`:

```python
"""Driver to program the ZynqMP FPGA at runtime via the fpga_manager sysfs.

The ZynqMP fpga_manager accepts a ``.bit`` and strips the Xilinx header
in-kernel; the firmware loader reads from ``/lib/firmware``. The driver binds
the command + file-transfer protocols and a TickArtifacts resource. The
strategy activates the driver before calling ``load_bitstream``.
"""

import attr
from labgrid.driver.common import Driver
from labgrid.driver.exception import ExecutionError
from labgrid.factory import target_factory
from labgrid.protocol import CommandProtocol, FileTransferProtocol

from ._tickcommon import stdout_text


@target_factory.reg_driver
@attr.s(eq=False)
class TickFpgaManagerDriver(Driver):
    """Load a bitstream through ``/sys/class/fpga_manager/fpga0``."""

    bindings = {
        "command": CommandProtocol,
        "fs": FileTransferProtocol,
        "artifacts": "TickArtifacts",
    }

    def load_bitstream(self):
        """Stage the bitstream into /lib/firmware and program the FPGA."""
        fw = self.artifacts.firmware_name
        self.fs.put(self.artifacts.bitstream_path, f"/lib/firmware/{fw}")
        self.command.run_check(f"sh -c 'echo {fw} > /sys/class/fpga_manager/fpga0/firmware'")
        state = stdout_text(self.command.run_check("cat /sys/class/fpga_manager/fpga0/state"))
        if "operating" not in state:
            raise ExecutionError(f"fpga_manager not operating after load: {state!r}")
```

- [ ] **Step 5: Register + entry point**

In `adi_lg_plugins/drivers/__init__.py`, add `"tickfpgamanagerdriver"` to `_MODULES` (do **not** add `_tickcommon` — it has no `reg_*` decorator). In `pyproject.toml` under `[project.entry-points."labgrid.drivers"]` add:

```toml
tickfpgamanagerdriver = "adi_lg_plugins.drivers.tickfpgamanagerdriver:TickFpgaManagerDriver"
```

- [ ] **Step 6: Format, run the test**

Run: `nox -s format && python3 -m pytest tests/test_tickfpgamanager_driver.py -q`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add adi_lg_plugins/drivers/_tickcommon.py adi_lg_plugins/drivers/tickfpgamanagerdriver.py \
        adi_lg_plugins/drivers/__init__.py pyproject.toml tests/test_tickfpgamanager_driver.py
git commit -m "feat: add TickFpgaManagerDriver"
```

---

## Task 3: `TickOverlayDriver`

**Files:**
- Create: `adi_lg_plugins/drivers/tickoverlaydriver.py`
- Create: `tests/test_tickoverlay_driver.py`
- Modify: `adi_lg_plugins/drivers/__init__.py`, `pyproject.toml`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tickoverlay_driver.py`:

```python
"""Unit tests for TickOverlayDriver."""

import logging
import types
from unittest import mock

import pytest

from adi_lg_plugins.drivers.tickoverlaydriver import TickOverlayDriver


def _driver(run_check_returns):
    d = TickOverlayDriver.__new__(TickOverlayDriver)
    d.artifacts = types.SimpleNamespace(
        overlay_dtbo_path="/run/tick.dtbo", overlay_name="tick", remote_dir="/tmp/tick"
    )
    d.command = types.SimpleNamespace(
        run_check=mock.Mock(side_effect=run_check_returns), run=mock.Mock(return_value=([], [], 0))
    )
    d.fs = types.SimpleNamespace(put=mock.Mock())
    d.logger = logging.getLogger("test_tickoverlay")
    return d


def test_apply_stages_dtbo_and_applies_overlay():
    # run_check order: mkdir remote, mount-check, mkdir overlay, cat>dtbo, cat status
    d = _driver([[], [], [], [], ["applied"]])
    d.apply()

    d.fs.put.assert_called_once_with("/run/tick.dtbo", "/tmp/tick/tick.dtbo")
    cmds = [c.args[0] for c in d.command.run_check.call_args_list]
    assert any("/sys/kernel/config/device-tree/overlays/tick/dtbo" in c for c in cmds)
    assert any("/sys/kernel/config/device-tree/overlays/tick/status" in c for c in cmds)


def test_apply_raises_when_status_not_applied():
    d = _driver([[], [], [], [], ["unapplied"]])
    with pytest.raises(Exception):
        d.apply()


def test_remove_rmdirs_overlay():
    d = _driver([])
    d.remove()
    assert any(
        "rmdir" in c.args[0] and "overlays/tick" in c.args[0]
        for c in d.command.run.call_args_list
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_tickoverlay_driver.py -q`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Create the driver**

Create `adi_lg_plugins/drivers/tickoverlaydriver.py`:

```python
"""Driver to apply/remove a Tick devicetree overlay via configfs.

Expects a prebuilt ``.dtbo`` (no dtc dependency). Stages it on the target,
ensures configfs is mounted, and applies it under
``/sys/kernel/config/device-tree/overlays/<overlay_name>``.
"""

import attr
from labgrid.driver.common import Driver
from labgrid.driver.exception import ExecutionError
from labgrid.factory import target_factory
from labgrid.protocol import CommandProtocol, FileTransferProtocol

from ._tickcommon import stdout_text

_CONFIGFS = "/sys/kernel/config/device-tree/overlays"


@target_factory.reg_driver
@attr.s(eq=False)
class TickOverlayDriver(Driver):
    """Apply and remove the Tick DT overlay through configfs."""

    bindings = {
        "command": CommandProtocol,
        "fs": FileTransferProtocol,
        "artifacts": "TickArtifacts",
    }

    def apply(self):
        """Stage the .dtbo and apply the overlay; raise unless it reports applied."""
        a = self.artifacts
        remote = f"{a.remote_dir}/{a.overlay_name}.dtbo"
        ovl = f"{_CONFIGFS}/{a.overlay_name}"
        self.command.run_check(f"mkdir -p {a.remote_dir}")
        self.fs.put(a.overlay_dtbo_path, remote)
        self.command.run_check(
            "sh -c 'mountpoint -q /sys/kernel/config || mount -t configfs none /sys/kernel/config'"
        )
        self.command.run(f"rmdir {ovl}")  # best-effort: clear a stale overlay
        self.command.run_check(f"mkdir -p {ovl}")
        self.command.run_check(f"sh -c 'cat {remote} > {ovl}/dtbo'")
        status = stdout_text(self.command.run_check(f"cat {ovl}/status"))
        if "applied" not in status:
            raise ExecutionError(f"overlay status not applied: {status!r}")

    def remove(self):
        """Remove the overlay (idempotent; used on teardown)."""
        ovl = f"{_CONFIGFS}/{self.artifacts.overlay_name}"
        self.command.run(f"rmdir {ovl}")
```

- [ ] **Step 4: Register + entry point**

Add `"tickoverlaydriver"` to `_MODULES` in `adi_lg_plugins/drivers/__init__.py`. In `pyproject.toml` add:

```toml
tickoverlaydriver = "adi_lg_plugins.drivers.tickoverlaydriver:TickOverlayDriver"
```

- [ ] **Step 5: Format, run the test**

Run: `nox -s format && python3 -m pytest tests/test_tickoverlay_driver.py -q`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add adi_lg_plugins/drivers/tickoverlaydriver.py adi_lg_plugins/drivers/__init__.py \
        pyproject.toml tests/test_tickoverlay_driver.py
git commit -m "feat: add TickOverlayDriver"
```

---

## Task 4: `TickModuleDriver`

**Files:**
- Create: `adi_lg_plugins/drivers/tickmoduledriver.py`
- Create: `tests/test_tickmodule_driver.py`
- Modify: `adi_lg_plugins/drivers/__init__.py`, `pyproject.toml`

- [ ] **Step 1: Write the failing test**

Create `tests/test_tickmodule_driver.py`:

```python
"""Unit tests for TickModuleDriver."""

import logging
import types
from unittest import mock

from adi_lg_plugins.drivers.tickmoduledriver import TickModuleDriver


def _driver(*, run_returns, run_check_returns, restart_iiod=True, force=True):
    d = TickModuleDriver.__new__(TickModuleDriver)
    d.artifacts = types.SimpleNamespace(
        module_ko_path="/run/axi_timed_command_scheduler.ko", remote_dir="/tmp/tick"
    )
    d.restart_iiod = restart_iiod
    d.force_on_vermagic_mismatch = force
    d.command = types.SimpleNamespace(
        run=mock.Mock(side_effect=run_returns),
        run_check=mock.Mock(side_effect=run_check_returns),
    )
    d.fs = types.SimpleNamespace(put=mock.Mock())
    d.logger = logging.getLogger("test_tickmodule")
    return d


def test_load_inserts_module_and_restarts_iiod():
    # run: rmmod (ok), insmod (ok); run_check: mkdir, modinfo, uname, restart iiod
    d = _driver(
        run_returns=[([], [], 0), ([], [], 0)],
        run_check_returns=[[], ["6.1.0-xilinx SMP mod_unload"], ["6.1.0-xilinx"], []],
    )
    d.load()

    d.fs.put.assert_called_once_with(
        "/run/axi_timed_command_scheduler.ko", "/tmp/tick/axi_timed_command_scheduler.ko"
    )
    run_cmds = [c.args[0] for c in d.command.run.call_args_list]
    assert any(c.startswith("insmod ") for c in run_cmds)
    check_cmds = [c.args[0] for c in d.command.run_check.call_args_list]
    assert any("systemctl restart iiod" in c for c in check_cmds)


def test_load_skips_iiod_when_disabled():
    d = _driver(
        run_returns=[([], [], 0), ([], [], 0)],
        run_check_returns=[[], ["6.1.0-xilinx"], ["6.1.0-xilinx"]],
        restart_iiod=False,
    )
    d.load()
    check_cmds = [c.args[0] for c in d.command.run_check.call_args_list]
    assert not any("iiod" in c for c in check_cmds)


def test_load_force_inserts_on_insmod_failure():
    # insmod fails (rc=1) -> force=y via run_check
    d = _driver(
        run_returns=[([], [], 0), ([], ["bad"], 1)],
        run_check_returns=[[], ["5.0-foo"], ["6.1.0-xilinx"], [], []],
        force=True,
    )
    d.load()
    check_cmds = [c.args[0] for c in d.command.run_check.call_args_list]
    assert any("force=y" in c for c in check_cmds)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_tickmodule_driver.py -q`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Create the driver**

Create `adi_lg_plugins/drivers/tickmoduledriver.py`:

```python
"""Driver to load/unload the Tick kernel module and expose its IIO device.

Stages the ``.ko`` on the target, checks vermagic against the running kernel,
``insmod``s it (with an optional ``force`` fallback), and optionally restarts
``iiod`` so the network IIO context re-enumerates the new device.
"""

import os

import attr
from labgrid.driver.common import Driver
from labgrid.driver.exception import ExecutionError
from labgrid.factory import target_factory
from labgrid.protocol import CommandProtocol, FileTransferProtocol

from ._tickcommon import stdout_text


@target_factory.reg_driver
@attr.s(eq=False)
class TickModuleDriver(Driver):
    """Insert/remove ``axi_timed_command_scheduler.ko`` over SSH."""

    bindings = {
        "command": CommandProtocol,
        "fs": FileTransferProtocol,
        "artifacts": "TickArtifacts",
    }

    restart_iiod = attr.ib(default=True, validator=attr.validators.instance_of(bool))
    force_on_vermagic_mismatch = attr.ib(
        default=True, validator=attr.validators.instance_of(bool)
    )

    def _modname(self):
        return os.path.basename(self.artifacts.module_ko_path).removesuffix(".ko")

    def load(self):
        """Stage and insmod the module; optionally restart iiod."""
        a = self.artifacts
        ko = f"{a.remote_dir}/{os.path.basename(a.module_ko_path)}"
        self.command.run_check(f"mkdir -p {a.remote_dir}")
        self.fs.put(a.module_ko_path, ko)

        vermagic = stdout_text(self.command.run_check(f"modinfo -F vermagic {ko}")).split()
        krel = stdout_text(self.command.run_check("uname -r")).strip()
        first = vermagic[0] if vermagic else ""
        if first and krel and first != krel:
            self.logger.warning("module vermagic %r != target kernel %r", first, krel)

        self.command.run(f"rmmod {self._modname()}")  # best-effort if already loaded
        _, stderr, rc = self.command.run(f"insmod {ko}")
        if rc != 0:
            if self.force_on_vermagic_mismatch:
                self.command.run_check(f"insmod {ko} force=y")
            else:
                raise ExecutionError(f"insmod failed (rc={rc}): {stderr!r}")

        if self.restart_iiod:
            self.command.run_check("systemctl restart iiod")

    def unload(self):
        """Remove the module (idempotent; used on teardown)."""
        self.command.run(f"rmmod {self._modname()}")
```

- [ ] **Step 4: Register + entry point**

Add `"tickmoduledriver"` to `_MODULES` in `adi_lg_plugins/drivers/__init__.py`. In `pyproject.toml` add:

```toml
tickmoduledriver = "adi_lg_plugins.drivers.tickmoduledriver:TickModuleDriver"
```

- [ ] **Step 5: Format, run the test**

Run: `nox -s format && python3 -m pytest tests/test_tickmodule_driver.py -q`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add adi_lg_plugins/drivers/tickmoduledriver.py adi_lg_plugins/drivers/__init__.py \
        pyproject.toml tests/test_tickmodule_driver.py
git commit -m "feat: add TickModuleDriver"
```

---

## Task 5: `BootTickFPGASSH` strategy

Subclasses `BootFPGASoCSSH`. Because Python `Enum`s are not extensible, this strategy defines its **own** `Status` with only the Tick states; `transition()` resolves Tick states locally and delegates everything else (parent state names/members) to `super().transition()`. The Tick logic lives in a plain `_transition_tick()` helper so it is unit-testable on a `__new__`'d instance (the inherited `__attrs_post_init__` touches bindings, so the constructor is not test-friendly).

**Files:**
- Create: `adi_lg_plugins/strategies/boottickfpgassh.py`
- Create: `tests/test_boottickfpgassh_strategy.py`
- Modify: `adi_lg_plugins/strategies/__init__.py`, `pyproject.toml`

- [ ] **Step 1: Write the failing test**

Create `tests/test_boottickfpgassh_strategy.py`:

```python
"""Unit tests for BootTickFPGASSH: Tick deploy ordering and delegation."""

import logging
from unittest import mock

from adi_lg_plugins.strategies.bootfpgasocssh import BootFPGASoCSSH
from adi_lg_plugins.strategies.boottickfpgassh import BootTickFPGASSH, Status


def _strategy():
    s = BootTickFPGASSH.__new__(BootTickFPGASSH)
    s.status = Status.unknown
    s.target = mock.MagicMock()
    s.logger = logging.getLogger("test_boottick")
    s.tick_fpga = mock.MagicMock()
    s.tick_overlay = mock.MagicMock()
    s.tick_module = mock.MagicMock()
    s.power = mock.MagicMock()
    return s


def test_module_loaded_runs_full_deploy_in_order():
    s = _strategy()
    with mock.patch.object(BootFPGASoCSSH, "transition") as parent:
        s._transition_tick(Status.tick_module_loaded)

    parent.assert_any_call("shell")  # booted to a shell before deploy
    s.tick_fpga.load_bitstream.assert_called_once()
    s.tick_overlay.apply.assert_called_once()
    s.tick_module.load.assert_called_once()
    assert s.status == Status.tick_module_loaded


def test_tick_off_reverses_then_powers_off():
    s = _strategy()
    s._transition_tick(Status.tick_off)
    s.tick_module.unload.assert_called_once()
    s.tick_overlay.remove.assert_called_once()
    s.power.off.assert_called_once()


def test_dispatch_delegates_unknown_states_to_parent():
    s = _strategy()
    with mock.patch.object(BootFPGASoCSSH, "transition") as parent:
        s._dispatch("shell")  # not a Tick Status -> parent handles it
    parent.assert_called_once_with("shell")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_boottickfpgassh_strategy.py -q`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Create the strategy**

Create `adi_lg_plugins/strategies/boottickfpgassh.py`:

```python
"""Strategy: boot a pre-baked Kuiper SD, then deploy Tick at runtime.

Subclasses BootFPGASoCSSH to reuse its power/boot-to-shell machinery
(``update_image`` stays off so the SD is not rewritten), then adds Tick
deploy states: program the FPGA, apply the DT overlay, and load the kernel
module. Tick states are resolved against this class's own Status enum;
any other value is delegated to the parent state machine.
"""

import enum

import attr
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.strategy import StrategyError

from ._compat import never_retry
from .bootfpgasocssh import BootFPGASoCSSH


class Status(enum.Enum):
    """Tick deploy states layered on top of BootFPGASoCSSH."""

    unknown = 0
    tick_fpga_loaded = 1
    tick_overlay_applied = 2
    tick_module_loaded = 3
    tick_off = 4


@target_factory.reg_driver
@attr.s(eq=False)
class BootTickFPGASSH(BootFPGASoCSSH):
    """BootFPGASoCSSH + runtime Tick deploy (bitstream, overlay, module)."""

    bindings = {
        **BootFPGASoCSSH.bindings,
        "tick_fpga": "TickFpgaManagerDriver",
        "tick_overlay": "TickOverlayDriver",
        "tick_module": "TickModuleDriver",
    }

    @never_retry
    @step()
    def transition(self, status, *, step):
        """Thin decorated entry point; real logic is in plain helpers (testable)."""
        self._dispatch(status)

    def _dispatch(self, status):
        """Resolve Tick states here; delegate all others to BootFPGASoCSSH."""
        if not isinstance(status, Status):
            try:
                status = Status[status]
            except (KeyError, TypeError):
                return super().transition(status)
        self._transition_tick(status)

    def _transition_tick(self, status):
        if status == Status.tick_fpga_loaded:
            super().transition("shell")
            self.target.activate(self.tick_fpga)
            self.tick_fpga.load_bitstream()
        elif status == Status.tick_overlay_applied:
            self._transition_tick(Status.tick_fpga_loaded)
            self.target.activate(self.tick_overlay)
            self.tick_overlay.apply()
        elif status == Status.tick_module_loaded:
            self._transition_tick(Status.tick_overlay_applied)
            self.target.activate(self.tick_module)
            self.tick_module.load()
        elif status == Status.tick_off:
            for drv, meth in ((self.tick_module, "unload"), (self.tick_overlay, "remove")):
                try:
                    self.target.activate(drv)
                    getattr(drv, meth)()
                except Exception as exc:  # noqa: BLE001 - best-effort teardown
                    self.logger.debug("tick teardown %s failed: %s", meth, exc)
            if self.power:
                self.target.activate(self.power)
                self.power.off()
        else:
            raise StrategyError(f"unhandled tick status {status}")
        self.status = status
```

- [ ] **Step 4: Register + entry point**

Add `"boottickfpgassh"` to `_MODULES` in `adi_lg_plugins/strategies/__init__.py`. In `pyproject.toml` under `[project.entry-points."labgrid.strategies"]` add:

```toml
boottickfpgassh = "adi_lg_plugins.strategies.boottickfpgassh:BootTickFPGASSH"
```

- [ ] **Step 5: Format, run the test**

Run: `nox -s format && python3 -m pytest tests/test_boottickfpgassh_strategy.py -q`
Expected: PASS (3 tests). The tests deliberately call the plain helpers `_dispatch`/`_transition_tick` (not the decorated `transition`), so the `@step`/`@never_retry` decorators are never exercised on a `__new__`'d instance. Do not remove those decorators from production code.

- [ ] **Step 6: Commit**

```bash
git add adi_lg_plugins/strategies/boottickfpgassh.py adi_lg_plugins/strategies/__init__.py \
        pyproject.toml tests/test_boottickfpgassh_strategy.py
git commit -m "feat: add BootTickFPGASSH strategy"
```

---

## Task 6: Registration / import test

Confirms importing the package registers all five new names with labgrid's `target_factory` (catches a missing `_MODULES` entry or entry point).

**Files:**
- Create: `tests/test_tick_registration.py`

- [ ] **Step 1: Write the test**

Create `tests/test_tick_registration.py`:

```python
"""Importing adi_lg_plugins must register all Tick drivers/resource/strategy."""

import adi_lg_plugins  # noqa: F401  (import side effects register the classes)
from labgrid.factory import target_factory


def test_tick_classes_are_registered():
    assert "TickArtifacts" in target_factory.resources
    for name in ("TickFpgaManagerDriver", "TickOverlayDriver", "TickModuleDriver", "BootTickFPGASSH"):
        assert name in target_factory.drivers, name
```

- [ ] **Step 2: Run the test**

Run: `python3 -m pytest tests/test_tick_registration.py -q`
Expected: PASS. If `target_factory.resources` / `.drivers` are not plain dicts keyed by class name in this labgrid version, adjust the assertion to the actual registry API — inspect with `python3 -c "from labgrid.factory import target_factory as t; print(type(t.drivers), list(t.drivers)[:3])"` and match the real structure (the class names must appear once the package is imported).

- [ ] **Step 3: Commit**

```bash
git add tests/test_tick_registration.py
git commit -m "test: assert Tick classes register with target_factory"
```

---

## Task 7: Docs page

**Files:**
- Create: `docs/source/tick.rst`
- Modify: the docs toctree (the `index.rst`/`.md` under `docs/source/` that lists pages)

- [ ] **Step 1: Locate the toctree**

Run: `grep -rn "toctree" docs/source | head`
Note the file and the existing entries so the new page is added consistently.

- [ ] **Step 2: Create the docs page**

Create `docs/source/tick.rst`:

```rst
Tick runtime deploy (ZCU102 + AD9081)
=====================================

The Tick classes deploy the ``axi_timed_command_scheduler`` IP onto a board
that already booted its pre-baked Kuiper SD image, at runtime over SSH.

Components
----------

- ``TickArtifacts`` (resource) -- paths to the bitstream, prebuilt ``.dtbo``
  overlay, and kernel module, plus target-side naming.
- ``TickFpgaManagerDriver`` -- programs the FPGA via the ``fpga_manager`` sysfs.
- ``TickOverlayDriver`` -- applies/removes the DT overlay via configfs.
- ``TickModuleDriver`` -- ``insmod``\ s the module and (optionally) restarts
  ``iiod`` so the IIO device is network-discoverable.
- ``BootTickFPGASSH`` -- subclasses ``BootFPGASoCSSH``; boots to a shell, then
  runs the three deploy steps. States:
  ``tick_fpga_loaded -> tick_overlay_applied -> tick_module_loaded``; ``tick_off``
  reverses the deploy and powers down.

Example environment
-------------------

.. code-block:: yaml

   imports:
     - adi_lg_plugins
   targets:
     main:
       resources:
         - RemotePlace: {name: mini2}
         - TickArtifacts:
             bitstream_path: /run/tick/ad9081_fmca_ebz_zcu102.bit
             overlay_dtbo_path: /run/tick/tick.dtbo
             module_ko_path: /run/tick/axi_timed_command_scheduler.ko
       drivers:
         - VesyncPowerDriver: {}
         - SSHDriver: {keyfile: ""}
         - TickFpgaManagerDriver: {}
         - TickOverlayDriver: {}
         - TickModuleDriver: {}
         - BootTickFPGASSH: {}

.. note::

   The Tick drivers bind the ``CommandProtocol`` + ``FileTransferProtocol``
   pair. When the env also defines a console-based shell that satisfies those
   protocols, name the intended SSH driver explicitly so binding is
   unambiguous.
```

- [ ] **Step 3: Add the page to the toctree**

Add `tick` to the toctree entry found in Step 1 (matching the existing indentation/format — bare page name, no extension).

- [ ] **Step 4: Build the docs**

Run: `nox -s docs`
Expected: build succeeds. If it fails because the page is not referenced, ensure Step 3 added it to a real toctree. Fix any rST warnings in the new file only.

- [ ] **Step 5: Commit**

```bash
git add docs/source/tick.rst docs/source
git commit -m "docs: document the Tick drivers and BootTickFPGASSH strategy"
```

---

## Task 8: Whole-suite green (lint + tests + docs)

**Files:** none (verification only)

- [ ] **Step 1: Format and lint**

Run: `nox -s format && nox -s lint`
Expected: `ruff check .` clean and `ruff format --check .` clean. Commit any formatting the `format` session applied:

```bash
git status --porcelain
# if files changed:
git add -A && git commit -m "style: ruff format Tick additions"
```

- [ ] **Step 2: Full test suite**

Run: `nox -s tests`
Expected: PASS — the new Tick tests plus the pre-existing suite. Investigate any regression before proceeding (the Tick additions are purely additive and import-guarded, so existing tests must remain green).

- [ ] **Step 3: Docs build**

Run: `nox -s docs`
Expected: build succeeds.

- [ ] **Step 4: Final status check**

```bash
git log --oneline main..HEAD
git status -sb
```

---

## Out of scope (per the spec)

SD reflash, `.dtso`→`.dtbo` compilation, the in-repo `tick` overlay-mode wiring to this strategy (separate follow-up spec in `tfcollins/tick`), and AD9081 converter-control. Do not add them here.
