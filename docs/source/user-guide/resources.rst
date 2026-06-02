Configuring Resources
=====================

Resources are configuration descriptors for hardware and network components. They define
what hardware is available to a target and store configuration parameters that drivers use.

Overview
--------

Resources in labgrid and adi-labgrid-plugins:

- Describe physical hardware (outlets, serial ports, USB devices, network endpoints)
- Store configuration parameters (IP addresses, credentials, device paths)
- Are defined in YAML configuration files
- Are bound to drivers which provide the actual functionality
- Contain validation logic to ensure configuration correctness

The plugin provides nine resources for different hardware scenarios:

- **VesyncOutlet** — WiFi smart outlet for power control
- **CyberPowerOutlet** — Network PDU outlet for power control
- **HomeAssistantOutlet** — Switch/outlet controlled via Home Assistant REST API
- **MassStorageDevice** — USB mass storage (typically SD card via mux)
- **KuiperRelease** — ADI Kuiper Linux release descriptor
- **CloudsmithRelease** — Cloudsmith boot-artifact descriptor (e.g. ``BOOT.BIN``)
- **TFTPServerResource** — TFTP server address/port/root configuration
- **XilinxVivadoTool** — Xilinx Vivado/Vitis install paths
- **XilinxDeviceJTAG** — Xilinx FPGA JTAG target IDs and firmware paths

Resource Definition Patterns
-----------------------------

Resource Binding
~~~~~~~~~~~~~~~~

Resources are bound to drivers via configuration:

.. code-block:: yaml

    targets:
      my_device:
        resources:
          VesyncOutlet:          # Resource type
            outlet_names: 'Lab Device 1'
            username: 'user@example.com'
            password: 'password'

        drivers:
          VesyncPowerDriver:     # Driver using the resource
            {}

The driver then accesses the resource:

.. code-block:: python

    class VesyncPowerDriver(Driver):
        bindings = {"vesync_outlet": {"VesyncOutlet"}}

        def __attrs_post_init__(self):
            # Access the bound resource
            self.pdu_dev = VeSync(
                self.vesync_outlet.username,
                self.vesync_outlet.password
            )

Resource Types and Configuration
---------------------------------

VesyncOutlet
~~~~~~~~~~~~

**Purpose**: Defines a VeSync smart outlet for power control

**Use With**: VesyncPowerDriver

**Required Parameters**

- **outlet_names** (str): Comma-separated list of outlet device names as configured in VeSync mobile app
- **username** (str): VeSync account email address
- **password** (str): VeSync account password

**Optional Parameters**

- **delay** (float, default=5.0): Delay in seconds between power off and on during power cycling

**Basic Example**

.. code-block:: yaml

    resources:
      VesyncOutlet:
        outlet_names: 'Lab Device Power'
        username: 'engineer@example.com'
        password: 'secure_password'
        delay: 5.0

**Multiple Outlets Example**

.. code-block:: yaml

    resources:
      VesyncOutlet:
        outlet_names: 'Device A,Device B,Device C'
        username: 'engineer@example.com'
        password: 'secure_password'

**Notes**

- Outlet names must match exactly (case-sensitive) what appears in VeSync mobile app
- All listed outlets are controlled together by VesyncPowerDriver
- Requires internet connectivity and active VeSync account

CyberPowerOutlet
~~~~~~~~~~~~~~~~

**Purpose**: Defines a CyberPower PDU outlet for SNMP-based power control

**Use With**: CyberPowerDriver

**Required Parameters**

- **address** (str): IP address or hostname of the PDU
- **outlet** (int): Outlet number to control (typically 1-8 depending on PDU model)

**Optional Parameters**

- **delay** (float, default=5.0): Delay in seconds between power off and on during cycling

**Basic Example**

.. code-block:: yaml

    resources:
      CyberPowerOutlet:
        address: '192.168.1.100'
        outlet: 3
        delay: 3.0

**Hostname Example**

.. code-block:: yaml

    resources:
      CyberPowerOutlet:
        address: 'lab-pdu-01.local'
        outlet: 5

**Notes**

- Uses SNMP "private" community string (standard for CyberPower)
- PDU must be accessible on network from host
- Outlet numbering depends on PDU model (check documentation)
- SNMP v2c protocol with read-write permissions required

MassStorageDevice
~~~~~~~~~~~~~~~~~

**Purpose**: Defines a mass storage device (typically SD card via USB mux) for file management

**Use With**: MassStorageDriver

**Required Parameters**

- **device** (str): Linux block device path (e.g., '/dev/sdb', '/dev/sdc')
- **partition** (int): Partition number to mount (typically 1 for boot partition)

**Basic Example**

.. code-block:: yaml

    resources:
      MassStorageDevice:
        device: '/dev/sdb'
        partition: 1

**Multiple Partition Example**

.. code-block:: yaml

    # For SD card with separate boot and rootfs partitions
    resources:
      MassStorageDevice:
        device: '/dev/sdb'
        partition: 1

**Important Notes**

- Device path must be discovered manually (use `lsblk` to identify)
- Device path can change across reboots if not using udev rules
- Typically used with USBSDMuxDriver to switch SD card between host and device
- Requires permissions to mount (usually sudo or running as root)

**Finding the Correct Device**

.. code-block:: bash

    # When SD card is connected via USB:
    lsblk
    # Look for the SD card device (often /dev/sdb or /dev/sdc)
    # Note the partition numbers and mount points

KuiperRelease
~~~~~~~~~~~~~~

**Purpose**: Defines an ADI Kuiper Linux release to download and manage

**Use With**: KuiperDLDriver

**Required Parameters**

- **release** (str): Release version identifier
- **cache_dir** (str): Directory path for caching downloaded files

**Supported Releases**

- '2018_R2'
- '2019_R1'
- '2023_R2_P1'

**Basic Example**

.. code-block:: yaml

    resources:
      KuiperRelease:
        release: '2023_R2_P1'
        cache_dir: '/var/cache/kuiper'

**System-Wide Cache Example**

.. code-block:: yaml

    resources:
      KuiperRelease:
        release: '2023_R2_P1'
        cache_dir: '/opt/labgrid/kuiper-cache'

**Notes**

- First download can be large (100+ MB)
- Cache directory must be writable
- Subsequent accesses use cached version (fast)
- Checksums are verified automatically

CloudsmithRelease
~~~~~~~~~~~~~~~~~

**Purpose**: Describes a boot artifact (e.g. ``BOOT.BIN``) hosted in a
Cloudsmith package repository, resolved by FPGA carrier + daughter card.

**Use With**: CloudsmithDLDriver

**Required Parameters**

- **fpga_carrier** (str): Short FPGA carrier name, e.g. ``zcu102``.
- **daughter_card** (str): Daughter card / chip, e.g. ``adrv9009``.

**Optional Parameters**

- **owner** (str, default ``adi``): Cloudsmith owner/org.
- **repo** (str, default ``sdg-boot-partition``): Cloudsmith repository.
- **filename** (str, default ``BOOT.BIN``): Artifact filename to resolve.
- **version** (str, default ``None``): Exact package version to pin. When
  unset, the *latest* matching package is resolved.
- **api_token** (str, default from ``$CLOUDSMITH_API_TOKEN``): Cloudsmith
  API token. Configurable in YAML but falls back to the environment so
  CI runs stay headless.
- **cache_path** (str, default ``~/.labgrid/cloudsmith_releases/``):
  Directory for cached downloads.

**Basic Example**

.. code-block:: yaml

    resources:
      CloudsmithRelease:
        fpga_carrier: 'zcu102'
        daughter_card: 'adrv9009'

**Pinned Version Example**

.. code-block:: yaml

    resources:
      CloudsmithRelease:
        fpga_carrier: 'zcu102'
        daughter_card: 'adrv9009'
        # Reproducible: resolve this exact package instead of latest.
        version: 'boot_partition/main/2025_06_14-07_18_12/zynqmp-zcu102-rev10-adrv9009/'

**Notes**

- The ``CLOUDSMITH_API_TOKEN`` environment variable must be set (or
  ``api_token`` provided) — Cloudsmith authenticates via a bearer token.
- The driver verifies the downloaded file's SHA256 against the checksum
  reported by the Cloudsmith API.

HomeAssistantOutlet
~~~~~~~~~~~~~~~~~~~

**Purpose**: Describes a switch/outlet controlled via the Home Assistant REST API.

**Use With**: HomeAssistantPowerDriver

**Required Parameters**

- **url** (str): Base URL of the Home Assistant instance (e.g. ``http://homeassistant.local:8123``)
- **token** (str): Long-lived access token
- **entity_id** (str): Entity ID of the switch to control (e.g. ``switch.lab_outlet_1``)

**Optional Parameters**

- **delay** (float, default=5.0): Delay in seconds between off and on during ``cycle``/``reset``

**Example**

.. code-block:: yaml

    resources:
      HomeAssistantOutlet:
        url: 'http://homeassistant.local:8123'
        token: 'eyJhbGciOiJI...'
        entity_id: 'switch.lab_outlet_1'
        delay: 5.0

**Notes**

- The domain portion of ``entity_id`` (``switch``, ``light``, ``input_boolean``, ...) selects the service endpoint, so non-outlet entities work as long as they support ``turn_on`` / ``turn_off``.

TFTPServerResource
~~~~~~~~~~~~~~~~~~

**Purpose**: Configures the TFTP server address, port, and root used by ``TFTPServerDriver`` and referenced by TFTP-based boot strategies.

**Use With**: TFTPServerDriver, BootFPGASoCTFTP

**Optional Parameters**

- **address** (str, default ``'auto'``): Host IP to bind. When set to ``'auto'``, the resource discovers the local IP used for outbound traffic.
- **port** (int, default 3069): UDP port to bind. Non-privileged; use ``iptables`` to redirect from the conventional port 69 if U-Boot requires it.
- **root** (str, default ``'/var/lib/tftpboot'``): Directory served by the TFTP server.

**Example**

.. code-block:: yaml

    resources:
      TFTPServerResource:
        address: 'auto'
        port: 3069
        root: '/var/lib/tftpboot'

**Notes**

- The resource has no required fields — an empty ``TFTPServerResource: {}`` stanza accepts all defaults.
- ``get_ip()`` returns the configured address, or opens a UDP socket to 8.8.8.8 to discover the outbound-interface IP when set to ``'auto'``.

XilinxVivadoTool
~~~~~~~~~~~~~~~~

**Purpose**: Declares the Xilinx Vivado/Vitis installation paths used by drivers that invoke ``xsdb``.

**Use With**: XilinxJTAGDriver

**Optional Parameters**

- **vivado_path** (str, default ``'/tools/Xilinx/2025.1/Vivado'``): Root of the Vivado install.
- **version** (str, optional): Informational version string.
- **xsdb_path** (str, optional): Absolute path to the ``xsdb`` binary. When unset, derived as ``{dirname(vivado_path)}/Vitis/bin/xsdb``.

**Example**

.. code-block:: yaml

    resources:
      XilinxVivadoTool:
        vivado_path: '/tools/Xilinx/2025.1/Vivado'
        version: '2025.1'

**Notes**

- The resource does *not* probe the filesystem, so it round-trips safely through a labgrid coordinator (the ``xsdb`` binary may live only on the exporter host).
- On 2022.2+ installs, Vivado and Vitis are siblings and ``xsdb`` ships with Vitis — the default derivation matches that layout.

XilinxDeviceJTAG
~~~~~~~~~~~~~~~~

**Purpose**: Declares JTAG target IDs and firmware paths for a Xilinx FPGA with a Microblaze soft processor.

**Use With**: XilinxJTAGDriver, BootFabric

**Optional Parameters**

- **root_target** (int, default=1): JTAG target ID for the FPGA fabric (from ``xsdb`` ``targets`` output).
- **microblaze_target** (int, default=3): JTAG target ID for the Microblaze core.
- **bitstream_path** (str, optional): Path to the ``.bit`` bitstream. Required for ``flash_bitstream`` and ``BootFabric``.
- **kernel_path** (str, optional): Path to the Microblaze Linux kernel image (``.strip``). Required for ``download_kernel`` and ``BootFabric``.
- **devicetree_path** (str, optional): Path to a standalone device-tree blob, if the kernel does not embed it.

**Example**

.. code-block:: yaml

    resources:
      XilinxDeviceJTAG:
        root_target: 1
        microblaze_target: 3
        bitstream_path: 'ref/vcu118_ad9081_m8_l4/system_top.bit'
        kernel_path:    'ref/vcu118_ad9081_m8_l4/simpleImage.vcu118_ad9081_m8_l4.strip'

**Notes**

- The default target IDs match typical VCU118 + Microblaze designs. Run ``xsdb`` ``targets`` on your hardware to verify.

Configuration Best Practices
-----------------------------

Security
~~~~~~~~

**Credentials in Version Control**

Never commit credentials to git:

.. code-block:: yaml

    # BAD - Don't do this!
    resources:
      VesyncOutlet:
        username: 'engineer@example.com'
        password: 'hardcoded_password'  # Never!

**Use Environment Variables**

.. code-block:: yaml

    # GOOD - Use environment variables
    resources:
      VesyncOutlet:
        outlet_names: 'Device Power'
        username: !env VESYNC_USERNAME
        password: !env VESYNC_PASSWORD

Then set environment before running:

.. code-block:: bash

    export VESYNC_USERNAME="user@example.com"
    export VESYNC_PASSWORD="secure_password"
    labgrid-client -c target.yaml ...

**Separate Credential Files**

.. code-block:: yaml

    # credentials.yaml (add to .gitignore)
    resources:
      VesyncOutlet:
        outlet_names: 'Device Power'
        username: 'user@example.com'
        password: 'password'

.. code-block:: yaml

    # target.yaml (committed to git)
    includes:
      - credentials.yaml

    targets:
      my_device:
        resources:
          VesyncOutlet: {}
        # ...

Device Path Stability
~~~~~~~~~~~~~~~~~~~~~

**Problem**: USB device paths change across reboots

**Solution: Use udev rules**

Create `/etc/udev/rules.d/99-labgrid.rules`:

.. code-block:: text

    # Map specific USB SD card to stable device name
    SUBSYSTEM=="block", ATTRS{manufacturer}=="SanDisk", \
      ATTRS{product}=="Ultra USB 3.0", \
      SYMLINK+="sd-mux-labgrid"

Then use in configuration:

.. code-block:: yaml

    resources:
      MassStorageDevice:
        device: '/dev/sd-mux-labgrid'
        partition: 1

Reload udev rules:

.. code-block:: bash

    sudo udevadm control --reload
    sudo udevadm trigger

Configuration Reusability
~~~~~~~~~~~~~~~~~~~~~~~~~

**Define Common Resources Once**

Create `common-resources.yaml`:

.. code-block:: yaml

    # common-resources.yaml
    resources:
      lab_pdu:
        CyberPowerOutlet:
          address: '192.168.1.100'
          delay: 3.0

      lab_storage:
        MassStorageDevice:
          device: '/dev/sdb'
          partition: 1

Then reference in target files:

.. code-block:: yaml

    # target1.yaml
    includes:
      - common-resources.yaml

    targets:
      zcu102_device:
        resources:
          CyberPowerOutlet: # From common-resources
            outlet: 3
        drivers:
          CyberPowerDriver: {}

Configuration Documentation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Comment Your Configuration**

.. code-block:: yaml

    targets:
      zcu102_dev:
        # Main test device in lab
        # Power controlled via PDU outlet 3
        # Serial: /dev/ttyUSB0 (mapped via udev)
        # SD card: /dev/sdb (SanDisk Ultra, blue connector)

        resources:
          CyberPowerOutlet:
            address: '10.0.1.100'  # Lab PDU IP
            outlet: 3              # Physical outlet on front panel
            delay: 3.0             # Device needs 3 sec before boot

          MassStorageDevice:
            device: '/dev/sdb'     # USB SD card reader
            partition: 1           # Boot partition

**Document Special Considerations**

.. code-block:: yaml

    resources:
      VesyncOutlet:
        # Note: WiFi outlet firmware requires IP in 192.168.x.x range
        # If lab network is 10.0.x.x, outlet won't connect to account
        outlet_names: 'Lab Bench Power'
        username: 'lab@example.com'
        password: 'password'
        delay: 10.0  # This outlet is slow, needs longer wait

Testing Configuration
---------------------

**Verify Resource Definition**

.. code-block:: bash

    # Labgrid validates resource definitions at load time
    labgrid-client -c target.yaml get-resource
    # Should list all resources without errors

**Test Connectivity**

.. code-block:: python

    from labgrid import Environment

    env = Environment("target.yaml")
    target = env.get_target("my_device")

    # Activate a driver to test resource binding
    power = target.get_driver("VesyncPowerDriver")
    target.activate(power)

    # If this succeeds, resource config is correct
    power.get()  # Test basic operation

    target.deactivate(power)

Resource Declaration Patterns
-----------------------------

Single Target Example
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

    targets:
      zcu102:
        resources:
          VesyncOutlet:
            outlet_names: 'ZCU102 Test Board'
            username: 'user@example.com'
            password: 'password'

          MassStorageDevice:
            device: '/dev/sdb'
            partition: 1

          KuiperRelease:
            release: '2023_R2_P1'
            cache_dir: '/var/cache/kuiper'

        drivers:
          VesyncPowerDriver: {}
          MassStorageDriver: {}
          KuiperDLDriver: {}

Multiple Targets Sharing Resources
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

    # shared.yaml
    resources:
      shared_pdu:
        CyberPowerOutlet:
          address: '192.168.1.100'
          delay: 3.0

      shared_kuiper:
        KuiperRelease:
          release: '2023_R2_P1'
          cache_dir: '/var/cache/kuiper'

    # target1.yaml
    includes:
      - shared.yaml

    targets:
      device1:
        resources:
          CyberPowerOutlet:
            outlet: 1
          KuiperRelease: {}
        drivers:
          CyberPowerDriver: {}

    # target2.yaml
    includes:
      - shared.yaml

    targets:
      device2:
        resources:
          CyberPowerOutlet:
            outlet: 2
          KuiperRelease: {}
        drivers:
          CyberPowerDriver: {}

Environment Variable Integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

    # template.yaml
    resources:
      storage:
        MassStorageDevice:
          device: !env STORAGE_DEVICE
          partition: !env STORAGE_PARTITION

Set before use:

.. code-block:: bash

    export STORAGE_DEVICE="/dev/sdb"
    export STORAGE_PARTITION="1"
    labgrid-client -c template.yaml ...

Common Configuration Issues
----------------------------

**Resource Not Found**

Error:
.. code-block:: text

    BindingError: Resource 'VesyncOutlet' not found

Solution: Ensure resource type is correctly spelled and exists in loaded configuration

**Invalid Device Path**

Error:
.. code-block:: text

    FileNotFoundError: /dev/sdb not found

Solution: Use `lsblk` to find current device path, may change across reboots

**Credential Errors**

Error:
.. code-block:: text

    CredentialError: Failed to login to VeSync

Solution: Verify username/password, check network connectivity

See Also
--------

- :doc:`../api/resources` - Complete resource API reference
- :doc:`drivers` - Driver configuration guide
- :doc:`../getting-started/configuration` - Full configuration examples
- :doc:`strategies` - How drivers use resources through strategies
