# Design: Tick deploy drivers + `BootTickFPGASSH` strategy (`adi_lg_plugins`)

- **Date:** 2026-06-24
- **Repo:** `tfcollins/labgrid-plugins` (package `adi_lg_plugins`)
- **Status:** Approved (pending written-spec review)
- **Sibling spec:** the in-repo Tick HIL foundation (already merged in `tfcollins/tick`,
  `docs/superpowers/specs/2026-06-22-labgrid-hil-verification-design.md`) scoped this as a
  roadmap. This spec is the upstream half it consumes.

## 1. Goal and scope

Add Tick-specific labgrid classes to `adi_lg_plugins` so a ZCU102 + AD9081 board can be
brought up and have the Tick scheduler deployed at **runtime** over SSH — program the FPGA,
apply the devicetree overlay, load the kernel module, and make the IIO device
network-discoverable — as a single labgrid strategy transition.

This matches today's validated path (`tick`'s `scripts/run_mini2_hardware_tests.sh`): the
board boots its **pre-baked Kuiper SD image** on power-up, then deploy happens at runtime
(`fpga_manager` sysfs → configfs overlay → `insmod`). It is **not** an SD reflash.

### In scope

- One Resource: `TickArtifacts`.
- Three Drivers: `TickFpgaManagerDriver`, `TickOverlayDriver`, `TickModuleDriver`.
- One Strategy: `BootTickFPGASSH` (subclasses the existing `BootFPGASoCSSH`).
- `pyproject.toml` entry points + package import registration.
- Unit tests (no hardware) mirroring the repo's existing mocked-binding pattern.
- A short Sphinx doc page.

### Out of scope (YAGNI)

SD reflash (the in-repo USBSDWire path owns clean-slate provisioning), `.dtso`→`.dtbo`
compilation (callers supply a prebuilt `.dtbo`), the in-repo `tick` overlay-mode wiring to
this strategy (separate follow-up spec in `tfcollins/tick`), and AD9081 converter-control.

## 2. Decisions locked during brainstorming

| Decision | Choice |
| --- | --- |
| Spec scope | Upstream `adi_lg_plugins` classes only |
| Strategy shape | Compose with `BootFPGASoCSSH` (subclass), reuse Kuiper boot-to-shell |
| Artifact model | A `TickArtifacts` Resource holding the three paths |
| DT overlay | Driver expects a prebuilt `.dtbo` (no `dtc` dependency) |
| iiod visibility | `TickModuleDriver` restarts `iiod` after `insmod`, gated by an attr (default on) |
| Strategy name | `BootTickFPGASSH` |
| Driver bindings | The protocol pair `CommandProtocol` (`run`) + `FileTransferProtocol` (`put`), plus `TickArtifacts` |

## 3. Repo conventions to follow

- Driver pattern: `@target_factory.reg_driver` + `@attr.s(eq=False)` subclassing `Driver`;
  `bindings = {...}`; methods decorated `@Driver.check_active` and `@step()`; target
  interaction through the bound protocols (the repo's `RemoteExecMixin` unifies host-side
  remote exec — reuse it only if a step runs on the coordinator host; on-target steps use the
  bound `CommandProtocol`).
- Resource pattern: `@target_factory.reg_resource` + `@attr.s(eq=False)` subclassing
  `Resource`; `attr.ib` fields with validators.
- Strategy pattern: `@target_factory.reg_driver` + `@attr.s(eq=False)` subclassing the chosen
  base; a `Status` `enum.Enum`; a `@never_retry @step()` `transition(status)` state machine
  (see `bootfpgasoc.py` / `bootfpgasocssh.py`).
- Packaging: classes are discovered via `pyproject.toml` `[project.entry-points."labgrid.*"]`
  and registered on import; mirror the existing entries.
- Style: ruff (line length 100; rules E,W,F,I,UP,B; E501 ignored), Apache-2.0, module
  docstrings, **no per-file license header**. Lint/format via `nox -s format` / `nox -s lint`.
- Tests: pytest, no hardware. Construct drivers via `Driver.__new__(...)` with bindings set as
  `types.SimpleNamespace` mocks; assert exact commands via `mock.patch.object`.

## 4. Components

### 4.1 `TickArtifacts` (Resource)

Holds the per-run artifact paths and target-side tunables. Pure config.

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `bitstream_path` | str | required | host path to the `.bit` |
| `overlay_dtbo_path` | str | required | host path to the **prebuilt** `.dtbo` |
| `module_ko_path` | str | required | host path to `axi_timed_command_scheduler.ko` |
| `firmware_name` | str | `"tick.bit"` | name under `/lib/firmware` on target |
| `overlay_name` | str | `"tick"` | configfs overlay directory name |
| `remote_dir` | str | `"/tmp/tick"` | scratch dir on target for `.dtbo`/`.ko` |

Path fields are `str` (not validated for existence at construction, so tests need no real
files); drivers surface a clear error if a `put` source is missing.

### 4.2 `TickFpgaManagerDriver` (Driver)

`bindings = {command: CommandProtocol, fs: FileTransferProtocol, artifacts: TickArtifacts}`.

- `load_bitstream()` (`@check_active @step()`):
  1. `fs.put(artifacts.bitstream_path, "/lib/firmware/<firmware_name>")`.
  2. `command.run_check("echo <firmware_name> > /sys/class/fpga_manager/fpga0/firmware")`.
  3. Read `/sys/class/fpga_manager/fpga0/state`; raise unless it reports `operating`.

The ZynqMP `fpga_manager` driver accepts a `.bit` and strips the Xilinx header in-kernel;
the firmware loader reads from `/lib/firmware`.

### 4.3 `TickOverlayDriver` (Driver)

Same bindings.

- `apply()`:
  1. `fs.put(artifacts.overlay_dtbo_path, "<remote_dir>/<overlay_name>.dtbo")`.
  2. Ensure configfs mounted (`mountpoint -q /sys/kernel/config || mount -t configfs ...`).
  3. Remove any stale `/sys/kernel/config/device-tree/overlays/<overlay_name>` (rmdir).
  4. `mkdir` it, then `cat <remote_dir>/<overlay_name>.dtbo > .../<overlay_name>/dtbo`.
  5. Read `.../<overlay_name>/status`; raise unless `applied`.
- `remove()`: `rmdir .../<overlay_name>` (idempotent; used on teardown).

### 4.4 `TickModuleDriver` (Driver)

Same bindings, plus attrs `restart_iiod = attr.ib(default=True)` and
`force_on_vermagic_mismatch = attr.ib(default=True)`.

- `load()`:
  1. `fs.put(artifacts.module_ko_path, "<remote_dir>/<basename>.ko")`.
  2. Compare on-target `modinfo -F vermagic <ko>` against `uname -r`; on mismatch, log a
     warning.
  3. `rmmod` the module if already loaded (ignore failure).
  4. `insmod`; if it fails and `force_on_vermagic_mismatch`, retry with `force=y` (mirrors the
     current `run_mini2` fallback).
  5. If `restart_iiod`: `systemctl restart iiod` and settle, so the **network** IIO context
     re-enumerates and exposes `axi-timed-command-scheduler`.
- `unload()`: `rmmod` (idempotent; teardown).

### 4.5 `BootTickFPGASSH` (Strategy, subclasses `BootFPGASoCSSH`)

Reuses the inherited Kuiper boot-to-shell machinery (with `update_image` defaulting off, so
the pre-baked SD is not rewritten) and adds Tick deploy states.

- `Status` extends the inherited states with, after `shell`:
  `tick_fpga_loaded → tick_overlay_applied → tick_module_loaded`.
- `bindings` adds `tick_fpga: TickFpgaManagerDriver`, `tick_overlay: TickOverlayDriver`,
  `tick_module: TickModuleDriver` (the inherited boot bindings remain).
- `transition(status)` (`@never_retry @step()`): for each new state, first
  `transition(Status.shell)` (inherited), then `target.activate(<driver>)` and call its
  action (`load_bitstream` / `apply` / `load`). `tick_module_loaded` is terminal and means
  "Tick device loaded and network-discoverable."
- Cleanup: a `soft_off` path deactivates in reverse — `tick_module.unload()` →
  `tick_overlay.remove()` → inherited power-off — leaving the place clean and re-runnable.

## 5. Data flow

```
lab env YAML
  RemotePlace
  VesyncPowerDriver
  <SSH shell driver>            # satisfies CommandProtocol + FileTransferProtocol
  TickArtifacts (3 paths)
  TickFpgaManagerDriver / TickOverlayDriver / TickModuleDriver
  BootTickFPGASSH
        |
  labgrid-client ... <transition to tick_module_loaded>
        |
  BootTickFPGASSH.transition():
    -> (inherited) power on, boot pre-baked Kuiper, reach SSH shell
    -> tick_fpga.load_bitstream()   (put .bit, fpga_manager firmware, check state)
    -> tick_overlay.apply()         (put .dtbo, configfs apply, check status)
    -> tick_module.load()           (put .ko, insmod, restart iiod)
        |
  Tick IIO device present and visible over ip:<target>
```

## 6. Error handling & teardown

- `transition()` is `@never_retry` (consistent with `BootFPGASoC`).
- Each driver step raises on a non-zero command or unexpected state: fpga `state != operating`,
  overlay `status != applied`, `insmod` failure after the optional force retry.
- Vermagic mismatch warns; with `force_on_vermagic_mismatch` it force-loads, else it surfaces
  the failure.
- `soft_off` deactivates in reverse (`rmmod` → overlay `remove` → power off) so a failed or
  completed run leaves the place clean.

## 7. Testing (pytest, no hardware)

Mirror `tests/test_massstorage_driver.py`: build each driver with `Driver.__new__(...)`, set
`command`/`fs`/`artifacts` to `types.SimpleNamespace` mocks (with `run`/`run_check`/`put`
patched), and assert the **exact command strings and order**.

- `TickFpgaManagerDriver`: asserts the `put` target and the `firmware` sysfs write; the
  failure branch when `state` is not `operating`.
- `TickOverlayDriver`: asserts the configfs apply sequence and the `status != applied` failure;
  `remove()` idempotence.
- `TickModuleDriver`: asserts `rmmod`→`insmod`(→`force`)→`systemctl restart iiod` ordering;
  the vermagic-mismatch warn/force branch; `restart_iiod=False` skips the restart.
- `BootTickFPGASSH`: mock the three Tick drivers and stub the inherited boot (patch
  `transition(Status.shell)` / `status`), drive through the three new states, assert each
  driver is activated and called once in order, and that `soft_off` reverses them.
- Registration: import `adi_lg_plugins` and assert `target_factory` resolves the new
  driver/resource/strategy names (catches missing entry points / imports).

## 8. Packaging & docs

- Add to `pyproject.toml`: 3 `labgrid.drivers`, 1 `labgrid.resources`, 1 `labgrid.strategies`
  entry points; import the new modules where the package registers the others so the
  `@target_factory.reg_*` decorators run.
- Run `nox -s format` then `nox -s lint` before committing.
- Add a Sphinx page documenting the three drivers + `BootTickFPGASSH`, an example env YAML, and
  the state sequence.

## 9. Risks

- **Protocol binding correctness** — `bindings` must name `CommandProtocol` and
  `FileTransferProtocol` so an SSH-based shell satisfies both; verify the inherited
  `BootFPGASoCSSH` shell binding is compatible (same SSH driver instance can serve both).
- **Overlap with `KuiperRelease`/`BootFPGASoC`** — the Tick deploy is runtime-only and must not
  re-trigger SD writes; relying on inherited `update_image=False` keeps the SD untouched.
- **iiod coupling** — restarting `iiod` is Kuiper-specific; gating it behind `restart_iiod`
  keeps the driver usable on images without it.
