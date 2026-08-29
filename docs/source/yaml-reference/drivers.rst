Drivers
=======

Canonical YAML arguments and bindings for every driver registered by
``labgrid-plugins``. Driver binding selectors belong in a ``bindings:`` mapping;
they are not constructor arguments.

.. note::

   Native labgrid providers such as ``SerialDriver`` and ``SSHDriver`` are included where
   useful. Replace their example resources with the devices exported by your lab.

APCDriver
~~~~~~~~~

APCDriver - Driver using a APC PDU to control a target's power.

This component has no class-specific YAML arguments. Use ``{}``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``APC_outlet``
     - ``APCOutlet`` supplies the PDU address, outlet number, SNMP
       communities, and switching delay.

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          APCOutlet:
            address: pdu.example.test
            outlet: 1
            delay: 5.0
            read_community: public
            write_community: private
        drivers:
          APCDriver: {}

VesyncPowerDriver
~~~~~~~~~~~~~~~~~

VesyncPowerDriver - Driver using a Vesync Smart Outlet to control a target's power - https://github.com/webdjoe/pyvesync. Uses pyvesync tool to control the outlet.

This component has no class-specific YAML arguments. Use ``{}``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``vesync_outlet``
     - ``VesyncOutlet`` supplies VeSync account credentials, the outlet name,
       and switching delay.

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          VesyncOutlet:
            outlet_names: Device Power
            username: user@example.test
            password: secret
            delay: 5.0
        drivers:
          VesyncPowerDriver: {}

MassStorageDriver
~~~~~~~~~~~~~~~~~

Mount and copy files to a USB mass storage device.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 24 24 52

   * - Argument
     - Requirement/default
     - Description and example
   * - ``partition``
     - ``None``
     - Overrides the bound resource's device path with an absolute partition
       path on the exporter host. For example,
       ``/dev/disk/by-partuuid/0123-4567``.
   * - ``mount_label``
     - ``'lg_mass_storage'``
     - Names the ``pmount`` mount, whose resulting directory is
       ``/media/<mount_label>``. For example, ``lg_mass_storage``.
   * - ``unmount_retries``
     - ``3``
     - Sets the number of ``pumount`` attempts before a lazy-unmount fallback.
       For example, ``3``.
   * - ``unmount_retry_delay``
     - ``2.0``
     - Sets the seconds to wait between unsuccessful unmount attempts.
       For example, ``2.0``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``mass_storage``
     - ``MassStorageDevice`` identifies the block device and exporter host and
       supplies the source-to-destination file update map.

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          MassStorageDevice:
            path: /dev/sdb
            file_updates:
              /srv/boot/BOOT.BIN: BOOT.BIN
              /srv/boot/Image: Image
            use_with_sdmux: true
        drivers:
          MassStorageDriver:
            partition: /dev/disk/by-partuuid/0123-4567
            mount_label: lg_mass_storage
            unmount_retries: 3
            unmount_retry_delay: 2.0

ADIShellDriver
~~~~~~~~~~~~~~

ADIShellDriver - Driver to execute commands on the shell ADIShellDriver binds on top of a ConsoleProtocol.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 24 24 52

   * - Argument
     - Requirement/default
     - Description and example
   * - ``prompt``
     - **required**
     - Regular expression used to recognize an interactive shell prompt.
       For example, ``root@analog:.*#``.
   * - ``login_prompt``
     - **required**
     - Regular expression that triggers submission of ``username``.
       For example, ``'analog login: '``.
   * - ``username``
     - **required**
     - Login name sent when ``login_prompt`` is matched. For example,
       ``root``.
   * - ``password``
     - ``None``
     - Password sent when the console requests ``Password:``; leaving it unset
       makes such a request fail. For example, ``analog``.
   * - ``keyfile``
     - ``''``
     - Local public-key file installed in the target user's
       ``authorized_keys`` after login; an empty string disables installation.
       For example, ``/home/lab/.ssh/id_ed25519.pub``.
   * - ``login_timeout``
     - ``60``
     - Overall seconds allowed to reach a usable shell during activation.
       For example, ``60``.
   * - ``console_ready``
     - ``''``
     - Optional regular expression for a message requesting Enter to activate
       the console; a match sends a newline. For example,
       ``'Press Enter to activate this console'``.
   * - ``await_login_timeout``
     - ``2``
     - Per-read idle timeout in seconds; after unchanged console input, the
       driver sends a newline to probe for login or shell prompts. For example,
       ``2``.
   * - ``post_login_settle_time``
     - ``0``
     - Seconds of console silence required after login before validating the
       prompt, useful while boot messages continue. For example, ``5``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``console``
     - ``ConsoleProtocol`` carries login interaction, shell commands, and
       XMODEM file data; ``SerialDriver`` commonly provides it.

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          RawSerialPort:
            port: /dev/ttyUSB0
            speed: 115200
        drivers:
          SerialDriver: {}
          ADIShellDriver:
            prompt: root@analog:.*#
            login_prompt: 'analog login: '
            username: root
            password: analog
            keyfile: ''
            login_timeout: 60
            console_ready: ''
            await_login_timeout: 2
            post_login_settle_time: 0

KuiperDLDriver
~~~~~~~~~~~~~~

KuiperDLDriver - Driver to download and manage Kuiper releases and provide files to the target device.

This component has no class-specific YAML arguments. Use ``{}``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``kuiper_resource``
     - ``KuiperRelease`` selects the release and names its boot artifacts and
       local cache directory.

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          KuiperRelease:
            release_version: 2023_R2_P1
            cache_path: ~/.labgrid/kuiper_releases/
            kernel_path: release:zynqmp-common/Image
            BOOTBIN_path: release:zynqmp-zcu102-rev10-ad9081/BOOT.BIN
            device_tree_path: release:zynqmp-zcu102-rev10-ad9081/system.dtb
        drivers:
          KuiperDLDriver: {}

CloudsmithDLDriver
~~~~~~~~~~~~~~~~~~

Driver to resolve and download Cloudsmith boot artifacts.

This component has no class-specific YAML arguments. Use ``{}``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``cloudsmith_resource``
     - ``CloudsmithRelease`` supplies package filters, repository credentials,
       artifact name, optional version pin, and cache directory.

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          CloudsmithRelease:
            fpga_carrier: zcu102
            daughter_card: adrv9009
            vfilter:
              - main
            vnot:
              - deprecated
            owner: adi
            repo: sdg-boot-partition
            filename: BOOT.BIN
            version: 2025.1.0
            api_token: ${CLOUDSMITH_API_TOKEN}
            cache_path: ~/.labgrid/cloudsmith_releases/
        drivers:
          CloudsmithDLDriver: {}

CyberPowerDriver
~~~~~~~~~~~~~~~~

CyberPowerDriver - Driver using a CyberPower PDU to control a target's power.

This component has no class-specific YAML arguments. Use ``{}``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``cyberpower_outlet``
     - ``CyberPowerOutlet`` supplies the PDU address, outlet number, and
       switching delay used for SNMP power control.

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          CyberPowerOutlet:
            address: pdu.example.test
            outlet: 3
            delay: 5.0
        drivers:
          CyberPowerDriver: {}

XilinxJTAGDriver
~~~~~~~~~~~~~~~~

Program Xilinx FPGAs via JTAG using xsdb.

This component has no class-specific YAML arguments. Use ``{}``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``xilinxdevicejtag``
     - ``XilinxDeviceJTAG`` supplies JTAG target IDs, boot artifact paths, and
       the exporter host on which those paths are visible.
   * - ``xilinxvivado``
     - ``XilinxVivadoTool`` locates the Vivado installation and ``xsdb``
       executable used to run programming scripts.

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          XilinxDeviceJTAG:
            root_target: 1
            microblaze_target: 3
            bitstream_path: /srv/images/system_top.bit
            kernel_path: /srv/images/simpleImage.vcu118.strip
            devicetree_path: /srv/images/system.dtb
          XilinxVivadoTool:
            vivado_path: /opt/Xilinx/2025.1/Vivado
            version: '2025.1'
            xsdb_path: /opt/Xilinx/2025.1/Vivado/bin/xsdb
        drivers:
          XilinxJTAGDriver: {}

TFTPServerDriver
~~~~~~~~~~~~~~~~

TFTPServerDriver provides a pure Python TFTP server.

This component has no class-specific YAML arguments. Use ``{}``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``resource``
     - ``TFTPServerResource`` supplies the listening address and port and the
       root directory from which files are served.

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          TFTPServerResource:
            address: auto
            port: 3069
            root: /var/lib/tftpboot
        drivers:
          TFTPServerDriver: {}

SoftwareInstallerDriver
~~~~~~~~~~~~~~~~~~~~~~~

SoftwareInstallerDriver - Driver to install software, clone repos, copy directories, and run builds/tests on a DUT.

This component has no class-specific YAML arguments. Use ``{}``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``command``
     - ``CommandProtocol`` executes package, repository, build, and test
       commands on the DUT; ``SSHDriver`` commonly provides it.
   * - ``file_transfer``
     - ``FileTransferProtocol`` copies local source trees to the DUT;
       ``SSHDriver`` can provide it alongside ``CommandProtocol``.

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          NetworkService:
            address: dut.example.test
            username: root
        drivers:
          SSHDriver: {}
          SoftwareInstallerDriver: {}

HomeAssistantPowerDriver
~~~~~~~~~~~~~~~~~~~~~~~~

HomeAssistantPowerDriver - Driver using a Home Assistant switch/outlet to control a target's power via the Home Assistant REST API.

This component has no class-specific YAML arguments. Use ``{}``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``ha_outlet``
     - ``HomeAssistantOutlet`` supplies the REST endpoint, access token,
       switch entity ID, and switching delay.

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          HomeAssistantOutlet:
            url: http://homeassistant.example.test:8123
            token: ${HOME_ASSISTANT_TOKEN}
            entity_id: switch.lab_outlet_1
            delay: 5.0
        drivers:
          HomeAssistantPowerDriver: {}

TickFpgaManagerDriver
~~~~~~~~~~~~~~~~~~~~~

Load a bitstream through ``/sys/class/fpga_manager/fpga0``.

This component has no class-specific YAML arguments. Use ``{}``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``command``
     - ``CommandProtocol`` creates firmware directories and programs the FPGA
       through sysfs; ``SSHDriver`` commonly provides it.
   * - ``fs``
     - ``FileTransferProtocol`` transfers the bitstream to the DUT;
       ``SSHDriver`` commonly provides it.
   * - ``artifacts``
     - ``TickArtifacts`` supplies the local bitstream path, firmware name, and
       remote staging directory.

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          TickArtifacts:
            bitstream_path: /run/tick/system.bit
            overlay_dtbo_path: /run/tick/tick.dtbo
            module_ko_path: /run/tick/axi_timed_command_scheduler.ko
            firmware_name: tick.bit
            overlay_name: tick
            remote_dir: /tmp/tick
          NetworkService:
            address: dut.example.test
            username: root
        drivers:
          SSHDriver: {}
          TickFpgaManagerDriver: {}

TickModuleDriver
~~~~~~~~~~~~~~~~

Insert/remove ``axi_timed_command_scheduler.ko`` over SSH.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 24 24 52

   * - Argument
     - Requirement/default
     - Description and example
   * - ``restart_iiod``
     - ``True``
     - Restarts ``iiod`` after inserting the module so its IIO context sees the
       new device. For example, ``true``.
   * - ``force_on_vermagic_mismatch``
     - ``True``
     - Retries a failed ``insmod`` with the module parameter ``force=y``;
       disabling it surfaces the original insertion error. For example,
       ``false``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``command``
     - ``CommandProtocol`` checks module metadata, inserts or removes the
       module, and optionally restarts ``iiod``.
   * - ``fs``
     - ``FileTransferProtocol`` transfers the kernel module to the DUT;
       ``SSHDriver`` commonly provides both Tick protocols.
   * - ``artifacts``
     - ``TickArtifacts`` supplies the local module path and remote staging
       directory.

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          TickArtifacts:
            bitstream_path: /run/tick/system.bit
            overlay_dtbo_path: /run/tick/tick.dtbo
            module_ko_path: /run/tick/axi_timed_command_scheduler.ko
            firmware_name: tick.bit
            overlay_name: tick
            remote_dir: /tmp/tick
          NetworkService:
            address: dut.example.test
            username: root
        drivers:
          SSHDriver: {}
          TickModuleDriver:
            restart_iiod: true
            force_on_vermagic_mismatch: true

TickOverlayDriver
~~~~~~~~~~~~~~~~~

Apply and remove the Tick DT overlay through configfs.

This component has no class-specific YAML arguments. Use ``{}``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``command``
     - ``CommandProtocol`` manages the configfs overlay directory and reads
       overlay status.
   * - ``fs``
     - ``FileTransferProtocol`` transfers the compiled overlay to the DUT;
       ``SSHDriver`` commonly provides both Tick protocols.
   * - ``artifacts``
     - ``TickArtifacts`` supplies the local ``.dtbo`` path, overlay name, and
       remote staging directory.

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          TickArtifacts:
            bitstream_path: /run/tick/system.bit
            overlay_dtbo_path: /run/tick/tick.dtbo
            module_ko_path: /run/tick/axi_timed_command_scheduler.ko
            firmware_name: tick.bit
            overlay_name: tick
            remote_dir: /tmp/tick
          NetworkService:
            address: dut.example.test
            username: root
        drivers:
          SSHDriver: {}
          TickOverlayDriver: {}

KasaPowerDriver
~~~~~~~~~~~~~~~

Driver controlling a target's power via a TP-Link Kasa device.

This component has no class-specific YAML arguments. Use ``{}``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``kasa_outlet``
     - ``KasaOutlet`` supplies the plug host, optional cloud credentials,
       child-outlet selector, and switching delay.

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          KasaOutlet:
            host: kasa-plug.example.test
            outlets: Bench DUT
            username: ${KASA_USERNAME}
            password: ${KASA_PASSWORD}
            delay: 5.0
        drivers:
          KasaPowerDriver: {}
