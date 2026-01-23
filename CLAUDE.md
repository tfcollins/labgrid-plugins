# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**adi-labgrid-plugins** is a collection of Analog Devices, Inc. (ADI) specific plugins for the labgrid hardware testing framework. The package provides drivers, resources, and boot strategies for controlling and testing embedded devices with various power management systems, file transfer mechanisms, and FPGA boot workflows.

**Key Details:**
- Language: Python 3.10+
- Package name: `adi-labgrid-plugins`
- Plugin system: Entry-point based discovery for labgrid framework integration
- License: LGPL-2.1-or-later

## Common Development Commands

### Setup and Installation

```bash
# Install in development mode with all dependencies
pip install -e ".[dev,docs]"

# Install only development dependencies
pip install -e ".[dev]"

# Install documentation dependencies
pip install -e ".[docs]"
```

### Linting and Code Quality

```bash
# Run ruff linter and formatter on all Python files
ruff check . --fix

# Format code
ruff format .

# Check code without fixing
ruff check .
```

**Ruff Configuration:**
- Line length: 100 characters
- Target version: Python 3.10+
- Enabled rules: E (pycodestyle errors), W (warnings), F (pyflakes), I (isort), UP (pyupgrade), B (flake8-bugbear)
- Ignored: E501 (line too long - handled by formatter)
- Quote style: Double quotes
- Indent style: Spaces

### Testing

```bash
# Run all tests
pytest

# Run a specific test file
pytest tests/test_soc_strat.py

# Run a specific test function
pytest tests/test_soc_strat.py::test_function_name

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=adi_lg_plugins tests/
```

**Test Location:** `/home/tcollins/dev/labgrid-plugins-cleanup/tests/`

### Documentation

```bash
# Build HTML documentation
cd docs && make html

# Build and watch for changes (requires sphinx-autobuild)
cd docs && make livehtml

# Clean build artifacts
cd docs && make clean
```

Documentation source is in `docs/source/` using reStructuredText format with Sphinx.

## Architecture and Code Organization

### High-Level Structure

The codebase consists of four main plugin component types that integrate with the labgrid hardware testing framework:

```
adi_lg_plugins/
├── drivers/           # Hardware control implementations (6 drivers)
├── resources/         # Configuration definitions (4 resources)
├── strategies/        # Boot workflow orchestration (3 strategies)
└── tools/             # Standalone CLI utilities (2 commands)
```

### Plugin Types and Integration

All plugins register via entry points in `pyproject.toml` and are automatically discovered by labgrid:

#### 1. **Drivers** — Hardware control implementations

Drivers extend `labgrid.driver.common.Driver` and implement hardware protocols. Each driver has an initialization phase in `__attrs_post_init__()` and interaction methods.

**Six drivers are provided:**
- **VesyncPowerDriver** — Network power control via VeSync smart outlets (uses `pyvesync`)
- **CyberPowerDriver** — SNMP-based power control for CyberPower PDUs (uses `pysnmp` v6.x/v7.x compatible)
- **ADIShellDriver** — SSH/serial shell access with command execution, file transfer (XMODEM), and login authentication
- **KuiperDLDriver** — Downloads and extracts Kuiper Linux releases with caching; provides boot files via `pytsk3` image extraction
- **MassStorageDriver** — Mounts USB mass storage partitions and manages file updates (uses `pmount`/`pumount`)
- **ImageExtractor** (helper) — Utility for extracting files from disk images without mounting

**Common patterns:**
- Drivers implement labgrid protocols: `PowerProtocol`, `CommandProtocol`, `ConsoleProtocol`, `FileTransferProtocol`
- All use `self.logger` for logging (inherited from labgrid)
- `@attr.s(eq=False)` decorator for attribute validation
- `bindings` dict declares dependencies on resources/other drivers

#### 2. **Resources** — Configuration containers

Resources extend `labgrid.resource.common.Resource` and define configurable properties. They bind to specific drivers and are declared in target configuration.

**Four resources provided:**
- **VesyncOutlet** — Properties: `outlet_names`, `username`, `password`, `delay`
- **CyberPowerOutlet** — Properties: `address` (PDU IP), `outlet` (outlet number), `delay`
- **KuiperRelease** — Properties: `release_version`, `cache_path`, `kernel_path`, `BOOTBIN_path`, `device_tree_path`
- **MassStorageDevice** — Properties: `path`, `file_updates` (dict), `use_with_sdmux` (bool)

Resources have minimal logic; primarily attribute validation and binding.

#### 3. **Strategies** — Boot workflow orchestrators

Strategies extend `labgrid.strategy.Strategy` and use state machines to coordinate complex multi-step boot workflows. They bind multiple drivers/resources together.

**Three strategies provided:**
- **BootFPGASoC** — 9-state machine for SD card-based boot: power off → SD to host → update files → SD to DUT → boot → shell. Supports full image flashing via USB storage driver.
- **BootSelMap** — 11-state machine for dual FPGA boot: Primary Zynq FPGA boots Linux, secondary Virtex FPGA boots via SelMap. Includes JESD204 monitoring and IIOD service management.
- **BootFPGASoCSSH** — 9-state machine for SSH-based boot (alternative to SD card): power → boot → SSH file transfer → reboot → shell.

**State machine pattern:**
- `__attrs_post_init__()` for pre-initialization
- `transition(status, *, step)` method implements the state machine
- Uses `@step()` decorator for labgrid test step reporting
- Bindings declare required drivers: `power` (PowerProtocol), `shell` (ADIShellDriver), `sdmux` (USBSDMuxDriver), etc.

#### 4. **Tools** — Standalone CLI utilities

Command-line tools registered in `[project.scripts]` entry point.

**Two tools provided:**
- **kuiperdl** (`tools/kuiperdl.py:main()`) — Lists Kuiper release boot files with args: `--release-version`, `--cache-path`
- **vesync** (`tools/vesync.py`) — VeSync outlet discovery utility

### Plugin Discovery and Activation Flow

1. Labgrid reads entry points from `pyproject.toml` sections:
   - `[project.entry-points."labgrid.drivers"]`
   - `[project.entry-points."labgrid.resources"]`
   - `[project.entry-points."labgrid.strategies"]`
   - `[project.scripts]`

2. Target configuration references resources and drivers by name

3. When `target.activate(driver)` is called:
   - Labgrid instantiates the driver/strategy class with `@attr.s` validation
   - Runs `__attrs_post_init__()` for initialization
   - Calls `on_activate()` if defined
   - Resolves binding dependencies (other drivers/resources)

4. Strategy state machines coordinate workflows via `transition()` calls

### Key Dependencies

**Core Framework:**
- **labgrid** (git fork: `https://github.com/tfcollins/labgrid.git@tfcollins/plugin-support`) — Hardware testing framework with plugin system, protocols, step decorators, target management

**Hardware/Protocol Libraries:**
- **pyvesync** (>=1.1.5, <3.0.0) — VeSync smart outlet API
- **pysnmp** — SNMP protocol (version-flexible for compatibility with v6.x and v7.x)
- **pytsk3** — Forensic toolkit for extracting files from disk images without mounting

**Utilities:**
- **tqdm** — Progress bars for downloads
- **pylibiio** — IIO device interface for Analog Devices hardware
- **xmodem** — XMODEM file transfer protocol (binary-safe)
- **attrs** — Class attribute validation

**Documentation:**
- **sphinx**, **furo**, **sphinx-copybutton**, **sphinx-design**

### Testing Considerations

Tests use the labgrid target fixture and test drivers/strategies with mock or real configurations:

- **test_kuiper_dl.py** — Tests KuiperDLDriver download, caching, and file extraction
- **test_soc_strat.py** — Tests BootFPGASoC strategy state transitions
- **test_soc_strat_custom.py** — Custom SOC strategy tests

Tests expect a labgrid target configuration with appropriate resources bound to drivers.

## Important Patterns and Conventions

### Attribute Definitions

All drivers, resources, and strategies use `@attr.s(eq=False)` from the `attrs` library for class definitions with automatic validation:

```python
@attr.s(eq=False)
class MyDriver(Driver):
    name = attr.ib()                    # Required attribute
    timeout = attr.ib(default=30)       # With default
    options = attr.ib(factory=dict)     # Mutable default
```

### Binding Dependencies

Components declare dependencies via `bindings` dict:

```python
bindings = {"power": PowerProtocol, "shell": ADIShellDriver}
```

Labgrid resolves these at activation time.

### Step Decorators and Logging

Use `@step()` for test step reporting and `self.logger` for logging:

```python
from labgrid import step

@step()
def my_operation(self):
    self.logger.info("Starting operation")
    # ...
```

### Protocol Implementation

Drivers implement labgrid protocols (interfaces) for interoperability:

```python
from labgrid.protocol import PowerProtocol

class MyPowerDriver(Driver, PowerProtocol):
    def on(self): ...
    def off(self): ...
    def reset(self): ...
```

## Working with Resources and Drivers

### Adding a New Driver

1. Create a new file in `drivers/` extending `Driver`
2. Implement required protocols (e.g., `PowerProtocol`)
3. Add entry point to `pyproject.toml` under `[project.entry-points."labgrid.drivers"]`
4. Use `@attr.s(eq=False)` for configuration and `bindings` for dependencies
5. Implement `__attrs_post_init__()` for initialization
6. Use `@step()` decorator for significant operations
7. Add tests in `tests/`

### Adding a New Resource

1. Create a new file in `resources/` extending `Resource`
2. Define properties using `attr.ib()`
3. Add entry point to `pyproject.toml` under `[project.entry-points."labgrid.resources"]`
4. Ensure `name` attribute matches driver binding string

### Adding a New Strategy

1. Create a new file in `strategies/` extending `Strategy`
2. Define state machine via `transition(status, *, step)` method
3. Declare driver/resource bindings via `bindings` dict
4. Add entry point to `pyproject.toml` under `[project.entry-points."labgrid.strategies"]`
5. Use `@step()` for state transitions
6. Add tests in `tests/`

## Known Constraints and Considerations

- **ADIShellDriver** requires XMODEM protocol support on target device for file transfer
- **MassStorageDriver** requires `pmount`/`pumount` utilities installed
- **CyberPowerDriver** supports both pysnmp v6.x (async) and v7.x (sync) APIs with version detection
- **KuiperDLDriver** uses `pytsk3` which may require system dependencies for filesyste support
- Strategies are stateful and assume state persistence across `transition()` calls
- All drivers use labgrid's `Timeout` class for timeout management

## Documentation

Sphinx documentation is in `docs/source/` with sections:
- `getting-started/` — Installation, quickstart, configuration
- `api/` — Driver, resource, and strategy API references
- `examples/` — Usage examples

Built HTML docs go to `docs/build/html/` via `make html`.
