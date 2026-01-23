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

.. mermaid::

   stateDiagram-v2
       [*] --> unknown

       unknown --> powered_off: Initialize
       powered_off --> sd_mux_to_host: Power off device
       sd_mux_to_host --> update_boot_files: Mux SD to host

       update_boot_files --> decide_image: Check update_image flag
       decide_image --> write_image: update_image=True
       decide_image --> copy_files: update_image=False
       write_image --> copy_files: Write full image
       copy_files --> sd_mux_to_dut: Copy boot files

       sd_mux_to_dut --> booting: Mux SD to device
       booting --> booted: Power on device
       booted --> shell: Wait for kernel + marker

       shell --> soft_off: Graceful shutdown
       soft_off --> [*]

       note right of sd_mux_to_host
           SD card accessible to host
       end note

       note right of write_image
           Optional: full image flash
       end note

       note right of booted
           Wait for Linux kernel + marker
       end note

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
-----------------------

**Purpose**: Boot an FPGA SoC device using SSH for file transfers instead of SD card mux. Useful when SSH access is available but SD card mux is not present.

**State Machine**:

The strategy manages 9 states with a two-stage boot process:

.. mermaid::

   stateDiagram-v2
       [*] --> unknown

       unknown --> powered_off: Initialize

       powered_off --> booting: Power on (if power driver)

       note right of powered_off
           Power control is optional
       end note

       booting --> booted: Wait for kernel + marker
       booted --> update_boot_files: SSH ready

       update_boot_files --> reboot: Transfer boot files via SSH

       note right of update_boot_files
           Validates and updates SSH IP address
       end note

       reboot --> booting_new: Issue reboot command
       booting_new --> shell: Wait for kernel + marker

       shell --> soft_off: Graceful shutdown
       soft_off --> [*]

       note right of booting
           First boot: initial system
       end note

       note right of booting_new
           Second boot: with updated files
       end note

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

**Troubleshooting**:

*Boot files don't transfer via SSH*:
   - Verify SSH access works: ``ssh root@<device-ip>``
   - Check SSH key is properly configured in resources
   - Ensure network connectivity between host and device
   - Verify pre_boot_boot_files and post_boot_boot_files paths are correct

*First boot succeeds but restart fails*:
   - This is expected behavior with SSH-based file transfer
   - Strategy only uploads files on first boot
   - To re-upload files, transition to powered_off and back to shell

*SSH connection hangs during boot*:
   - Increase wait_for_linux_prompt_timeout (default: 60s)
   - Check device is booting correctly via serial console
   - Verify network interface is configured in device tree

*Permission denied errors*:
   - Ensure SSH key has correct permissions (chmod 600)
   - Verify device allows root login via SSH
   - Check /boot partition is writable on device

BootSelMap Strategy
-------------------

**Purpose**: Boot a dual-FPGA design with primary Zynq FPGA (running Linux) and secondary Virtex FPGA (booted via SelMap interface).

**State Machine**:

The strategy manages 11 states with dual-FPGA boot orchestration:

.. mermaid::

   stateDiagram-v2
       [*] --> unknown
       unknown --> powered_off: Initialize
       powered_off --> booting_zynq: Power on
       booting_zynq --> booted_zynq: Wait for boot

       booted_zynq --> update_zynq_boot_files: Check files needed
       update_zynq_boot_files --> update_zynq_boot_files: Restart if files uploaded
       update_zynq_boot_files --> update_virtex_boot_files: Zynq ready

       update_virtex_boot_files --> trigger_selmap_boot: Files uploaded
       trigger_selmap_boot --> wait_for_virtex_boot: Run SelMap script

       wait_for_virtex_boot --> wait_for_virtex_boot: Poll IIO device (30s)
       wait_for_virtex_boot --> wait_for_virtex_boot: Poll JESD status (120s)
       wait_for_virtex_boot --> booted_virtex: JESD complete

       booted_virtex --> shell: Activate shell
       shell --> soft_off: Graceful shutdown
       soft_off --> [*]

       note right of update_zynq_boot_files
           Self-transition for boot file restart
       end note

       note right of wait_for_virtex_boot
           Polls IIO and JESD completion
       end note

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

    # Boot and wait for shell access
    # The strategy automatically transitions through all intermediate states
    strategy.transition("shell")

    # Verify both FPGAs are booted
    shell = target.get_driver("ADIShellDriver")
    shell.run_command("cat /proc/device-tree/chosen/fpga/axi-ad9081-rx-hpc/status")

    # Graceful shutdown
    strategy.transition("soft_off")

Note:
   The strategy automatically transitions through all intermediate states
   (powered_off → booting_zynq → booted_zynq → update_zynq_boot_files →
   update_virtex_boot_files → trigger_selmap_boot → wait_for_virtex_boot →
   booted_virtex → shell). You only need to request the final state.

**Advanced: Pre/Post Boot Files**:

The strategy supports optional pre-boot and post-boot file copying:

.. code-block:: python

    # In target configuration:
    # BootSelMap:
    #   pre_boot_boot_files: {'local_path': '/boot/remote_path'}
    #   post_boot_boot_files: {'local_path': '/boot/remote_path'}

    # Pre-boot files are copied before Zynq boot
    # Post-boot files are copied after Zynq boots but before Virtex boot

**Configuration Details**:

The BootSelMap strategy requires careful configuration of boot files for both
the Zynq (primary) and Virtex (secondary) FPGAs:

- **pre_boot_boot_files**: Files uploaded to Zynq before Virtex configuration.
  Dictionary format: ``{local_path: remote_path}``

  Example files:
  - Zynq device tree blob (system.dtb)
  - Zynq boot files (BOOT.BIN, image.ub)

  These files are uploaded via SSH, then the Zynq is rebooted to apply them.

- **post_boot_boot_files**: Files uploaded after Zynq boots with new device tree.
  Dictionary format: ``{local_path: remote_path}``

  Example files:
  - Virtex bitstream (.bin)
  - Virtex device tree overlay (.dtbo)
  - SelMap boot script (selmap_dtbo.sh)

  These files are used to configure the Virtex FPGA via SelMap interface.

- **ethernet_interface**: Network interface name on target (e.g., "eth0").
  Used to discover target IP address for SSH connections.

- **iio_jesd_driver_name**: IIO device name to poll after Virtex boot.
  Example: "axi-ad9081-rx-hpc" for AD9081 transceiver.
  Strategy polls this device to verify Virtex has booted successfully.

**Troubleshooting**:

*Zynq boots but Virtex doesn't configure*:
   - Check pre_boot_boot_files and post_boot_boot_files are correctly specified
   - Verify .dtbo and .bin files exist at specified paths
   - Check SelMap script exists: ``/boot/ci/selmap_dtbo.sh``
   - Run script manually: ``cd /boot/ci && ./selmap_dtbo.sh -d vu11p.dtbo -b vu11p.bin``

*IIO JESD device not found (wait_for_virtex_boot timeout)*:
   - Increase timeout if device takes longer than 30s to appear
   - Check device tree is correct for your hardware
   - Verify Virtex bitstream matches Zynq device tree configuration
   - Run ``dmesg | grep iio`` to see IIO driver messages

*JESD state machine doesn't reach opt_post_running_stage*:
   - Check JESD clock configuration in device tree
   - Verify AD9081 (or similar) transceiver is properly configured
   - Check for JESD sync errors: ``iio_attr -d <device> jesd204_fsm_error``
   - Typical JESD states: link_setup → clocks → link → opt_post_running_stage

*Files uploaded but boot still fails*:
   - Strategy restarts after uploading pre_boot_boot_files
   - Check serial console for Zynq boot errors after restart
   - Verify uploaded files are valid (not corrupted)
   - Ensure sufficient space on /boot partition

*"Permission denied" when uploading files via SSH*:
   - Verify SSH key is configured correctly
   - Check target filesystem is mounted read-write
   - Ensure sufficient disk space on target
   - Try manual SSH: ``scp localfile root@<device>:/boot/``

*Restart loop with pre_boot_boot_files*:
   - Strategy uploads files, restarts, and checks again
   - If files are different, it restarts again (infinite loop possible)
   - Ensure local files don't change between boots
   - Check _copied_pre_boot_files flag is being set correctly

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

BootFabric Strategy
-------------------

**Purpose**: Boot logic-only Xilinx FPGAs (Virtex/Artix/Kintex) with Microblaze soft processors via JTAG.

**Use Case**: Useful for FPGA-based systems without SoC (no ARM cores), where the processor is implemented in FPGA fabric. Common with ADI high-speed data converter evaluation boards (AD9081, AD9371, etc.) on Xilinx FPGA development boards like VCU118.

**State Machine**:

.. mermaid::

   stateDiagram-v2
       [*] --> unknown
       unknown --> powered_off: Initialize
       powered_off --> powered_on: Power on FPGA
       powered_on --> flash_fpga: Flash bitstream and kernel via JTAG
       flash_fpga --> booted: Start kernel execution and wait for boot
       booted --> shell: Activate shell access
       shell --> soft_off: Graceful shutdown
       soft_off --> [*]

       note right of flash_fpga
           Flash bitstream, download kernel, start execution
       end note

       note right of booted
           Wait for kernel boot marker (e.g., "login:")
       end note

**Configuration Example**:

.. code-block:: yaml

   targets:
     vcu118:
       resources:
         RawSerialPort:
           port: "/dev/ttyUSB0"
           speed: 115200

         XilinxDeviceJTAG:
           root_target: 1
           microblaze_target: 3
           bitstream_path: "/builds/system_top.bit"
           kernel_path: "/builds/simpleImage.vcu118.strip"

         XilinxVivadoTool:
           vivado_path: "/tools/Xilinx/Vivado"
           version: "2023.2"

         NetworkPowerPort:
           model: "gude"
           host: "192.168.1.100"
           index: 1

       drivers:
         SerialDriver: {}
         ADIShellDriver: {}
         XilinxJTAGDriver: {}
         NetworkPowerDriver: {}

         BootFabric:
           reached_boot_marker: "login:"
           wait_for_boot_timeout: 120
           verify_iio_device: "axi-ad9081-rx-hpc"

**Usage Example**:

.. code-block:: python

   from labgrid import Environment

   # Load environment
   env = Environment("vcu118.yaml")
   target = env.get_target("vcu118")

   # Get strategy and boot
   strategy = target.get_driver("BootFabric")
   strategy.transition("shell")

   # Run commands
   shell = target.get_driver("ADIShellDriver")
   stdout, _, _ = shell.run("cat /proc/cpuinfo")
   print(stdout)

   # Shutdown
   strategy.transition("soft_off")

**Attributes**:

- ``reached_boot_marker`` (str): String to expect in console when boot complete (default: "login:")
- ``wait_for_boot_timeout`` (int): Seconds to wait for boot marker (default: 120)
- ``verify_iio_device`` (str, optional): IIO device name to verify after boot

**Troubleshooting**:

*Bitstream flash fails*:
   - Verify JTAG cable is connected
   - Check bitstream file exists and path is correct
   - Run ``xsdb -interactive`` to verify xsdb works
   - Ensure FPGA is powered on

*Kernel download fails*:
   - Verify kernel file exists and path is correct
   - Ensure bitstream was flashed first
   - Check Microblaze target ID matches your hardware (run ``xsdb``, then ``targets``)

*Boot timeout*:
   - Increase ``wait_for_boot_timeout``
   - Check serial console is properly connected
   - Verify kernel is compatible with bitstream design

*IIO device not found*:
   - Check kernel has appropriate IIO drivers compiled
   - Verify device tree matches your hardware
   - Run ``dmesg`` to see kernel boot messages

State Transition Reference
---------------------------

This section provides quick reference tables for valid state transitions in each strategy.

**BootSelMap State Transitions**:

.. list-table::
   :header-rows: 1
   :widths: 30 30 40

   * - From State
     - To State
     - Actions Performed
   * - unknown
     - powered_off
     - Initialize, power off
   * - powered_off
     - booting_zynq
     - Power on Zynq
   * - booting_zynq
     - booted_zynq
     - Wait for Zynq boot
   * - booted_zynq
     - update_zynq_boot_files
     - Upload Zynq files via SSH (if configured)
   * - update_zynq_boot_files
     - update_zynq_boot_files
     - Restart if boot files uploaded
   * - update_zynq_boot_files
     - update_virtex_boot_files
     - Zynq ready for next stage
   * - update_virtex_boot_files
     - trigger_selmap_boot
     - Virtex files uploaded
   * - trigger_selmap_boot
     - wait_for_virtex_boot
     - Run SelMap script
   * - wait_for_virtex_boot
     - booted_virtex
     - Verify IIO device and JESD completion
   * - booted_virtex
     - shell
     - Activate shell driver
   * - shell
     - soft_off
     - Graceful shutdown
   * - soft_off
     - (end)
     - Both FPGAs powered down

**BootFabric State Transitions**:

.. list-table::
   :header-rows: 1
   :widths: 30 30 40

   * - From State
     - To State
     - Actions Performed
   * - unknown
     - powered_off
     - Initialize
   * - powered_off
     - powered_on
     - Power on FPGA
   * - powered_on
     - flash_fpga
     - Flash bitstream via JTAG
   * - flash_fpga
     - booted
     - Download kernel and start execution
   * - booted
     - shell
     - Wait for boot marker and activate shell
   * - shell
     - soft_off
     - Graceful shutdown
   * - soft_off
     - (end)
     - FPGA powered down

See Also
~~~~~~~~

- :doc:`../api/strategies` - Complete API reference for all strategies
- :doc:`drivers` - Information about available drivers
- :doc:`resources` - Resource configuration reference
- :doc:`../examples/advanced/full-boot-cycle` - Complete boot workflow example
- Labgrid documentation: https://labgrid.readthedocs.io/
