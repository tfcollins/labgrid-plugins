# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**adi-labgrid-plugins** is a collection of Analog Devices, Inc. (ADI) specific plugins for the labgrid hardware testing framework. The package provides drivers, resources, and boot strategies for controlling and testing embedded devices with various power management systems, file transfer mechanisms, and FPGA boot workflows.

- Language: Python 3.10+
- Package name: `adi-labgrid-plugins`
- Plugin system: Entry-point based discovery for labgrid framework integration
- License: `pyproject.toml` declares LGPL-2.1-or-later but `LICENSE`/`README.md` are Apache 2.0 — treat as unresolved; ask before adding license headers.
- Core dependency: upstream `labgrid>=25.0` (PyPI). Plugins register via package self-import (`adi_lg_plugins/__init__.py` imports all driver/resource/strategy submodules so their `@reg_driver`/`@reg_resource` decorators run) **and** labgrid's native `imports: [adi_lg_plugins]` config key. Upstream labgrid has no entry-point plugin auto-discovery, so any labgrid env YAML that names ADI drivers/resources/strategies must include `imports: [adi_lg_plugins]` (or the consuming process must `import adi_lg_plugins`). The fork-only `never_retry` strategy decorator is shimmed in `adi_lg_plugins/strategies/_compat.py`.

## Common Development Commands

```bash
# Install in development mode
pip install -e ".[dev,docs]"
pip install -e ".[kuiper]"   # Adds pytsk3 (needs C toolchain) for KuiperDLDriver

# Nox automation (uses uv backend)
nox                          # Default sessions only: lint, tests, docs (NOT typecheck)
nox -s lint                  # Ruff check + format check
nox -s format                # Auto-fix: ruff format + ruff check --fix
nox -s tests                 # Run pytest
nox -s tests -- -k test_name # Run specific test
nox -s docs                  # Build Sphinx docs
nox -s typecheck             # Opt-in: ty static check; baseline not yet clean

# Direct commands
pytest tests/test_cli.py                    # Run a specific test file
pytest tests/test_soc_strat.py::test_name   # Run a specific test function
ruff check . --fix && ruff format .         # Lint + format in one shot

# CLI tools
adi-lg --debug boot-fabric --config config.yaml --target main
adi-lg-mcp                   # Start FastMCP server
kuiperdl --release-version 2023_R2_P1
```

**Ruff rules:** line length 100, double quotes, spaces, rules E/W/F/I/UP/B enabled, E501 ignored.

**ty rules (`pyproject.toml`):** `unresolved-attribute` and `too-many-positional-arguments` are intentionally ignored — labgrid injects `bindings` attributes at bind time (invisible to ty) and `@step()` mangles signatures. Don't "fix" these by adding annotations to driver bindings without understanding the framework's injection model.

## Testing

Tests are in `tests/`. Two categories:

- **Unit/integration tests** — run without hardware (e.g., `test_cli.py`, `test_mcp.py`, `test_fabric_strat.py`).
- **Hardware tests** — require `--run-hardware` flag and a labgrid config via `--lg-config`. Marked with `@pytest.mark.hardware`.

Some test modules (`test_soc_strat.py`, `test_soc_strat_custom.py`, `test_soc_strat_tftp.py`, `test_rpi_hw.py`) are excluded from collection by default in `conftest.py` because they crash without `--lg-env`.

**CI** (`.github/workflows/tests.yml`): Python 3.10/3.11/3.12 matrix. Runs `nox -s lint` (blocking) → `nox -s typecheck` (`continue-on-error: true`, informational) → `nox -s tests -- tests/test_cli.py tests/test_mcp.py`. New unit tests must opt-in here to be exercised by CI.

## Architecture

The codebase has four plugin component types, all registered via entry points in `pyproject.toml`:

```
adi_lg_plugins/
├── drivers/       # Hardware control (power, shell, JTAG, TFTP, downloads, mass storage)
├── resources/     # Configuration containers (outlet configs, device paths, release info)
├── strategies/    # Boot workflow state machines (SoC, FPGA fabric, SelMap, RPi, SSH, TFTP)
└── tools/         # CLI (click-based), MCP server (FastMCP), utilities
```

### Plugin Discovery Flow

1. Labgrid reads entry points from `pyproject.toml` (`labgrid.drivers`, `labgrid.resources`, `labgrid.strategies`)
2. Target YAML config references resources/drivers by name
3. `target.activate(driver)` instantiates with `@attr.s` validation, runs `__attrs_post_init__()`, resolves bindings
4. Strategies coordinate multi-driver workflows via state machine `transition()` calls

### Key Patterns

**All components** use `@attr.s(eq=False)` for attrs-based class definitions and `@target_factory.reg_driver`/`@target_factory.reg_resource` for labgrid registration.

**Drivers** extend `labgrid.driver.common.Driver` and implement labgrid protocols (`PowerProtocol`, `CommandProtocol`, `FileTransferProtocol`). They declare dependencies via a `bindings` dict:

```python
bindings = {"power": PowerProtocol, "shell": ADIShellDriver}
```

**Strategies** extend `labgrid.strategy.Strategy` and implement state machines via `transition(status, *, step)`. They use `@step()` for test step reporting and `self.logger` for logging. State persists across `transition()` calls.

**Resources** extend `labgrid.resource.common.Resource` with `attr.ib()` properties. Minimal logic.

**MCP server** (`tools/mcp.py`) uses FastMCP with session management, threading locks, and async boot operations. Exposes labgrid functionality as MCP tools.

**CLI** (`tools/cli.py`) uses Click with subcommands for boot workflows (`boot-fabric`, `boot-soc`, etc.).

### Adding New Components

For any new driver, resource, or strategy:
1. Create the class in the appropriate subdirectory following existing patterns
2. Register the entry point in `pyproject.toml` under the correct section
3. Add tests in `tests/`

### Known Constraints

- **ADIShellDriver** requires XMODEM support on target device for file transfer
- **MassStorageDriver** requires `pmount`/`pumount` installed on host
- **CyberPowerDriver** handles both pysnmp v6.x (async) and v7.x (sync) with version detection
- **KuiperDLDriver** depends on `pytsk3` which needs system-level filesystem libraries (install via the `kuiper` extra)

## Sibling Projects in This Repo

The repo is not just the `adi_lg_plugins` package — two sibling subprojects live alongside it and have their own toolchains:

- **`coordinator/`** — Docker-compose stack: a labgrid coordinator, a FastAPI REST/WebSocket bridge in `coordinator/api/` (its own `pyproject.toml`, ruff config, and ~30 pytest files under `coordinator/api/tests/`), and a React/Vite/TypeScript dashboard in `coordinator/web/`. Brought up with `docker compose up -d` from `coordinator/`. Ports: coordinator `:20408`, API `:8000`, web `:3000`. The API package depends on the same upstream `labgrid>=25.0`. Run its tests from `coordinator/api/` — they are *not* picked up by the top-level `nox -s tests`.
- **`exporter_configs/`** — YAML templates (`templates/*.yaml`) for deploying labgrid exporters on RPi / VCU118 / ZCU102 hosts, plus `validate.py` and JSON schemas under `schemas/`. Use these when wiring up a new exporter host.

When a task touches a coordinator concern (places, recordings, OIDC auth, env-gen, gRPC bridge, web UI), work inside `coordinator/` — its conventions and dependency set are independent of the top-level package.

## Sibling Repo CI (reusable hw-matrix workflow)

This repo also hosts the **reusable GitHub Actions workflow** that sibling repos (`pyadi-dt`, `pyadi-iio`, `vrt49`) consume to run HW tests. Three things live here on top of the per-repo CI:

- `.github/workflows/hw-matrix.yml` — `workflow_call`-triggered. Preflight probes the coordinator for available places, then fans out a per-place matrix (`hw-direct` and/or `hw-coord` legs) with JUnit aggregation and optional Prism upload.
- `.github/actions/{setup-uv-venv,acquire-place}/action.yml` — composite actions used by `hw-matrix.yml` and reusable standalone.
- `.github/scripts/register-hw-runners.sh` — parameterized runner-registration helper with `--scopes` for dual/triple registration (one lab host, multiple GH scopes — see `docs/source/user-guide/hardware-ci.rst`).

Consumer repos pin via `uses: tfcollins/labgrid-plugins/.github/workflows/hw-matrix.yml@v<tag>`. This repo must stay **public** for cross-org callers to skip the allowlist gate.

### labgrid dependency

Both `pyproject.toml` and `coordinator/api/pyproject.toml` depend on upstream `labgrid>=25.0` (PyPI). There is **no** fork pin and no `lint-labgrid-pin` CI job anymore.

Plugin registration no longer relies on entry-point auto-discovery (a fork-only feature). Instead:
- `import adi_lg_plugins` registers everything (the package `__init__` imports all driver/resource/strategy submodules; missing optional deps log a warning and skip rather than failing the import).
- Every committed labgrid env YAML and the `adi_lg_plugins/hw_ci/templates/*.yaml` render templates carry `imports: [adi_lg_plugins]`; the coordinator env-gen (`coordinator/api/app/env_gen.py`) emits it too. **Downstream configs must include this key** to resolve ADI drivers/resources/strategies by name.
