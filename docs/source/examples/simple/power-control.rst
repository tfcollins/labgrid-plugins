Power Control Example
=====================

This example demonstrates how to control device power using both VeSync smart outlets and CyberPower PDUs. Power control is fundamental for device testing - you'll use it to boot devices, trigger resets, and safely power down hardware.

VeSync Smart Outlet Control
----------------------------

VeSync provides cloud-connected smart outlets that can be controlled remotely. This example shows how to use them with labgrid.

**What You'll Need**:

- VeSync account with one or more smart outlets
- VeSync outlet name (configured in your VeSync account)
- Account credentials (email and password)

**Configuration File** (target.yaml):

.. code-block:: yaml

    targets:
      my_fpga_board:
        resources:
          VesyncOutlet:
            outlet_names: 'FPGA Board Power'  # Name of outlet in VeSync app
            username: 'your_email@example.com'
            password: 'your_password'
            delay: 5.0  # Seconds to wait between off and on during cycle

        drivers:
          VesyncPowerDriver: {}

**Basic Usage Script**:

.. code-block:: python

    from labgrid import Environment

    # Load target configuration
    env = Environment("target.yaml")
    target = env.get_target("my_fpga_board")

    # Get the power driver
    power = target.get_driver("VesyncPowerDriver")

    # Activate the driver
    target.activate(power)

    # Turn on the device
    print("Powering on device...")
    power.on()

    # Do some work with the device...
    # (run tests, interact with serial console, etc.)

    # Power off the device
    print("Powering off device...")
    power.off()

    # Deactivate the driver
    target.deactivate(power)

**Power Cycle Operation** (reset device):

.. code-block:: python

    from labgrid import Environment
    import time

    env = Environment("target.yaml")
    target = env.get_target("my_fpga_board")
    power = target.get_driver("VesyncPowerDriver")
    target.activate(power)

    # Power cycle: off -> wait -> on
    print("Performing power cycle (reset)...")
    power.cycle()  # Automatically handles delay configured in resource

    # Wait for device to fully boot
    time.sleep(10)

    print("Device reset complete")
    target.deactivate(power)

**Multiple Outlets**:

VeSync supports controlling multiple outlets from a single driver:

.. code-block:: yaml

    targets:
      test_rack:
        resources:
          VesyncOutlet:
            outlet_names: 'Board A,Board B,Board C'  # Comma-separated outlet names
            username: 'your_email@example.com'
            password: 'your_password'
            delay: 5.0

        drivers:
          VesyncPowerDriver: {}

.. code-block:: python

    from labgrid import Environment

    env = Environment("target.yaml")
    target = env.get_target("test_rack")
    power = target.get_driver("VesyncPowerDriver")
    target.activate(power)

    # All configured outlets are controlled together
    print("Powering on all outlets...")
    power.on()   # Powers on: Board A, Board B, Board C

    print("Powering off all outlets...")
    power.off()  # Powers off: Board A, Board B, Board C

    target.deactivate(power)

CyberPower PDU Control
----------------------

CyberPower PDUs provide industrial-grade power distribution with SNMP control. This is more reliable than cloud-connected outlets for critical testing environments.

**What You'll Need**:

- CyberPower PDU (tested on PDU15SWHVIEC8FNET and similar)
- PDU hostname/IP address
- SNMP community string (default is typically "public")
- Outlet number (usually 1-8)

**Configuration File** (target.yaml):

.. code-block:: yaml

    targets:
      lab_device:
        resources:
          CyberPowerOutlet:
            hostname: '192.168.1.100'
            outlet_number: 1  # Outlet 1-8
            snmp_version: '2c'
            community: 'public'

        drivers:
          CyberPowerDriver: {}

**Basic Usage Script**:

.. code-block:: python

    from labgrid import Environment

    # Load target configuration
    env = Environment("target.yaml")
    target = env.get_target("lab_device")

    # Get the power driver
    power = target.get_driver("CyberPowerDriver")

    # Activate the driver
    target.activate(power)

    # Turn on the outlet
    print("Powering on via CyberPower PDU outlet 1...")
    power.on()

    # Work with device...

    # Power off
    print("Powering off...")
    power.off()

    target.deactivate(power)

**Multi-Outlet Control**:

.. code-block:: yaml

    targets:
      multi_outlet_system:
        resources:
          CyberPowerOutlet:
            hostname: '192.168.1.100'
            outlet_number: 1  # Can create multiple resources for different outlets
            snmp_version: '2c'
            community: 'public'

          CyberPowerOutlet@board_b_power:
            hostname: '192.168.1.100'
            outlet_number: 2
            snmp_version: '2c'
            community: 'public'

        drivers:
          CyberPowerDriver: {}
          CyberPowerDriver@board_b:
            cyberpoweroutlet: CyberPowerOutlet@board_b_power

.. code-block:: python

    from labgrid import Environment

    env = Environment("target.yaml")
    target = env.get_target("multi_outlet_system")

    # Get drivers for each outlet
    power_a = target.get_driver("CyberPowerDriver")
    power_b = target.get_driver("CyberPowerDriver@board_b")

    target.activate(power_a)
    target.activate(power_b)

    # Control outlets independently
    print("Powering on board A...")
    power_a.on()

    print("Powering on board B...")
    power_b.on()

    # Later...
    print("Powering off board A...")
    power_a.off()

    target.deactivate(power_a)
    target.deactivate(power_b)

Error Handling Patterns
-----------------------

**Graceful Power Management with Error Recovery**:

.. code-block:: python

    from labgrid import Environment
    import time

    def safe_power_control(target, outlet_name, command, retries=3):
        """Safely control power with error handling and retries."""
        for attempt in range(retries):
            try:
                power = target.get_driver("VesyncPowerDriver")
                target.activate(power)

                if command == "on":
                    power.on()
                elif command == "off":
                    power.off()
                elif command == "cycle":
                    power.cycle()

                target.deactivate(power)
                print(f"Power {command} successful for {outlet_name}")
                return True

            except Exception as e:
                print(f"Power control failed (attempt {attempt+1}/{retries}): {e}")
                time.sleep(5)  # Wait before retry

        print(f"Failed to power {command} {outlet_name} after {retries} attempts")
        return False

    # Usage
    env = Environment("target.yaml")
    target = env.get_target("my_fpga_board")
    safe_power_control(target, "my_fpga_board", "cycle")

**Power Down with Validation**:

.. code-block:: python

    from labgrid import Environment
    import time

    def ensure_powered_off(target, timeout=30):
        """Ensure device is powered off with validation."""
        power = target.get_driver("VesyncPowerDriver")
        target.activate(power)

        try:
            # Try graceful shutdown first
            shell = target.get_driver("ADIShellDriver")
            if target.get(shell):
                try:
                    shell.sendline("poweroff")
                    time.sleep(5)
                except:
                    pass

            # Force power off if needed
            power.off()
            time.sleep(2)

            print("Device powered off successfully")

        except Exception as e:
            print(f"Error powering off: {e}")
        finally:
            target.deactivate(power)

**Monitoring Power State During Test**:

.. code-block:: python

    from labgrid import Environment
    import time

    def run_test_with_power_monitoring(target, test_func, timeout=300):
        """Run test with periodic power state checks."""
        power = target.get_driver("VesyncPowerDriver")
        target.activate(power)

        start_time = time.time()
        try:
            # Run test function
            test_func()

        except Exception as e:
            print(f"Test failed: {e}")
            # Power cycle on test failure
            print("Performing emergency power cycle...")
            power.cycle()
            raise

        finally:
            elapsed = time.time() - start_time
            print(f"Test completed in {elapsed:.1f} seconds")
            target.deactivate(power)

Integration with Boot Strategies
---------------------------------

Power control is usually managed automatically by boot strategies, but you can also use it directly:

**Manual Power Control Before Strategy**:

.. code-block:: python

    from labgrid import Environment
    from adi_lg_plugins.strategies.bootfpgasoc import Status

    env = Environment("target.yaml")
    target = env.get_target("my_device")

    # Ensure device is powered off before boot
    power = target.get_driver("VesyncPowerDriver")
    target.activate(power)
    power.off()
    target.deactivate(power)

    # Now use strategy to boot (which handles power on)
    strategy = target.get_strategy("BootFPGASoC")
    strategy.transition("shell")

    # Device now booted and at shell
    shell = target.get_driver("ADIShellDriver")
    shell.run_command("uname -a")

    # Cleanup - strategy handles power down
    strategy.transition("soft_off")

**Power Cycling Between Tests**:

.. code-block:: python

    from labgrid import Environment
    import time

    env = Environment("target.yaml")
    target = env.get_target("my_device")
    power = target.get_driver("VesyncPowerDriver")
    strategy = target.get_strategy("BootFPGASoC")

    def run_test_cycle(test_number):
        """Run a single test cycle with power management."""
        print(f"\nTest cycle {test_number}")

        # Ensure clean start with power cycle
        target.activate(power)
        power.cycle()
        target.deactivate(power)

        time.sleep(5)

        # Boot device
        strategy.transition("shell")

        # Run tests
        shell = target.get_driver("ADIShellDriver")
        result = shell.run_command("./test_suite.sh")
        print(f"Test result: {result}")

        # Clean shutdown
        strategy.transition("soft_off")

        return "PASS" in result

    # Run multiple test cycles
    for cycle in range(5):
        try:
            success = run_test_cycle(cycle + 1)
            print(f"Cycle {cycle+1}: {'PASSED' if success else 'FAILED'}")
        except Exception as e:
            print(f"Cycle {cycle+1}: ERROR - {e}")
            # Ensure power is off on error
            try:
                target.get_driver("VesyncPowerDriver").off()
            except:
                pass

Complete Working Example
------------------------

**target.yaml**:

.. code-block:: yaml

    targets:
      test_device:
        resources:
          VesyncOutlet:
            outlet_names: 'Test Device'
            username: 'your_email@example.com'
            password: 'your_password'
            delay: 5.0

          SerialPort:
            port: '/dev/ttyUSB0'
            baudrate: 115200

        drivers:
          VesyncPowerDriver: {}
          ADIShellDriver:
            console: SerialPort
            prompt: 'root@.*:.*#'
            login_prompt: 'login:'
            username: 'root'
            password: 'analog'
            login_timeout: 60

**test_power_control.py**:

.. code-block:: python

    from labgrid import Environment
    import time

    def test_power_on_off():
        """Test basic power on/off operations."""
        env = Environment("target.yaml")
        target = env.get_target("test_device")
        power = target.get_driver("VesyncPowerDriver")

        # Test power on
        print("Test 1: Power on")
        target.activate(power)
        power.on()
        time.sleep(2)
        assert power is not None  # Device should be on
        print("  PASSED")

        # Test power off
        print("Test 2: Power off")
        power.off()
        time.sleep(2)
        assert power is not None  # Device should be off
        print("  PASSED")

        target.deactivate(power)

    def test_power_cycle():
        """Test power cycle (reset) operation."""
        env = Environment("target.yaml")
        target = env.get_target("test_device")
        power = target.get_driver("VesyncPowerDriver")

        print("Test 3: Power cycle")
        target.activate(power)

        # Perform cycle
        power.cycle()
        time.sleep(15)  # Wait for device to boot

        # Check device is booted
        shell = target.get_driver("ADIShellDriver")
        target.activate(shell)

        output = shell.run_command("uname -a")
        assert len(output) > 0
        print("  Device booted after cycle")
        print("  PASSED")

        target.deactivate(shell)
        target.deactivate(power)

    if __name__ == "__main__":
        test_power_on_off()
        test_power_cycle()
        print("\nAll tests passed!")

Troubleshooting
---------------

**VeSync Login Fails**:

.. code-block:: text

    Error: Failed to login to VeSync account

    Solutions:
    - Verify email and password are correct
    - Check that account is not locked (too many login attempts)
    - Ensure outlet is visible in VeSync app
    - Verify outlet name matches exactly (case-sensitive)

**CyberPower PDU Connection Failed**:

.. code-block:: text

    Error: SNMP connection to PDU failed

    Solutions:
    - Verify PDU hostname/IP is reachable: ping 192.168.1.100
    - Confirm SNMP is enabled on PDU
    - Check community string (usually "public")
    - Verify outlet number (typically 1-8)
    - Check firewall allows SNMP (UDP port 161)

**Power Command Times Out**:

.. code-block:: text

    Error: Power command did not complete in time

    Solutions:
    - Check network connectivity
    - Verify VeSync/PDU is accessible
    - Try cycling power manually to verify hardware works
    - Increase timeout in configuration

See Also
--------

- :doc:`../../user-guide/examples` - Common use cases and patterns
- :doc:`../../api/drivers` - Driver API reference
- :doc:`../../api/resources` - Resource configuration reference
- :doc:`shell-commands` - Shell command execution examples
- :doc:`../advanced/full-boot-cycle` - Complete boot workflow
