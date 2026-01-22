Complete Boot Cycle Example
============================

This comprehensive guide demonstrates a complete FPGA SoC boot cycle using the BootFPGASoC strategy. It includes hardware setup, configuration, step-by-step boot sequence, output examples, and advanced usage patterns.

Overview
--------

The BootFPGASoC strategy orchestrates a complex boot process:

1. **Power Off** - Ensure device is off and clean
2. **SD Card to Host** - Switch SD mux to host computer
3. **Prepare Boot Files** - Copy Kuiper boot artifacts to SD card
4. **Optional Image Flash** - Write full image if configured
5. **SD Card to Device** - Switch SD mux back to device
6. **Power On** - Apply power to device
7. **Monitor Boot** - Watch for Linux kernel and shell prompt
8. **Shell Ready** - Interactive shell session available
9. **Cleanup** - Graceful shutdown on completion

Hardware Setup
--------------

**Physical Connections Required**:

1. **Power Control**
   - Vesync Smart Outlet or CyberPower PDU
   - Controlled outlet powers the FPGA SoC board

2. **Serial Console**
   - USB serial adapter (FT232RL, CH340, or similar)
   - Connected to device serial port (typically UART0)
   - Enables boot monitoring and shell interaction

3. **SD Card Mux**
   - USB SD Card Mux (e.g., DZC firmware)
   - One port to USB on host computer
   - One port to SD card slot on device
   - Allows host to mount device's SD card

4. **Mass Storage Access**
   - SD card must be visible as /dev/sd* device on host
   - Typically /dev/sda or /dev/sdb depending on system

**Block Diagram**:

.. code-block:: text

    Host Computer
    ├── USB Serial Device  ──→  Device UART (boot messages + shell)
    ├── USB SD Card Mux    ──→  Device SD Card Slot
    │   └─ Hosts SD Card (mounted as /dev/sda or similar)
    └── Network (VeSync)   ──→  Smart Outlet
        └─ Powers Device

Complete Configuration
----------------------

**target.yaml - Full Example**:

.. code-block:: yaml

    targets:
      fpga_soc_board:
        resources:
          VesyncOutlet:
            outlet_names: 'FPGA SoC Power'
            username: 'your_email@example.com'
            password: 'your_password'
            delay: 5.0  # Wait 5s between power off and on

          SerialPort:
            port: '/dev/ttyUSB0'
            baudrate: 115200

          USBSDMuxDriver:
            serial: '00012345'  # Serial of your SD mux device

          MassStorageDevice:
            path: '/dev/sda1'  # Your SD card partition

          KuiperRelease:
            version: '2024.r1'  # Release version to boot
            cache_dir: '/tmp/kuiper_cache'

        drivers:
          VesyncPowerDriver: {}

          ADIShellDriver:
            console: SerialPort
            prompt: 'root@.*:.*# '  # Adjust to match your prompt
            login_prompt: 'login:'
            username: 'root'
            password: 'analog'
            login_timeout: 60
            post_login_settle_time: 2

          USBSDMuxDriver: {}

          MassStorageDriver:
            device: MassStorageDevice

          KuiperDLDriver: {}

        strategies:
          BootFPGASoC:
            reached_linux_marker: 'analog'  # String in login prompt
            update_image: false  # Set to true to flash full image

Basic Boot Script
-----------------

**Minimal Working Example**:

.. code-block:: python

    from labgrid import Environment

    # Load configuration
    env = Environment("target.yaml")
    target = env.get_target("fpga_soc_board")

    # Get strategy
    strategy = target.get_strategy("BootFPGASoC")

    # Boot to shell (handles all intermediate states)
    print("Booting device...")
    strategy.transition("shell")

    print("Device is now booted!")
    print(f"Current state: {strategy.status}")

    # Device is ready for testing
    shell = target.get_driver("ADIShellDriver")
    output = shell.run_command("uname -a")
    print(f"Kernel info: {output}")

    # Cleanup
    print("Shutting down...")
    strategy.transition("soft_off")
    print("Done!")

Step-by-Step Boot Sequence
---------------------------

**Detailed Boot Process with State Monitoring**:

.. code-block:: python

    from labgrid import Environment
    from adi_lg_plugins.strategies.bootfpgasoc import Status
    import time

    env = Environment("target.yaml")
    target = env.get_target("fpga_soc_board")
    strategy = target.get_strategy("BootFPGASoC")

    boot_states = [
        "powered_off",
        "sd_mux_to_host",
        "update_boot_files",
        "sd_mux_to_dut",
        "booting",
        "booted",
        "shell",
    ]

    print("Starting boot sequence...")
    print(f"Initial state: {strategy.status}")

    for state_name in boot_states:
        print(f"\n--- Transitioning to: {state_name} ---")

        start_time = time.time()
        strategy.transition(state_name)
        elapsed = time.time() - start_time

        print(f"✓ State reached in {elapsed:.1f}s")
        print(f"Current state: {strategy.status.name}")

        # Add delays between certain states for observation
        if state_name == "booting":
            print("Waiting for boot messages...")
            time.sleep(5)

    print("\n--- Boot Complete ---")
    print("Device ready for testing")

Boot Output Examples
--------------------

**Expected Serial Console Output**:

.. code-block:: text

    [Serial Console Output During Boot]

    U-Boot 2018.01 (Jan 01 2024)

    CPU:   Xilinx ZynqMP
    Board: Analog Devices ADI FPGA SoC
    I2C:   ready
    MMC:   sdhci@ff160000: 0, sdhci@ff170000: 1
    Loading Environment from MMC... OK
    In:    serial@ff010000
    Out:   serial@ff010000
    Err:   serial@ff010000
    SOM init timeout
    Trying other addresses...
    Model: Analog Devices ZynqMP SOM
    ...

    [Linux Kernel Boot]
    Booting with device tree blob at 0x100000
    ...
    Welcome to Petalinux 2021.1
    minimal /init: setting up..
    ...
    systemd[1]: Started User Manager...
    login:

    [Shell Login Prompt]
    login: root
    Password:
    Last login: Jan 1 00:00:00 UTC 2024 from console
    root@zynqmp:~#

Advanced Usage - Full Image Flash
----------------------------------

**Boot with Complete Image Update**:

When ``update_image: true``, the strategy writes the entire Kuiper image to the SD card before copying individual boot files. This ensures a clean filesystem.

**Configuration**:

.. code-block:: yaml

    strategies:
      BootFPGASoC:
        reached_linux_marker: 'analog'
        update_image: true  # Enable full image flash

**With Image Flash**:

.. code-block:: python

    from labgrid import Environment
    from adi_lg_plugins.strategies.bootfpgasoc import Status
    import time

    env = Environment("target.yaml")
    target = env.get_target("fpga_soc_board")
    strategy = target.get_strategy("BootFPGASoC")

    print("Booting with full image flash...")

    # Boot to update_boot_files state
    # This will:
    # 1. Power off device
    # 2. Mux SD card to host
    # 3. Write full Kuiper image using bmap-tool
    # 4. Copy individual boot files on top
    # 5. Mux SD card back to device

    strategy.transition("update_boot_files")
    print("Image flashed successfully")

    # Continue to shell
    strategy.transition("booting")
    time.sleep(20)  # Wait for boot

    strategy.transition("booted")
    strategy.transition("shell")

    # Verify clean filesystem
    shell = target.get_driver("ADIShellDriver")
    df_output = shell.run_command("df -h /")
    print(f"Root filesystem: {df_output}")

    strategy.transition("soft_off")

Custom Boot Files
-----------------

**Using Custom Device Tree and Kernel**:

.. code-block:: python

    from labgrid import Environment
    import shutil
    import os

    env = Environment("target.yaml")
    target = env.get_target("fpga_soc_board")

    # Prepare custom boot files before strategy
    kuiper = target.get_driver("KuiperDLDriver")
    target.activate(kuiper)

    # Download standard Kuiper release
    kuiper.download_release()
    kuiper.get_boot_files_from_release()

    # Replace devicetree with custom one
    custom_dtb = "/path/to/custom/system.dtb"
    boot_files_dir = kuiper._boot_files_dir

    print(f"Original boot files in: {boot_files_dir}")
    shutil.copy(custom_dtb, os.path.join(boot_files_dir, "system.dtb"))

    target.deactivate(kuiper)

    # Now boot with custom device tree
    strategy = target.get_strategy("BootFPGASoC")
    strategy.transition("shell")

    # Verify custom devicetree loaded
    shell = target.get_driver("ADIShellDriver")
    dmesg = shell.run_command("dmesg | grep -i device")
    print(f"Device tree messages: {dmesg}")

    strategy.transition("soft_off")

pytest Integration
------------------

**Automated Testing with pytest Fixtures**:

**conftest.py**:

.. code-block:: python

    import pytest
    from labgrid import Environment
    from adi_lg_plugins.strategies.bootfpgasoc import Status

    @pytest.fixture(scope="session")
    def env():
        """Load environment once per test session."""
        return Environment("target.yaml")

    @pytest.fixture(scope="session")
    def target(env):
        """Get target from environment."""
        return env.get_target("fpga_soc_board")

    @pytest.fixture(scope="session", autouse=True)
    def boot_device(target):
        """Boot device at start of session, power off at end."""
        strategy = target.get_strategy("BootFPGASoC")

        print("\n=== Booting device ===")
        try:
            strategy.transition("shell")
            print("Device booted successfully")
        except Exception as e:
            print(f"Boot failed: {e}")
            raise

        yield  # Run all tests

        print("\n=== Powering down device ===")
        try:
            strategy.transition("soft_off")
            print("Device powered off successfully")
        except:
            pass  # OK if power down fails

    @pytest.fixture
    def shell(target):
        """Get shell driver (already activated by strategy)."""
        return target.get_driver("ADIShellDriver")

**test_boot_and_functionality.py**:

.. code-block:: python

    def test_device_is_booted(target):
        """Verify device successfully booted."""
        strategy = target.get_strategy("BootFPGASoC")
        assert strategy.status == Status.shell

    def test_kernel_is_running(shell):
        """Verify Linux kernel is running."""
        output = shell.run_command("uname -s").strip()
        assert output == "Linux"

    def test_filesystem_mounted(shell):
        """Verify root filesystem is accessible."""
        output = shell.run_command("ls /")
        assert "etc" in output
        assert "var" in output

    def test_system_clock(shell):
        """Verify system clock is synchronized."""
        output = shell.run_command("date +%Y")
        year = int(output.strip())
        assert year >= 2024

    def test_iio_device_present(shell):
        """Verify IIO device is loaded."""
        output = shell.run_command("ls /sys/bus/iio/devices/")
        assert "iio:device0" in output

    def test_adc_reading(shell):
        """Verify ADC is functional."""
        adc_val = shell.run_command(
            "cat /sys/bus/iio/devices/iio:device0/in_voltage0_raw"
        ).strip()
        value = int(adc_val)
        assert 0 <= value <= 65535

**Run Tests**:

.. code-block:: bash

    pytest test_boot_and_functionality.py -v

    # Output:
    # test_boot_and_functionality.py::test_device_is_booted PASSED
    # test_boot_and_functionality.py::test_kernel_is_running PASSED
    # test_boot_and_functionality.py::test_filesystem_mounted PASSED
    # ...

Troubleshooting Guide
---------------------

**Boot Hangs at "Booting" State**

.. code-block:: text

    Problem: Device doesn't boot within timeout

    Diagnostic Steps:
    1. Check serial console manually:
       $ screen /dev/ttyUSB0 115200
       - Look for U-Boot output
       - Check for error messages

    2. Verify SD card is visible to host:
       $ ls -la /dev/sd*
       - Should see SD card device
       - Check it's in dmesg: dmesg | tail -20

    3. Verify SD mux is switched:
       - Physically check SD mux position
       - Verify serial number in config

    Solutions:
    - Increase login_timeout: login_timeout: 120
    - Check power supply (may be insufficient)
    - Verify serial cable connection
    - Try different SD card
    - Check U-Boot console for FPGA configuration errors

**"No transition found" Error**

.. code-block:: text

    Problem: StrategyError with no valid transition

    Causes:
    - SD mux not responding (check USB connection)
    - MassStorageDriver can't mount SD card
    - Power driver authentication failed
    - Shell can't login to device

    Debug:
    - Manually activate each driver:
        power = target.get_driver("VesyncPowerDriver")
        target.activate(power)

    - Test SD mux:
        sdmux = target.get_driver("USBSDMuxDriver")
        target.activate(sdmux)
        sdmux.set_mode("host")  # or "dut"

    - Test mass storage:
        mass_storage = target.get_driver("MassStorageDriver")
        target.activate(mass_storage)
        mass_storage.mount_partition()

**Timeout in "update_boot_files"**

.. code-block:: text

    Problem: Hangs when copying boot files

    Causes:
    - /dev/sda1 is wrong device
    - Partition not visible
    - Insufficient disk space
    - Permission denied

    Check:
    - Verify device path: lsblk
    - Check mounted filesystems: mount | grep /dev/sd
    - Check free space: df -h /dev/sda1
    - Verify read/write permissions: stat /dev/sda1

    Solutions:
    - Unmount device: umount /dev/sda1
    - Try as root: sudo python3 script.py
    - Reseat SD card in mux
    - Try different USB port on host

**Shell Login Fails**

.. code-block:: text

    Problem: Device boots but can't login

    Causes:
    - Wrong username/password
    - Prompt regex doesn't match
    - Login timeout too short
    - Serial console not responding

    Check:
    - Manually login via serial console
    - Verify prompt matches configured regex
    - Check for extra characters/spaces

    Solutions:
    - Adjust prompt regex: prompt: 'root@.*# '
    - Increase login_timeout: login_timeout: 120
    - Add post_login_settle_time: 5
    - Check serial connection quality

**Power Control Not Working**

.. code-block:: text

    Problem: VeSync outlet doesn't respond

    Causes:
    - Network connectivity issue
    - Wrong outlet name
    - VeSync account locked
    - Credentials invalid

    Debug:
    - Test VeSync manually:
        from pyvesync import VeSync
        vesync = VeSync("email", "password")
        vesync.login()
        vesync.get_devices()
        for outlet in vesync.outlets:
            print(outlet.device_name)

    - Verify outlet name matches exactly
    - Check VeSync app on phone

Advanced Patterns
-----------------

**Recovery from Boot Failure**

.. code-block:: python

    from labgrid import Environment
    from labgrid.strategy import StrategyError
    from adi_lg_plugins.strategies.bootfpgasoc import Status

    def boot_with_recovery(target, max_attempts=3):
        """Boot with automatic recovery on failure."""
        strategy = target.get_strategy("BootFPGASoC")

        for attempt in range(max_attempts):
            try:
                print(f"Boot attempt {attempt + 1}/{max_attempts}")
                strategy.transition("shell")
                print("Boot successful!")
                return True

            except StrategyError as e:
                print(f"Boot failed: {e}")

                # Reset to known state
                try:
                    strategy.transition("powered_off")
                except:
                    pass

                if attempt < max_attempts - 1:
                    print(f"Waiting before retry...")
                    time.sleep(10)

        print(f"Failed to boot after {max_attempts} attempts")
        return False

    env = Environment("target.yaml")
    target = env.get_target("fpga_soc_board")
    if boot_with_recovery(target):
        shell = target.get_driver("ADIShellDriver")
        shell.run_command("uname -a")

**Multiple Boot Cycles for Stress Testing**

.. code-block:: python

    from labgrid import Environment
    import time

    def stress_test_boot_cycles(target, num_cycles=10):
        """Stress test device with multiple boot cycles."""
        strategy = target.get_strategy("BootFPGASoC")
        shell = target.get_driver("ADIShellDriver")

        results = []

        for cycle in range(num_cycles):
            print(f"\n=== Boot Cycle {cycle + 1}/{num_cycles} ===")

            try:
                # Boot
                start = time.time()
                strategy.transition("shell")
                boot_time = time.time() - start

                # Quick test
                output = shell.run_command("uptime").strip()

                # Shutdown
                strategy.transition("soft_off")

                results.append({
                    'cycle': cycle + 1,
                    'status': 'PASS',
                    'boot_time': boot_time,
                    'output': output,
                })

                print(f"✓ PASS (boot time: {boot_time:.1f}s)")
                time.sleep(5)  # Delay between cycles

            except Exception as e:
                results.append({
                    'cycle': cycle + 1,
                    'status': 'FAIL',
                    'error': str(e),
                })
                print(f"✗ FAIL: {e}")

        # Summary
        print(f"\n=== Results ===")
        passed = sum(1 for r in results if r['status'] == 'PASS')
        print(f"Passed: {passed}/{num_cycles}")

        for result in results:
            print(f"Cycle {result['cycle']}: {result['status']}")

        return passed == num_cycles

See Also
--------

- :doc:`../../user-guide/strategies` - Strategy documentation
- :doc:`../../user-guide/examples` - Common use cases
- :doc:`../simple/power-control` - Power control details
- :doc:`../simple/shell-commands` - Shell command execution
- :doc:`../../api/drivers` - Complete driver reference
- :doc:`../../api/strategies` - Strategy API reference
