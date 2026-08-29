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
   :widths: 22 23 55

   * - Argument
     - Requirement/default
     - Description and example
   * - ``address``
     - **required**
     - Hostname or IP address contacted over SNMP.
       For example,
       ``pdu.example.test``.
   * - ``outlet``
     - **required**
     - PDU outlet number appended to the APC control and status OIDs.
       For example,
       ``6``.
   * - ``delay``
     - ``5.0``
     - Seconds to wait between switching off and on during a reset or cycle.
       For example, ``5.0``.
   * - ``read_community``
     - ``'public'``
     - SNMP community used to read outlet status.
       For example, ``public``.
   * - ``write_community``
     - ``'private'``
     - SNMP community used to send outlet-control commands.
       For example,
       ``private``.

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
   :widths: 22 23 55

   * - Argument
     - Requirement/default
     - Description and example
   * - ``outlet_names``
     - **required**
     - Comma-separated VeSync device names; every named outlet is controlled.
       For example, ``Device Power,USB Hub``.
   * - ``username``
     - **required**
     - Email address used to log in to the VeSync account.
       For example,
       ``user@example.test``.
   * - ``password``
     - **required**
     - Password used to log in to the VeSync account.
       For example, ``secret``.
   * - ``delay``
     - ``5.0``
     - Seconds to wait between switching off and on during a reset or cycle.
       For example, ``5.0``.

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
   :widths: 22 23 55

   * - Argument
     - Requirement/default
     - Description and example
   * - ``path``
     - **required**
     - Device or partition path mounted by the mass-storage driver on its host.
       For example, ``/dev/disk/by-partuuid/0123-4567``.
   * - ``file_updates``
     - ``{}``
     - Mapping from source files on the runner to destinations relative to the
       mounted filesystem.
       For example, ``{'/srv/boot/Image': 'Image'}``.
   * - ``use_with_sdmux``
     - ``False``
     - Signals that a strategy should coordinate this device with a USB SD mux.
       For example, ``true``.

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
              /srv/boot/BOOT.BIN: BOOT.BIN
              /srv/boot/Image: Image
            use_with_sdmux: true

KuiperRelease
~~~~~~~~~~~~~

The KuiperRelease describes a Kuiper release resource.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 22 23 55

   * - Argument
     - Requirement/default
     - Description and example
   * - ``release_version``
     - **required**
     - Kuiper release identifier used for lookup, download, and cache indexing.
       For example, ``2023_R2_P1``.
   * - ``cache_path``
     - ``'~/.labgrid/kuiper_releases/'``
     - Directory for downloaded images, cache metadata, and extracted boot files.
       For example, ``/var/cache/labgrid/kuiper``.
   * - ``kernel_path``
     - ``None``
     - Local kernel path, or ``release:`` path to extract from the image; unset skips
       it.
       For example, ``release:zynqmp-common/Image``.
   * - ``BOOTBIN_path``
     - ``None``
     - Local BOOT.BIN path, or ``release:`` path to extract from the image; unset
       skips it.
       For example, ``release:zynqmp-zcu102-rev10-ad9081/BOOT.BIN``.
   * - ``device_tree_path``
     - ``None``
     - Local DTB path, or ``release:`` path to extract from the image; unset skips
       it.
       For example, ``release:zynqmp-zcu102-rev10-ad9081/system.dtb``.

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
   :widths: 22 23 55

   * - Argument
     - Requirement/default
     - Description and example
   * - ``fpga_carrier``
     - ``None``
     - Carrier term used to narrow the package version search and parsed matches.
       For example, ``zcu102``.
   * - ``daughter_card``
     - ``None``
     - Daughter-card term used to narrow the package version search.
       For example,
       ``adrv9009``.
   * - ``vfilter``
     - ``None``
     - String or list of terms that each add an inclusive version filter.
       For example, ``['main', 'linux']``.
   * - ``vnot``
     - ``None``
     - String or list of terms that each add an exclusion version filter.
       For example, ``['deprecated']``.
   * - ``owner``
     - ``'adi'``
     - Cloudsmith owner or organization containing the repository.
       For example,
       ``adi``.
   * - ``repo``
     - ``'sdg-boot-partition'``
     - Cloudsmith repository searched for the artifact.
       For example,
       ``sdg-boot-partition``.
   * - ``filename``
     - ``'BOOT.BIN'``
     - Artifact filename included in the package query and local download path.
       For example, ``BOOT.BIN``.
   * - ``version``
     - ``None``
     - Exact package version to select; unset selects the newest uploaded match.
       For example, ``2025.1.0``.
   * - ``api_token``
     - ``environment-derived``
     - Cloudsmith bearer token, defaulting to ``CLOUDSMITH_API_TOKEN``.
       For example,
       ``${CLOUDSMITH_API_TOKEN}``.
   * - ``cache_path``
     - ``'~/.labgrid/cloudsmith_releases/'``
     - Directory for downloaded artifacts and cache metadata.
       For example,
       ``~/.labgrid/cloudsmith_releases/``.

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
   :widths: 22 23 55

   * - Argument
     - Requirement/default
     - Description and example
   * - ``address``
     - **required**
     - Hostname or IP address contacted over SNMP.
       For example,
       ``pdu.example.test``.
   * - ``outlet``
     - **required**
     - PDU outlet number appended to the CyberPower control OID.
       For example,
       ``3``.
   * - ``delay``
     - ``5.0``
     - Seconds to wait between switching off and on during a reset or cycle.
       For example, ``5.0``.

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
   :widths: 22 23 55

   * - Argument
     - Requirement/default
     - Description and example
   * - ``root_target``
     - ``1``
     - xsdb target ID selected before programming the FPGA fabric.
       For example,
       ``1``.
   * - ``microblaze_target``
     - ``3``
     - xsdb target ID selected to download and start the MicroBlaze kernel.
       For example, ``3``.
   * - ``bitstream_path``
     - ``None``
     - Bitstream path as seen by the host running xsdb.
       For example,
       ``/srv/images/system_top.bit``.
   * - ``kernel_path``
     - ``None``
     - MicroBlaze kernel path as seen by the host running xsdb.
       For example,
       ``/srv/images/simpleImage.vcu118.strip``.
   * - ``devicetree_path``
     - ``None``
     - Standalone DTB path retained for workflows whose kernel does not embed it.
       For example, ``/srv/images/system.dtb``.

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
   :widths: 22 23 55

   * - Argument
     - Requirement/default
     - Description and example
   * - ``vivado_path``
     - ``'/tools/Xilinx/2025.1/Vivado'``
     - Vivado installation root used to derive the sibling Vitis xsdb path.
       For example, ``/opt/Xilinx/2025.1/Vivado``.
   * - ``version``
     - ``None``
     - Informational Vivado version string; the resource does not probe it.
       For example, ``2025.1``.
   * - ``xsdb_path``
     - ``None``
     - xsdb executable used by the JTAG driver; unset derives it from
       ``vivado_path``.
       For example, ``/opt/Xilinx/2025.1/Vitis/bin/xsdb``.

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
   :widths: 22 23 55

   * - Argument
     - Requirement/default
     - Description and example
   * - ``address``
     - ``'auto'``
     - IP address to bind; ``auto`` discovers the outbound local IP and falls back
       to loopback.
       For example, ``192.0.2.10``.
   * - ``port``
     - ``3069``
     - UDP port on which the built-in TFTP server listens.
       For example, ``3069``.
   * - ``root``
     - ``'/var/lib/tftpboot'``
     - Host directory created if needed and used as the read-only TFTP root.
       For example, ``/var/lib/tftpboot``.

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
   :widths: 22 23 55

   * - Argument
     - Requirement/default
     - Description and example
   * - ``url``
     - **required**
     - Base URL used for Home Assistant REST API requests.
       For example,
       ``http://homeassistant.example.test:8123``.
   * - ``token``
     - **required**
     - Long-lived token sent as the REST API bearer credential.
       For example,
       ``${HOME_ASSISTANT_TOKEN}``.
   * - ``entity_id``
     - **required**
     - Entity passed to its domain's turn-on, turn-off, and state endpoints.
       For example, ``switch.lab_outlet_1``.
   * - ``delay``
     - ``5.0``
     - Seconds to wait between switching off and on during a reset or cycle.
       For example, ``5.0``.

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
   :widths: 22 23 55

   * - Argument
     - Requirement/default
     - Description and example
   * - ``bitstream_path``
     - **required**
     - Runner-side ``.bit`` staged into the target firmware directory.
       For example,
       ``/run/tick/system.bit``.
   * - ``overlay_dtbo_path``
     - **required**
     - Runner-side ``.dtbo`` staged and applied through configfs.
       For example,
       ``/run/tick/tick.dtbo``.
   * - ``module_ko_path``
     - **required**
     - Runner-side kernel module staged and inserted on the target.
       For example,
       ``/run/tick/axi_timed_command_scheduler.ko``.
   * - ``firmware_name``
     - ``'tick.bit'``
     - Filename used under ``/lib/firmware`` and passed to fpga_manager.
       For example, ``tick.bit``.
   * - ``overlay_name``
     - ``'tick'``
     - configfs overlay directory name and staged DTBO basename.
       For example,
       ``tick``.
   * - ``remote_dir``
     - ``'/tmp/tick'``
     - Target-side scratch directory for the staged DTBO and kernel module.
       For example, ``/tmp/tick``.

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
   :widths: 22 23 55

   * - Argument
     - Requirement/default
     - Description and example
   * - ``host``
     - **required**
     - Hostname or IP address used for local Kasa device discovery.
       For example,
       ``kasa-plug.example.test``.
   * - ``outlets``
     - ``None``
     - Comma-separated child aliases or zero-based indexes; unset controls every
       strip socket or the single plug.
       For example, ``Bench DUT,1``.
   * - ``username``
     - ``environment-derived``
     - TP-Link account email, defaulting to ``KASA_USERNAME`` when needed.
       For example, ``${KASA_USERNAME}``.
   * - ``password``
     - ``environment-derived``
     - TP-Link account password, defaulting to ``KASA_PASSWORD`` when needed.
       For example, ``${KASA_PASSWORD}``.
   * - ``delay``
     - ``5.0``
     - Seconds to wait between switching off and on during a reset or cycle.
       For example, ``5.0``.

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
