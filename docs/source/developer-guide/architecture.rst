Architecture
============

The adi-labgrid-plugins project follows the **labgrid plugin architecture** with three main component types: Resources, Drivers, and Strategies. This document explains the design, component relationships, and extensibility patterns.

Component Overview
------------------

**Resources**: Configuration descriptors that define hardware and connectivity details. Resources are passive - they don't perform actions but describe the setup needed for drivers.

**Drivers**: Low-level abstractions that control hardware. Drivers implement one or more protocols (e.g., PowerProtocol, ConsoleProtocol, FileTransferProtocol) and interact directly with hardware.

**Strategies**: High-level state machines that coordinate multiple drivers to accomplish complex workflows. Strategies manage the lifecycle of drivers and handle multi-step procedures.

**Relationship Diagram**:

.. code-block:: text

    Target Configuration (YAML)
    │
    ├─ Resources
    │  └─ VesyncOutlet (credentials, outlet names)
    │  └─ SerialPort (port, baudrate)
    │  └─ MassStorageDevice (device path)
    │
    ├─ Drivers (bind to resources, implement protocols)
    │  └─ VesyncPowerDriver (PowerProtocol)
    │  └─ ADIShellDriver (CommandProtocol, ConsoleProtocol)
    │  └─ MassStorageDriver (FileTransferProtocol)
    │
    └─ Strategies (coordinate drivers)
       └─ BootFPGASoC
          └─ Manages: Power, SDMux, MassStorage, Shell, Kuiper

Resources
---------

Resources describe hardware configuration without performing actions. They are validated and instantiated from the target configuration YAML.

**Key Characteristics**:

- Declared with ``@target_factory.reg_resource`` decorator
- Defined using attrs library for automatic validation
- Validated on instantiation (type checking, required fields)
- Passed to drivers that depend on them

**Example - VesyncOutlet Resource**:

.. code-block:: python

    import attr
    from labgrid.factory import target_factory
    from labgrid.resource.common import Resource

    @target_factory.reg_resource
    @attr.s(eq=False)
    class VesyncOutlet(Resource):
        """Describes a VeSync smart outlet connection."""

        # Required attributes with validation
        outlet_names = attr.ib(validator=attr.validators.instance_of(str))
        username = attr.ib(validator=attr.validators.instance_of(str))
        password = attr.ib(validator=attr.validators.instance_of(str))

        # Optional with defaults
        delay = attr.ib(default=5.0, validator=attr.validators.instance_of(float))

**YAML Configuration**:

.. code-block:: yaml

    targets:
      mydevice:
        resources:
          VesyncOutlet:
            outlet_names: 'Device Power'
            username: 'user@example.com'
            password: 'password'
            delay: 5.0

**Validation**:

Resources are automatically validated when instantiated. Invalid types raise ``TypeError``:

.. code-block:: python

    # This will raise TypeError during resource validation
    resources:
      VesyncOutlet:
        outlet_names: 12345  # Must be string, not int
        username: 'user@example.com'
        password: 'password'

Drivers
-------

Drivers are the bridge between resources and actual hardware. Each driver binds to required resources and implements one or more protocol interfaces.

**Key Characteristics**:

- Registered with ``@target_factory.reg_driver`` decorator
- Inherit from ``labgrid.driver.common.Driver``
- Define ``bindings`` dict specifying required/optional resources and drivers
- Implement protocol interfaces (PowerProtocol, CommandProtocol, etc.)
- Activated/deactivated by strategies or test code

**Binding Types**:

.. code-block:: python

    # Required binding
    bindings = {
        "power": "PowerProtocol",  # Require PowerProtocol implementation
    }

    # Optional binding (can be None)
    bindings = {
        "image_writer": {"USBStorageDriver", None},
    }

    # Multiple options (first available is used)
    bindings = {
        "power": {"VesyncPowerDriver", "CyberPowerDriver"},
    }

**Example - VesyncPowerDriver**:

.. code-block:: python

    import attr
    from labgrid.driver.common import Driver
    from labgrid.driver.powerdriver import PowerResetMixin
    from labgrid.factory import target_factory
    from labgrid.protocol import PowerProtocol
    from labgrid.step import step
    from pyvesync import VeSync

    @target_factory.reg_driver
    @attr.s(eq=False)
    class VesyncPowerDriver(Driver, PowerResetMixin, PowerProtocol):
        """Control power via VeSync smart outlet."""

        bindings = {"vesync_outlet": {"VesyncOutlet"}}

        def __attrs_post_init__(self):
            super().__attrs_post_init__()
            # Initialize from resource
            self.pdu_dev = VeSync(
                self.vesync_outlet.username,
                self.vesync_outlet.password
            )
            self.pdu_dev.login()
            self.pdu_dev.get_devices()

        @Driver.check_active
        @step()
        def on(self):
            """Turn on all configured outlets."""
            for outlet in self.outlets:
                outlet.turn_on()
            self.logger.info("Power ON")

        @Driver.check_active
        @step()
        def off(self):
            """Turn off all configured outlets."""
            for outlet in self.outlets:
                outlet.turn_off()
            self.logger.info("Power OFF")

**Protocols**:

Drivers implement standard labgrid protocols to provide interchangeable functionality:

- **PowerProtocol**: Control power (on, off, cycle)
- **CommandProtocol**: Execute commands and capture output
- **ConsoleProtocol**: Raw console access (pexpect)
- **FileTransferProtocol**: Transfer files to/from device

**Driver Activation Lifecycle**:

.. code-block:: text

    1. on_activate() - Called when driver is activated
       └─ Initialize hardware connection
       └─ Perform login/authentication
       └─ Setup resources

    2. [Driver is active and usable]
       └─ Methods can be called with @Driver.check_active

    3. on_deactivate() - Called when driver is deactivated
       └─ Clean up resources
       └─ Close connections
       └─ Logout if needed

**Example - Activation Lifecycle**:

.. code-block:: python

    @target_factory.reg_driver
    @attr.s(eq=False)
    class ADIShellDriver(Driver, CommandProtocol, FileTransferProtocol):
        """Execute shell commands on device."""

        def __attrs_post_init__(self):
            super().__attrs_post_init__()
            self._status = 0

        def on_activate(self):
            """Called when driver is activated."""
            if not self.bypass_login:
                self._await_login()  # Wait for login prompt
                self._inject_run()   # Inject SSH keys if configured

        def on_deactivate(self):
            """Called when driver is deactivated."""
            # Cleanup console
            if self.console:
                try:
                    self.console.close()
                except:
                    pass

        @Driver.check_active
        @step()
        def run_command(self, command):
            """Execute command (only works when active)."""
            # Command execution logic
            pass

Strategies
----------

Strategies are state machines that coordinate multiple drivers to accomplish complex workflows. They manage driver activation/deactivation and handle multi-step procedures.

**Key Characteristics**:

- Inherit from ``labgrid.strategy.Strategy``
- Define state machine as enum
- Declare driver bindings
- Implement ``transition()`` method
- Automatically manage driver activation

**State Machine Pattern**:

.. code-block:: python

    import enum
    from labgrid.strategy import Strategy, StrategyError, never_retry

    class Status(enum.Enum):
        """Boot states."""
        unknown = 0
        powered_off = 1
        booting = 2
        shell = 3

    @target_factory.reg_driver
    @attr.s(eq=False)
    class BootStrategy(Strategy):
        """Boot device to shell."""

        bindings = {
            "power": "PowerProtocol",
            "shell": "ADIShellDriver",
        }

        status = attr.ib(default=Status.unknown)

        @never_retry
        @step()
        def transition(self, status, *, step):
            """Transition to target state."""
            if status == Status.powered_off:
                self.target.activate(self.power)
                self.power.off()

            elif status == Status.booting:
                self.transition(Status.powered_off)
                self.power.on()

            elif status == Status.shell:
                self.transition(Status.booting)
                self.target.activate(self.shell)
                # Wait for shell prompt

            else:
                raise StrategyError(f"Invalid transition to {status}")

            self.status = status

**Strategy Decorator**:

- ``@never_retry``: Don't retry on failure
- ``@step()``: Log transition as test step
- Together they integrate with labgrid's test reporting

**Example - BootFPGASoC**:

The BootFPGASoC strategy demonstrates the full pattern:

.. code-block:: python

    class Status(enum.Enum):
        unknown = 0
        powered_off = 1
        sd_mux_to_host = 2
        update_boot_files = 3
        sd_mux_to_dut = 4
        booting = 5
        booted = 6
        shell = 7

    @target_factory.reg_driver
    @attr.s(eq=False)
    class BootFPGASoC(Strategy):
        bindings = {
            "power": "PowerProtocol",
            "shell": "ADIShellDriver",
            "sdmux": "USBSDMuxDriver",
            "mass_storage": "MassStorageDriver",
            "kuiper": "KuiperDLDriver",
        }

        status = attr.ib(default=Status.unknown)
        reached_linux_marker = attr.ib(default="analog")
        update_image = attr.ib(default=False)

        @never_retry
        @step()
        def transition(self, status, *, step):
            # ... transition logic ...
            self.status = status

Architectural Patterns
----------------------

**Binding Protocol**:

Drivers specify what they need, not specific driver types. This allows flexible substitution:

.. code-block:: python

    # Strategy can use any PowerProtocol implementation
    bindings = {
        "power": "PowerProtocol",  # Could be Vesync, CyberPower, etc.
    }

    # In config, specify implementation
    drivers:
      VesyncPowerDriver: {}      # Or CyberPowerDriver, etc.

**Activation Lifecycle**:

Strategies manage the activation order to ensure dependencies are met:

.. code-block:: python

    # In transition logic:
    self.target.activate(self.power)      # Power must be on
    self.target.activate(self.sdmux)      # SD mux after power
    self.target.activate(self.mass_storage) # Mass storage mounts
    # ... copy files ...
    self.target.deactivate(self.mass_storage)
    self.sdmux.set_mode("dut")            # Switch SD mux to device
    self.power.on()                         # Power on device
    self.target.activate(self.shell)       # Wait for shell

**Data Flow**:

.. code-block:: text

    Test Code
    │
    ├─ strategy.transition("shell")
    │  │
    │  └─ [State machine logic]
    │     │
    │     ├─ target.activate(power)
    │     │  └─ power.on()
    │     │
    │     ├─ target.activate(sdmux)
    │     │  └─ sdmux.set_mode()
    │     │
    │     ├─ target.activate(mass_storage)
    │     │  └─ mass_storage.copy_file()
    │     │
    │     └─ target.activate(shell)
    │        └─ shell.run_command()
    │
    └─ Test can now use shell directly

Plugin Discovery
----------------

Plugins are discovered and registered using Python entry points. This allows third-party drivers and strategies without modifying core code.

**Entry Points** (pyproject.toml):

.. code-block:: toml

    [project.entry-points."labgrid.drivers"]
    VesyncPowerDriver = "adi_lg_plugins.drivers.vesyncdriver:VesyncPowerDriver"
    ADIShellDriver = "adi_lg_plugins.drivers.shelldriver:ADIShellDriver"
    CyberPowerDriver = "adi_lg_plugins.drivers.cyberpowerdriver:CyberPowerDriver"

    [project.entry-points."labgrid.strategies"]
    BootFPGASoC = "adi_lg_plugins.strategies.bootfpgasoc:BootFPGASoC"
    BootFPGASoCSSH = "adi_lg_plugins.strategies.bootfpgasocssh:BootFPGASoCSSH"

    [project.entry-points."labgrid.resources"]
    VesyncOutlet = "adi_lg_plugins.resources.vesync:VesyncOutlet"
    CyberPowerOutlet = "adi_lg_plugins.resources.cyberpowerpdu:CyberPowerOutlet"

**Discovery Process**:

1. Labgrid loads all installed packages
2. Searches for entry points in labgrid.drivers, labgrid.strategies, labgrid.resources
3. Imports and registers components via @target_factory decorators
4. Makes components available in target configuration

Component Dependencies
----------------------

**Dependency Graph**:

.. code-block:: text

    BootFPGASoC Strategy
    ├─ Requires: PowerProtocol
    │  └─ Implemented by: VesyncPowerDriver
    │     └─ Depends on: VesyncOutlet resource
    │
    ├─ Requires: USBSDMuxDriver
    │  └─ Depends on: Nothing (hardware device)
    │
    ├─ Requires: MassStorageDriver
    │  └─ Depends on: MassStorageDevice resource
    │
    ├─ Requires: ADIShellDriver
    │  └─ Depends on: SerialPort resource
    │
    └─ Requires: KuiperDLDriver
       └─ Depends on: KuiperRelease resource

**Binding Resolution**:

When a target is instantiated, labgrid resolves bindings:

1. Reads target configuration YAML
2. Instantiates resources (validates, creates instances)
3. Instantiates drivers (validates, checks bindings)
4. Instantiates strategies (validates, checks driver bindings)
5. Raises error if any binding cannot be satisfied

**Example Configuration** with dependencies:

.. code-block:: yaml

    targets:
      complete_system:
        resources:
          VesyncOutlet:
            outlet_names: 'Device'
            username: 'user@example.com'
            password: 'pass'
            delay: 5.0

          SerialPort:
            port: '/dev/ttyUSB0'
            baudrate: 115200

          MassStorageDevice:
            path: '/dev/sda1'

        drivers:
          # Driver for power (satisfies PowerProtocol)
          VesyncPowerDriver: {}

          # Drivers for serial access
          ADIShellDriver:
            console: SerialPort
            prompt: 'root@.*:.*#'
            login_prompt: 'login:'
            username: 'root'
            password: 'analog'

          # Storage driver
          MassStorageDriver:
            device: MassStorageDevice

        strategies:
          # Strategy bindings are all satisfied:
          BootFPGASoC:
            reached_linux_marker: 'analog'
            update_image: false
          # - power: VesyncPowerDriver (✓ PowerProtocol)
          # - shell: ADIShellDriver (✓ ADIShellDriver)
          # - mass_storage: MassStorageDriver (✓ MassStorageDriver)

Error Handling
--------------

**Exception Hierarchy**:

.. code-block:: python

    labgrid.resource.common.ResourceError
    labgrid.driver.exception.DriverError
    labgrid.strategy.StrategyError
    labgrid.driver.exception.ExecutionError  # Command execution failed

**Resource Validation**:

.. code-block:: python

    # ValueError or TypeError on bad configuration
    try:
        env = Environment("target.yaml")
        target = env.get_target("device")
    except Exception as e:
        # Configuration is invalid
        print(f"Configuration error: {e}")

**Strategy Errors**:

.. code-block:: python

    from labgrid.strategy import StrategyError

    try:
        strategy.transition("shell")
    except StrategyError as e:
        # Transition failed
        print(f"Transition failed: {e}")

**Driver Errors**:

.. code-block:: python

    from labgrid.driver.exception import ExecutionError

    try:
        output = shell.run_command("command")
    except ExecutionError as e:
        # Command failed on device
        print(f"Command failed: {e}")

Extensibility
-------------

**Creating Custom Drivers**:

.. code-block:: python

    import attr
    from labgrid.driver.common import Driver
    from labgrid.factory import target_factory
    from labgrid.protocol import PowerProtocol
    from labgrid.step import step

    @target_factory.reg_driver
    @attr.s(eq=False)
    class CustomPowerDriver(Driver, PowerProtocol):
        """Custom power control implementation."""

        bindings = {
            "custom_outlet": "CustomOutlet",
        }

        @Driver.check_active
        @step()
        def on(self):
            self.logger.info("Power ON")
            # Implementation

        @Driver.check_active
        @step()
        def off(self):
            self.logger.info("Power OFF")
            # Implementation

        @Driver.check_active
        @step()
        def cycle(self, wait=5):
            self.off()
            time.sleep(wait)
            self.on()

**Creating Custom Resources**:

.. code-block:: python

    import attr
    from labgrid.factory import target_factory
    from labgrid.resource.common import Resource

    @target_factory.reg_resource
    @attr.s(eq=False)
    class CustomOutlet(Resource):
        """Custom outlet configuration."""

        hostname = attr.ib(validator=attr.validators.instance_of(str))
        port = attr.ib(default=8080, validator=attr.validators.instance_of(int))
        api_key = attr.ib(validator=attr.validators.instance_of(str))

**Creating Custom Strategies**:

.. code-block:: python

    import enum
    from labgrid.strategy import Strategy, StrategyError, never_retry

    class MyStatus(enum.Enum):
        unknown = 0
        state_a = 1
        state_b = 2

    @target_factory.reg_driver
    @attr.s(eq=False)
    class CustomStrategy(Strategy):
        """Custom workflow coordination."""

        bindings = {
            "driver_a": "DriverA",
            "driver_b": {"DriverB", None},
        }

        status = attr.ib(default=MyStatus.unknown)

        @never_retry
        @step()
        def transition(self, status, *, step):
            # Custom state machine logic
            pass

Directory Structure
-------------------

**Project Layout**:

.. code-block:: text

    adi_lg_plugins/
    ├── __init__.py
    │
    ├── resources/
    │  ├── __init__.py
    │  ├── vesync.py           # VesyncOutlet resource
    │  ├── cyberpowerpdu.py    # CyberPowerOutlet resource
    │  ├── massstorage.py      # MassStorageDevice resource
    │  └── kuiperrelease.py    # KuiperRelease resource
    │
    ├── drivers/
    │  ├── __init__.py
    │  ├── vesyncdriver.py     # VesyncPowerDriver
    │  ├── cyberpowerdriver.py # CyberPowerDriver
    │  ├── shelldriver.py      # ADIShellDriver
    │  ├── massstoragedriver.py# MassStorageDriver
    │  ├── kuiperdldriver.py   # KuiperDLDriver
    │  └── imageextractor.py   # ImageExtractor
    │
    ├── strategies/
    │  ├── __init__.py
    │  ├── bootfpgasoc.py      # BootFPGASoC strategy
    │  ├── bootfpgasocssh.py   # BootFPGASoCSSH strategy
    │  └── bootselmap.py       # BootSelMap strategy
    │
    └── tools/
       ├── vesync.py           # VeSync CLI tool
       └── kuiperdl.py         # Kuiper download CLI tool

**Resource Organization**:

- Resource classes define the configuration schema
- One resource per file for clarity
- Resource names match @attr.s class names
- Validators ensure data integrity

**Driver Organization**:

- One driver per file
- Driver name matches class name
- implements specific protocols
- @target_factory.reg_driver registers with labgrid

**Strategy Organization**:

- One strategy per file
- Manages related drivers
- Implements state machine
- @never_retry prevents retry loops

Design Principles
-----------------

**1. Separation of Concerns**

- Resources describe configuration (data)
- Drivers control hardware (actions)
- Strategies coordinate workflows (orchestration)

**2. Protocol-Based Bindings**

- Drivers implement protocols, not named types
- Strategies depend on protocols, not driver names
- Allows flexible implementation swapping

**3. Automatic Lifecycle Management**

- Strategies manage activation/deactivation
- Prevents manual lifecycle errors
- Ensures consistent state

**4. Composition Over Inheritance**

- Drivers combine mixins for functionality
- PowerResetMixin provides cycle() via on/off
- CommandMixin provides run_command() utilities

**5. Validation at Boundaries**

- Resources validated on instantiation
- Bindings validated before driver creation
- Errors reported immediately

**6. Extensibility Through Plugins**

- Entry points allow third-party components
- No core modification needed
- Standard interfaces ensure compatibility

See Also
--------

- :doc:`../user-guide/strategies` - Strategy usage guide
- :doc:`../user-guide/drivers` - Driver reference
- :doc:`../user-guide/resources` - Resource configuration
- :doc:`../api/index` - Complete API reference
- Labgrid documentation: https://labgrid.readthedocs.io/
