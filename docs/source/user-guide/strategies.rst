Working with Strategies
=======================

Strategies are high-level state machines that coordinate multiple drivers to accomplish complex workflows. They abstract away the detailed choreography of hardware interactions, allowing test engineers to focus on the overall boot and test sequence.

Overview
--------

A strategy represents a reusable workflow composed of multiple state transitions. Each transition may activate or deactivate drivers, execute commands, and wait for expected conditions. Strategies form the bridge between raw driver capabilities and practical test procedures.

Key Concepts
~~~~~~~~~~~~

- **State Machine**: Strategies are implemented as state machines with discrete states representing different phases of a workflow (e.g., powered_off, booting, shell).
- **Bindings**: Each strategy declares required and optional driver/resource bindings that must be present on the target.
- **Transitions**: The ``transition()`` method moves the strategy from one state to another, handling all intermediate steps automatically.
- **Activation Lifecycle**: Drivers are activated and deactivated as needed by the strategy, not manually by the test.
- **Error Handling**: StrategyError exceptions indicate invalid transitions or failed operations.

BootFPGASoC Strategy
--------------------

**Purpose**: Boot an FPGA SoC device (e.g., Zynq UltraScale+) using an SD card mux and Kuiper release images.

**State Machine**:

The strategy manages 9 states:

.. code-block:: text

    unknown
      ↓
    powered_off
      ↓
    sd_mux_to_host ← SD card accessible to host
      ↓
    update_boot_files ← Copy boot files and optionally flash full image
      ↓
    sd_mux_to_dut ← SD card accessible to device
      ↓
    booting ← Power on device
      ↓
    booted ← Wait for kernel and marker
      ↓
    shell ← Shell interaction available
      ↓
    soft_off ← Graceful shutdown via poweroff command

**Hardware Requirements**:

- Power control (VeSync, CyberPower, or other PowerProtocol implementation)
- SD card mux (USBSDMuxDriver) to switch SD card between host and device
- Mass storage access (MassStorageDriver) for copying files to SD card
- Serial console access (ADIShellDriver) for boot monitoring and shell interaction
- Kuiper release files (KuiperDLDriver) for boot artifacts
- Optional: USB storage writer (USBStorageDriver) for full image flashing

**Configuration Example**:

.. code-block:: yaml

    targets:
      mydevice:
        resources:
          VesyncOutlet:
            outlet_names: 'Device Power'
            username: 'your_email@example.com'
            password: 'your_password'
            delay: 5.0

          USBSDMuxDriver:
            serial: '00012345'

          MassStorageDriver:
            path: '/dev/sda1'

          SerialPort:
            port: '/dev/ttyUSB0'
            baudrate: 115200

          KuiperDLDriver:
            release_version: '2024.r1'

        drivers:
          VesyncPowerDriver: {}
          USBSDMuxDriver: {}
          MassStorageDriver: {}
          ADIShellDriver:
            prompt: 'root@.*:.*#'
            login_prompt: 'login:'
            username: 'root'
            password: 'analog'
          KuiperDLDriver: {}

        strategies:
          BootFPGASoC:
            reached_linux_marker: 'analog'
            update_image: true  # Flash full image, not just boot files

**Usage Example**:

.. code-block:: python

    from labgrid import Environment
    from adi_lg_plugins.strategies import BootFPGASoC

    env = Environment("target.yaml")
    target = env.get_target("mydevice")
    strategy = target.get_strategy("BootFPGASoC")

    # Boot the device to shell
    strategy.transition("shell")

    # Now shell access is available
    shell = target.get_driver("ADIShellDriver")
    shell.run_command("uname -a")

    # Power off cleanly
    strategy.transition("soft_off")

**Advanced Usage - Full Image Flash**:

When ``update_image=True``, the strategy will flash the complete Kuiper release image to the SD card before copying individual boot files. This is useful for ensuring a clean filesystem:

.. code-block:: python

    # In target configuration:
    # BootFPGASoC:
    #   update_image: true

    # The strategy automatically:
    # 1. Muxes SD card to host
    # 2. Writes full image using USB storage writer
    # 3. Copies specific boot files on top
    # 4. Muxes SD card back to device
    # 5. Boots device

**Error Handling**:

The strategy raises ``StrategyError`` for invalid transitions. Common scenarios:

.. code-block:: python

    from labgrid.strategy import StrategyError

    try:
        strategy.transition("shell")
    except StrategyError as e:
        if "can not transition to unknown" in str(e):
            print("Cannot transition to initial state")
        elif "no transition found" in str(e):
            print("Invalid state transition")

**State Awareness**:

Always check the current state before transitioning:

.. code-block:: python

    from adi_lg_plugins.strategies.bootfpgasoc import Status

    strategy = target.get_strategy("BootFPGASoC")

    if strategy.status == Status.unknown:
        strategy.transition(Status.shell)
    elif strategy.status == Status.shell:
        print("Already at shell")
    elif strategy.status == Status.powered_off:
        strategy.transition(Status.shell)

BootFPGASoCSSH Strategy
----------------------

**Purpose**: Boot an FPGA SoC device using SSH for file transfers instead of SD card mux. Useful when SSH access is available but SD card mux is not present.

**State Machine**:

The strategy manages 9 states:

.. code-block:: text

    unknown
      ↓
    powered_off
      ↓
    booting ← Power on and wait for initial boot
      ↓
    booted ← Linux kernel available, waiting for shell access
      ↓
    update_boot_files ← Transfer boot files via SSH
      ↓
    reboot ← Reboot device with new boot files
      ↓
    booting_new ← Boot with updated files
      ↓
    shell ← Full shell session available
      ↓
    soft_off ← Graceful shutdown

**Key Differences from BootFPGASoC**:

- Uses SSH (SSHDriver) instead of SD card mux for file transfer
- Does not require mass storage driver or SD mux hardware
- Power control is optional (devices may boot automatically on power)
- More suitable for devices with network access
- Faster boot cycles after initial boot (no physical SD mux switching)

**Configuration Example**:

.. code-block:: yaml

    targets:
      netdevice:
        resources:
          VesyncOutlet:
            outlet_names: 'Device Power'
            username: 'your_email@example.com'
            password: 'your_password'

          SerialPort:
            port: '/dev/ttyUSB0'
            baudrate: 115200

          NetworkInterface:
            hostname: 'analog.local'
            username: 'root'
            password: 'analog'

          KuiperDLDriver:
            release_version: '2024.r1'

        drivers:
          VesyncPowerDriver: {}
          ADIShellDriver:
            prompt: 'root@.*:.*#'
            login_prompt: 'login:'
            username: 'root'
            password: 'analog'
          SSHDriver:
            hostname: 'analog.local'
            username: 'root'
            password: 'analog'
          KuiperDLDriver: {}

        strategies:
          BootFPGASoCSSH:
            hostname: 'analog.local'
            reached_linux_marker: 'analog'

**Usage Example**:

.. code-block:: python

    env = Environment("target.yaml")
    target = env.get_target("netdevice")
    strategy = target.get_strategy("BootFPGASoCSSH")

    # Boot to shell via SSH
    strategy.transition("shell")

    # Update boot files via SSH and reboot
    strategy.transition("update_boot_files")
    strategy.transition("reboot")
    strategy.transition("shell")

**Cleanup and Shutdown**:

Always transition to ``soft_off`` to gracefully shutdown:

.. code-block:: python

    strategy.transition("soft_off")

BootSelMap Strategy
-------------------

**Purpose**: Boot a dual-FPGA design with primary Zynq FPGA (running Linux) and secondary Virtex FPGA (booted via SelMap interface).

**State Machine**:

The strategy manages 11 states:

.. code-block:: text

    unknown
      ↓
    powered_off ← Both FPGAs powered off
      ↓
    booting_zynq ← Primary Zynq FPGA booting
      ↓
    booted_zynq ← Zynq FPGA has booted Linux
      ↓
    update_zynq_boot_files ← Copy Zynq boot files if needed
      ↓
    update_virtex_boot_files ← Copy Virtex bitstream files
      ↓
    trigger_selmap_boot ← Initiate secondary FPGA boot via SelMap
      ↓
    wait_for_virtex_boot ← Monitor secondary FPGA boot progress
      ↓
    booted_virtex ← Secondary Virtex FPGA ready
      ↓
    shell ← Interactive shell on Zynq
      ↓
    soft_off ← Shutdown both FPGAs

**Hardware Requirements**:

- Power control for both FPGAs
- Serial console access to Zynq (ADIShellDriver)
- SSH access to Zynq after boot
- SelMap interface connected from Zynq to Virtex for secondary FPGA programming
- Kuiper release files for both Zynq and Virtex bitstreams

**Configuration Example**:

.. code-block:: yaml

    targets:
      dual_fpga:
        resources:
          VesyncOutlet:
            outlet_names: 'Dual FPGA Power'
            username: 'your_email@example.com'
            password: 'your_password'

          SerialPort:
            port: '/dev/ttyUSB0'
            baudrate: 115200

          NetworkInterface:
            hostname: 'zynq.local'
            username: 'root'
            password: 'analog'

          KuiperDLDriver:
            release_version: '2024.r1'

        drivers:
          VesyncPowerDriver: {}
          ADIShellDriver:
            prompt: 'root@.*:.*#'
            login_prompt: 'login:'
            username: 'root'
            password: 'analog'
          SSHDriver:
            hostname: 'zynq.local'
            username: 'root'
            password: 'analog'

        strategies:
          BootSelMap:
            reached_linux_marker: 'analog'
            ethernet_interface: 'eth0'
            iio_jesd_driver_name: 'axi-ad9081-rx-hpc'
            pre_boot_boot_files: null
            post_boot_boot_files: null

**Usage Example**:

.. code-block:: python

    env = Environment("target.yaml")
    target = env.get_target("dual_fpga")
    strategy = target.get_strategy("BootSelMap")

    # Boot primary Zynq FPGA
    strategy.transition("booted_zynq")

    # Update and boot secondary Virtex FPGA via SelMap
    strategy.transition("update_virtex_boot_files")
    strategy.transition("trigger_selmap_boot")
    strategy.transition("booted_virtex")

    # Get shell access
    strategy.transition("shell")

    # Verify both FPGAs are booted
    shell = target.get_driver("ADIShellDriver")
    shell.run_command("cat /proc/device-tree/chosen/fpga/axi-ad9081-rx-hpc/status")

**Advanced: Pre/Post Boot Files**:

The strategy supports optional pre-boot and post-boot file copying:

.. code-block:: python

    # In target configuration:
    # BootSelMap:
    #   pre_boot_boot_files: ['fpga_primary.dtb', 'boot.bin']
    #   post_boot_boot_files: ['devicetree.dtb', 'ad9081.bin']

    # Pre-boot files are copied before Zynq boot
    # Post-boot files are copied after Zynq boots but before Virtex boot

Best Practices
--------------

**1. State Awareness**

Always understand the current state before transitioning:

.. code-block:: python

    # Check current state
    if strategy.status != Status.shell:
        strategy.transition("shell")

    # Avoid redundant transitions
    if strategy.status != Status.powered_off:
        strategy.transition("powered_off")

**2. Error Recovery**

Implement error handling for robust test sequences:

.. code-block:: python

    from labgrid.strategy import StrategyError

    def safe_transition(strategy, target_state, max_retries=3):
        for attempt in range(max_retries):
            try:
                strategy.transition(target_state)
                return True
            except StrategyError as e:
                print(f"Transition failed (attempt {attempt+1}): {e}")
                if attempt < max_retries - 1:
                    # Reset to known state
                    try:
                        strategy.transition(Status.powered_off)
                    except:
                        pass
                    time.sleep(5)
        return False

**3. Driver Lifecycle Management**

Understand that strategies activate/deactivate drivers automatically. Do not manually activate drivers that are managed by the strategy:

.. code-block:: python

    # Good - Let strategy manage power driver
    strategy.transition("shell")

    # Bad - Don't double-activate
    strategy.transition("shell")
    power = target.get_driver("VesyncPowerDriver")  # Already active

**4. Timeout Configuration**

Set appropriate timeouts for slow hardware:

.. code-block:: python

    # In shell driver configuration
    ADIShellDriver:
      prompt: 'root@.*:.*#'
      login_prompt: 'login:'
      username: 'root'
      password: 'analog'
      login_timeout: 120  # Increase for slow boots
      post_login_settle_time: 5  # Extra time after login

**5. Cleanup on Failure**

Always attempt graceful shutdown in test cleanup:

.. code-block:: python

    def test_device_functionality():
        try:
            strategy.transition("shell")
            # Run tests
            shell.run_command("some_test_command")
        finally:
            # Cleanup even if test fails
            try:
                strategy.transition("soft_off")
            except:
                pass  # Power off if soft off fails

**6. Logging and Debugging**

Enable debug logging to understand strategy behavior:

.. code-block:: python

    import logging

    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger("labgrid")
    logger.setLevel(logging.DEBUG)

    strategy.transition("shell")  # Now see detailed debug output

Custom Strategy Development
-----------------------------

Creating custom strategies follows the labgrid plugin pattern. A strategy must:

1. Inherit from ``labgrid.strategy.Strategy``
2. Define required/optional bindings
3. Implement a state machine with an enum
4. Provide a ``transition()`` method
5. Register with ``@target_factory.reg_driver``

**Minimal Example**:

.. code-block:: python

    import enum
    import attr
    from labgrid.factory import target_factory
    from labgrid.step import step
    from labgrid.strategy import Strategy, StrategyError, never_retry

    class MyStatus(enum.Enum):
        unknown = 0
        state_a = 1
        state_b = 2

    @target_factory.reg_driver
    @attr.s(eq=False)
    class MyStrategy(Strategy):
        """Custom strategy template."""

        bindings = {
            "power": "PowerProtocol",
            "shell": "ADIShellDriver",
        }

        status = attr.ib(default=MyStatus.unknown)

        @never_retry
        @step()
        def transition(self, status, *, step):
            if not isinstance(status, MyStatus):
                status = MyStatus[status]

            if status == MyStatus.state_a:
                self.target.activate(self.power)
                self.power.on()
            elif status == MyStatus.state_b:
                self.transition(MyStatus.state_a)
                self.target.activate(self.shell)
            else:
                raise StrategyError(f"no transition to {status}")

            self.status = status

**Advanced Pattern - Hooks**:

.. code-block:: python

    @attr.s(eq=False)
    class HookedStrategy(Strategy):
        """Strategy with before/after hooks."""

        status = attr.ib(default=Status.unknown)
        _hooks = attr.ib(factory=dict, init=False)

        def register_hook(self, state, hook_fn):
            """Register a callable to run after transitioning to state."""
            if state not in self._hooks:
                self._hooks[state] = []
            self._hooks[state].append(hook_fn)

        @never_retry
        @step()
        def transition(self, status, *, step):
            # ... transition logic ...

            # Run hooks
            if status in self._hooks:
                for hook in self._hooks[status]:
                    hook()

See Also
~~~~~~~~

- :doc:`../api/strategies` - Complete API reference for all strategies
- :doc:`drivers` - Information about available drivers
- :doc:`resources` - Resource configuration reference
- :doc:`../examples/advanced/full-boot-cycle` - Complete boot workflow example
- Labgrid documentation: https://labgrid.readthedocs.io/
