# Standalone scripts: driving hardware directly

For automation that runs *outside* GitHub Actions — a lab script, a notebook, a nightly cron, a
non-GitHub CI runner — that needs to acquire a board, boot/flash it, do something, and release.

Prefer the **highest-level tool that does the job.** Each level down is more control and more
ways to leak a reservation or boot incorrectly.

## Level 1 — `request()` context manager (default)

`from adi_lg_plugins.request import request`. Reserve + acquire + boot + release, all handled.
This is the right tool for "give me a booted board" and "flash this firmware and check serial."
**Re-read `adi_lg_plugins/request/core.py` for the current signature and return fields** — the
fields below are illustrative, not a contract.

```python
from adi_lg_plugins.request import request

with request(part="adrv9002", carrier="zcu102", mode="uri",
             coord="lab-host:20408") as board:
    # board.uri      -> network IIO URI (uri mode)
    # board.place    -> labgrid place name (str)
    # board.target   -> labgrid Target (flash mode, or uri after boot)
    # board.console  -> serial console driver (flash mode)
    # board.env_path -> rendered env.yaml path (reserve mode)
    import adi
    sdr = adi.adrv9002(uri=board.uri)
    ...
# on exit: optional soft power-off, release place, clean up temp env
```

What `request()` does under the hood (so you know what you're inheriting):
1. Resolve coordinator (`$LG_COORDINATOR` or the `coord=` arg).
2. Query the coordinator REST bridge to match `(part, carrier, mode)` to a board.
3. Reserve + acquire over gRPC, **blocking until the place is free** (default ~30 min wait).
4. Render a temp labgrid `env.yaml` from the live place metadata.
5. For uri/flash: boot to shell via the place's strategy and verify (URI reachable / serial banner).
6. On exit: release the place and clean up.

The three `mode=` values:
- **`uri`** (default) — boot to Linux, return a network URI. For pyadi-iio-style tests.
- **`flash`** — JTAG-load no-OS firmware, return the serial console for banner assertions.
- **`reserve`** — acquire + render env but **do not boot**; you drive the board yourself.

Because acquire/release is automatic, `request()` is also the safest choice for cron jobs — a
crash inside the `with` still releases the place.

## Level 2 — the `adi-lg` CLI

When a shell one-liner is cleaner than Python. Entry point `adi-lg` (Click); each subcommand
takes `--config <labgrid.yaml>`, `--target` (default `main`), and `--state` (default `shell`).
**Run `adi-lg <cmd> --help` for the authoritative current options** — these drift.

| Subcommand                  | Purpose                                                                 |
|-----------------------------|-------------------------------------------------------------------------|
| `boot-fabric`               | Logic-only Xilinx FPGA (Virtex/Artix/Kintex): power, JTAG bitstream, kernel to MicroBlaze |
| `boot-soc`                  | Zynq/ZynqMP: flash BOOT.BIN/kernel/DTB to SD via SD-mux, boot           |
| `boot-soc-ssh`              | Upload boot files to an already-running system over SSH, reboot         |
| `boot-selmap`              | Dual-FPGA SelMap: boot primary Zynq SoC, trigger secondary Virtex       |
| `provision-software`        | Install packages / clone repos / build / run tests on a booted target   |
| `download-cloudsmith`       | Fetch a boot artifact (e.g. BOOT.BIN) from the Cloudsmith registry       |
| `build-recovery-initramfs`  | Build a Zynq-7000 recovery initramfs (cpio.gz or uImage)                |
| `request`                   | Programmatic-style board request from the CLI                            |
| `config-gen`                | Generate/scaffold a labgrid config                                       |

Sister tools: `kuiperdl` (list/download Kuiper boot files for a release), `cloudsmithdl`,
`adi-lg-mcp` (FastMCP server exposing these as MCP tools).

Example:

```bash
adi-lg --debug boot-soc --config env.yaml --target main \
  --release 2023_R2_P1 --update-image
```

## Level 3 — raw labgrid (custom fallback)

Only when the wrappers don't expose what you need, or you're inside a pytest hardware test with
an `--lg-config`. This is the most control and the easiest place to leak a reservation, so reach
for it last and handle acquire/release explicitly.

```python
from labgrid import Environment

env = Environment("env.yaml")          # must contain `imports: [adi_lg_plugins]`
target = env.get_target("main")

# Drive a driver directly:
drv = target.get_driver("ADIShellDriver")
target.activate(drv)
print(drv.run("uname -a"))

# …or run a boot strategy state machine:
strat = target.get_driver("BootFPGASoC")
strat.transition("shell")              # common terminal states: "shell", "powered_off"
```

Acquiring a *remote* place (coordinator-managed) from a script means reserving + acquiring via
`labgrid-client` (or the reservation helpers in `adi_lg_plugins/request/`) and pointing the env
at a `RemotePlace`. If you find yourself reimplementing reserve/acquire/release, stop — that's
exactly what `request()` already does correctly; prefer Level 1.

## Strategy catalog

In `adi_lg_plugins/strategies/`. Each is a labgrid state machine with `transition(state)`. Pick
the strategy that matches the board class; the place's `boot-strategy` tag names it.

| Strategy                    | Boots                                                                |
|-----------------------------|---------------------------------------------------------------------|
| `BootFabric`                | Logic-only Xilinx FPGA, kernel on MicroBlaze via JTAG               |
| `BootFPGASoC`               | Zynq/ZynqMP via SD-mux (flash boot files to SD, boot)              |
| `BootFPGASoCSSH`            | Already-running system: push boot files over SSH, reboot           |
| `BootFPGASoCTFTP`           | U-Boot loads kernel/DTB over TFTP (stable MAC via `ethaddr` tag)   |
| `BootSelMap`                | Primary Zynq SoC, then secondary Virtex via SelMap                 |
| `BootRPI`                   | Raspberry Pi over SSH (optional power/serial/SD-mux)               |
| `BootVPK180`                | Versal VPK180 platform                                             |
| `BootZynq7000JTAGRecovery`  | JTAG-bootstrap U-Boot+DDR, TFTP recovery Linux, dd a fresh SD image |
| `BootNoOSJTAG`              | Flash + run no-OS bare-metal `.elf` via JTAG; validate serial banner|
| `ReflashVPK180SD`           | Reflash a Versal VPK180 SD card                                     |
| `SoftwareProvisioningStrategy` | Install/clone/build/test on an already-booted target            |

## Running pytest against hardware

Hardware tests in this repo (and the pattern to copy) use these `conftest.py` hooks:

- `--lg-config <path>` — the real labgrid YAML (required for hardware tests).
- `--run-hardware` — enable tests marked `@pytest.mark.hardware` (skipped by default).
- `--run-destructive` — enable `@pytest.mark.destructive` (implies `--run-hardware`; these
  overwrite DUT storage).
- Fixture `lg_config` returns the `--lg-config` path (or `None`).

```bash
pytest tests/test_soc_strat_tftp.py --run-hardware --lg-config /path/to/env.yaml
pytest tests/ --run-destructive --lg-config /path/to/env.yaml
```

A typical hardware test acquires the target from the config and drives a driver:

```python
@pytest.fixture
def target(lg_config):
    if not lg_config:
        pytest.skip("No labgrid config provided via --lg-config")
    return Environment(lg_config).get_target("main")

@pytest.mark.hardware
def test_uname(target):
    drv = target.get_driver("ADIShellDriver")
    target.activate(drv)
    assert "Linux" in drv.run("uname -a")[0][0]
```

Note: several hardware test modules are in `conftest.py`'s `collect_ignore_glob` and only
collected under `--run-hardware` (they crash without a real config). When you add a new
hardware test module, follow that pattern so it doesn't break the no-hardware test run.
