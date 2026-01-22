Using Drivers
=============

Drivers provide low-level hardware control and protocol implementations. They bind to resources
and expose protocols that can be used by strategies or tests.

Overview
--------

Drivers in adi-labgrid-plugins:

- Control hardware devices via serial, network, or USB interfaces
- Implement standardized protocols for interoperability (PowerProtocol, CommandProtocol, etc.)
- Are activated/deactivated explicitly by strategies or tests
- Provide high-level methods abstracting hardware complexity

The plugin provides six drivers for different hardware control scenarios:

- **Power Drivers**: Control device power via smart outlets and PDUs
- **Shell Driver**: Execute commands and transfer files via serial console or SSH
- **Storage Drivers**: Mount and manage SD card filesystems
- **Kuiper Driver**: Download and extract ADI Kuiper Linux releases

Driver Lifecycle
----------------

Drivers follow an explicit activation pattern:

.. code-block:: python

    # Get driver reference from target
    driver = target.get_driver("DriverName")

    # Activate driver (calls on_activate(), initializes connections)
    target.activate(driver)

    # Use driver methods
    driver.method()

    # Deactivate when done (calls on_deactivate(), closes connections)
    target.deactivate(driver)

Or within a strategy context (automatic activation):

.. code-block:: python

    # Strategies handle activation/deactivation automatically
    strategy = target.get_driver("BootFPGASoC")
    strategy.transition("shell")

Power Control Drivers
---------------------

VesyncPowerDriver
~~~~~~~~~~~~~~~~~

**Purpose**: Control devices via VeSync smart outlets (WiFi-based network power switches)

**Required Resource**: VesyncOutlet

**Bindings**: Implements ``PowerProtocol`` and ``PowerResetMixin``

**Configuration**

.. code-block:: yaml

    targets:
      test_device:
        resources:
          VesyncOutlet:
            outlet_names: 'My Test Device,Lab Bench Power'
            username: 'your_email@example.com'
            password: 'your_password'
            delay: 5.0  # Seconds to wait between off/on during cycle

        drivers:
          VesyncPowerDriver: {}

**Key Parameters**

- **outlet_names** (required): Comma-separated list of outlet device names as they appear in VeSync mobile app
- **username** (required): VeSync account email address
- **password** (required): VeSync account password
- **delay** (default=5.0): Delay in seconds between power off and on during reset/cycle

**Methods**

.. code-block:: python

    power = target.get_driver("VesyncPowerDriver")
    target.activate(power)

    # Basic control
    power.on()              # Turn on all configured outlets
    power.off()             # Turn off all outlets
    power.cycle()           # Power cycle: off → wait → on (uses delay parameter)
    power.reset()           # Same as cycle()

    # Query state
    is_on = power.get()     # Returns True if all outlets are on

**Usage Examples**

Simple power cycling:

.. code-block:: python

    power = target.get_driver("VesyncPowerDriver")
    target.activate(power)

    power.off()
    time.sleep(2)
    power.on()

    target.deactivate(power)

Multiple outlets:

.. code-block:: python

    # This config powers three devices together
    # outlets: 'Device 1,Device 2,Device 3'

    power.on()   # All three outlets turn on
    power.off()  # All three outlets turn off

**Troubleshooting**

- **"Outlet not found"**: Verify outlet names match exactly what appears in VeSync app (case-sensitive)
- **"Failed to login"**: Check VeSync credentials are correct
- **"No outlets found"**: Ensure outlets are added to VeSync account via mobile app first

**Notes**

- Requires internet connection and VeSync account
- Outlets must be preconfigured in VeSync mobile application
- Supports multiple outlets controlled simultaneously
- Delay should be tuned based on device power-up requirements

CyberPowerDriver
~~~~~~~~~~~~~~~~

**Purpose**: Control devices via CyberPower PDU using SNMP protocol

**Required Resource**: CyberPowerOutlet

**Bindings**: Implements ``PowerProtocol`` and ``PowerResetMixin``

**Configuration**

.. code-block:: yaml

    targets:
      lab_device:
        resources:
          CyberPowerOutlet:
            address: '192.168.1.100'    # PDU IP address or hostname
            outlet: 3                    # Outlet number (1-8 for most models)
            delay: 3.0                   # Seconds between off/on

        drivers:
          CyberPowerDriver: {}

**Key Parameters**

- **address** (required): IP address or hostname of the PDU
- **outlet** (required): Outlet number to control (typically 1-8, check your PDU model)
- **delay** (default=5.0): Delay in seconds for power cycling

**Methods**

.. code-block:: python

    power = target.get_driver("CyberPowerDriver")
    target.activate(power)

    power.on()      # Turn on outlet
    power.off()     # Turn off outlet
    power.cycle()   # Power cycle
    power.reset()   # Same as cycle()

**Usage Example**

.. code-block:: python

    power = target.get_driver("CyberPowerDriver")
    target.activate(power)

    print("Powering off device...")
    power.off()
    time.sleep(1)

    print("Powering on device...")
    power.on()
    time.sleep(5)  # Wait for device to boot

    target.deactivate(power)

**Supported Models**

- PDU15SWHVIEC8FNET
- Other CyberPower PDUs with SNMP support (may need adjustments)

**Implementation Notes**

- Uses SNMP "private" community string
- Compatible with both pysnmp < 7.0.0 (async) and >= 7.0.0 (sync) APIs
- Automatically detects and uses appropriate API version
- Requires network access to PDU IP address

**Troubleshooting**

- **Timeout/No response**: Check network connectivity to PDU, verify IP address
- **Access denied**: Confirm SNMP community string is "private" (standard for CyberPower)
- **Outlet out of range**: Verify outlet number (typically 1-8, check your PDU documentation)

Shell and File Transfer Driver
------------------------------

ADIShellDriver
~~~~~~~~~~~~~~

**Purpose**: Execute commands and transfer files on target device via serial console with optional SSH

**Bindings**: Implements ``CommandProtocol``, ``ConsoleProtocol``, ``FileTransferProtocol``

**Configuration**

.. code-block:: yaml

    drivers:
      ADIShellDriver:
        prompt: 'root@analog:.*#'              # Regex matching shell prompt
        login_prompt: 'login:'                 # Regex matching login prompt
        username: 'root'                       # Login username
        password: 'analog'                     # Login password
        login_timeout: 60                      # Seconds to wait for login
        console_ready: 'Press ENTER'           # Optional: marker before login
        await_login_timeout: 5                 # Seconds to detect login requirement
        keyfile: 'keys/id_rsa.pub'             # Optional: SSH key to inject

**Key Parameters**

- **prompt** (required): Regex pattern matching the shell prompt after login
- **login_prompt** (required): Regex pattern matching login prompt
- **username** (required): Login username
- **password** (required): Login password
- **login_timeout** (required): Maximum seconds to wait for login completion
- **console_ready** (optional): Marker string to wait for before attempting login
- **keyfile** (optional): Path to SSH public key to inject into device

**Methods**

.. code-block:: python

    shell = target.get_driver("ADIShellDriver")
    target.activate(shell)

    # Command execution
    output = shell.run("uname -a")                  # Execute command, return output
    shell.run("mkdir -p /tmp/test")                 # Command without capture

    # File transfer via XMODEM (binary safe)
    shell.put("/local/file.bin", "/tmp/file.bin")  # Upload to device
    shell.get("/tmp/output.log", "/local/log.txt")  # Download from device

    # Advanced
    shell.put_bytes(binary_data, "/tmp/data.bin")  # Upload binary data
    data = shell.get_bytes("/tmp/data.bin")        # Download as binary

    # Query device networking
    ips = shell.get_ip_addresses()                 # Returns dict of interfaces

    # Deactivate
    target.deactivate(shell)

**Usage Examples**

Basic command execution:

.. code-block:: python

    shell = target.get_driver("ADIShellDriver")
    target.activate(shell)

    # Get kernel version
    kernel = shell.run("uname -r").strip()
    print(f"Kernel: {kernel}")

    # List IIO devices
    iio_devices = shell.run("iio_info -s")
    print(f"IIO Devices:\n{iio_devices}")

    target.deactivate(shell)

File upload and execution:

.. code-block:: python

    # Upload script
    shell.put("/local/test_script.sh", "/tmp/test.sh")
    shell.run("chmod +x /tmp/test.sh")

    # Run script and capture output
    result = shell.run("/tmp/test.sh")
    print(result)

SSH key injection for passwordless access:

.. code-block:: yaml

    # Config with SSH key
    drivers:
      ADIShellDriver:
        prompt: 'root@.*#'
        login_prompt: 'login:'
        username: 'root'
        password: 'analog'
        keyfile: 'keys/id_rsa.pub'    # Public key to inject

.. code-block:: bash

    # After driver activation with keyfile configured:
    # 1. Logs in with password
    # 2. Creates /root/.ssh directory
    # 3. Copies your public key to /root/.ssh/authorized_keys
    # 4. Sets correct permissions (700, 600)

    # Afterwards, SSH access works without password
    ssh root@device

**Features**

- Automatic login handling with regex prompt matching
- XMODEM binary-safe file transfer protocol
- SSH public key injection for passwordless access
- Command execution with output capture
- IP address detection for network interfaces
- Console ready detection for handling boot prompts

**Troubleshooting**

- **Timeout during login**: Increase ``login_timeout``, check serial connection
- **Wrong prompt regex**: Test regex against actual device prompt
- **File transfer hangs**: Ensure XMODEM support on device
- **SSH key injection fails**: Check file permissions and SSH directory

**Notes**

- Requires active serial console connection
- Uses XMODEM for file transfer (add binary protocol support if needed)
- Regex patterns are Python regex, test with actual device output
- Login is automatic on driver activation

Storage Management Drivers
--------------------------

MassStorageDriver
~~~~~~~~~~~~~~~~~

**Purpose**: Mount USB mass storage devices and manage file updates (typically SD cards via USB mux)

**Required Resource**: MassStorageDevice

**Configuration**

.. code-block:: yaml

    resources:
      MassStorageDevice:
        device: '/dev/sdb'              # Block device path
        partition: 1                     # Partition number to mount

    drivers:
      MassStorageDriver: {}

**Key Parameters**

- **device** (required): Block device path (e.g., /dev/sdb, /dev/sdc)
- **partition** (required): Partition number to mount (typically 1 for boot partition)

**Methods**

.. code-block:: python

    storage = target.get_driver("MassStorageDriver")
    target.activate(storage)

    # Mount/unmount
    storage.mount_partition()              # Mount the configured partition
    storage.unmount_partition()            # Unmount partition

    # File operations
    storage.copy_file("/local/BOOT.BIN", "/BOOT/")  # Copy to device
    storage.update_files({
        "/local/BOOT.BIN": "/BOOT.BIN",
        "/local/image.ub": "/image.ub"
    })                                      # Copy multiple files

    target.deactivate(storage)

**Usage Example**

Updating boot files on SD card:

.. code-block:: python

    # Typically used with USBSDMuxDriver to switch SD to host
    storage = target.get_driver("MassStorageDriver")
    target.activate(storage)

    # Mount SD card partition
    storage.mount_partition()

    # Copy boot files
    storage.copy_file("/local/BOOT.BIN", "/BOOT.BIN")
    storage.copy_file("/local/image.ub", "/image.ub")

    # Unmount before switching back to device
    storage.unmount_partition()

    target.deactivate(storage)

**Common Workflow**

Typically used within BootFPGASoC strategy:

.. code-block:: python

    strategy = target.get_driver("BootFPGASoC")

    # Strategy handles SD mux switching
    strategy.transition("sd_mux_to_host")

    # Now storage driver is activated, can mount and copy files
    storage = target.get_driver("MassStorageDriver")
    storage.mount_partition()
    storage.copy_file("/new/BOOT.BIN", "/BOOT.BIN")
    storage.unmount_partition()

    # Switch back and boot
    strategy.transition("sd_mux_to_dut")
    strategy.transition("booted")

**Important Notes**

- Requires USB SD card mux (usually USBSDMuxDriver) to switch card between host and device
- Device path may change based on USB enumeration order
- Consider using udev rules for stable device names
- Partition number depends on SD card layout (typically 1 for first partition)

**Troubleshooting**

- **Device not found**: Verify device path with ``lsblk``, may need to use different /dev entry
- **Permission denied**: Usually requires sudo or running as root
- **Mount fails**: Check if partition is already mounted elsewhere

Kuiper Linux Driver
-------------------

KuiperDLDriver
~~~~~~~~~~~~~~

**Purpose**: Download ADI Kuiper Linux releases and extract boot files from disk images

**Required Resource**: KuiperRelease

**Configuration**

.. code-block:: yaml

    resources:
      KuiperRelease:
        release: '2023_R2_P1'               # Release version
        cache_dir: '/var/cache/kuiper'    # Download cache directory

    drivers:
      KuiperDLDriver: {}

**Key Parameters**

- **release** (required): Release version identifier
- **cache_dir** (required): Directory for caching downloaded files

**Supported Releases**

- '2018_R2'
- '2019_R1'
- '2023_R2_P1'

**Methods**

.. code-block:: python

    kuiper = target.get_driver("KuiperDLDriver")
    target.activate(kuiper)

    # Download and extract boot files
    files = kuiper.get_boot_files_from_release()

    # Files returned: list of paths to extracted boot files
    # Typically: ['/path/to/BOOT.BIN', '/path/to/image.ub', ...]

    # Access boot files directly
    boot_bin = kuiper._boot_files.get('BOOT.BIN')

    target.deactivate(kuiper)

**Usage Example**

Downloading Kuiper release:

.. code-block:: python

    kuiper = target.get_driver("KuiperDLDriver")
    target.activate(kuiper)

    print("Downloading Kuiper release...")
    boot_files = kuiper.get_boot_files_from_release()

    print("Boot files available:")
    for file in boot_files:
        print(f"  - {file}")

    # Use with MassStorageDriver to copy files
    storage = target.get_driver("MassStorageDriver")
    target.activate(storage)
    storage.mount_partition()

    for boot_file in boot_files:
        filename = os.path.basename(boot_file)
        storage.copy_file(boot_file, f"/{filename}")

    storage.unmount_partition()
    target.deactivate(storage)
    target.deactivate(kuiper)

**Features**

- Automatic download with progress reporting (via tqdm)
- MD5 checksum verification
- Automatic extraction of .xz and .zip archives
- File extraction from disk image without mounting (via pytsk3)
- Caching to avoid re-downloading
- Supports multiple Kuiper releases

**Implementation Details**

- Extracts files from .img disk images without requiring mount (uses pytsk3 forensic toolkit)
- Caches downloaded releases locally to avoid re-downloading
- Verifies checksums against ADI provided values
- Automatically handles .xz or .zip compression

**Troubleshooting**

- **Download failed**: Check network connectivity and storage space in cache_dir
- **Checksum mismatch**: Download may be corrupted, try clearing cache and re-downloading
- **Extraction fails**: Ensure pytsk3 is installed with filesystem support

**Notes**

- First run downloads the full release (can be large, 100+MB)
- Subsequent runs use cached version (fast)
- Boot files extracted to cache_dir automatically
- Used by BootFPGASoC strategy for automatic Kuiper boot

See Also
--------

- :doc:`../api/drivers` - Complete driver API reference
- :doc:`resources` - Resource configuration guide
- :doc:`strategies` - Strategy usage guide
- :doc:`../getting-started/quickstart` - Quick start examples
