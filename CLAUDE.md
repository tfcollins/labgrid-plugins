# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**adi-labgrid-plugins** is a collection of Analog Devices, Inc. (ADI) specific plugins for the labgrid hardware testing framework. The package provides drivers, resources, and boot strategies for controlling and testing embedded devices with various power management systems, file transfer mechanisms, and FPGA boot workflows.

- Language: Python 3.10+
- Package name: `adi-labgrid-plugins`
- Plugin system: Entry-point based discovery for labgrid framework integration
- License: LGPL-2.1-or-later
- Core dependency: labgrid fork at `https://github.com/tfcollins/labgrid.git@tfcollins/plugin-support`

## Common Development Commands

```bash
# Install in development mode
pip install -e ".[dev,docs]"

# Nox automation (uses uv backend)
nox                          # Run all default sessions: lint, tests, docs
nox -s lint                  # Ruff check + format check
nox -s format                # Auto-fix: ruff format + ruff check --fix
nox -s tests                 # Run pytest
nox -s tests -- -k test_name # Run specific test
nox -s docs                  # Build Sphinx docs

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

## Testing

Tests are in `tests/`. Two categories:

- **Unit/integration tests** — run without hardware (e.g., `test_cli.py`, `test_mcp.py`, `test_fabric_strat.py`). CI only runs `test_cli.py` and `test_mcp.py`.
- **Hardware tests** — require `--run-hardware` flag and a labgrid config via `--lg-config`. Marked with `@pytest.mark.hardware`.

Some test modules (`test_soc_strat.py`, `test_soc_strat_custom.py`, `test_soc_strat_tftp.py`, `test_rpi_hw.py`) are excluded from collection by default in `conftest.py` because they crash without `--lg-env`.

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
- **KuiperDLDriver** depends on `pytsk3` which needs system-level filesystem libraries
