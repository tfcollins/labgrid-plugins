Common Use Cases
================

This page provides quick reference examples for typical workflows with adi-labgrid-plugins. Each example shows both configuration and Python usage.

Basic Power Control
--------------------

Turn on/off a device using a smart outlet:

**Configuration**:

.. code-block:: yaml

    targets:
      mydevice:
        resources:
          VesyncOutlet:
            outlet_names: 'Device Power'
            username: 'your_email@example.com'
            password: 'your_password'
            delay: 5.0

        drivers:
          VesyncPowerDriver: {}

**Usage**:

.. code-block:: python

    from labgrid import Environment

    env = Environment("target.yaml")
    target = env.get_target("mydevice")
    power = target.get_driver("VesyncPowerDriver")

    power.on()      # Turn on
    power.off()     # Turn off
    power.cycle()   # Power cycle (off, delay, on)

Serial Console Access
---------------------

Connect to a device's serial console for interactive shell commands:

**Configuration**:

.. code-block:: yaml

    targets:
      serial_device:
        resources:
          SerialPort:
            port: '/dev/ttyUSB0'
            baudrate: 115200

        drivers:
          ADIShellDriver:
            console: SerialPort
            prompt: 'root@.*:.*#'
            login_prompt: 'login:'
            username: 'root'
            password: 'analog'
            login_timeout: 60

**Usage**:

.. code-block:: python

    from labgrid import Environment

    env = Environment("target.yaml")
    target = env.get_target("serial_device")
    shell = target.get_driver("ADIShellDriver")
    target.activate(shell)

    # Run commands
    output = shell.run_command("uname -a")
    print(output)

    # Interactive: send command and wait for output
    shell.sendline("ls -la")
    shell.console.expect("root@.*:.*#")

File Transfer via XMODEM
------------------------

Upload/download files using XMODEM protocol over serial:

**Configuration**:

.. code-block:: yaml

    targets:
      xmodem_device:
        resources:
          SerialPort:
            port: '/dev/ttyUSB0'
            baudrate: 115200

        drivers:
          ADIShellDriver:
            prompt: 'root@.*:.*#'
            login_prompt: 'login:'
            username: 'root'
            password: 'analog'

**Upload file to device**:

.. code-block:: python

    from labgrid import Environment

    env = Environment("target.yaml")
    target = env.get_target("xmodem_device")
    shell = target.get_driver("ADIShellDriver")
    target.activate(shell)

    # Upload file using XMODEM
    shell.send_xmodem(
        local_path="/path/to/local/file.bin",
        remote_path="/tmp/file.bin"
    )

**Download file from device**:

.. code-block:: python

    # Download file using XMODEM
    shell.recv_xmodem(
        remote_path="/tmp/output.dat",
        local_path="/path/to/local/output.dat"
    )

Automated Boot Sequences
------------------------

Boot a device to shell using a strategy:

**Configuration**:

.. code-block:: yaml

    targets:
      bootable_device:
        resources:
          VesyncOutlet:
            outlet_names: 'Device Power'
            username: 'your_email@example.com'
            password: 'your_password'
            delay: 5.0

          SerialPort:
            port: '/dev/ttyUSB0'
            baudrate: 115200

          MassStorageDevice:
            path: '/dev/sda1'

          KuiperRelease:
            version: '2024.r1'

        drivers:
          VesyncPowerDriver: {}
          ADIShellDriver:
            prompt: 'root@.*:.*#'
            login_prompt: 'login:'
            username: 'root'
            password: 'analog'
          MassStorageDriver: {}
          KuiperDLDriver: {}

        strategies:
          BootFPGASoC:
            reached_linux_marker: 'analog'
            update_image: false

**Usage**:

.. code-block:: python

    from labgrid import Environment

    env = Environment("target.yaml")
    target = env.get_target("bootable_device")
    strategy = target.get_strategy("BootFPGASoC")

    # Boot to shell (goes through all intermediate states)
    strategy.transition("shell")

    # Device is now ready for testing
    shell = target.get_driver("ADIShellDriver")
    shell.run_command("echo 'Device booted successfully'")

    # Cleanup
    strategy.transition("soft_off")

SD Card Management
------------------

Mount SD card, copy files, prepare for device boot:

**Configuration**:

.. code-block:: yaml

    targets:
      sd_device:
        resources:
          MassStorageDevice:
            path: '/dev/sda1'

        drivers:
          MassStorageDriver:
            device: MassStorageDevice

**Usage**:

.. code-block:: python

    from labgrid import Environment

    env = Environment("target.yaml")
    target = env.get_target("sd_device")
    mass_storage = target.get_driver("MassStorageDriver")
    target.activate(mass_storage)

    # Mount partition
    mass_storage.mount_partition()

    # Copy files to SD card
    mass_storage.copy_file("/path/to/local/boot.bin", "/")
    mass_storage.copy_file("/path/to/local/devicetree.dtb", "/")

    # Verify files
    mass_storage.list_files("/")

    # Unmount
    mass_storage.unmount_partition()

Kuiper Release Download
-----------------------

Download and manage Kuiper release boot files:

**Configuration**:

.. code-block:: yaml

    targets:
      kuiper_device:
        resources:
          KuiperRelease:
            version: '2024.r1'
            cache_dir: '/tmp/kuiper_cache'

        drivers:
          KuiperDLDriver:
            kuiper_release: KuiperRelease

**Usage**:

.. code-block:: python

    from labgrid import Environment

    env = Environment("target.yaml")
    target = env.get_target("kuiper_device")
    kuiper = target.get_driver("KuiperDLDriver")
    target.activate(kuiper)

    # Download and extract release
    kuiper.download_release()

    # Get boot files paths
    boot_files = kuiper.get_boot_files_from_release()
    print(f"Boot files: {boot_files}")

    # Access individual files
    for file_path in kuiper._boot_files:
        print(f"File: {file_path}")

Testing Pattern with pytest
----------------------------

Integration with pytest for automated testing:

**conftest.py**:

.. code-block:: python

    import pytest
    from labgrid import Environment

    @pytest.fixture(scope="session")
    def env():
        """Load labgrid environment once per test session."""
        return Environment("target.yaml")

    @pytest.fixture(scope="function")
    def target(env):
        """Get target for each test."""
        return env.get_target("mydevice")

    @pytest.fixture(autouse=True)
    def setup_teardown(target):
        """Boot device before test, power off after."""
        strategy = target.get_strategy("BootFPGASoC")
        try:
            strategy.transition("shell")
            yield
        finally:
            try:
                strategy.transition("soft_off")
            except:
                pass

**test_device.py**:

.. code-block:: python

    def test_device_boots(target):
        """Verify device boots to shell."""
        strategy = target.get_strategy("BootFPGASoC")
        assert strategy.status.name == "shell"

    def test_kernel_version(target):
        """Verify kernel version."""
        shell = target.get_driver("ADIShellDriver")
        output = shell.run_command("uname -r")
        assert len(output) > 0

    def test_iio_devices(target):
        """Verify IIO devices are present."""
        shell = target.get_driver("ADIShellDriver")
        output = shell.run_command("ls /sys/bus/iio/devices/")
        assert "iio:device0" in output

Multi-Device Coordination
--------------------------

Manage multiple devices in a single test session:

**Configuration**:

.. code-block:: yaml

    targets:
      device_a:
        resources:
          VesyncOutlet:
            outlet_names: 'Device A Power'
            username: 'your_email@example.com'
            password: 'your_password'
            delay: 5.0

          SerialPort:
            port: '/dev/ttyUSB0'
            baudrate: 115200

        drivers:
          VesyncPowerDriver: {}
          ADIShellDriver:
            prompt: 'root@.*:.*#'
            login_prompt: 'login:'
            username: 'root'
            password: 'analog'

      device_b:
        resources:
          VesyncOutlet:
            outlet_names: 'Device B Power'
            username: 'your_email@example.com'
            password: 'your_password'
            delay: 5.0

          SerialPort:
            port: '/dev/ttyUSB1'
            baudrate: 115200

        drivers:
          VesyncPowerDriver: {}
          ADIShellDriver:
            prompt: 'root@.*:.*#'
            login_prompt: 'login:'
            username: 'root'
            password: 'analog'

**Usage**:

.. code-block:: python

    from labgrid import Environment

    env = Environment("target.yaml")
    device_a = env.get_target("device_a")
    device_b = env.get_target("device_b")

    # Power on both devices
    device_a.get_driver("VesyncPowerDriver").on()
    device_b.get_driver("VesyncPowerDriver").on()

    # Boot both to shell
    device_a.get_strategy("BootFPGASoC").transition("shell")
    device_b.get_strategy("BootFPGASoC").transition("shell")

    # Run commands on both
    shell_a = device_a.get_driver("ADIShellDriver")
    shell_b = device_b.get_driver("ADIShellDriver")

    output_a = shell_a.run_command("hostname")
    output_b = shell_b.run_command("hostname")

    print(f"Device A: {output_a}")
    print(f"Device B: {output_b}")

    # Cleanup
    device_a.get_strategy("BootFPGASoC").transition("soft_off")
    device_b.get_strategy("BootFPGASoC").transition("soft_off")

CyberPower PDU Control
----------------------

Control power via CyberPower PDU with SNMP:

**Configuration**:

.. code-block:: yaml

    targets:
      cyberpower_device:
        resources:
          CyberPowerOutlet:
            hostname: '192.168.1.100'
            outlet_number: 1
            snmp_version: '2c'
            community: 'public'

        drivers:
          CyberPowerDriver: {}

**Usage**:

.. code-block:: python

    from labgrid import Environment

    env = Environment("target.yaml")
    target = env.get_target("cyberpower_device")
    power = target.get_driver("CyberPowerDriver")
    target.activate(power)

    # Control power
    power.on()      # Turn on outlet
    power.off()     # Turn off outlet
    power.cycle()   # Reboot (off, delay, on)

    # Check power status (if supported)
    if hasattr(power, 'get_state'):
        state = power.get_state()
        print(f"Outlet state: {state}")

See Also
--------

- :doc:`strategies` - Strategy documentation for boot workflows
- :doc:`drivers` - Driver reference and capabilities
- :doc:`resources` - Resource configuration options
- :doc:`../examples/simple/power-control` - Power control detailed guide
- :doc:`../examples/simple/shell-commands` - Shell command guide
- :doc:`../examples/advanced/full-boot-cycle` - Complete boot cycle walkthrough
