Shell Commands Example
======================

This guide demonstrates how to execute shell commands on target devices, transfer files using XMODEM, and manage interactive shell sessions. The ADIShellDriver provides these capabilities over serial console or SSH connections.

Basic Command Execution
-----------------------

Execute simple commands and capture output:

**Configuration**:

.. code-block:: yaml

    targets:
      device_under_test:
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

**Basic Usage**:

.. code-block:: python

    from labgrid import Environment

    env = Environment("target.yaml")
    target = env.get_target("device_under_test")
    shell = target.get_driver("ADIShellDriver")

    # Activate the shell driver (handles login)
    target.activate(shell)

    # Run simple command and get output
    output = shell.run_command("uname -a")
    print(output)

    # Run command and capture result
    hostname = shell.run_command("hostname").strip()
    print(f"Device hostname: {hostname}")

    # Get kernel version
    kernel_version = shell.run_command("uname -r").strip()
    print(f"Kernel: {kernel_version}")

    target.deactivate(shell)

**Multiple Commands**:

.. code-block:: python

    from labgrid import Environment

    env = Environment("target.yaml")
    target = env.get_target("device_under_test")
    shell = target.get_driver("ADIShellDriver")
    target.activate(shell)

    # Run sequence of commands
    commands = [
        "pwd",
        "ls -la",
        "cat /proc/cpuinfo",
        "df -h",
    ]

    for cmd in commands:
        print(f"\n$ {cmd}")
        output = shell.run_command(cmd)
        print(output)

    target.deactivate(shell)

File Transfer with XMODEM
-------------------------

XMODEM is a reliable file transfer protocol that works over serial connections without requiring network access. The ADIShellDriver supports both sending (upload) and receiving (download) files.

**Upload File to Device**:

.. code-block:: python

    from labgrid import Environment

    env = Environment("target.yaml")
    target = env.get_target("device_under_test")
    shell = target.get_driver("ADIShellDriver")
    target.activate(shell)

    # Upload a binary file to the device
    shell.send_xmodem(
        local_path="/path/to/local/firmware.bin",
        remote_path="/tmp/firmware.bin"
    )

    # Verify file was transferred
    output = shell.run_command("ls -la /tmp/firmware.bin")
    print(f"File transferred: {output}")

    target.deactivate(shell)

**Download File from Device**:

.. code-block:: python

    from labgrid import Environment

    env = Environment("target.yaml")
    target = env.get_target("device_under_test")
    shell = target.get_driver("ADIShellDriver")
    target.activate(shell)

    # Download a file from the device
    shell.recv_xmodem(
        remote_path="/tmp/test_output.dat",
        local_path="/path/to/local/test_output.dat"
    )

    print("File downloaded successfully")

    target.deactivate(shell)

**Complete File Transfer Workflow**:

.. code-block:: python

    from labgrid import Environment
    import os

    env = Environment("target.yaml")
    target = env.get_target("device_under_test")
    shell = target.get_driver("ADIShellDriver")
    target.activate(shell)

    # Prepare test
    test_file = "/path/to/test_script.sh"
    remote_dir = "/tmp"

    # Upload test script
    print("Uploading test script...")
    shell.send_xmodem(test_file, f"{remote_dir}/test_script.sh")

    # Make script executable
    shell.run_command("chmod +x /tmp/test_script.sh")

    # Run the test script
    print("Running test script...")
    output = shell.run_command("cd /tmp && ./test_script.sh")
    print(output)

    # Download results
    print("Downloading results...")
    shell.recv_xmodem(
        f"{remote_dir}/test_results.txt",
        "/path/to/local/test_results.txt"
    )

    target.deactivate(shell)
    print("Test workflow complete")

Multi-line Commands
-------------------

Execute commands that span multiple lines or have complex shell syntax:

**Shell Pipes and Redirects**:

.. code-block:: python

    from labgrid import Environment

    env = Environment("target.yaml")
    target = env.get_target("device_under_test")
    shell = target.get_driver("ADIShellDriver")
    target.activate(shell)

    # Command with pipes
    output = shell.run_command("ps aux | grep -i python")
    print("Python processes:")
    print(output)

    # Command with redirection
    shell.run_command("dmesg > /tmp/kernel_log.txt")
    log = shell.run_command("cat /tmp/kernel_log.txt")
    print("Kernel log:")
    print(log)

    target.deactivate(shell)

**Shell Scripts**:

.. code-block:: python

    from labgrid import Environment

    env = Environment("target.yaml")
    target = env.get_target("device_under_test")
    shell = target.get_driver("ADIShellDriver")
    target.activate(shell)

    # Create and execute inline script
    script = """
    for i in 1 2 3 4 5; do
        echo "Iteration $i"
        sleep 1
    done
    echo "Script complete"
    """

    # Write script to file
    shell.run_command("cat > /tmp/loop_script.sh << 'EOF'\n" + script + "\nEOF")

    # Execute script
    output = shell.run_command("bash /tmp/loop_script.sh")
    print(output)

    target.deactivate(shell)

**Conditional Execution**:

.. code-block:: python

    from labgrid import Environment

    env = Environment("target.yaml")
    target = env.get_target("device_under_test")
    shell = target.get_driver("ADIShellDriver")
    target.activate(shell)

    # Check if device has network
    output = shell.run_command("ip link show eth0 || echo 'No ethernet'")
    print(output)

    # Conditional execution with && and ||
    shell.run_command("mkdir -p /tmp/test && cd /tmp/test && pwd")

    # Chain commands with error handling
    result = shell.run_command(
        "test -f /sys/class/iio/iio:device0/name && "
        "cat /sys/class/iio/iio:device0/name || echo 'IIO device not found'"
    )
    print(f"IIO device: {result}")

    target.deactivate(shell)

SSH Key Injection Workflow
---------------------------

Enable passwordless SSH access by injecting SSH keys into the device:

**Configuration with Key File**:

.. code-block:: yaml

    targets:
      ssh_enabled_device:
        resources:
          SerialPort:
            port: '/dev/ttyUSB0'
            baudrate: 115200

          SSHKey:
            keyfile: '~/.ssh/id_rsa.pub'

        drivers:
          ADIShellDriver:
            console: SerialPort
            keyfile: '~/.ssh/id_rsa.pub'  # Inject this key on login
            prompt: 'root@.*:.*#'
            login_prompt: 'login:'
            username: 'root'
            password: 'analog'

**Workflow**:

.. code-block:: python

    from labgrid import Environment

    env = Environment("target.yaml")
    target = env.get_target("ssh_enabled_device")
    shell = target.get_driver("ADIShellDriver")

    # Activate shell driver
    # If keyfile is configured, it's automatically injected during login
    target.activate(shell)

    # Verify SSH key is present
    output = shell.run_command("cat ~/.ssh/authorized_keys | head -1")
    print(f"SSH key installed: {len(output) > 0}")

    # Now you can use SSH driver for file transfer without passwords
    target.deactivate(shell)

**Manual Key Injection**:

.. code-block:: python

    from labgrid import Environment
    import os

    env = Environment("target.yaml")
    target = env.get_target("device_under_test")
    shell = target.get_driver("ADIShellDriver")
    target.activate(shell)

    # Create .ssh directory
    shell.run_command("mkdir -p ~/.ssh")
    shell.run_command("chmod 700 ~/.ssh")

    # Copy your public key to authorized_keys
    pub_key_path = os.path.expanduser("~/.ssh/id_rsa.pub")
    with open(pub_key_path, 'r') as f:
        pub_key = f.read().strip()

    # Add key to authorized_keys
    shell.run_command(f"echo '{pub_key}' >> ~/.ssh/authorized_keys")
    shell.run_command("chmod 600 ~/.ssh/authorized_keys")

    # Verify
    output = shell.run_command("cat ~/.ssh/authorized_keys | wc -l")
    print(f"Number of authorized keys: {output}")

    target.deactivate(shell)

Practical Examples
------------------

**System Information Gathering**:

.. code-block:: python

    from labgrid import Environment

    def gather_system_info(target):
        """Gather comprehensive device information."""
        shell = target.get_driver("ADIShellDriver")
        target.activate(shell)

        info = {}

        # Basic system info
        info['hostname'] = shell.run_command("hostname").strip()
        info['kernel'] = shell.run_command("uname -r").strip()
        info['uptime'] = shell.run_command("uptime").strip()

        # CPU info
        info['cpu_count'] = shell.run_command("nproc").strip()
        info['cpu_model'] = shell.run_command(
            "cat /proc/cpuinfo | grep 'model name' | head -1"
        ).strip()

        # Memory info
        info['memory'] = shell.run_command(
            "free -h | grep Mem"
        ).strip()

        # Disk space
        info['disk'] = shell.run_command("df -h /").strip()

        # Network interfaces
        info['interfaces'] = shell.run_command("ip link show").strip()

        target.deactivate(shell)
        return info

    env = Environment("target.yaml")
    target = env.get_target("device_under_test")
    info = gather_system_info(target)

    print("System Information:")
    for key, value in info.items():
        print(f"  {key}: {value}")

**IIO Device Testing**:

.. code-block:: python

    from labgrid import Environment

    def test_iio_devices(target):
        """Test IIO (Industrial I/O) subsystem."""
        shell = target.get_driver("ADIShellDriver")
        target.activate(shell)

        # List IIO devices
        output = shell.run_command("ls /sys/bus/iio/devices/")
        print("IIO devices found:")
        print(output)

        # Get device details
        devices = shell.run_command(
            "ls /sys/bus/iio/devices/ | grep iio:device"
        ).strip().split('\n')

        for device in devices:
            name = shell.run_command(
                f"cat /sys/bus/iio/devices/{device}/name"
            ).strip()
            channels = shell.run_command(
                f"ls /sys/bus/iio/devices/{device}/in_* | wc -l"
            ).strip()
            print(f"  {device}: {name} ({channels} channels)")

        # Read ADC sample
        sample = shell.run_command(
            "cat /sys/bus/iio/devices/iio:device0/in_voltage0_raw"
        ).strip()
        print(f"ADC Sample: {sample}")

        target.deactivate(shell)

    env = Environment("target.yaml")
    target = env.get_target("device_under_test")
    test_iio_devices(target)

**Sensor Data Logging**:

.. code-block:: python

    from labgrid import Environment
    import time

    def log_sensor_data(target, duration=60, interval=5):
        """Log sensor data over time."""
        shell = target.get_driver("ADIShellDriver")
        target.activate(shell)

        start_time = time.time()
        readings = []

        while time.time() - start_time < duration:
            # Read ADC values
            ch0 = shell.run_command(
                "cat /sys/bus/iio/devices/iio:device0/in_voltage0_raw"
            ).strip()
            ch1 = shell.run_command(
                "cat /sys/bus/iio/devices/iio:device0/in_voltage1_raw"
            ).strip()

            timestamp = time.time() - start_time
            readings.append({
                'time': timestamp,
                'ch0': int(ch0),
                'ch1': int(ch1),
            })

            print(f"[{timestamp:.1f}s] CH0={ch0}, CH1={ch1}")

            time.sleep(interval)

        target.deactivate(shell)
        return readings

    env = Environment("target.yaml")
    target = env.get_target("device_under_test")
    data = log_sensor_data(target, duration=30, interval=5)
    print(f"\nCollected {len(data)} readings")

Error Handling Patterns
-----------------------

**Command Error Detection**:

.. code-block:: python

    from labgrid import Environment
    from labgrid.driver.exception import ExecutionError

    env = Environment("target.yaml")
    target = env.get_target("device_under_test")
    shell = target.get_driver("ADIShellDriver")
    target.activate(shell)

    # Run command that might fail
    try:
        output = shell.run_command("cat /nonexistent/file")
        print(output)
    except ExecutionError as e:
        print(f"Command failed: {e}")

    target.deactivate(shell)

**Timeout Handling**:

.. code-block:: python

    from labgrid import Environment
    from labgrid.util import Timeout

    env = Environment("target.yaml")
    target = env.get_target("device_under_test")
    shell = target.get_driver("ADIShellDriver")
    target.activate(shell)

    # Run command with custom timeout
    try:
        with Timeout(5.0, "Command timeout"):
            output = shell.run_command("sleep 2 && echo done")
            print(output)
    except Exception as e:
        print(f"Timeout: {e}")

    target.deactivate(shell)

**Retry Logic**:

.. code-block:: python

    from labgrid import Environment
    import time

    def run_command_with_retry(shell, command, retries=3, delay=1):
        """Run command with automatic retry on failure."""
        for attempt in range(retries):
            try:
                output = shell.run_command(command)
                return output
            except Exception as e:
                print(f"Attempt {attempt+1} failed: {e}")
                if attempt < retries - 1:
                    time.sleep(delay)
                else:
                    raise

    env = Environment("target.yaml")
    target = env.get_target("device_under_test")
    shell = target.get_driver("ADIShellDriver")
    target.activate(shell)

    output = run_command_with_retry(shell, "cat /proc/cpuinfo")
    print(output)

    target.deactivate(shell)

Console Access Techniques
-------------------------

**Interactive Console Session**:

.. code-block:: python

    from labgrid import Environment

    env = Environment("target.yaml")
    target = env.get_target("device_under_test")
    shell = target.get_driver("ADIShellDriver")
    target.activate(shell)

    # Send command and wait for specific output
    shell.sendline("ls -la /")
    shell.console.expect("root@.*:.*#")

    # Send command without expecting prompt
    shell.sendline("date")

    # Expect specific pattern
    shell.console.expect("20\\d{2}")  # Expect year

    target.deactivate(shell)

**Long-Running Commands**:

.. code-block:: python

    from labgrid import Environment
    import time

    env = Environment("target.yaml")
    target = env.get_target("device_under_test")
    shell = target.get_driver("ADIShellDriver")
    target.activate(shell)

    # Start long-running command
    shell.sendline("ping 8.8.8.8")

    # Wait for output
    time.sleep(5)

    # Interrupt with Ctrl-C
    shell.console.send("\x03")

    # Wait for prompt
    shell.console.expect("root@.*:.*#")

    target.deactivate(shell)

**Expect Patterns**:

.. code-block:: python

    from labgrid import Environment
    import pexpect

    env = Environment("target.yaml")
    target = env.get_target("device_under_test")
    shell = target.get_driver("ADIShellDriver")
    target.activate(shell)

    # Wait for specific strings or patterns
    shell.sendline("cat /proc/version")

    try:
        # Wait for either "Linux" or error
        index = shell.console.expect(["Linux", "Error", pexpect.TIMEOUT], timeout=5)
        if index == 0:
            print("Found Linux in output")
        elif index == 1:
            print("Found error in output")
        else:
            print("Timeout waiting for output")
    except:
        pass

    target.deactivate(shell)

Complete Working Example
------------------------

**target.yaml**:

.. code-block:: yaml

    targets:
      shell_test_device:
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

**test_shell_commands.py**:

.. code-block:: python

    from labgrid import Environment
    import time

    def test_shell_commands():
        """Test shell command execution."""
        env = Environment("target.yaml")
        target = env.get_target("shell_test_device")
        shell = target.get_driver("ADIShellDriver")

        print("1. Testing basic command execution...")
        target.activate(shell)

        hostname = shell.run_command("hostname").strip()
        assert len(hostname) > 0
        print(f"  Device hostname: {hostname}")

        print("2. Testing multiple commands...")
        for cmd in ["pwd", "whoami", "date"]:
            output = shell.run_command(cmd).strip()
            print(f"  {cmd}: {output}")

        print("3. Testing file transfer...")
        # Create test file
        test_content = "Test data from local machine"
        with open("/tmp/test_upload.txt", "w") as f:
            f.write(test_content)

        # Upload
        shell.send_xmodem("/tmp/test_upload.txt", "/tmp/test_upload.txt")

        # Verify
        downloaded = shell.run_command("cat /tmp/test_upload.txt").strip()
        assert downloaded == test_content
        print("  File transfer: PASSED")

        target.deactivate(shell)
        print("\nAll shell command tests passed!")

    if __name__ == "__main__":
        test_shell_commands()

Troubleshooting
---------------

**Command Execution Hangs**:

.. code-block:: text

    Problem: Shell doesn't return after command

    Solutions:
    - Increase login_timeout in configuration
    - Check device serial port connection
    - Verify shell prompt regex matches actual prompt
    - Try simpler commands first (echo, pwd)

**XMODEM Transfer Fails**:

.. code-block:: text

    Problem: File transfer times out or corrupts

    Solutions:
    - Check serial connection is stable
    - Reduce baudrate if necessary
    - Verify /tmp has enough space
    - Try transferring smaller file first

**Unexpected Output**:

.. code-block:: text

    Problem: Command output differs from expected

    Solutions:
    - Check for boot messages still appearing
    - Increase post_login_settle_time
    - Add post_boot_settle_time if using strategies
    - Verify shell prompt regex matches all cases

See Also
--------

- :doc:`../../user-guide/examples` - Common use cases
- :doc:`../../api/drivers` - Driver API reference
- :doc:`power-control` - Power control examples
- :doc:`../advanced/full-boot-cycle` - Full boot workflow
- Labgrid documentation: https://labgrid.readthedocs.io/
