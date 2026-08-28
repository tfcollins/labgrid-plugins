Resources
=========

Canonical, implementation-checked YAML arguments for every resource registered by
``labgrid-plugins``. Every example includes the required plugin import and a complete
target wrapper, so it can be copied into an environment file.

.. note::

   ``name`` is the universal labgrid instance selector and may be added to any resource.
   Class-specific arguments and defaults are listed below. Secrets shown as ``${...}``
   are illustrative strings; use your normal secret injection mechanism.

APCOutlet
~~~~~~~~~

The APCOutlet describes an APC smart PDU outlet.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``address``
     - **required**
   * - ``outlet``
     - **required**
   * - ``delay``
     - ``5.0``
   * - ``read_community``
     - ``'public'``
   * - ``write_community``
     - ``'private'``

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

VesyncOutlet
~~~~~~~~~~~~

The VeSyncOutlet describes a smart outlet controlled with VeSync.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``outlet_names``
     - **required**
   * - ``username``
     - **required**
   * - ``password``
     - **required**
   * - ``delay``
     - ``5.0``

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

MassStorageDevice
~~~~~~~~~~~~~~~~~

The MassStorageDevice describes a USB mass storage device.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``path``
     - **required**
   * - ``file_updates``
     - ``{}``
   * - ``use_with_sdmux``
     - ``False``

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

KuiperRelease
~~~~~~~~~~~~~

The KuiperRelease describes a Kuiper release resource.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``release_version``
     - **required**
   * - ``cache_path``
     - ``'~/.labgrid/kuiper_releases/'``
   * - ``kernel_path``
     - ``None``
   * - ``BOOTBIN_path``
     - ``None``
   * - ``device_tree_path``
     - ``None``

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

CloudsmithRelease
~~~~~~~~~~~~~~~~~

The CloudsmithRelease describes a Cloudsmith-hosted boot artifact.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``fpga_carrier``
     - ``None``
   * - ``daughter_card``
     - ``None``
   * - ``vfilter``
     - ``None``
   * - ``vnot``
     - ``None``
   * - ``owner``
     - ``'adi'``
   * - ``repo``
     - ``'sdg-boot-partition'``
   * - ``filename``
     - ``'BOOT.BIN'``
   * - ``version``
     - ``None``
   * - ``api_token``
     - ``environment-derived``
   * - ``cache_path``
     - ``'~/.labgrid/cloudsmith_releases/'``

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

CyberPowerOutlet
~~~~~~~~~~~~~~~~

The CyberPowerOutlet describes a smart outlet controlled with CyberPower.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``address``
     - **required**
   * - ``outlet``
     - **required**
   * - ``delay``
     - ``5.0``

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

XilinxDeviceJTAG
~~~~~~~~~~~~~~~~

Xilinx FPGA device JTAG configuration.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``root_target``
     - ``1``
   * - ``microblaze_target``
     - ``3``
   * - ``bitstream_path``
     - ``None``
   * - ``kernel_path``
     - ``None``
   * - ``devicetree_path``
     - ``None``

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

XilinxVivadoTool
~~~~~~~~~~~~~~~~

Xilinx Vivado/Vitis tool installation configuration.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``vivado_path``
     - ``'/tools/Xilinx/2025.1/Vivado'``
   * - ``version``
     - ``None``
   * - ``xsdb_path``
     - ``None``

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          XilinxVivadoTool:
            vivado_path: /opt/Xilinx/2025.1/Vivado
            version: '2025.1'
            xsdb_path: /opt/Xilinx/2025.1/Vivado/bin/xsdb

TFTPServerResource
~~~~~~~~~~~~~~~~~~

Resource to configure or discover the TFTP server address.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``address``
     - ``'auto'``
   * - ``port``
     - ``3069``
   * - ``root``
     - ``'/var/lib/tftpboot'``

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

HomeAssistantOutlet
~~~~~~~~~~~~~~~~~~~

The HomeAssistantOutlet describes a switch/outlet controlled via Home Assistant REST API.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``url``
     - **required**
   * - ``token``
     - **required**
   * - ``entity_id``
     - **required**
   * - ``delay``
     - ``5.0``

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

TickArtifacts
~~~~~~~~~~~~~

Paths and names for the Tick runtime deploy.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``bitstream_path``
     - **required**
   * - ``overlay_dtbo_path``
     - **required**
   * - ``module_ko_path``
     - **required**
   * - ``firmware_name``
     - ``'tick.bit'``
   * - ``overlay_name``
     - ``'tick'``
   * - ``remote_dir``
     - ``'/tmp/tick'``

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

KasaOutlet
~~~~~~~~~~

The KasaOutlet describes a TP-Link Kasa smart plug or power strip.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``host``
     - **required**
   * - ``outlets``
     - ``None``
   * - ``username``
     - ``environment-derived``
   * - ``password``
     - ``environment-derived``
   * - ``delay``
     - ``5.0``

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
