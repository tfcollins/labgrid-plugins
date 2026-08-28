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
     - ``APCOutlet``

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
     - ``VesyncOutlet``

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
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``partition``
     - ``None``
   * - ``mount_label``
     - ``'lg_mass_storage'``
   * - ``unmount_retries``
     - ``3``
   * - ``unmount_retry_delay``
     - ``2.0``

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``mass_storage``
     - ``MassStorageDevice``

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          MassStorageDevice:
            path: /dev/disk/by-partuuid/0123-4567
            file_updates:
              BOOT.BIN: /srv/boot/BOOT.BIN
              Image: /srv/boot/Image
            use_with_sdmux: true
        drivers:
          MassStorageDriver:
            partition: '1'
            mount_label: lg_mass_storage
            unmount_retries: 3
            unmount_retry_delay: 2.0

ADIShellDriver
~~~~~~~~~~~~~~

ADIShellDriver - Driver to execute commands on the shell ADIShellDriver binds on top of a ConsoleProtocol.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``prompt``
     - **required**
   * - ``login_prompt``
     - **required**
   * - ``username``
     - **required**
   * - ``password``
     - ``None``
   * - ``keyfile``
     - ``''``
   * - ``login_timeout``
     - ``60``
   * - ``console_ready``
     - ``''``
   * - ``await_login_timeout``
     - ``2``
   * - ``post_login_settle_time``
     - ``0``

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``console``
     - ``ConsoleProtocol``

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
     - ``KuiperRelease``

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
     - ``CloudsmithRelease``

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
     - ``CyberPowerOutlet``

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
     - ``XilinxDeviceJTAG``
   * - ``xilinxvivado``
     - ``XilinxVivadoTool``

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
     - ``TFTPServerResource``

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
     - ``CommandProtocol``
   * - ``file_transfer``
     - ``FileTransferProtocol``

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
     - ``HomeAssistantOutlet``

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
     - ``CommandProtocol``
   * - ``fs``
     - ``FileTransferProtocol``
   * - ``artifacts``
     - ``TickArtifacts``

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
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``restart_iiod``
     - ``True``
   * - ``force_on_vermagic_mismatch``
     - ``True``

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``command``
     - ``CommandProtocol``
   * - ``fs``
     - ``FileTransferProtocol``
   * - ``artifacts``
     - ``TickArtifacts``

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
     - ``CommandProtocol``
   * - ``fs``
     - ``FileTransferProtocol``
   * - ``artifacts``
     - ``TickArtifacts``

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
     - ``KasaOutlet``

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
