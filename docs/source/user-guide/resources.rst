Configuring Resources
=====================

Resources are configuration descriptors for hardware and network components. They define
what hardware is available to a target and store configuration parameters that drivers use.

Overview
--------

Resources in labgrid and labgrid-plugins:

- Describe physical hardware (outlets, serial ports, USB devices, network endpoints)
- Store configuration parameters (IP addresses, credentials, device paths)
- Are defined in YAML configuration files
- Are bound to drivers which provide the actual functionality
- Contain validation logic to ensure configuration correctness

The plugin provides twelve resources for different hardware scenarios:

- **VesyncOutlet** — WiFi smart outlet for power control
- **APCOutlet** — APC network PDU outlet for SNMP-based power control
- **CyberPowerOutlet** — Network PDU outlet for power control
- **HomeAssistantOutlet** — Switch/outlet controlled via Home Assistant REST API
- **MassStorageDevice** — USB mass storage (typically SD card via mux)
- **KuiperRelease** — ADI Kuiper Linux release descriptor
- **CloudsmithRelease** — Cloudsmith boot-artifact descriptor (e.g. ``BOOT.BIN``)
- **TFTPServerResource** — TFTP server address/port/root configuration
- **XilinxVivadoTool** — Xilinx Vivado/Vitis install paths
- **XilinxDeviceJTAG** — Xilinx FPGA JTAG target IDs and firmware paths
- **KasaOutlet** — TP-Link Kasa plug or named strip outlet
- **TickArtifacts** — Tick bitstream, overlay, and kernel-module paths

Resource Definition Patterns
-----------------------------

Resource Binding
~~~~~~~~~~~~~~~~

Resources are bound to drivers via configuration:

.. tab-set::

    .. tab-item:: Exporter

        Exporter resource configuration (``resources.yaml``):

        .. code-block:: yaml

            my_device:
              VesyncOutlet:
                cls: VesyncOutlet
                outlet_names: 'Lab Device 1'
                username: 'user@example.com'
                password: 'password'

        Client environment configuration (``target.yaml``):

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              my_device:
                resources:
                  RemotePlace:
                    name: my_device
                drivers:
                  VesyncPowerDriver: {}

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
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

.. tab-set::

    .. tab-item:: Exporter

        .. code-block:: yaml

            main:
              VesyncOutlet:
                cls: VesyncOutlet
                outlet_names: 'Lab Device Power'
                username: 'engineer@example.com'
                password: 'secure_password'
                delay: 5.0

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              main:
                resources:
                  VesyncOutlet:
                    outlet_names: 'Lab Device Power'
                    username: 'engineer@example.com'
                    password: 'secure_password'
                    delay: 5.0

**Multiple Outlets Example**

.. tab-set::

    .. tab-item:: Exporter

        .. code-block:: yaml

            main:
              VesyncOutlet:
                cls: VesyncOutlet
                outlet_names: 'Device A,Device B,Device C'
                username: 'engineer@example.com'
                password: 'secure_password'

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              main:
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

.. tab-set::

    .. tab-item:: Exporter

        .. code-block:: yaml

            main:
              CyberPowerOutlet:
                cls: CyberPowerOutlet
                address: '192.168.1.100'
                outlet: 3
                delay: 3.0

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              main:
                resources:
                  CyberPowerOutlet:
                    address: '192.168.1.100'
                    outlet: 3
                    delay: 3.0

**Hostname Example**

.. tab-set::

    .. tab-item:: Exporter

        .. code-block:: yaml

            main:
              CyberPowerOutlet:
                cls: CyberPowerOutlet
                address: 'lab-pdu-01.local'
                outlet: 5

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              main:
                resources:
                  CyberPowerOutlet:
                    address: 'lab-pdu-01.local'
                    outlet: 5

**Notes**

- Uses SNMP "private" community string (standard for CyberPower)
- PDU must be accessible on network from host
- Outlet numbering depends on PDU model (check documentation)
- SNMP v2c protocol with read-write permissions required

APCOutlet
~~~~~~~~~

**Purpose**: Defines an APC PDU outlet for SNMP-based power control

**Use With**: APCDriver

**Required Parameters**

- **address** (str): IP address or hostname of the APC PDU
- **outlet** (int): Outlet number to control (typically 1-8 depending on PDU model)

**Optional Parameters**

- **delay** (float, default=5.0): Delay in seconds between power off and on during cycling

**Basic Example**

.. tab-set::

    .. tab-item:: Exporter

        .. code-block:: yaml

            main:
              APCOutlet:
                cls: APCOutlet
                address: '192.168.1.50'
                outlet: 1
                delay: 3.0

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              main:
                resources:
                  APCOutlet:
                    address: '192.168.1.50'
                    outlet: 1
                    delay: 3.0

**Hostname Example**

.. tab-set::

    .. tab-item:: Exporter

        .. code-block:: yaml

            main:
              APCOutlet:
                cls: APCOutlet
                address: 'lab-apc-01.local'
                outlet: 4

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              main:
                resources:
                  APCOutlet:
                    address: 'lab-apc-01.local'
                    outlet: 4

**Notes**

- Uses the SNMP ``public`` community for status reads and ``private`` for outlet control
- PDU must be reachable on the network from the labgrid host
- Outlet numbering and supported state values depend on the APC model
- SNMP v2c access must be enabled on the PDU

MassStorageDevice
~~~~~~~~~~~~~~~~~

**Purpose**: Defines a mass storage device (typically SD card via USB mux) for file management

**Use With**: MassStorageDriver

**Required Parameters**

- **path** (str): Linux block-device or partition path. Prefer a stable
  ``/dev/disk/by-*`` path over an enumeration-dependent ``/dev/sdX`` name.

**Optional Parameters**

- **file_updates** (dict, default ``{}``): Mapping of destination names to local files.
- **use_with_sdmux** (bool, default ``False``): Mark the device as SD-mux managed.

**Basic Example**

.. tab-set::

    .. tab-item:: Exporter

        .. code-block:: yaml

            main:
              MassStorageDevice:
                cls: MassStorageDevice
                path: '/dev/disk/by-partuuid/0123-4567'
                use_with_sdmux: true

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              main:
                resources:
                  MassStorageDevice:
                    path: '/dev/disk/by-partuuid/0123-4567'
                    use_with_sdmux: true

**File Update Example**

.. tab-set::

    .. tab-item:: Exporter

        .. code-block:: yaml

            main:
              MassStorageDevice:
                cls: MassStorageDevice
                path: '/dev/disk/by-partuuid/0123-4567'
                file_updates:
                  BOOT.BIN: '/srv/boot/BOOT.BIN'
                  Image: '/srv/boot/Image'

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              main:
                resources:
                  MassStorageDevice:
                    path: '/dev/disk/by-partuuid/0123-4567'
                    file_updates:
                      BOOT.BIN: '/srv/boot/BOOT.BIN'
                      Image: '/srv/boot/Image'

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

- **release_version** (str): Release version identifier.

**Optional Parameters**

- **cache_path** (str, default ``~/.labgrid/kuiper_releases/``): Download cache.
- **kernel_path**, **BOOTBIN_path**, **device_tree_path** (str or ``None``):
  Explicit paths or ``release:`` selectors for boot files.

**Supported Releases**

- '2018_R2'
- '2019_R1'
- '2023_R2_P1'

**Basic Example**

.. tab-set::

    .. tab-item:: Exporter

        .. code-block:: yaml

            main:
              KuiperRelease:
                cls: KuiperRelease
                release_version: '2023_R2_P1'
                cache_path: '/var/cache/kuiper'

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              main:
                resources:
                  KuiperRelease:
                    release_version: '2023_R2_P1'
                    cache_path: '/var/cache/kuiper'

**System-Wide Cache Example**

.. tab-set::

    .. tab-item:: Exporter

        .. code-block:: yaml

            main:
              KuiperRelease:
                cls: KuiperRelease
                release_version: '2023_R2_P1'
                cache_path: '/opt/labgrid/kuiper-cache'

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              main:
                resources:
                  KuiperRelease:
                    release_version: '2023_R2_P1'
                    cache_path: '/opt/labgrid/kuiper-cache'

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

.. tab-set::

    .. tab-item:: Exporter

        .. code-block:: yaml

            main:
              CloudsmithRelease:
                cls: CloudsmithRelease
                fpga_carrier: 'zcu102'
                daughter_card: 'adrv9009'

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              main:
                resources:
                  CloudsmithRelease:
                    fpga_carrier: 'zcu102'
                    daughter_card: 'adrv9009'

**Pinned Version Example**

.. tab-set::

    .. tab-item:: Exporter

        .. code-block:: yaml

            main:
              CloudsmithRelease:
                cls: CloudsmithRelease
                fpga_carrier: 'zcu102'
                daughter_card: 'adrv9009'
                ## Reproducible: resolve this exact package instead of latest.
                version: 'boot_partition/main/2025_06_14-07_18_12/zynqmp-zcu102-rev10-adrv9009/'

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              main:
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

.. tab-set::

    .. tab-item:: Exporter

        .. code-block:: yaml

            main:
              HomeAssistantOutlet:
                cls: HomeAssistantOutlet
                url: 'http://homeassistant.local:8123'
                token: 'eyJhbGciOiJI...'
                entity_id: 'switch.lab_outlet_1'
                delay: 5.0

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              main:
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

.. tab-set::

    .. tab-item:: Exporter

        .. code-block:: yaml

            main:
              TFTPServerResource:
                cls: TFTPServerResource
                address: 'auto'
                port: 3069
                root: '/var/lib/tftpboot'

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              main:
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

.. tab-set::

    .. tab-item:: Exporter

        .. code-block:: yaml

            main:
              XilinxVivadoTool:
                cls: XilinxVivadoTool
                vivado_path: '/tools/Xilinx/2025.1/Vivado'
                version: '2025.1'

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              main:
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

.. tab-set::

    .. tab-item:: Exporter

        .. code-block:: yaml

            main:
              XilinxDeviceJTAG:
                cls: XilinxDeviceJTAG
                root_target: 1
                microblaze_target: 3
                bitstream_path: 'ref/vcu118_ad9081_m8_l4/system_top.bit'
                kernel_path:    'ref/vcu118_ad9081_m8_l4/simpleImage.vcu118_ad9081_m8_l4.strip'

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              main:
                resources:
                  XilinxDeviceJTAG:
                    root_target: 1
                    microblaze_target: 3
                    bitstream_path: 'ref/vcu118_ad9081_m8_l4/system_top.bit'
                    kernel_path:    'ref/vcu118_ad9081_m8_l4/simpleImage.vcu118_ad9081_m8_l4.strip'

**Notes**

- The default target IDs match typical VCU118 + Microblaze designs. Run ``xsdb`` ``targets`` on your hardware to verify.

KasaOutlet
~~~~~~~~~~

**Purpose**: Describes a TP-Link Kasa smart plug or power strip, controlled over the local
network.

**Use With**: KasaPowerDriver

**Required Parameters**

- **host** (str): IP address or hostname of the plug or strip.

**Optional Parameters**

- **outlets** (str): Comma-separated strip sockets to control, each a 0-based index or a socket
  alias. Unset controls a single plug, or all of a strip's sockets together.
- **username** / **password** (str): TP-Link account credentials, needed by newer
  (KLAP/SMART) devices even for local control. Default to ``KASA_USERNAME`` /
  ``KASA_PASSWORD`` from the environment.
- **delay** (float, default=5.0): Seconds between off and on during a power cycle.

**Example**

.. code-block:: yaml

    KasaOutlet:
      cls: KasaOutlet
      host: '192.168.1.60'
      outlets: '0,2'

See :ref:`the KasaPowerDriver section <kasapowerdriver>` in :doc:`drivers` for the full
Exporter and Local configuration.

TickArtifacts
~~~~~~~~~~~~~

**Purpose**: Paths and target-side names for a runtime Tick deploy.

**Use With**: TickFpgaManagerDriver, TickOverlayDriver, TickModuleDriver, BootTickFPGASSH

**Required Parameters**

- **bitstream_path** (str): Path to the FPGA ``.bit``.
- **overlay_dtbo_path** (str): Path to the prebuilt device-tree overlay (``.dtbo``).
- **module_ko_path** (str): Path to ``axi_timed_command_scheduler.ko``.

**Optional Parameters**

- **firmware_name** (str, default ``tick.bit``): File name written under ``/lib/firmware`` on the target.
- **overlay_name** (str, default ``tick``): configfs overlay directory name.
- **remote_dir** (str, default ``/tmp/tick``): Scratch directory on the target for staged files.

See :doc:`tick` for a complete environment.

Configuration Best Practices
-----------------------------

Security
~~~~~~~~

**Credentials in Version Control**

Never commit credentials to git:

.. tab-set::

    .. tab-item:: Exporter

        .. code-block:: yaml

            ## BAD - Don't do this!
            my_group:
              VesyncOutlet:
                cls: VesyncOutlet
                username: 'engineer@example.com'
                password: 'hardcoded_password'  # Never!

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            # BAD - Don't do this!
            imports:
              - adi_lg_plugins
            targets:
              main:
                resources:
                  VesyncOutlet:
                    username: 'engineer@example.com'
                    password: 'hardcoded_password'  # Never!

**Use Environment Variables**

labgrid has no ``!env`` tag; the substitution syntax depends on which file holds the credential
(see `Environment Variable Integration`_):

.. tab-set::

    .. tab-item:: Exporter

        .. code-block:: yaml

            ## GOOD - read credentials from the exporter's environment
            my_group:
              VesyncOutlet:
                cls: VesyncOutlet
                outlet_names: 'Device Power'
                username: '{{ env["VESYNC_USERNAME"] }}'
                password: '{{ env["VESYNC_PASSWORD"] }}'

        Provide the variables to the exporter process - for a systemd service, through an
        ``EnvironmentFile=`` readable only by the service user:

        .. code-block:: ini

            # /etc/labgrid/exporter.env (mode 600)
            VESYNC_USERNAME=user@example.com
            VESYNC_PASSWORD=secure_password

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            # GOOD - read credentials from LG_* environment variables
            imports:
              - adi_lg_plugins
            targets:
              main:
                resources:
                  VesyncOutlet:
                    outlet_names: 'Device Power'
                    username: !template $LG_VESYNC_USERNAME
                    password: !template $LG_VESYNC_PASSWORD

        .. code-block:: bash

            export LG_VESYNC_USERNAME="user@example.com"
            export LG_VESYNC_PASSWORD="secure_password"
            labgrid-client -c target.yaml ...

**Separate Credential Files**

labgrid has no ``includes:`` key, so a committed config can't read credentials from another
YAML file. Keep the values in a git-ignored file that is loaded into the environment, and
reference them as shown above:

- **Exporter**: the service's ``EnvironmentFile=`` (mode ``600``) is that file.
- **Client**: put the ``LG_*`` variables in a git-ignored file and export them before running
  labgrid:

  .. code-block:: bash

      # lab.env (add to .gitignore)
      LG_VESYNC_USERNAME=user@example.com
      LG_VESYNC_PASSWORD=secure_password

  .. code-block:: bash

      set -a; . ./lab.env; set +a
      labgrid-client -c target.yaml ...

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

.. tab-set::

    .. tab-item:: Exporter

        .. code-block:: yaml

            my_group:
              MassStorageDevice:
                cls: MassStorageDevice
                path: '/dev/sd-mux-labgrid1'

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              main:
                resources:
                  MassStorageDevice:
                    path: '/dev/sd-mux-labgrid1'

Reload udev rules:

.. code-block:: bash

    sudo udevadm control --reload
    sudo udevadm trigger

Configuration Reusability
~~~~~~~~~~~~~~~~~~~~~~~~~

**Define Common Values Once**

labgrid has no ``includes:`` key for sharing configuration between files. Each file type has
its own mechanism:

.. tab-set::

    .. tab-item:: Exporter

        ``resources.yaml`` is a Jinja2 template, so a value can be set once with
        ``{% set %}`` and reused:

        .. code-block:: yaml+jinja

            {% set pdu_address = '192.168.1.100' %}
            zcu102_group:
              CyberPowerOutlet:
                cls: CyberPowerOutlet
                address: '{{ pdu_address }}'
                outlet: 3
            vcu118_group:
              CyberPowerOutlet:
                cls: CyberPowerOutlet
                address: '{{ pdu_address }}'
                outlet: 4

        ``{% include 'common.yaml' %}`` inserts another file's text, resolved relative to
        ``resources.yaml``; the included file must contain complete resource groups.

    .. tab-item:: Local (Non-Exporter)

        A ``target.yaml`` is a single file: reuse values inside it with YAML anchors and
        aliases (see `Multiple Targets Sharing Resources`_), and take values that differ per
        machine from ``LG_*`` environment variables with ``!template`` (see
        `Environment Variable Integration`_).

Configuration Documentation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Comment Your Configuration**

.. tab-set::

    .. tab-item:: Exporter

        .. code-block:: yaml

            zcu102_dev:
              ## Main test device in lab
              ## Power controlled via PDU outlet 3
              ## Serial: /dev/ttyUSB0 (mapped via udev)
              ## SD card: /dev/sdb (SanDisk Ultra, blue connector)

              CyberPowerOutlet:
                cls: CyberPowerOutlet
                address: '10.0.1.100'  # Lab PDU IP
                outlet: 3              # Physical outlet on front panel
                delay: 3.0             # Device needs 3 sec before boot

              MassStorageDevice:
                cls: MassStorageDevice
                path: '/dev/sdb1'      # USB SD card boot partition

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
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
                    path: '/dev/sdb1'      # USB SD card boot partition

**Document Special Considerations**

.. tab-set::

    .. tab-item:: Exporter

        .. code-block:: yaml

            my_group:
              VesyncOutlet:
                cls: VesyncOutlet
                ## Note: WiFi outlet firmware requires IP in 192.168.x.x range
                ## If lab network is 10.0.x.x, outlet won't connect to account
                outlet_names: 'Lab Bench Power'
                username: 'lab@example.com'
                password: 'password'
                delay: 10.0  # This outlet is slow, needs longer wait

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              main:
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

.. tab-set::

    .. tab-item:: Exporter

        ``resources.yaml`` (on exporter host):

        .. code-block:: yaml

            zcu102_group:
              VesyncOutlet:
                cls: VesyncOutlet
                outlet_names: 'ZCU102 Test Board'
                username: 'user@example.com'
                password: 'password'

              MassStorageDevice:
                cls: MassStorageDevice
                path: '/dev/sdb1'

              KuiperRelease:
                cls: KuiperRelease
                release_version: '2023_R2_P1'
                cache_path: '/var/cache/kuiper'

        ``target.yaml`` (on client):

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              zcu102:
                resources:
                  RemotePlace:
                    name: zcu102_place
                drivers:
                  VesyncPowerDriver: {}
                  MassStorageDriver: {}
                  KuiperDLDriver: {}

    .. tab-item:: Local (Non-Exporter)

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              zcu102:
                resources:
                  VesyncOutlet:
                    outlet_names: 'ZCU102 Test Board'
                    username: 'user@example.com'
                    password: 'password'

                  MassStorageDevice:
                    path: '/dev/sdb1'

                  KuiperRelease:
                    release_version: '2023_R2_P1'
                    cache_path: '/var/cache/kuiper'

                drivers:
                  VesyncPowerDriver: {}
                  MassStorageDriver: {}
                  KuiperDLDriver: {}

Multiple Targets Sharing Resources
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. tab-set::

    .. tab-item:: Exporter

        ``resources.yaml`` (on exporter host):

        .. code-block:: yaml

            device1_group:
              CyberPowerOutlet:
                cls: CyberPowerOutlet
                address: '192.168.1.100'
                outlet: 1
                delay: 3.0
              KuiperRelease:
                cls: KuiperRelease
                release_version: '2023_R2_P1'
                cache_path: '/var/cache/kuiper'

            device2_group:
              CyberPowerOutlet:
                cls: CyberPowerOutlet
                address: '192.168.1.100'
                outlet: 2
                delay: 3.0
              KuiperRelease:
                cls: KuiperRelease
                release_version: '2023_R2_P1'
                cache_path: '/var/cache/kuiper'

        ``targets.yaml`` (on client):

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              device1:
                resources:
                  RemotePlace:
                    name: device1_place
                drivers:
                  CyberPowerDriver: {}
              device2:
                resources:
                  RemotePlace:
                    name: device2_place
                drivers:
                  CyberPowerDriver: {}

    .. tab-item:: Local (Non-Exporter)

        labgrid has no ``includes:`` key, and its YAML loader rejects merge keys
        (``<<: *name``). Share values between targets in one ``target.yaml`` with YAML anchors
        (``&name``) and aliases (``*name``):

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              device1:
                resources:
                  CyberPowerOutlet:
                    address: &pdu_address '192.168.1.100'
                    outlet: 1
                    delay: &pdu_delay 3.0
                  KuiperRelease: &kuiper
                    release_version: '2023_R2_P1'
                    cache_path: '/var/cache/kuiper'
                drivers:
                  CyberPowerDriver: {}
              device2:
                resources:
                  CyberPowerOutlet:
                    address: *pdu_address
                    outlet: 2
                    delay: *pdu_delay
                  KuiperRelease: *kuiper
                drivers:
                  CyberPowerDriver: {}

        Each target still gets its own resource instances; the anchors only avoid repeating
        the values.

Environment Variable Integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

labgrid has no ``!env`` tag. How a value comes from the environment depends on which file it is in:

.. tab-set::

    .. tab-item:: Exporter

        ``labgrid-exporter`` renders ``resources.yaml`` as a Jinja2 template with its own process
        environment available as ``env``:

        .. code-block:: yaml

            my_group:
              MassStorageDevice:
                cls: MassStorageDevice
                path: '{{ env["STORAGE_DEVICE"] }}'

        Set ``STORAGE_DEVICE=/dev/sdb1`` in the exporter's environment before it starts. An
        unset variable renders as an empty string, not an error.

    .. tab-item:: Local (Non-Exporter)

        labgrid substitutes ``!template`` values in ``target.yaml`` from environment variables
        whose names start with ``LG_`` (plus ``$BASE``, the config file's directory):

        .. code-block:: yaml

            imports:
              - adi_lg_plugins
            targets:
              main:
                resources:
                  MassStorageDevice:
                    path: !template $LG_STORAGE_DEVICE

        .. code-block:: bash

            export LG_STORAGE_DEVICE="/dev/sdb1"
            labgrid-client -c target.yaml ...

        An unset ``LG_`` variable fails config loading with
        ``refers to unknown variable 'LG_STORAGE_DEVICE'``.

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
