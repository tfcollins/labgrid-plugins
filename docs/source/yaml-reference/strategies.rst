Strategies
==========

Canonical YAML arguments and bindings for every strategy registered by
``labgrid-plugins``.

.. important::

   Labgrid strategies are drivers. Configure them under ``targets.<name>.drivers``.
   A top-level or target-level ``strategies:`` mapping is invalid and will not create the
   strategy. All examples below use the correct structure and include ``imports``.

The examples use a ``RemotePlace`` because most strategies need board-specific native
resources (power, serial, JTAG, SD mux, or network service). The listed support drivers
show the binding shape; the acquired place must export matching resources. Paths used by
JTAG and recovery strategies are paths on the host which executes the corresponding
driver (normally the exporter).

BootFPGASoC
~~~~~~~~~~~

BootFPGASoC strategy for FPGA SoC devices using Kuiper releases.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``reached_linux_marker``
     - ``'analog'``
   * - ``update_image``
     - ``False``
   * - ``wait_for_linux_prompt_timeout``
     - ``60``
   * - ``wait_for_kernel_banner_timeout``
     - ``120``
   * - ``kernel_banner_retries``
     - ``1``
   * - ``restart_iiod_on_shell``
     - ``True``
   * - ``debug_write_boot_log``
     - ``False``

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol``
   * - ``shell``
     - ``ADIShellDriver``
   * - ``sdmux``
     - ``USBSDMuxDriver``
   * - ``mass_storage``
     - ``MassStorageDriver``
   * - ``image_writer``
     - ``USBStorageDriver`` (optional)
   * - ``kuiper``
     - ``CloudsmithDLDriver`` or ``KuiperDLDriver``

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          RemotePlace:
            name: example-place
        drivers:
          VesyncPowerDriver: {}
          USBSDMuxDriver: {}
          SerialDriver: {}
          ADIShellDriver:
            prompt: root@.*#
            login_prompt: 'login: '
            username: root
            password: analog
          KuiperDLDriver: {}
          MassStorageDriver: {}
          BootFPGASoC:
            reached_linux_marker: analog
            update_image: false
            wait_for_linux_prompt_timeout: 180
            wait_for_kernel_banner_timeout: 120
            kernel_banner_retries: 1
            restart_iiod_on_shell: true
            debug_write_boot_log: true

BootFPGASoCSSH
~~~~~~~~~~~~~~

Strategy to boot an FPGA SoC device using ShellDriver and SSHDriver.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``reached_linux_marker``
     - ``'analog'``
   * - ``wait_for_linux_prompt_timeout``
     - ``60``
   * - ``debug_write_boot_log``
     - ``False``
   * - ``ipv4_poll_timeout``
     - ``60.0``
   * - ``ipv4_poll_interval``
     - ``3.0``

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol`` (optional)
   * - ``shell``
     - ``ADIShellDriver``
   * - ``ssh``
     - ``SSHDriver``
   * - ``kuiper``
     - ``CloudsmithDLDriver`` or ``KuiperDLDriver`` (optional)

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          RemotePlace:
            name: example-place
        drivers:
          VesyncPowerDriver: {}
          SerialDriver: {}
          ADIShellDriver:
            prompt: root@.*#
            login_prompt: 'login: '
            username: root
            password: analog
          SSHDriver: {}
          KuiperDLDriver: {}
          BootFPGASoCSSH:
            reached_linux_marker: analog
            wait_for_linux_prompt_timeout: 180
            debug_write_boot_log: false
            ipv4_poll_timeout: 60.0
            ipv4_poll_interval: 3.0

BootTickFPGASSH
~~~~~~~~~~~~~~~

BootFPGASoCSSH + runtime Tick deploy (bitstream, overlay, module).

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``reached_linux_marker``
     - ``'analog'``
   * - ``wait_for_linux_prompt_timeout``
     - ``60``
   * - ``debug_write_boot_log``
     - ``False``
   * - ``ipv4_poll_timeout``
     - ``60.0``
   * - ``ipv4_poll_interval``
     - ``3.0``

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol`` (optional)
   * - ``shell``
     - ``ADIShellDriver``
   * - ``ssh``
     - ``SSHDriver``
   * - ``kuiper``
     - ``CloudsmithDLDriver`` or ``KuiperDLDriver`` (optional)
   * - ``tick_fpga``
     - ``TickFpgaManagerDriver``
   * - ``tick_overlay``
     - ``TickOverlayDriver``
   * - ``tick_module``
     - ``TickModuleDriver``

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          RemotePlace:
            name: example-place
        drivers:
          VesyncPowerDriver: {}
          SerialDriver: {}
          ADIShellDriver:
            prompt: root@.*#
            login_prompt: 'login: '
            username: root
            password: analog
          SSHDriver: {}
          TickFpgaManagerDriver: {}
          TickOverlayDriver: {}
          TickModuleDriver: {}
          BootTickFPGASSH:
            reached_linux_marker: analog
            wait_for_linux_prompt_timeout: 180
            ipv4_poll_timeout: 60.0
            ipv4_poll_interval: 3.0

BootSelMap
~~~~~~~~~~

BootSelMap - Strategy to boot SelMap based dual FPGA design.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``reached_linux_marker``
     - ``'analog'``
   * - ``ethernet_interface``
     - ``None``
   * - ``iio_jesd_driver_name``
     - ``'axi-ad9081-rx-hpc'``
   * - ``iio_jesd_data_mode``
     - ``'DATA'``
   * - ``iio_jesd_link_mode_attr``
     - ``'jesd204_fsm_state'``
   * - ``pre_boot_boot_files``
     - ``None``
   * - ``post_boot_boot_files``
     - ``None``
   * - ``target_dut_folder``
     - ``'/boot/ci'``
   * - ``local_kernel_filename``
     - ``None``
   * - ``local_device_tree_filename``
     - ``None``
   * - ``selmap_boot_script_name``
     - ``'selmap_dtbo.sh'``
   * - ``local_overlay_filename``
     - ``None``
   * - ``local_bitstream_filename``
     - ``None``
   * - ``pre_load_commands``
     - ``None``

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol``
   * - ``shell``
     - ``ADIShellDriver``
   * - ``ssh``
     - ``SSHDriver``

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          RemotePlace:
            name: example-place
        drivers:
          VesyncPowerDriver: {}
          SerialDriver: {}
          ADIShellDriver:
            prompt: root@.*#
            login_prompt: 'login: '
            username: root
            password: analog
          SSHDriver: {}
          BootSelMap:
            reached_linux_marker: analog
            ethernet_interface: eth0
            iio_jesd_driver_name: axi-ad9081-rx-hpc
            iio_jesd_data_mode: DATA
            iio_jesd_link_mode_attr: jesd204_fsm_state
            pre_boot_boot_files:
              Image: /boot/Image
            post_boot_boot_files:
              system.dtb: /boot/system.dtb
            target_dut_folder: /boot/ci
            local_kernel_filename: /srv/boot/Image
            local_device_tree_filename: /srv/boot/system.dtb
            selmap_boot_script_name: selmap_dtbo.sh
            local_overlay_filename: /srv/boot/vu11p.dtbo
            local_bitstream_filename: /srv/boot/vu11p.bin
            pre_load_commands:
              - systemctl stop iiod

BootFabric
~~~~~~~~~~

BootFabric - Strategy to boot logic-only Xilinx FPGAs with Microblaze.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``reached_boot_marker``
     - ``'login:'``
   * - ``wait_for_boot_timeout``
     - ``120``
   * - ``verify_iio_device``
     - ``None``
   * - ``trigger_dhcp_reset``
     - ``False``
   * - ``power_off_delay``
     - ``2``
   * - ``debug_write_boot_log``
     - ``False``

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol`` (optional)
   * - ``jtag``
     - ``XilinxJTAGDriver``
   * - ``shell``
     - ``ADIShellDriver`` (optional)
   * - ``ssh``
     - ``SSHDriver`` (optional)

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          RemotePlace:
            name: example-place
        drivers:
          VesyncPowerDriver: {}
          XilinxJTAGDriver: {}
          SerialDriver: {}
          ADIShellDriver:
            prompt: root@.*#
            login_prompt: 'login: '
            username: root
            password: analog
          BootFabric:
            reached_boot_marker: 'login:'
            wait_for_boot_timeout: 700
            verify_iio_device: axi-ad9081-rx-hpc
            trigger_dhcp_reset: true
            power_off_delay: 30
            debug_write_boot_log: true

BootFPGASoCTFTP
~~~~~~~~~~~~~~~

Strategy to boot an FPGA SoC device using ShellDriver and TFTP.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``reached_linux_marker``
     - ``'analog'``
   * - ``wait_for_linux_prompt_timeout``
     - ``60``
   * - ``wait_for_autoboot_prompt_timeout``
     - ``60``
   * - ``autoboot_banner_retries``
     - ``1``
   * - ``tftp_root_folder``
     - ``'/var/lib/tftpboot'``
   * - ``kernel_addr``
     - ``'0x30000000'``
   * - ``dtb_addr``
     - ``'0x2A000000'``
   * - ``bootargs``
     - ``'console=ttyPS0,115200 root=/dev/mmcblk0p2 rw earlycon earlyprintk rootfstype=ext4 rootwait'``
   * - ``uboot_prompt``
     - ``'ZynqMP>.*'``
   * - ``kernel_image_name``
     - ``'Image'``
   * - ``dtb_image_name``
     - ``'system.dtb'``
   * - ``boot_cmd``
     - ``'booti'``
   * - ``ps7_init_tcl``
     - ``None``
   * - ``uboot_elf``
     - ``None``
   * - ``fsbl_elf``
     - ``None``
   * - ``bitstream_path``
     - ``None``
   * - ``a9_target_name``
     - ``'*Cortex-A9 MPCore #0'``
   * - ``jtag_bootstrap_retries``
     - ``2``
   * - ``sd_autoboot``
     - ``False``
   * - ``ethaddr``
     - ``''``

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol``
   * - ``shell``
     - ``ADIShellDriver``
   * - ``ssh``
     - ``SSHDriver`` (optional)
   * - ``kuiper``
     - ``CloudsmithDLDriver`` or ``KuiperDLDriver`` (optional)
   * - ``jtag``
     - ``XilinxJTAGDriver`` (optional)
   * - ``tftp_server``
     - ``TFTPServerResource``
   * - ``tftp_driver``
     - ``TFTPServerDriver``

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          RemotePlace:
            name: example-place
        drivers:
          VesyncPowerDriver: {}
          XilinxJTAGDriver: {}
          SerialDriver: {}
          ADIShellDriver:
            prompt: root@.*#
            login_prompt: 'login: '
            username: root
            password: analog
          KuiperDLDriver: {}
          TFTPServerDriver: {}
          BootFPGASoCTFTP:
            reached_linux_marker: analog
            wait_for_linux_prompt_timeout: 240
            wait_for_autoboot_prompt_timeout: 60
            autoboot_banner_retries: 1
            tftp_root_folder: /var/lib/tftpboot
            kernel_addr: '0x30000000'
            dtb_addr: '0x2A000000'
            bootargs: console=ttyPS0,115200 root=/dev/mmcblk0p2 rw rootwait
            uboot_prompt: ZynqMP>.*
            kernel_image_name: Image
            dtb_image_name: system.dtb
            boot_cmd: booti
            ps7_init_tcl: /srv/jtag/ps7_init.tcl
            uboot_elf: /srv/jtag/u-boot.elf
            fsbl_elf: /srv/jtag/fsbl.elf
            bitstream_path: /srv/jtag/system.bit
            a9_target_name: '*Cortex-A9 MPCore #0'
            jtag_bootstrap_retries: 2
            sd_autoboot: false
            ethaddr: 02:00:00:00:00:01

SoftwareProvisioningStrategy
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Strategy to provision software on a target using SoftwareInstallerDriver.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``packages``
     - ``[]``
   * - ``repos``
     - ``[]``
   * - ``build_steps``
     - ``[]``
   * - ``test_steps``
     - ``[]``

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``installer``
     - ``SoftwareInstallerDriver``

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          RemotePlace:
            name: example-place
        drivers:
          SSHDriver: {}
          SoftwareInstallerDriver: {}
          SoftwareProvisioningStrategy:
            packages:
              - git
              - cmake
            repos:
              - url: https://github.com/analogdevicesinc/libiio
                dest: /opt/libiio
                branch: main
            build_steps:
              - cmd: cmake -S . -B build && cmake --build build
                dir: /opt/libiio
            test_steps:
              - cmd: ctest --test-dir build
                dir: /opt/libiio

BootRPI
~~~~~~~

Strategy to manage Raspberry Pi devices primarily via SSH.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``ssh_boot_timeout``
     - ``120``
   * - ``power_off_delay``
     - ``2``

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``ssh``
     - ``SSHDriver``
   * - ``power``
     - ``PowerProtocol`` (optional)
   * - ``shell``
     - ``ADIShellDriver`` (optional)
   * - ``sdmux``
     - ``USBSDMuxDriver`` (optional)

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          RemotePlace:
            name: example-place
        drivers:
          VesyncPowerDriver: {}
          SSHDriver: {}
          BootRPI:
            ssh_boot_timeout: 120
            power_off_delay: 2

BootVPK180
~~~~~~~~~~

Boot strategy for AMD Versal Premium VPK180 with a Zynq system controller.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``reached_linux_marker``
     - ``'analog'``
   * - ``kernel_banner_pattern``
     - ``'Starting kernel'``
   * - ``sc_commands``
     - ``[]``
   * - ``wait_for_sc_command_timeout``
     - ``30``
   * - ``wait_for_kernel_banner_timeout``
     - ``120``
   * - ``wait_for_linux_prompt_timeout``
     - ``60``
   * - ``sc_login_retries``
     - ``3``
   * - ``sc_command_retries``
     - ``3``
   * - ``kernel_banner_retries``
     - ``3``
   * - ``update_image``
     - ``False``
   * - ``update_boot_files``
     - ``False``
   * - ``boot_partition_path``
     - ``'/boot'``
   * - ``ssh_reboot_command``
     - ``'sudo reboot'``
   * - ``warm_boot_if_sc_alive``
     - ``True``
   * - ``warm_probe_timeout``
     - ``3``
   * - ``debug_write_boot_log``
     - ``False``

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol``
   * - ``sc_shell``
     - ``ADIShellDriver``
   * - ``target_shell``
     - ``ADIShellDriver``
   * - ``sdmux``
     - ``USBSDMuxDriver`` (optional)
   * - ``mass_storage``
     - ``MassStorageDriver`` (optional)
   * - ``image_writer``
     - ``USBStorageDriver`` (optional)
   * - ``kuiper``
     - ``KuiperDLDriver`` (optional)
   * - ``ssh``
     - ``SSHDriver`` (optional)

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          RemotePlace:
            name: example-place
        drivers:
          VesyncPowerDriver: {}
          SerialDriver@sc-console: {}
          ADIShellDriver@sc-shell:
            bindings:
              console: sc-console
            prompt: root@.*#
            login_prompt: 'login: '
            username: root
            password: analog
          SerialDriver@target-console: {}
          ADIShellDriver@target-shell:
            bindings:
              console: target-console
            prompt: root@.*#
            login_prompt: 'login: '
            username: root
            password: analog
          SSHDriver: {}
          BootVPK180:
            bindings:
              sc_shell: sc-shell
              target_shell: target-shell
            reached_linux_marker: root@
            kernel_banner_pattern: Starting kernel
            sc_commands:
              - bootmode sd1
              - reset
            wait_for_sc_command_timeout: 30
            wait_for_kernel_banner_timeout: 120
            wait_for_linux_prompt_timeout: 240
            sc_login_retries: 3
            sc_command_retries: 3
            kernel_banner_retries: 3
            update_image: false
            update_boot_files: false
            boot_partition_path: /boot
            ssh_reboot_command: sudo reboot
            warm_boot_if_sc_alive: true
            warm_probe_timeout: 3
            debug_write_boot_log: true

BootZynq7000JTAGRecovery
~~~~~~~~~~~~~~~~~~~~~~~~

Recover a Zynq-7000 board with a corrupted SD card.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``ps7_init_tcl``
     - ``None``
   * - ``uboot_elf``
     - ``None``
   * - ``fsbl_elf``
     - ``None``
   * - ``bitstream_path``
     - ``None``
   * - ``a9_target_name``
     - ``'*Cortex-A9 MPCore #0'``
   * - ``recovery_kernel``
     - ``None``
   * - ``recovery_dtb``
     - ``None``
   * - ``recovery_initramfs``
     - ``'uInitrd.recovery'``
   * - ``recovery_login_marker``
     - ``'recovery login:'``
   * - ``sd_image_url``
     - ``None``
   * - ``sd_device``
     - ``'/dev/mmcblk0'``
   * - ``download_cmd_template``
     - ``'wget -q -O - "{url}"'``
   * - ``board_variant``
     - ``None``
   * - ``board_variant_files``
     - ``('BOOT.BIN', 'uImage', 'devicetree.dtb')``
   * - ``board_variant_paths``
     - ``None``
   * - ``sd_boot_partition``
     - ``1``
   * - ``sd_mount_point``
     - ``'/mnt'``
   * - ``post_flash_commands``
     - ``[]``
   * - ``post_flash_timeout``
     - ``120``
   * - ``auto_build_initramfs``
     - ``True``
   * - ``auto_serve_http``
     - ``True``
   * - ``busybox_static_path``
     - ``None``
   * - ``busybox_source_url``
     - ``None``
   * - ``cross_compile``
     - ``None``
   * - ``recovery_cache_dir``
     - ``None``
   * - ``sd_image_path``
     - ``None``
   * - ``http_serve_port``
     - ``0``
   * - ``http_serve_address``
     - ``None``
   * - ``uboot_prompt``
     - ``'zynq-uboot>|U-Boot>|=>'``
   * - ``kernel_addr``
     - ``'0x2080000'``
   * - ``dtb_addr``
     - ``'0x2000000'``
   * - ``initramfs_addr``
     - ``'0x4000000'``
   * - ``bootargs``
     - ``'console=ttyPS0,115200 earlyprintk loglevel=8 rdinit=/init'``
   * - ``jtag_bootstrap_retries``
     - ``2``
   * - ``wait_for_uboot_prompt_timeout``
     - ``60``
   * - ``wait_for_recovery_linux_timeout``
     - ``180``
   * - ``wait_for_sd_flash_timeout``
     - ``1800``
   * - ``verify_kernel_name``
     - ``'uImage'``
   * - ``verify_dtb_name``
     - ``'devicetree.dtb'``
   * - ``verify_bootargs``
     - ``'console=ttyPS0,115200 root=/dev/mmcblk0p2 rw earlyprintk rootfstype=ext4 rootwait'``
   * - ``verify_boot_login_marker``
     - ``'(analog|raspberrypi|kuiper).*login:'``
   * - ``wait_for_verify_boot_timeout``
     - ``180``

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol``
   * - ``jtag``
     - ``XilinxJTAGDriver``
   * - ``shell``
     - ``ADIShellDriver``
   * - ``tftp_server``
     - ``TFTPServerResource``
   * - ``tftp_driver``
     - ``TFTPServerDriver``
   * - ``ssh``
     - ``SSHDriver`` (optional)

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          RemotePlace:
            name: example-place
        drivers:
          VesyncPowerDriver: {}
          XilinxJTAGDriver: {}
          SerialDriver: {}
          ADIShellDriver:
            prompt: root@.*#
            login_prompt: 'login: '
            username: root
            password: analog
          TFTPServerDriver: {}
          BootZynq7000JTAGRecovery:
            ps7_init_tcl: /srv/recovery/ps7_init.tcl
            uboot_elf: /srv/recovery/u-boot.elf
            recovery_kernel: zImage.recovery
            recovery_dtb: system.recovery.dtb
            sd_image_path: /srv/images/kuiper.img
            board_variant: zynq-zc706-adv7511-ad9361-fmcomms2-3
            wait_for_recovery_linux_timeout: 240
            wait_for_sd_flash_timeout: 1800
            wait_for_verify_boot_timeout: 180

BootNoOSJTAG
~~~~~~~~~~~~

Load and run a no-os firmware ELF on a Zynq-7000 board via JTAG.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``firmware_elf``
     - ``None``
   * - ``bitstream_path``
     - ``None``
   * - ``ps7_init_tcl``
     - ``None``
   * - ``a9_target_name``
     - ``'*Cortex-A9 MPCore #0'``
   * - ``boot_marker``
     - ``'Successfully initialized'``
   * - ``boot_timeout``
     - ``60``
   * - ``power_settle_time``
     - ``2``

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol``
   * - ``jtag``
     - ``XilinxJTAGDriver``
   * - ``shell``
     - ``ADIShellDriver``

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          RemotePlace:
            name: example-place
        drivers:
          VesyncPowerDriver: {}
          XilinxJTAGDriver: {}
          SerialDriver: {}
          ADIShellDriver:
            prompt: root@.*#
            login_prompt: 'login: '
            username: root
            password: analog
          BootNoOSJTAG:
            firmware_elf: /srv/no-os/app.elf
            bitstream_path: /srv/no-os/system.bit
            ps7_init_tcl: /srv/no-os/ps7_init.tcl
            a9_target_name: '*Cortex-A9 MPCore #0'
            boot_marker: Successfully initialized
            boot_timeout: 60
            power_settle_time: 2

ReflashVPK180SD
~~~~~~~~~~~~~~~

Re-image the VPK180's Versal SD card from a Kuiper release via QSPI rescue.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``sc_to_qspi_commands``
     - ``factory value``
   * - ``sc_to_sd_commands``
     - ``factory value``
   * - ``recovery_kernel_banner_pattern``
     - ``'Starting kernel'``
   * - ``tftp_image_filename``
     - ``'kuiper.img'``
   * - ``target_sd_device``
     - ``'/dev/mmcblk0'``
   * - ``dd_block_size``
     - ``'4M'``
   * - ``dd_command_template``
     - ``'set -o pipefail; tftp -g -r {filename} -l - {server_ip} {server_port} | dd of={dev} bs={bs} status=progress conv=fsync'``
   * - ``dd_timeout``
     - ``1800``
   * - ``dd_retries``
     - ``1``
   * - ``verify_after_write``
     - ``False``
   * - ``verify_command_template``
     - ``'tftp -g -r {filename} -l - {server_ip} {server_port} | head -c $(blockdev --getsize64 {dev}) | sha256sum'``
   * - ``stage_method``
     - ``'symlink'``
   * - ``sc_login_retries``
     - ``3``
   * - ``sc_command_retries``
     - ``3``
   * - ``recovery_banner_retries``
     - ``3``
   * - ``wait_for_sc_command_timeout``
     - ``30``
   * - ``wait_for_recovery_banner_timeout``
     - ``120``
   * - ``wait_for_recovery_login_timeout``
     - ``60``
   * - ``power_off_when_done``
     - ``True``
   * - ``restore_sd_bootmode``
     - ``True``
   * - ``debug_write_uart_log``
     - ``False``

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol``
   * - ``sc_shell``
     - ``ADIShellDriver``
   * - ``target_shell``
     - ``ADIShellDriver``
   * - ``kuiper``
     - ``KuiperDLDriver``
   * - ``tftp``
     - ``TFTPServerDriver``

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          RemotePlace:
            name: example-place
        drivers:
          VesyncPowerDriver: {}
          SerialDriver@sc-console: {}
          ADIShellDriver@sc-shell:
            bindings:
              console: sc-console
            prompt: root@.*#
            login_prompt: 'login: '
            username: root
            password: analog
          SerialDriver@target-console: {}
          ADIShellDriver@target-shell:
            bindings:
              console: target-console
            prompt: root@.*#
            login_prompt: 'login: '
            username: root
            password: analog
          KuiperDLDriver: {}
          TFTPServerDriver: {}
          ReflashVPK180SD:
            bindings:
              sc_shell: sc-shell
              target_shell: target-shell
            tftp_image_filename: kuiper.img
            target_sd_device: /dev/mmcblk0
            dd_block_size: 4M
            dd_timeout: 1800
            dd_retries: 1
            verify_after_write: true
            stage_method: symlink
            power_off_when_done: true
            restore_sd_bootmode: true
            debug_write_uart_log: true

BootZynqMPJTAG
~~~~~~~~~~~~~~

Bring up a ZynqMP board over JTAG via the mini U-Boot SPL.

**Arguments**

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Argument
     - Requirement / default
   * - ``psu_init_tcl``
     - ``None``
   * - ``spl_elf``
     - ``None``
   * - ``bitstream_path``
     - ``None``
   * - ``pmufw_bin``
     - ``None``
   * - ``uboot_bin``
     - ``None``
   * - ``handoff_bin``
     - ``None``
   * - ``bl31_bin``
     - ``None``
   * - ``atf_handoff_bin``
     - ``None``
   * - ``pm_config_bin``
     - ``None``
   * - ``bl31_console_uart_base``
     - ``None``
   * - ``bl31_console_ref_ctrl_address``
     - ``None``
   * - ``bl31_console_reset_mask``
     - ``'0x2'``
   * - ``ddr_scrub_elf``
     - ``None``
   * - ``recovery_trampoline_elf``
     - ``None``
   * - ``recovery_kernel_image``
     - ``None``
   * - ``recovery_initramfs``
     - ``None``
   * - ``recovery_dtb``
     - ``None``
   * - ``recovery_marker``
     - ``'RECOVERY_READY'``
   * - ``recovery_prompt``
     - ``'root@zu11eg-recovery:.*#'``
   * - ``recovery_timeout``
     - ``180``
   * - ``recovery_ddr_scrub_elf``
     - ``None``
   * - ``ddr_scrub_done_address``
     - ``None``
   * - ``recovery_ddr_scrub_done_address``
     - ``None``
   * - ``recovery_ddr_scrub_settle_ms``
     - ``30000``
   * - ``recovery_bitstream_path``
     - ``None``
   * - ``recovery_post_init_mask_writes``
     - ``[]``
   * - ``sd_image_url``
     - ``None``
   * - ``sd_device``
     - ``'/dev/mmcblk0'``
   * - ``sd_download_cmd_template``
     - ``'wget -O - "{url}"'``
   * - ``sd_flash_timeout``
     - ``3600``
   * - ``sd_image_size``
     - ``None``
   * - ``sd_head_sha256``
     - ``None``
   * - ``sd_tail_sha256``
     - ``None``
   * - ``sd_sample_bytes``
     - ``1048576``
   * - ``post_flash_commands``
     - ``[]``
   * - ``post_flash_timeout``
     - ``180``
   * - ``production_uboot_prompt``
     - ``'ZynqMP>'``
   * - ``production_prompt_timeout``
     - ``60``
   * - ``sd_boot_command``
     - ``'setenv partid 1; run sdboot'``
   * - ``kuiper_kernel_marker``
     - ``'Starting kernel'``
   * - ``kuiper_shell_marker``
     - ``'root@analog:.*#'``
   * - ``kuiper_boot_timeout``
     - ``300``
   * - ``kuiper_verify_timeout``
     - ``120``
   * - ``kuiper_verify_commands``
     - ``factory value``
   * - ``a53_target_name``
     - ``'*Cortex-A53*#0*'``
   * - ``apu_release_rst_value``
     - ``'0x380E'``
   * - ``dcc_log_path``
     - ``None``
   * - ``spl_settle_ms``
     - ``12000``
   * - ``production_settle_ms``
     - ``12000``
   * - ``pmufw_timeout_ms``
     - ``10000``
   * - ``ddr_scrub_settle_ms``
     - ``30000``
   * - ``jtag_url``
     - ``'TCP:127.0.0.1:3121'``
   * - ``serial_host_override``
     - ``None``
   * - ``serial_protocol_override``
     - ``None``
   * - ``power_off_settle_s``
     - ``5``
   * - ``power_on_settle_s``
     - ``8``

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol``
   * - ``jtag``
     - ``XilinxJTAGDriver``
   * - ``shell``
     - ``ADIShellDriver`` (optional)

**Example**

.. code-block:: yaml

    imports:
      - adi_lg_plugins
    targets:
      main:
        resources:
          RemotePlace:
            name: example-place
        drivers:
          VesyncPowerDriver: {}
          XilinxJTAGDriver: {}
          SerialDriver: {}
          ADIShellDriver:
            prompt: root@.*#
            login_prompt: 'login: '
            username: root
            password: analog
          BootZynqMPJTAG:
            psu_init_tcl: /srv/recovery/psu_init.tcl
            spl_elf: /srv/recovery/spl.elf
            pmufw_bin: /srv/recovery/pmufw.bin
            uboot_bin: /srv/recovery/u-boot.bin
            handoff_bin: /srv/recovery/handoff.bin
            bl31_bin: /srv/recovery/bl31.bin
            atf_handoff_bin: /srv/recovery/atf-handoff.bin
            pm_config_bin: /srv/recovery/pm-config.bin
            bitstream_path: /srv/recovery/system_top.bit
            ddr_scrub_elf: /srv/recovery/ddr-scrub.elf
            ddr_scrub_done_address: '0xFFFC0054'
            jtag_url: TCP:127.0.0.1:3121
            production_uboot_prompt: ZynqMP>
            sd_boot_command: setenv partid 1; run sdboot
            kuiper_shell_marker: root@analog:.*#
            kuiper_boot_timeout: 300
