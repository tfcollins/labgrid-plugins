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
   :widths: 24 24 52

   * - Argument
     - Requirement/default
     - Description and example
   * - ``reached_linux_marker``
     - ``'analog'``
     - Console pattern that confirms Linux has reached the expected login or shell text. For
       example, ``root@analog``.
   * - ``update_image``
     - ``False``
     - Enables writing the complete Kuiper disk image instead of only using the existing media. For
       example, ``true``.
   * - ``wait_for_linux_prompt_timeout``
     - ``60``
     - Maximum seconds to wait for the configured Linux marker after the kernel starts. For example,
       ``180``.
   * - ``wait_for_kernel_banner_timeout``
     - ``120``
     - Maximum seconds to wait after power-on for the kernel-start banner. For example, ``120``.
   * - ``kernel_banner_retries``
     - ``1``
     - Number of cold-cycle retries after a kernel-banner timeout, in addition to the first attempt.
       For example, ``2``.
   * - ``restart_iiod_on_shell``
     - ``True``
     - Restarts iiod after the shell is ready so it discovers devices that probed late. For example,
       ``true``.
   * - ``debug_write_boot_log``
     - ``False``
     - Writes captured UART boot output to a local debug log when enabled. For example, ``true``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol`` — controls board power for cold cycles and shutdown states.
   * - ``shell``
     - ``ADIShellDriver`` — drives the serial console, watches boot markers, and provides target
       shell commands.
   * - ``sdmux``
     - ``USBSDMuxDriver`` — switches the removable SD card between the host and DUT.
   * - ``mass_storage``
     - ``MassStorageDriver`` — mounts the host-visible SD partition and copies boot files.
   * - ``image_writer``
     - ``USBStorageDriver`` (optional) — writes a complete disk image to host-visible USB storage.
   * - ``kuiper``
     - ``CloudsmithDLDriver`` or ``KuiperDLDriver`` — downloads or exposes Kuiper images and
       extracted boot files.

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
   :widths: 24 24 52

   * - Argument
     - Requirement/default
     - Description and example
   * - ``reached_linux_marker``
     - ``'analog'``
     - Console pattern that confirms Linux has reached the expected login or shell text. For
       example, ``root@analog``.
   * - ``wait_for_linux_prompt_timeout``
     - ``60``
     - Maximum seconds to wait for the configured Linux marker after the kernel starts. For example,
       ``180``.
   * - ``debug_write_boot_log``
     - ``False``
     - Writes captured UART boot output to a local debug log when enabled. For example, ``true``.
   * - ``ipv4_poll_timeout``
     - ``60.0``
     - Maximum seconds to poll the DUT for an IPv4 address before SSH file updates. For example,
       ``90.0``.
   * - ``ipv4_poll_interval``
     - ``3.0``
     - Delay in seconds between IPv4-address polling attempts. For example, ``2.0``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol`` (optional) — controls board power for cold cycles and shutdown states.
   * - ``shell``
     - ``ADIShellDriver`` — drives the serial console, watches boot markers, and provides target
       shell commands.
   * - ``ssh``
     - ``SSHDriver`` — transfers files or runs commands over the booted target network.
   * - ``kuiper``
     - ``CloudsmithDLDriver`` or ``KuiperDLDriver`` (optional) — downloads or exposes Kuiper images
       and extracted boot files.

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
   :widths: 24 24 52

   * - Argument
     - Requirement/default
     - Description and example
   * - ``reached_linux_marker``
     - ``'analog'``
     - Console pattern that confirms Linux has reached the expected login or shell text. For
       example, ``root@analog``.
   * - ``wait_for_linux_prompt_timeout``
     - ``60``
     - Maximum seconds to wait for the configured Linux marker after the kernel starts. For example,
       ``180``.
   * - ``debug_write_boot_log``
     - ``False``
     - Writes captured UART boot output to a local debug log when enabled. For example, ``true``.
   * - ``ipv4_poll_timeout``
     - ``60.0``
     - Maximum seconds to poll the DUT for an IPv4 address before SSH file updates. For example,
       ``90.0``.
   * - ``ipv4_poll_interval``
     - ``3.0``
     - Delay in seconds between IPv4-address polling attempts. For example, ``2.0``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol`` (optional) — controls board power for cold cycles and shutdown states.
   * - ``shell``
     - ``ADIShellDriver`` — drives the serial console, watches boot markers, and provides target
       shell commands.
   * - ``ssh``
     - ``SSHDriver`` — transfers files or runs commands over the booted target network.
   * - ``kuiper``
     - ``CloudsmithDLDriver`` or ``KuiperDLDriver`` (optional) — downloads or exposes Kuiper images
       and extracted boot files.
   * - ``tick_fpga``
     - ``TickFpgaManagerDriver`` — loads the Tick FPGA bitstream through Linux fpga_manager.
   * - ``tick_overlay``
     - ``TickOverlayDriver`` — applies the Tick device-tree overlay through configfs.
   * - ``tick_module``
     - ``TickModuleDriver`` — loads the Tick kernel module and refreshes dependent services.

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
   :widths: 24 24 52

   * - Argument
     - Requirement/default
     - Description and example
   * - ``reached_linux_marker``
     - ``'analog'``
     - Console pattern that confirms Linux has reached the expected login or shell text. For
       example, ``root@analog``.
   * - ``ethernet_interface``
     - ``None``
     - Interface whose address is copied into the SSH provider before file transfer. For example,
       ``eth0``.
   * - ``iio_jesd_driver_name``
     - ``'axi-ad9081-rx-hpc'``
     - IIO device name polled to determine whether the secondary FPGA JESD design appeared. For
       example, ``axi-ad9081-rx-hpc``.
   * - ``iio_jesd_data_mode``
     - ``'DATA'``
     - Expected JESD link data-mode value used to validate the secondary FPGA. For example,
       ``DATA``.
   * - ``iio_jesd_link_mode_attr``
     - ``'jesd204_fsm_state'``
     - IIO attribute read to inspect the JESD link state. For example, ``jesd204_fsm_state``.
   * - ``pre_boot_boot_files``
     - ``None``
     - Mapping of host files to DUT paths copied before rebooting the primary Zynq. For example,
       ``{/srv/Image: /boot/Image}``.
   * - ``post_boot_boot_files``
     - ``None``
     - Mapping of extra host files to DUT paths copied for the secondary FPGA boot. For example,
       ``{/srv/vu11p.bin: /boot/ci/vu11p.bin}``.
   * - ``target_dut_folder``
     - ``'/boot/ci'``
     - DUT directory that receives the SelectMAP script, overlay, and bitstream. For example,
       ``/boot/ci``.
   * - ``local_kernel_filename``
     - ``None``
     - Host path of an optional replacement Zynq kernel copied into /boot. For example,
       ``/srv/boot/Image``.
   * - ``local_device_tree_filename``
     - ``None``
     - Host path of an optional replacement Zynq device tree copied into /boot. For example,
       ``/srv/boot/system.dtb``.
   * - ``selmap_boot_script_name``
     - ``'selmap_dtbo.sh'``
     - Declared SelectMAP helper-script name; the current trigger command still invokes
       ``selmap_dtbo.sh`` directly. For example, ``selmap_dtbo.sh``.
   * - ``local_overlay_filename``
     - ``None``
     - Host path of the device-tree overlay applied for the secondary FPGA. For example,
       ``/srv/boot/vu11p.dtbo``.
   * - ``local_bitstream_filename``
     - ``None``
     - Host path of the secondary-FPGA binary loaded through SelectMAP. For example,
       ``/srv/boot/vu11p.bin``.
   * - ``pre_load_commands``
     - ``None``
     - Command or ordered commands run over SSH immediately before invoking the SelectMAP script.
       For example, ``[systemctl stop iiod]``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol`` — controls board power for cold cycles and shutdown states.
   * - ``shell``
     - ``ADIShellDriver`` — drives the serial console, watches boot markers, and provides target
       shell commands.
   * - ``ssh``
     - ``SSHDriver`` — transfers files or runs commands over the booted target network.

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
   :widths: 24 24 52

   * - Argument
     - Requirement/default
     - Description and example
   * - ``reached_boot_marker``
     - ``'login:'``
     - Console pattern that marks completion of the fabric/MicroBlaze boot. For example, ``buildroot
       login``.
   * - ``wait_for_boot_timeout``
     - ``120``
     - Maximum seconds to wait for the fabric boot marker. For example, ``700``.
   * - ``verify_iio_device``
     - ``None``
     - Optional IIO device name checked after boot; no check is made when unset. For example,
       ``axi-ad9081-rx-hpc``.
   * - ``trigger_dhcp_reset``
     - ``False``
     - Runs the strategy DHCP-reset path after boot so the target obtains a fresh lease. For
       example, ``true``.
   * - ``power_off_delay``
     - ``2``
     - Seconds to wait after switching power off before continuing. For example, ``5``.
   * - ``debug_write_boot_log``
     - ``False``
     - Writes captured UART boot output to a local debug log when enabled. For example, ``true``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol`` (optional) — controls board power for cold cycles and shutdown states.
   * - ``jtag``
     - ``XilinxJTAGDriver`` — programs FPGA images and downloads bootstrap or firmware payloads
       through xsdb.
   * - ``shell``
     - ``ADIShellDriver`` (optional) — drives the serial console, watches boot markers, and provides
       target shell commands.
   * - ``ssh``
     - ``SSHDriver`` (optional) — transfers files or runs commands over the booted target network.

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
   :widths: 24 24 52

   * - Argument
     - Requirement/default
     - Description and example
   * - ``reached_linux_marker``
     - ``'analog'``
     - Console pattern that confirms Linux has reached the expected login or shell text. For
       example, ``root@analog``.
   * - ``wait_for_linux_prompt_timeout``
     - ``60``
     - Maximum seconds to wait for the configured Linux marker after the kernel starts. For example,
       ``180``.
   * - ``wait_for_autoboot_prompt_timeout``
     - ``60``
     - Maximum seconds to wait for U-Boot’s autoboot-interrupt banner. For example, ``90``.
   * - ``autoboot_banner_retries``
     - ``1``
     - Number of power-cycle retries after a silent autoboot-banner timeout. For example, ``2``.
   * - ``tftp_root_folder``
     - ``'/var/lib/tftpboot'``
     - Host directory in which boot files are staged for the TFTP daemon. For example,
       ``/var/lib/tftpboot``.
   * - ``kernel_addr``
     - ``'0x30000000'``
     - U-Boot RAM address at which the strategy loads the kernel image. For example, ``0x30000000``.
   * - ``dtb_addr``
     - ``'0x2A000000'``
     - U-Boot RAM address at which the strategy loads the device tree. For example, ``0x2A000000``.
   * - ``bootargs``
     - ``'console=ttyPS0,115200 root=/dev/mmcblk0p2 rw earlycon earlyprintk rootfstype=ext4 rootwait'``
     - Linux kernel command line installed in U-Boot before starting recovery or normal Linux. For
       example, ``console=ttyPS0,115200 root=/dev/mmcblk0p2 rw rootwait``.
   * - ``uboot_prompt``
     - ``'ZynqMP>.*'``
     - Regular expression used to recognize and synchronize with the U-Boot prompt. For example,
       ``ZynqMP>.*``.
   * - ``kernel_image_name``
     - ``'Image'``
     - Kernel filename requested from the TFTP root. For example, ``Image``.
   * - ``dtb_image_name``
     - ``'system.dtb'``
     - Device-tree filename requested from the TFTP root. For example, ``system.dtb``.
   * - ``boot_cmd``
     - ``'booti'``
     - U-Boot command used to start the loaded kernel; select it for the kernel format and
       architecture. For example, ``booti``.
   * - ``ps7_init_tcl``
     - ``None``
     - Host path to the board-specific Zynq-7000 PS initialization Tcl sourced by xsdb. For example,
       ``/srv/jtag/ps7_init.tcl``.
   * - ``uboot_elf``
     - ``None``
     - Host path to the U-Boot ELF downloaded into DDR for JTAG bootstrap. For example,
       ``/srv/jtag/u-boot.elf``.
   * - ``fsbl_elf``
     - ``None``
     - Optional host path to an FSBL ELF run as part of JTAG bootstrap. For example,
       ``/srv/jtag/fsbl.elf``.
   * - ``bitstream_path``
     - ``None``
     - Optional host path to the FPGA bitstream programmed before software that accesses PL
       peripherals. For example, ``/srv/jtag/system.bit``.
   * - ``a9_target_name``
     - ``'*Cortex-A9 MPCore #0'``
     - xsdb target-filter pattern selecting the Zynq Cortex-A9 core. For example, ``*Cortex-A9
       MPCore #0``.
   * - ``jtag_bootstrap_retries``
     - ``2``
     - Number of cold-cycle retries after a failed JTAG U-Boot bootstrap. For example, ``2``.
   * - ``sd_autoboot``
     - ``False``
     - Uses JTAG only to start U-Boot, then lets its SD autoboot command boot the installed image.
       For example, ``true``.
   * - ``ethaddr``
     - ``''``
     - Optional stable MAC address assigned in U-Boot before the interactive TFTP boot path. For
       example, ``02:00:00:00:00:01``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol`` — controls board power for cold cycles and shutdown states.
   * - ``shell``
     - ``ADIShellDriver`` — drives the serial console, watches boot markers, and provides target
       shell commands.
   * - ``ssh``
     - ``SSHDriver`` (optional) — transfers files or runs commands over the booted target network.
   * - ``kuiper``
     - ``CloudsmithDLDriver`` or ``KuiperDLDriver`` (optional) — downloads or exposes Kuiper images
       and extracted boot files.
   * - ``jtag``
     - ``XilinxJTAGDriver`` (optional) — programs FPGA images and downloads bootstrap or firmware
       payloads through xsdb.
   * - ``tftp_server``
     - ``TFTPServerResource`` — supplies the TFTP address, port, and root-directory resource.
   * - ``tftp_driver``
     - ``TFTPServerDriver`` — starts or accesses the TFTP service used to serve boot artifacts.

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
   :widths: 24 24 52

   * - Argument
     - Requirement/default
     - Description and example
   * - ``packages``
     - ``[]``
     - Ordered operating-system package names passed to the software installer. For example, ``[git,
       cmake]``.
   * - ``repos``
     - ``[]``
     - Repository specifications cloned by the installer, including URL, destination, and optional
       branch. For example, ``[{url: https://github.com/analogdevicesinc/libiio, dest:
       /opt/libiio}]``.
   * - ``build_steps``
     - ``[]``
     - Ordered command/directory records used to build the cloned software. For example, ``[{cmd:
       cmake -S . -B build, dir: /opt/libiio}]``.
   * - ``test_steps``
     - ``[]``
     - Ordered command/directory records run after the build to validate the installation. For
       example, ``[{cmd: ctest --test-dir build, dir: /opt/libiio}]``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``installer``
     - ``SoftwareInstallerDriver`` — installs packages, clones repositories, and executes build/test
       steps.

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
   :widths: 24 24 52

   * - Argument
     - Requirement/default
     - Description and example
   * - ``ssh_boot_timeout``
     - ``120``
     - Maximum seconds to wait for the Raspberry Pi SSH service to become reachable. For example,
       ``120``.
   * - ``power_off_delay``
     - ``2``
     - Seconds to wait after switching power off before continuing. For example, ``5``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``ssh``
     - ``SSHDriver`` — transfers files or runs commands over the booted target network.
   * - ``power``
     - ``PowerProtocol`` (optional) — controls board power for cold cycles and shutdown states.
   * - ``shell``
     - ``ADIShellDriver`` (optional) — drives the serial console, watches boot markers, and provides
       target shell commands.
   * - ``sdmux``
     - ``USBSDMuxDriver`` (optional) — switches the removable SD card between the host and DUT.

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
   :widths: 24 24 52

   * - Argument
     - Requirement/default
     - Description and example
   * - ``reached_linux_marker``
     - ``'analog'``
     - Console pattern that confirms Linux has reached the expected login or shell text. For
       example, ``root@analog``.
   * - ``kernel_banner_pattern``
     - ``'Starting kernel'``
     - Console pattern proving the Versal kernel jump occurred without matching U-Boot error text.
       For example, ``Starting kernel``.
   * - ``sc_commands``
     - ``[]``
     - Ordered board-management commands run on the VPK180 system controller after login. For
       example, ``[bootmode sd1, reset]``.
   * - ``wait_for_sc_command_timeout``
     - ``30``
     - Per-command timeout in seconds for system-controller commands. For example, ``30``.
   * - ``wait_for_kernel_banner_timeout``
     - ``120``
     - Maximum seconds to wait after power-on for the kernel-start banner. For example, ``120``.
   * - ``wait_for_linux_prompt_timeout``
     - ``60``
     - Maximum seconds to wait for the configured Linux marker after the kernel starts. For example,
       ``180``.
   * - ``sc_login_retries``
     - ``3``
     - Number of whole-board cold-cycle retries after system-controller login failure. For example,
       ``3``.
   * - ``sc_command_retries``
     - ``3``
     - Number of whole-board cold-cycle retries after a system-controller command failure. For
       example, ``3``.
   * - ``kernel_banner_retries``
     - ``3``
     - Number of cold-cycle retries after a kernel-banner timeout, in addition to the first attempt.
       For example, ``2``.
   * - ``update_image``
     - ``False``
     - Enables writing the complete Kuiper disk image instead of only using the existing media. For
       example, ``true``.
   * - ``update_boot_files``
     - ``False``
     - Stages Kuiper boot files through SD mux or SSH before booting. For example, ``true``.
   * - ``boot_partition_path``
     - ``'/boot'``
     - Destination directory used when copying Kuiper boot files over SSH. For example, ``/boot``.
   * - ``ssh_reboot_command``
     - ``'sudo reboot'``
     - Command sent after SSH boot-file staging to request a reboot. For example, ``sudo reboot``.
   * - ``warm_boot_if_sc_alive``
     - ``True``
     - Skips the initial cold cycle when the system controller responds to a short prompt probe. For
       example, ``true``.
   * - ``warm_probe_timeout``
     - ``3``
     - Seconds allowed for the non-destructive system-controller prompt probe. For example, ``3``.
   * - ``debug_write_boot_log``
     - ``False``
     - Writes captured UART boot output to a local debug log when enabled. For example, ``true``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol`` — controls board power for cold cycles and shutdown states.
   * - ``sc_shell``
     - ``ADIShellDriver`` — logs into the VPK180 system controller and runs boot-mode or reset
       commands.
   * - ``target_shell``
     - ``ADIShellDriver`` — watches and logs into the Versal target Linux console.
   * - ``sdmux``
     - ``USBSDMuxDriver`` (optional) — switches the removable SD card between the host and DUT.
   * - ``mass_storage``
     - ``MassStorageDriver`` (optional) — mounts the host-visible SD partition and copies boot
       files.
   * - ``image_writer``
     - ``USBStorageDriver`` (optional) — writes a complete disk image to host-visible USB storage.
   * - ``kuiper``
     - ``KuiperDLDriver`` (optional) — downloads or exposes Kuiper images and extracted boot files.
   * - ``ssh``
     - ``SSHDriver`` (optional) — transfers files or runs commands over the booted target network.

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
   :widths: 24 24 52

   * - Argument
     - Requirement/default
     - Description and example
   * - ``ps7_init_tcl``
     - ``None``
     - Host path to the board-specific Zynq-7000 PS initialization Tcl sourced by xsdb. For example,
       ``/srv/jtag/ps7_init.tcl``.
   * - ``uboot_elf``
     - ``None``
     - Host path to the U-Boot ELF downloaded into DDR for JTAG bootstrap. For example,
       ``/srv/jtag/u-boot.elf``.
   * - ``fsbl_elf``
     - ``None``
     - Optional host path to an FSBL ELF run as part of JTAG bootstrap. For example,
       ``/srv/jtag/fsbl.elf``.
   * - ``bitstream_path``
     - ``None``
     - Optional host path to the FPGA bitstream programmed before software that accesses PL
       peripherals. For example, ``/srv/jtag/system.bit``.
   * - ``a9_target_name``
     - ``'*Cortex-A9 MPCore #0'``
     - xsdb target-filter pattern selecting the Zynq Cortex-A9 core. For example, ``*Cortex-A9
       MPCore #0``.
   * - ``recovery_kernel``
     - ``None``
     - Filename of the Zynq-7000 recovery kernel already present in the TFTP root. For example,
       ``zImage.recovery``.
   * - ``recovery_dtb``
     - ``None``
     - Filename of the Zynq-7000 recovery device tree already present in the TFTP root. For example,
       ``system.recovery.dtb``.
   * - ``recovery_initramfs``
     - ``'uInitrd.recovery'``
     - Filename of the recovery initramfs loaded from TFTP; it may be auto-built. For example,
       ``uInitrd.recovery``.
   * - ``recovery_login_marker``
     - ``'recovery login:'``
     - Console pattern confirming the RAM-rooted recovery Linux reached its login prompt. For
       example, ``recovery login:``.
   * - ``sd_image_url``
     - ``None``
     - HTTP URL streamed by recovery Linux when writing the target SD card. For example,
       ``http://10.0.0.1:8000/kuiper.img``.
   * - ``sd_device``
     - ``'/dev/mmcblk0'``
     - Block-device path overwritten by the destructive SD recovery phase. For example,
       ``/dev/mmcblk0``.
   * - ``download_cmd_template``
     - ``'wget -q -O - "{url}"'``
     - Shell template that emits the image bytes; it must contain the {url} placeholder. For
       example, ``wget -q -O - "{url}"``.
   * - ``board_variant``
     - ``None``
     - Kuiper FAT subdirectory whose standard boot files are copied to the partition root. For
       example, ``zynq-zc706-adv7511-adrv937x``.
   * - ``board_variant_files``
     - ``('BOOT.BIN', 'uImage', 'devicetree.dtb')``
     - Filenames copied from board_variant to the FAT root after flashing. For example, ``[BOOT.BIN,
       uImage, devicetree.dtb]``.
   * - ``board_variant_paths``
     - ``None``
     - Explicit target-filename to FAT-source-path mapping; it overrides board_variant. For example,
       ``{BOOT.BIN: zynq-zc706/BOOT.BIN}``.
   * - ``sd_boot_partition``
     - ``1``
     - FAT partition number containing BOOT.BIN, kernel, and device tree. For example, ``1``.
   * - ``sd_mount_point``
     - ``'/mnt'``
     - Temporary mount directory used inside recovery Linux for the boot partition. For example,
       ``/mnt``.
   * - ``post_flash_commands``
     - ``[]``
     - Ordered recovery-shell commands run after the SD write and board-file copy. For example,
       ``[sync, reboot]``.
   * - ``post_flash_timeout``
     - ``120``
     - Per-command timeout in seconds for each post-flash command. For example, ``120``.
   * - ``auto_build_initramfs``
     - ``True``
     - Builds and stages the recovery initramfs when it is absent from the TFTP root. For example,
       ``true``.
   * - ``auto_serve_http``
     - ``True``
     - Starts a temporary HTTP server for sd_image_path when no explicit image URL is set. For
       example, ``true``.
   * - ``busybox_static_path``
     - ``None``
     - Host path to a prebuilt static ARM BusyBox used instead of compiling one. For example,
       ``/srv/recovery/busybox``.
   * - ``busybox_source_url``
     - ``None``
     - BusyBox source archive URL used by the automatic initramfs builder. For example,
       ``https://busybox.net/downloads/busybox-1.36.1.tar.bz2``.
   * - ``cross_compile``
     - ``None``
     - Cross-compiler prefix used to build static ARM BusyBox. For example,
       ``arm-linux-gnueabihf-``.
   * - ``recovery_cache_dir``
     - ``None``
     - Host cache directory for BusyBox build artifacts. For example, ``~/.cache/adi-lg-recovery``.
   * - ``sd_image_path``
     - ``None``
     - Local SD-image path exposed by the automatic HTTP server. For example,
       ``/srv/images/kuiper.img``.
   * - ``http_serve_port``
     - ``0``
     - TCP port for the temporary image server; zero requests an available ephemeral port. For
       example, ``8080``.
   * - ``http_serve_address``
     - ``None``
     - Address advertised to recovery Linux for the temporary HTTP server. For example,
       ``10.0.0.1``.
   * - ``uboot_prompt``
     - ``'zynq-uboot>|U-Boot>|=>'``
     - Regular expression used to recognize and synchronize with the U-Boot prompt. For example,
       ``ZynqMP>.*``.
   * - ``kernel_addr``
     - ``'0x2080000'``
     - U-Boot RAM address at which the strategy loads the kernel image. For example, ``0x2080000``.
   * - ``dtb_addr``
     - ``'0x2000000'``
     - U-Boot RAM address at which the strategy loads the device tree. For example, ``0x2000000``.
   * - ``initramfs_addr``
     - ``'0x4000000'``
     - U-Boot RAM address at which the recovery initramfs is loaded. For example, ``0x4000000``.
   * - ``bootargs``
     - ``'console=ttyPS0,115200 earlyprintk loglevel=8 rdinit=/init'``
     - Linux kernel command line installed in U-Boot before starting recovery or normal Linux. For
       example, ``console=ttyPS0,115200 rdinit=/init``.
   * - ``jtag_bootstrap_retries``
     - ``2``
     - Number of cold-cycle retries after a failed JTAG U-Boot bootstrap. For example, ``2``.
   * - ``wait_for_uboot_prompt_timeout``
     - ``60``
     - Maximum seconds to find the U-Boot prompt after JTAG bootstrap. For example, ``60``.
   * - ``wait_for_recovery_linux_timeout``
     - ``180``
     - Maximum seconds to wait for recovery Linux to reach its login marker. For example, ``240``.
   * - ``wait_for_sd_flash_timeout``
     - ``1800``
     - Maximum seconds allowed for the streamed SD-card write. For example, ``1800``.
   * - ``verify_kernel_name``
     - ``'uImage'``
     - Kernel filename loaded from the freshly written SD during boot verification. For example,
       ``uImage``.
   * - ``verify_dtb_name``
     - ``'devicetree.dtb'``
     - Device-tree filename loaded from the freshly written SD during boot verification. For
       example, ``devicetree.dtb``.
   * - ``verify_bootargs``
     - ``'console=ttyPS0,115200 root=/dev/mmcblk0p2 rw earlyprintk rootfstype=ext4 rootwait'``
     - Kernel command line used for the post-flash boot verification. For example,
       ``console=ttyPS0,115200 root=/dev/mmcblk0p2 rw rootwait``.
   * - ``verify_boot_login_marker``
     - ``'(analog|raspberrypi|kuiper).*login:'``
     - Console regular expression that proves the flashed SD reached normal Linux login. For
       example, ``analog.*login:``.
   * - ``wait_for_verify_boot_timeout``
     - ``180``
     - Maximum seconds for the flashed-SD verification boot to reach its login marker. For example,
       ``180``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol`` — controls board power for cold cycles and shutdown states.
   * - ``jtag``
     - ``XilinxJTAGDriver`` — programs FPGA images and downloads bootstrap or firmware payloads
       through xsdb.
   * - ``shell``
     - ``ADIShellDriver`` — drives the serial console, watches boot markers, and provides target
       shell commands.
   * - ``tftp_server``
     - ``TFTPServerResource`` — supplies the TFTP address, port, and root-directory resource.
   * - ``tftp_driver``
     - ``TFTPServerDriver`` — starts or accesses the TFTP service used to serve boot artifacts.
   * - ``ssh``
     - ``SSHDriver`` (optional) — transfers files or runs commands over the booted target network.

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
   :widths: 24 24 52

   * - Argument
     - Requirement/default
     - Description and example
   * - ``firmware_elf``
     - ``None``
     - Required host path to the no-OS firmware ELF downloaded and started through JTAG. For
       example, ``/srv/no-os/app.elf``.
   * - ``bitstream_path``
     - ``None``
     - Optional host path to the FPGA bitstream programmed before software that accesses PL
       peripherals. For example, ``/srv/no-os/system.bit``.
   * - ``ps7_init_tcl``
     - ``None``
     - Host path to the board-specific Zynq-7000 PS initialization Tcl sourced by xsdb. For example,
       ``/srv/no-os/ps7_init.tcl``.
   * - ``a9_target_name``
     - ``'*Cortex-A9 MPCore #0'``
     - xsdb target-filter pattern selecting the Zynq Cortex-A9 core. For example, ``*Cortex-A9
       MPCore #0``.
   * - ``boot_marker``
     - ``'Successfully initialized'``
     - Serial-console text proving the no-OS firmware initialized successfully. For example,
       ``Successfully initialized``.
   * - ``boot_timeout``
     - ``60``
     - Maximum seconds to wait for the no-OS firmware boot marker. For example, ``60``.
   * - ``power_settle_time``
     - ``2``
     - Seconds to wait after power-on before starting JTAG operations. For example, ``2``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol`` — controls board power for cold cycles and shutdown states.
   * - ``jtag``
     - ``XilinxJTAGDriver`` — programs FPGA images and downloads bootstrap or firmware payloads
       through xsdb.
   * - ``shell``
     - ``ADIShellDriver`` — drives the serial console, watches boot markers, and provides target
       shell commands.

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
   :widths: 24 24 52

   * - Argument
     - Requirement/default
     - Description and example
   * - ``sc_to_qspi_commands``
     - ``factory value``
     - Ordered system-controller commands that select QSPI rescue boot and reset Versal. For
       example, ``[sc_app -c setbootmode -t QSPI32, sc_app -c reset]``.
   * - ``sc_to_sd_commands``
     - ``factory value``
     - Ordered system-controller commands that restore SD boot and reset Versal. For example,
       ``[sc_app -c setbootmode -t SD, sc_app -c reset]``.
   * - ``recovery_kernel_banner_pattern``
     - ``'Starting kernel'``
     - Versal UART pattern proving the QSPI rescue kernel has started. For example, ``Starting
       kernel``.
   * - ``tftp_image_filename``
     - ``'kuiper.img'``
     - Filename under the TFTP root requested by recovery Linux. For example, ``kuiper.img``.
   * - ``target_sd_device``
     - ``'/dev/mmcblk0'``
     - Recovery-Linux block device overwritten with the staged Kuiper image. For example,
       ``/dev/mmcblk0``.
   * - ``dd_block_size``
     - ``'4M'``
     - Value substituted for dd’s bs option in the write command. For example, ``4M``.
   * - ``dd_command_template``
     - ``'set -o pipefail; tftp -g -r {filename} -l - {server_ip} {server_port} | dd of={dev} bs={bs} status=progress conv=fsync'``
     - TFTP-to-dd shell template formatted with filename, server, device, and block size. For
       example, ``tftp -g -r {filename} -l - {server_ip} | dd of={dev} bs={bs}``.
   * - ``dd_timeout``
     - ``1800``
     - Maximum seconds for each image-write attempt. For example, ``1800``.
   * - ``dd_retries``
     - ``1``
     - Number of in-place image-write retries after the first attempt. For example, ``1``.
   * - ``verify_after_write``
     - ``False``
     - Runs verify_command_template after a successful SD write when enabled. For example, ``true``.
   * - ``verify_command_template``
     - ``'tftp -g -r {filename} -l - {server_ip} {server_port} | head -c $(blockdev --getsize64 {dev}) | sha256sum'``
     - Shell template used to re-read or hash the written SD against fetched image data. For
       example, ``tftp -g -r {filename} -l - {server_ip} | sha256sum``.
   * - ``stage_method``
     - ``'symlink'``
     - Method used to place the cached Kuiper image in the TFTP root. For example, ``copy``.
   * - ``sc_login_retries``
     - ``3``
     - Number of whole-board cold-cycle retries after system-controller login failure. For example,
       ``3``.
   * - ``sc_command_retries``
     - ``3``
     - Number of whole-board cold-cycle retries after a system-controller command failure. For
       example, ``3``.
   * - ``recovery_banner_retries``
     - ``3``
     - Number of cold-cycle retries when the rescue-kernel banner is not observed. For example,
       ``3``.
   * - ``wait_for_sc_command_timeout``
     - ``30``
     - Per-command timeout in seconds for system-controller commands. For example, ``30``.
   * - ``wait_for_recovery_banner_timeout``
     - ``120``
     - Maximum seconds per attempt to wait for the rescue-kernel banner. For example, ``120``.
   * - ``wait_for_recovery_login_timeout``
     - ``60``
     - Compatibility knob retained by the strategy; login timing currently comes from the bound
       target shell driver. For example, ``60``.
   * - ``power_off_when_done``
     - ``True``
     - Powers the board off after restoring boot mode and completing the reflash. For example,
       ``true``.
   * - ``restore_sd_bootmode``
     - ``True``
     - Returns the Versal boot mode to SD after writing; disabling leaves it in QSPI rescue. For
       example, ``true``.
   * - ``debug_write_uart_log``
     - ``False``
     - Writes a timestamped UART capture for each failed retry phase when enabled. For example,
       ``true``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol`` — controls board power for cold cycles and shutdown states.
   * - ``sc_shell``
     - ``ADIShellDriver`` — logs into the VPK180 system controller and runs boot-mode or reset
       commands.
   * - ``target_shell``
     - ``ADIShellDriver`` — watches and logs into the Versal target Linux console.
   * - ``kuiper``
     - ``KuiperDLDriver`` — downloads or exposes Kuiper images and extracted boot files.
   * - ``tftp``
     - ``TFTPServerDriver`` — stages and serves the full SD image to VPK180 recovery Linux.

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
   :widths: 24 24 52

   * - Argument
     - Requirement/default
     - Description and example
   * - ``psu_init_tcl``
     - ``None``
     - Host path to board-generated ZynqMP PS initialization Tcl used by xsdb. For example,
       ``/srv/recovery/psu_init.tcl``.
   * - ``spl_elf``
     - ``None``
     - Host path to the mini U-Boot SPL ELF used for the initial JTAG bootstrap. For example,
       ``/srv/recovery/spl.elf``.
   * - ``bitstream_path``
     - ``None``
     - Optional host path to the FPGA bitstream programmed before software that accesses PL
       peripherals. For example, ``/srv/recovery/system_top.bit``.
   * - ``pmufw_bin``
     - ``None``
     - Raw PMU firmware payload loaded for the production handoff. For example,
       ``/srv/recovery/pmufw.bin``.
   * - ``uboot_bin``
     - ``None``
     - Raw production U-Boot payload loaded through JTAG. For example, ``/srv/recovery/u-boot.bin``.
   * - ``handoff_bin``
     - ``None``
     - Optional one-way handoff payload used when BL31 artifacts are not supplied. For example,
       ``/srv/recovery/handoff.bin``.
   * - ``bl31_bin``
     - ``None``
     - ARM Trusted Firmware BL31 payload; it must be paired with atf_handoff_bin. For example,
       ``/srv/recovery/bl31.bin``.
   * - ``atf_handoff_bin``
     - ``None``
     - Trampoline/handoff payload that starts BL31; it must be paired with bl31_bin. For example,
       ``/srv/recovery/atf-handoff.bin``.
   * - ``pm_config_bin``
     - ``None``
     - Optional PMU configuration object loaded with production firmware. For example,
       ``/srv/recovery/pm-config.bin``.
   * - ``bl31_console_uart_base``
     - ``None``
     - UART base address patched into BL31 console setup for the target board. For example,
       ``0xFF010000``.
   * - ``bl31_console_ref_ctrl_address``
     - ``None``
     - Reference-clock control register address used for BL31 UART initialization. For example,
       ``0xFF5E0050``.
   * - ``bl31_console_reset_mask``
     - ``'0x2'``
     - Bit mask applied while releasing the BL31 console UART from reset. For example, ``0x2``.
   * - ``ddr_scrub_elf``
     - ``None``
     - Optional ELF that initializes or scrubs DDR before production payloads are loaded. For
       example, ``/srv/recovery/ddr-scrub.elf``.
   * - ``recovery_trampoline_elf``
     - ``None``
     - ELF trampoline that enters the direct-JTAG RAM recovery kernel. For example,
       ``/srv/recovery/trampoline.elf``.
   * - ``recovery_kernel_image``
     - ``None``
     - Host path to the raw kernel image used by direct-JTAG recovery Linux. For example,
       ``/srv/recovery/Image``.
   * - ``recovery_initramfs``
     - ``None``
     - Host path to the initramfs used for direct-JTAG RAM recovery Linux. For
       example, ``/srv/recovery/rootfs.cpio.gz.u-boot``.
   * - ``recovery_dtb``
     - ``None``
     - Host path to the device tree used for direct-JTAG RAM recovery Linux. For
       example, ``/srv/recovery/system.dtb``.
   * - ``recovery_marker``
     - ``'RECOVERY_READY'``
     - Console text emitted when direct-JTAG recovery Linux is ready. For example,
       ``RECOVERY_READY``.
   * - ``recovery_prompt``
     - ``'root@zu11eg-recovery:.*#'``
     - Shell prompt regular expression installed after recovery readiness is detected. For example,
       ``root@zu11eg-recovery:.*#``.
   * - ``recovery_timeout``
     - ``180``
     - Maximum seconds to observe both the recovery marker and prompt. For example, ``180``.
   * - ``recovery_ddr_scrub_elf``
     - ``None``
     - Recovery-specific DDR scrub ELF; it overrides ddr_scrub_elf for recovery. For example,
       ``/srv/recovery/recovery-ddr-scrub.elf``.
   * - ``ddr_scrub_done_address``
     - ``None``
     - Memory address polled to determine that the default DDR scrub completed. For example,
       ``0xFFFC0054``.
   * - ``recovery_ddr_scrub_done_address``
     - ``None``
     - Recovery-specific scrub completion address overriding ddr_scrub_done_address. For example,
       ``0xFFFC0058``.
   * - ``recovery_ddr_scrub_settle_ms``
     - ``30000``
     - Milliseconds allowed for the recovery DDR scrub to settle. For example, ``30000``.
   * - ``recovery_bitstream_path``
     - ``None``
     - Recovery-specific PL bitstream overriding bitstream_path. For example,
       ``/srv/recovery/recovery.bit``.
   * - ``recovery_post_init_mask_writes``
     - ``[]``
     - Register mask-write records applied after PS initialization in recovery mode. For example,
       ``[{address: 0xFF5E0200, mask: 0x1, value: 0x1}]``.
   * - ``sd_image_url``
     - ``None``
     - HTTP URL streamed by recovery Linux when writing the target SD card. For example,
       ``https://images.example/kuiper.img``.
   * - ``sd_device``
     - ``'/dev/mmcblk0'``
     - Block-device path overwritten by the destructive SD recovery phase. For example,
       ``/dev/mmcblk0``.
   * - ``sd_download_cmd_template``
     - ``'wget -O - "{url}"'``
     - Recovery-shell download template containing {url} and producing image bytes. For example,
       ``wget -O - "{url}"``.
   * - ``sd_flash_timeout``
     - ``3600``
     - Maximum seconds for the ZynqMP SD write and sample-hash verification command. For example,
       ``3600``.
   * - ``sd_image_size``
     - ``None``
     - Exact source-image size in bytes, used to locate the tail verification sample. For example,
       ``8589934592``.
   * - ``sd_head_sha256``
     - ``None``
     - Expected SHA-256 of the first sd_sample_bytes bytes on the flashed SD. For example,
       ``0123456789abcdef…``.
   * - ``sd_tail_sha256``
     - ``None``
     - Expected SHA-256 of the final aligned sample on the flashed SD. For example,
       ``fedcba9876543210…``.
   * - ``sd_sample_bytes``
     - ``1048576``
     - Number of bytes hashed at each end of the SD image for verification. For example,
       ``1048576``.
   * - ``post_flash_commands``
     - ``[]``
     - Ordered recovery-shell commands run after the SD write and board-file copy. For example,
       ``[sync, reboot]``.
   * - ``post_flash_timeout``
     - ``180``
     - Per-command timeout in seconds for each post-flash command. For example, ``120``.
   * - ``production_uboot_prompt``
     - ``'ZynqMP>'``
     - Prompt regular expression proving production U-Boot reached the external UART. For example,
       ``ZynqMP>``.
   * - ``production_prompt_timeout``
     - ``60``
     - Maximum seconds to detect the production U-Boot prompt. For example, ``60``.
   * - ``sd_boot_command``
     - ``'setenv partid 1; run sdboot'``
     - U-Boot command sent to boot the production Kuiper image from SD. For example, ``setenv partid
       1; run sdboot``.
   * - ``kuiper_kernel_marker``
     - ``'Starting kernel'``
     - Console pattern confirming the Kuiper kernel started. For example, ``Starting kernel``.
   * - ``kuiper_shell_marker``
     - ``'root@analog:.*#'``
     - Console prompt pattern confirming Kuiper userspace is ready. For example,
       ``root@analog:.*#``.
   * - ``kuiper_boot_timeout``
     - ``300``
     - Maximum seconds for each Kuiper kernel and shell marker wait. For example, ``300``.
   * - ``kuiper_verify_timeout``
     - ``120``
     - Per-command timeout for post-boot Kuiper validation commands. For example, ``120``.
   * - ``kuiper_verify_commands``
     - ``factory value``
     - Ordered shell commands that validate networking, IIO devices, and JESD initialization. For
       example, ``[ip -4 addr show dev eth0, iio_info -s]``.
   * - ``a53_target_name``
     - ``'*Cortex-A53*#0*'``
     - xsdb target-filter pattern selecting the first Cortex-A53 core. For example,
       ``*Cortex-A53*#0*``.
   * - ``apu_release_rst_value``
     - ``'0x380E'``
     - Reset-register value written when releasing the ZynqMP application processors. For example,
       ``0x380E``.
   * - ``dcc_log_path``
     - ``None``
     - Optional host path receiving the mini-SPL ARM DCC console capture. For example,
       ``/tmp/zynqmp-dcc.log``.
   * - ``spl_settle_ms``
     - ``12000``
     - Milliseconds to wait after starting the mini U-Boot SPL. For example, ``12000``.
   * - ``production_settle_ms``
     - ``12000``
     - Milliseconds to wait after starting the production handoff. For example, ``12000``.
   * - ``pmufw_timeout_ms``
     - ``10000``
     - Milliseconds allowed for PMU firmware startup during production loading. For example,
       ``10000``.
   * - ``ddr_scrub_settle_ms``
     - ``30000``
     - Milliseconds allowed for the production DDR scrub to settle. For example, ``30000``.
   * - ``jtag_url``
     - ``'TCP:127.0.0.1:3121'``
     - hw_server connection URL passed to xsdb. For example, ``TCP:127.0.0.1:3121``.
   * - ``serial_host_override``
     - ``None``
     - Optional network-serial host substituted before activating the shell console. For example,
       ``192.0.2.10``.
   * - ``serial_protocol_override``
     - ``None``
     - Optional network-serial protocol override; the implementation currently accepts raw. For
       example, ``raw``.
   * - ``power_off_settle_s``
     - ``5``
     - Seconds to keep power off during a ZynqMP cold cycle. For example, ``5``.
   * - ``power_on_settle_s``
     - ``8``
     - Seconds to wait after applying power before JTAG access. For example, ``8``.

**Bindings**

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Binding
     - Provider
   * - ``power``
     - ``PowerProtocol`` — controls board power for cold cycles and shutdown states.
   * - ``jtag``
     - ``XilinxJTAGDriver`` — programs FPGA images and downloads bootstrap or firmware payloads
       through xsdb.
   * - ``shell``
     - ``ADIShellDriver`` (optional) — drives the serial console, watches boot markers, and provides
       target shell commands.

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
