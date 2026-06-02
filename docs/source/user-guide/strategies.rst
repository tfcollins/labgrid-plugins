Working with Strategies
=======================

Strategies are high-level state machines that coordinate multiple drivers to accomplish complex workflows. They abstract away the detailed choreography of hardware interactions, allowing test engineers to focus on the overall boot and test sequence.

Overview
--------

A strategy represents a reusable workflow composed of multiple state transitions. Each transition may activate or deactivate drivers, execute commands, and wait for expected conditions. Strategies form the bridge between raw driver capabilities and practical test procedures.

Key Concepts
~~~~~~~~~~~~

- **State Machine**: Strategies are implemented as state machines with discrete states representing different phases of a workflow (e.g., powered_off, booting, shell).
- **Bindings**: Each strategy declares required and optional driver/resource bindings that must be present on the target.
- **Transitions**: The ``transition()`` method moves the strategy from one state to another, handling all intermediate steps automatically.
- **Activation Lifecycle**: Drivers are activated and deactivated as needed by the strategy, not manually by the test.
- **Error Handling**: StrategyError exceptions indicate invalid transitions or failed operations.

BootFPGASoC Strategy
--------------------

**Purpose**: Boot an FPGA SoC device (e.g., Zynq UltraScale+) using an SD card mux and Kuiper release images.

**State Machine**:

The strategy manages 9 states:

.. mermaid::

   stateDiagram-v2
       [*] --> unknown

       unknown --> powered_off: Initialize
       powered_off --> sd_mux_to_host: Power off device
       sd_mux_to_host --> update_boot_files: Mux SD to host

       update_boot_files --> decide_image: Check update_image flag
       decide_image --> write_image: update_image=True
       decide_image --> copy_files: update_image=False
       write_image --> copy_files: Write full image
       copy_files --> sd_mux_to_dut: Copy boot files

       sd_mux_to_dut --> booting: Mux SD to device
       booting --> booted: Power on device
       booted --> shell: Wait for kernel + marker

       shell --> soft_off: Graceful shutdown
       soft_off --> [*]

       note right of sd_mux_to_host
           SD card accessible to host
       end note

       note right of write_image
           Optional: full image flash
       end note

       note right of booted
           Wait for Linux kernel + marker
       end note

**Hardware Requirements**:

- Power control (VeSync, CyberPower, or other PowerProtocol implementation)
- SD card mux (USBSDMuxDriver) to switch SD card between host and device
- Mass storage access (MassStorageDriver) for copying files to SD card
- Serial console access (ADIShellDriver) for boot monitoring and shell interaction
- Boot artifacts via ``KuiperDLDriver`` or ``CloudsmithDLDriver`` (the
  ``kuiper`` binding accepts either)
- Optional: USB storage writer (USBStorageDriver) for full image flashing

**Configuration Example**:

.. code-block:: yaml

    targets:
      mydevice:
        resources:
          VesyncOutlet:
            outlet_names: 'Device Power'
            username: 'your_email@example.com'
            password: 'your_password'
            delay: 5.0

          USBSDMuxDriver:
            serial: '00012345'

          MassStorageDriver:
            path: '/dev/sda1'

          SerialPort:
            port: '/dev/ttyUSB0'
            baudrate: 115200

          KuiperDLDriver:
            release_version: '2024.r1'

        drivers:
          VesyncPowerDriver: {}
          USBSDMuxDriver: {}
          MassStorageDriver: {}
          ADIShellDriver:
            prompt: 'root@.*:.*#'
            login_prompt: 'login:'
            username: 'root'
            password: 'analog'
          KuiperDLDriver: {}

        strategies:
          BootFPGASoC:
            reached_linux_marker: 'analog'
            update_image: true  # Flash full image, not just boot files

**Usage Example**:

.. code-block:: python

    from labgrid import Environment
    from adi_lg_plugins.strategies import BootFPGASoC

    env = Environment("target.yaml")
    target = env.get_target("mydevice")
    strategy = target.get_strategy("BootFPGASoC")

    # Boot the device to shell
    strategy.transition("shell")

    # Now shell access is available
    shell = target.get_driver("ADIShellDriver")
    shell.run_command("uname -a")

    # Power off cleanly
    strategy.transition("soft_off")

**Advanced Usage - Full Image Flash**:

When ``update_image=True``, the strategy will flash the complete Kuiper release image to the SD card before copying individual boot files. This is useful for ensuring a clean filesystem:

.. code-block:: python

    # In target configuration:
    # BootFPGASoC:
    #   update_image: true

    # The strategy automatically:
    # 1. Muxes SD card to host
    # 2. Writes full image using USB storage writer
    # 3. Copies specific boot files on top
    # 4. Muxes SD card back to device
    # 5. Boots device

**Error Handling**:

The strategy raises ``StrategyError`` for invalid transitions. Common scenarios:

.. code-block:: python

    from labgrid.strategy import StrategyError

    try:
        strategy.transition("shell")
    except StrategyError as e:
        if "can not transition to unknown" in str(e):
            print("Cannot transition to initial state")
        elif "no transition found" in str(e):
            print("Invalid state transition")

**State Awareness**:

Always check the current state before transitioning:

.. code-block:: python

    from adi_lg_plugins.strategies.bootfpgasoc import Status

    strategy = target.get_strategy("BootFPGASoC")

    if strategy.status == Status.unknown:
        strategy.transition(Status.shell)
    elif strategy.status == Status.shell:
        print("Already at shell")
    elif strategy.status == Status.powered_off:
        strategy.transition(Status.shell)

BootFPGASoCSSH Strategy
-----------------------

**Purpose**: Boot an FPGA SoC device using SSH for file transfers instead of SD card mux. Useful when SSH access is available but SD card mux is not present.

**State Machine**:

The strategy manages 9 states with a two-stage boot process:

.. mermaid::

   stateDiagram-v2
       [*] --> unknown

       unknown --> powered_off: Initialize

       powered_off --> booting: Power on (if power driver)

       note right of powered_off
           Power control is optional
       end note

       booting --> booted: Wait for kernel + marker
       booted --> update_boot_files: SSH ready

       update_boot_files --> reboot: Transfer boot files via SSH

       note right of update_boot_files
           Validates and updates SSH IP address
       end note

       reboot --> booting_new: Issue reboot command
       booting_new --> shell: Wait for kernel + marker

       shell --> soft_off: Graceful shutdown
       soft_off --> [*]

       note right of booting
           First boot: initial system
       end note

       note right of booting_new
           Second boot: with updated files
       end note

**Key Differences from BootFPGASoC**:

- Uses SSH (SSHDriver) instead of SD card mux for file transfer
- Does not require mass storage driver or SD mux hardware
- Power control is optional (devices may boot automatically on power)
- More suitable for devices with network access
- Faster boot cycles after initial boot (no physical SD mux switching)

**Configuration Example**:

.. code-block:: yaml

    targets:
      netdevice:
        resources:
          VesyncOutlet:
            outlet_names: 'Device Power'
            username: 'your_email@example.com'
            password: 'your_password'

          SerialPort:
            port: '/dev/ttyUSB0'
            baudrate: 115200

          NetworkInterface:
            hostname: 'analog.local'
            username: 'root'
            password: 'analog'

          KuiperDLDriver:
            release_version: '2024.r1'

        drivers:
          VesyncPowerDriver: {}
          ADIShellDriver:
            prompt: 'root@.*:.*#'
            login_prompt: 'login:'
            username: 'root'
            password: 'analog'
          SSHDriver:
            hostname: 'analog.local'
            username: 'root'
            password: 'analog'
          KuiperDLDriver: {}

        strategies:
          BootFPGASoCSSH:
            hostname: 'analog.local'
            reached_linux_marker: 'analog'

**Usage Example**:

.. code-block:: python

    env = Environment("target.yaml")
    target = env.get_target("netdevice")
    strategy = target.get_strategy("BootFPGASoCSSH")

    # Boot to shell via SSH
    strategy.transition("shell")

    # Update boot files via SSH and reboot
    strategy.transition("update_boot_files")
    strategy.transition("reboot")
    strategy.transition("shell")

**Cleanup and Shutdown**:

Always transition to ``soft_off`` to gracefully shutdown:

.. code-block:: python

    strategy.transition("soft_off")

**Troubleshooting**:

*Boot files don't transfer via SSH*:
   - Verify SSH access works: ``ssh root@<device-ip>``
   - Check SSH key is properly configured in resources
   - Ensure network connectivity between host and device
   - Verify pre_boot_boot_files and post_boot_boot_files paths are correct

*First boot succeeds but restart fails*:
   - This is expected behavior with SSH-based file transfer
   - Strategy only uploads files on first boot
   - To re-upload files, transition to powered_off and back to shell

*SSH connection hangs during boot*:
   - Increase wait_for_linux_prompt_timeout (default: 60s)
   - Check device is booting correctly via serial console
   - Verify network interface is configured in device tree

*Permission denied errors*:
   - Ensure SSH key has correct permissions (chmod 600)
   - Verify device allows root login via SSH
   - Check /boot partition is writable on device

BootFPGASoCTFTP Strategy
------------------------

**Purpose**: Boot an FPGA SoC device by interrupting U-Boot and loading the kernel and device tree over TFTP. Useful when the SD card cannot be rewritten between boots — new boot images land in the TFTP root on the host instead.

**State Machine**:

The strategy manages 7 states:

.. mermaid::

   stateDiagram-v2
       [*] --> unknown

       unknown --> powered_off: Initialize
       powered_off --> update_boot_files: Deactivate shell + TFTP driver, power off
       update_boot_files --> booting: Stage Image/dtb into TFTP root
       booting --> booted: Power on, interrupt U-Boot, tftpboot, booti
       booted --> shell: Activate shell on Linux prompt
       shell --> soft_off: poweroff, then hard power cut
       soft_off --> [*]

       note right of update_boot_files
           Copies Kuiper boot files into tftp_root_folder.
           Requires KuiperDLDriver when files are staged.
       end note

       note right of booted
           U-Boot: dhcp, set serverip/tftpport,
           tftpboot Image + system.dtb, then booti.
       end note

**Required Resources and Drivers**

- ``PowerProtocol`` (any power driver, optional — skipped if absent)
- ``ADIShellDriver`` (serial console)
- ``TFTPServerResource`` + ``TFTPServerDriver`` (host-side TFTP server)
- ``KuiperDLDriver`` or ``CloudsmithDLDriver`` (optional — source of boot files)
- ``SSHDriver`` (optional — not used by this strategy itself, accepted for composition)

**Configuration Example**

.. code-block:: yaml

    targets:
      zcu102_tftp:
        resources:
          RawSerialPort:
            port: '/dev/ttyUSB0'
            speed: 115200

          VesyncOutlet:
            outlet_names: 'ZCU102 Power'
            username: 'lab@example.com'
            password: '...'

          TFTPServerResource:
            address: 'auto'
            port: 3069
            root: '/var/lib/tftpboot'

          KuiperRelease:
            release: '2023_R2_P1'
            cache_dir: '/var/cache/kuiper'

        drivers:
          SerialDriver: {}
          ADIShellDriver:
            prompt: 'root@analog:.*#'
            login_prompt: 'login:'
            username: 'root'
            password: 'analog'
          VesyncPowerDriver: {}
          TFTPServerDriver: {}
          KuiperDLDriver: {}

          BootFPGASoCTFTP:
            reached_linux_marker: 'analog'
            wait_for_linux_prompt_timeout: 60
            kernel_addr: '0x30000000'
            dtb_addr:    '0x2A000000'
            bootargs: 'console=ttyPS0,115200 root=/dev/mmcblk0p2 rw earlycon earlyprintk rootfstype=ext4 rootwait'

**Attributes**

- ``reached_linux_marker`` (str, default ``'analog'``): Console marker that signals Linux has booted.
- ``wait_for_linux_prompt_timeout`` (int, default 60): Seconds to wait for that marker after ``booti``.
- ``tftp_root_folder`` (str, default ``'/var/lib/tftpboot'``): Overridden at init time from the bound ``TFTPServerDriver``'s resource root.
- ``kernel_addr`` (str, default ``'0x30000000'``): Memory address loaded by the ``tftpboot Image`` command.
- ``dtb_addr`` (str, default ``'0x2A000000'``): Memory address loaded by the ``tftpboot system.dtb`` command.
- ``bootargs`` (str): Default Linux kernel command line. Override for non- ``/dev/mmcblk0p2`` rootfs.

**Usage Example**

.. code-block:: python

    strategy = target.get_driver("BootFPGASoCTFTP")

    # Boot kernel over TFTP and drop into a shell
    strategy.transition("shell")

    shell = target.get_driver("ADIShellDriver")
    print(shell.run("uname -a"))

    # Graceful shutdown
    strategy.transition("soft_off")

**Troubleshooting**

- **``tftpboot`` times out in U-Boot**: Confirm the host TFTP server is actually listening on ``port`` (``ss -lun | grep 3069``). If U-Boot talks to port 69, add an ``iptables`` redirect to ``port``.
- **``dhcp`` fails on the DUT**: Make sure the DUT's Ethernet is connected to the same L2 segment as the host running the TFTP server.
- **Boot files missing**: Attach a ``KuiperDLDriver`` to stage ``Image`` / ``system.dtb``, or drop them into ``tftp_root_folder`` manually.

BootZynq7000JTAGRecovery Strategy
---------------------------------

**Purpose**: Re-flash a Zynq-7000 SD card when ``BOOT.BIN`` is unreadable, so BootROM cannot stage FSBL. Bypasses the SD entirely by loading U-Boot directly into DDR over JTAG, then boots a minimal RAM-rooted Linux that streams a fresh disk image to ``/dev/mmcblk0``.

**Use Case**: SD recovery when an interrupted ``BootFPGASoCTFTP`` write, a power cut during file update, or filesystem corruption makes the on-card BOOT.BIN unbootable. Also useful for first-time provisioning of a blank SD on a board where SD-mux hardware is not present.

**State Machine**:

The strategy manages 9 states. Each transition cascades through prior states, so ``transition('sd_flash_done')`` from ``unknown`` runs everything end-to-end.

.. mermaid::

   stateDiagram-v2
       [*] --> unknown

       unknown --> powered_off: Initialize
       powered_off --> powered_on: Cold-cycle (off+5s+on)

       powered_on --> jtag_bootstrap: xsdb load FPGA bitstream\n+ ps7_init + dow u-boot.elf

       jtag_bootstrap --> uboot_prompt: Catch "Hit any key to stop autoboot"\n+ send space

       uboot_prompt --> tftp_recovery_kernel: setenv autoload/serverip/bootargs\n+ tftpboot kernel/dtb/uInitrd
       tftp_recovery_kernel --> linux_recovery: bootm \n+ wait for recovery_login_marker
       linux_recovery --> sd_flash_done: ADIShellDriver login\n+ wget URL | dd of=/dev/mmcblk0\n+ sync

       sd_flash_done --> soft_off: poweroff (or hard power cut)
       soft_off --> sd_boot_verified: cold-cycle\n+ wait for normal login marker
       sd_boot_verified --> [*]

       note right of jtag_bootstrap
           FPGA bitstream is mandatory when the
           DTB references fabric IPs (axi_clkgen,
           axi_jesd204_*, axi_adxcvr); kernel
           hangs on the AXI probe otherwise.
       end note

       note right of sd_boot_verified
           Optional post-flash check. No boot-mode
           switches change — the board is on SD the
           whole time; BootROM now reads the freshly
           written BOOT.BIN instead of the corrupt one.
       end note

       note right of linux_recovery
           Initramfs prints "recovery login:" then
           drops to /bin/sh with PS1='root@recovery:/#';
           ADIShellDriver drives it normally.
       end note

       note right of sd_flash_done
           ~12 min wall-clock for a 10 GB image
           over gigabit LAN (busybox wget|dd).
       end note

**Sequence diagram** — actor interactions through a successful run:

.. mermaid::

   sequenceDiagram
       participant Host as Test runner (host)
       participant HA as HomeAssistant outlet
       participant XSDB as xsdb / hw_server
       participant Cable as Digilent JTAG cable
       participant SoC as Zynq-7000 (PS + PL)
       participant UART as Serial console
       participant TFTP as TFTP server (host)
       participant HTTP as HTTP server (host)

       Host->>HA: turn_off (REST)
       Host->>HA: turn_on (REST)
       Note over SoC: BootROM probes SD; fails on bad BOOT.BIN.

       Host->>XSDB: connect, rst -system
       XSDB->>Cable: JTAG TAP control
       Cable->>SoC: halt A9 #0
       XSDB->>SoC: ps7_init (DDR + clocks + MIO)
       XSDB->>SoC: fpga -f system_top.bit
       XSDB->>SoC: dow u-boot.elf @ 0x4000000
       XSDB->>SoC: con (resume A9 from U-Boot entry)
       SoC->>UART: U-Boot banner

       Host->>UART: read until "Hit any key..."
       Host->>UART: send space (stop autoboot)
       Host->>UART: setenv autoload no / dhcp / serverip / tftpport
       Host->>UART: setenv bootargs ...rdinit=/init
       Host->>UART: tftpboot kernel / dtb / uInitrd.recovery
       UART->>TFTP: TFTP GET (over Ethernet)
       TFTP-->>UART: kernel + dtb + uInitrd bytes
       Host->>UART: bootm <kernel> <initramfs> <dtb>

       SoC->>UART: Linux boot, /init runs
       Note over SoC: udhcpc brings eth0 up.
       SoC->>UART: "recovery login:"
       Host->>UART: send "root\n" + "analog\n"
       SoC->>UART: PS1='root@recovery:/# '

       Host->>UART: wget URL | dd of=/dev/mmcblk0 bs=4M conv=fsync && sync && echo SD_FLASH_OK
       UART->>SoC: dd writes to MMC
       SoC->>HTTP: GET sd-image.img (over Ethernet)
       HTTP-->>SoC: ~10 GB image
       SoC->>UART: "SD_FLASH_OK"
       Host->>HA: turn_off

**Hardware Requirements**:

- Power control (any ``PowerProtocol`` implementation; HomeAssistant outlets and VeSync both work)
- Serial console on ``/dev/ttyPS0`` via ``ADIShellDriver``
- Digilent or compatible JTAG cable on the Zynq's PJTAG header, accessible to ``xsdb`` (Vivado/Vitis 2023.2+)
- TFTP server (labgrid's ``TFTPServerDriver`` is fine) serving kernel/dtb/initramfs from a directory the strategy can read
- HTTP server (e.g. ``python3 -m http.server``) hosting the SD image to flash
- A recovery initramfs that prints ``recovery login:`` and drops to a busybox shell; see ``examples/zynq7000_recovery/`` for a working reference

**Configuration Example**:

.. code-block:: yaml

   targets:
     zc706_recovery:
       resources:
         RawSerialPort:
           port: '/dev/serial/by-id/usb-Silicon_Labs_CP2103_USB_to_UART_Bridge_Controller_0001-if00-port0'
           speed: 115200

         HomeAssistantOutlet:
           url: 'http://YOUR_HA_HOST:8123'
           token: '${HA_TOKEN}'
           entity_id: 'switch.your_board_outlet'

         TFTPServerResource:
           address: '10.0.0.156'
           port: 3069
           root: '/var/lib/tftpboot'

         XilinxDeviceJTAG:
           root_target: 1
         XilinxVivadoTool:
           vivado_path: '/opt/Xilinx/Vivado/2023.2'
           xsdb_path: '/opt/Xilinx/Vivado/2023.2/bin/xsdb'
           version: '2023.2'

       drivers:
         SerialDriver: {}
         HomeAssistantPowerDriver: {}
         TFTPServerDriver: {}
         XilinxJTAGDriver: {}

         ADIShellDriver:
           prompt: 'root@.*[#$]'
           login_prompt: '(analog|recovery) login: ?'
           username: 'root'
           password: 'analog'

         BootZynq7000JTAGRecovery:
           ps7_init_tcl: '/tmp/recovery/ps7_init.tcl'
           uboot_elf: '/tmp/recovery/u-boot.elf'
           bitstream_path: '/tmp/recovery/system_top.bit'
           recovery_kernel: 'uImage'
           recovery_dtb: 'devicetree.dtb'
           recovery_initramfs: 'uInitrd.recovery'
           recovery_login_marker: 'recovery login:'
           sd_image_url: 'http://10.0.0.156:8080/2025-03-18-ADI-Kuiper-full.img'
           sd_device: '/dev/mmcblk0'
           download_cmd_template: 'wget -q -O - "{url}"'
           uboot_prompt: 'Zynq>.*'
           kernel_addr: '0x3000000'
           dtb_addr: '0x2A00000'
           initramfs_addr: '0x10000000'
           bootargs: 'console=ttyPS0,115200 earlyprintk loglevel=8 rdinit=/init'
           wait_for_sd_flash_timeout: 1800

**Attributes**:

- ``ps7_init_tcl`` / ``uboot_elf`` (str, required): host paths xsdb sources to bring up DDR and load U-Boot. Extract from a known-good ``BOOT.BIN`` with ``bootgen -arch zynq -read BOOT.BIN``.
- ``bitstream_path`` (str, optional but **required when the recovery DTB references FPGA-fabric peripherals**): Vivado ``.bit`` file. The driver re-flashes it via ``fpga -f`` before downloading U-Boot.
- ``fsbl_elf`` (str, optional): if your bring-up needs an FSBL stage between ps7_init and U-Boot, set this; the driver downloads + runs it, then halts before the U-Boot stage.
- ``a9_target_name`` (str, default ``'*Cortex-A9 MPCore #0'``): xsdb target filter.
- ``recovery_kernel`` / ``recovery_dtb`` / ``recovery_initramfs`` (str, required): filenames inside the bound TFTP root.
- ``recovery_login_marker`` (str, default ``'recovery login:'``): what ``/init`` prints just before reading the username.
- ``sd_image_url`` (str, required): HTTP URL of the SD-card image to flash.
- ``sd_device`` (str, default ``'/dev/mmcblk0'``): target block device inside the recovery rootfs.
- ``download_cmd_template`` (str, default ``'wget -q -O - "{url}"'``): formatted with ``url=<sd_image_url>`` to compose the download command. Switch to ``'curl -fsSL --retry 3 "{url}"'`` if your rootfs has curl.
- ``board_variant`` (str, optional): subdirectory name inside the FAT boot partition that holds the per-board ``BOOT.BIN`` / ``uImage`` / ``devicetree.dtb`` (e.g. ``zynq-zc706-adv7511-adrv937x``). When set, the strategy mounts ``{sd_device}p{sd_boot_partition}`` after the dd and copies the listed files up to the partition root, sync, unmount. Required when flashing ADI's multi-board ``Kuiper-full`` image — Zynq-7000 BootROM only reads ``BOOT.BIN`` at the root, and a raw dd of that image leaves the root empty of board-specific boot files.
- ``board_variant_files`` (tuple[str, ...], default ``("BOOT.BIN", "uImage", "devicetree.dtb")``): file names copied from the variant subdirectory to the partition root. Extend for Kuiper variants that also ship ``boot.scr``, custom ``system.dtb``, etc.
- ``sd_boot_partition`` (int, default ``1``): which numbered partition of ``sd_device`` holds the FAT boot files (so the strategy mounts ``/dev/mmcblk0p<N>``).
- ``sd_mount_point`` (str, default ``'/mnt'``): mount point inside the recovery initramfs.
- ``post_flash_commands`` (list[str], default ``[]``): extra shell commands run in the recovery shell after the dd + board-variant copy. Use for tweaks that don't fit the board-variant pattern.
- ``post_flash_timeout`` (int, default ``120``): per-command timeout for the board-variant copy and each ``post_flash_commands`` entry.
- ``uboot_prompt`` (str, default ``'zynq-uboot>|U-Boot>|=>'``): regex matched against the U-Boot prompt; tighten to e.g. ``'Zynq>.*'`` for Xilinx's shipped U-Boot.
- ``kernel_addr`` / ``dtb_addr`` / ``initramfs_addr`` (str hex): DDR addresses loaded by ``tftpboot``. Defaults are conservative for a 1 GB Zynq-7000; bump ``initramfs_addr`` higher if your initramfs is large.
- ``bootargs`` (str): kernel command line. Default uses ``rdinit=/init`` (cpio's own ``/init``) and intentionally omits ``root=`` because the unpacked initramfs is the rootfs.
- ``jtag_bootstrap_retries`` (int, default 2): max retries on xsdb failure; cold-cycles power between attempts.
- ``wait_for_uboot_prompt_timeout`` (int, default 60) / ``wait_for_recovery_linux_timeout`` (int, default 180) / ``wait_for_sd_flash_timeout`` (int, default 1800): per-phase timeouts.

**Usage Example**:

.. code-block:: python

   from labgrid import Environment

   env = Environment("zc706_recovery.yaml")
   target = env.get_target("zc706_recovery")
   strategy = target.get_driver("BootZynq7000JTAGRecovery")

   # Walk the whole pipeline; cascades through all prior states.
   strategy.transition("sd_flash_done")

   # Power off and leave the freshly-flashed SD ready for a normal cold boot.
   strategy.transition("soft_off")

**Building the recovery initramfs**:

The recovery initramfs builder lives in :mod:`adi_lg_plugins.recovery`.
You provide a cross-compiled static busybox; the module bundles the
``/init`` script, udhcpc hook, applet symlinks, cpio packer, and
``mkimage`` wrap.

.. code-block:: bash

   # One-time: cross-compile static busybox for ARMv7-A (Cortex-A9).
   export CROSS_COMPILE=/path/to/arm-none-linux-gnueabihf-
   export ARCH=arm
   cd busybox-1.36.1 && make defconfig
   sed -i 's/^# CONFIG_STATIC is not set/CONFIG_STATIC=y/' .config
   make -j$(nproc) busybox

   # Build + stage the initramfs in one shot.
   adi-lg build-recovery-initramfs \
       --busybox $(pwd)/busybox \
       --out /var/lib/tftpboot/uInitrd.recovery

Or programmatically:

.. code-block:: python

   from adi_lg_plugins.recovery import build_recovery_initramfs
   build_recovery_initramfs(
       busybox="/path/to/static/busybox",
       output="/var/lib/tftpboot/uInitrd.recovery",
   )

See ``examples/zynq7000_recovery/README.md`` for customization hooks
(``stage_recovery_rootfs`` + ``build_cpio``) when the defaults don't fit.

**Troubleshooting**:

*Kernel goes silent at "zynq-pinctrl initialized" and never reaches /init*:
   The recovery DTB references FPGA-fabric peripherals (``axi_clkgen``, ``axi_jesd204_*``, ``axi_adxcvr``, etc.) and your ``bitstream_path`` isn't set or the bitstream is wrong. AXI reads to unprogrammed fabric hang the CPU. Set ``bitstream_path`` to the matching ``.bit`` file extracted from ``BOOT.BIN``.

*"Run /init as init process" prints but nothing further*:
   The cpio is missing ``/dev/console`` (char 5:1). The kernel ``exec``'s ``/init`` with closed stdio so every ``echo`` vanishes. Standard ``find . | cpio -o -H newc`` cannot create device nodes without root; use the bundled ``examples/zynq7000_recovery/build_cpio.py`` which writes the newc bytes directly.

*"sh: mktemp: not found" / "No XMODEM receiver (lrz, rz, rx) available"*:
   ADIShellDriver's file-transfer path needs ``mktemp`` and ``rx``/``rz``/``lrz``. Add the corresponding busybox applet symlinks in the rootfs:

   .. code-block:: bash

      for app in mktemp rx rz base64 tee find head tail wc tr; do
          ln -sf busybox rootfs/bin/$app
      done

*sd_flash hangs after XMODEM xfer*:
   busybox ``rx`` over a raw initramfs console can fail to return to prompt cleanly. The strategy avoids this by using ``shell.run()`` inline rather than ``shell.run_script()``. If you've subclassed and reintroduced ``run_script``, switch back to inline ``run``.

*"FTDMGR wasn't properly initialized" from xsdb*:
   Vivado's bundled FTDI plumbing needs Digilent Adept Runtime installed system-wide. ``sudo apt install ./digilent.adept.runtime_*.deb`` from the Digilent website.

*xsdb says "available targets: none" with the cable plugged in*:
   Linux's ``ftdi_sio`` driver claimed the Digilent FT232H as a TTY. Add a udev rule that unbinds it:

   .. code-block:: text

      # /etc/udev/rules.d/53-digilent-jtag-unbind.rules
      ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="0403", \
          ATTR{idProduct}=="6014", ATTR{manufacturer}=="Digilent", \
          RUN+="/bin/bash -c 'sleep 0.3; echo -n %k:1.0 > /sys/bus/usb/drivers/ftdi_sio/unbind 2>/dev/null || true'"

   Then ``sudo udevadm control --reload-rules`` and replug (or power-cycle the board, since the FT232H is bus-powered from it).

BootSelMap Strategy
-------------------

**Purpose**: Boot a dual-FPGA design with primary Zynq FPGA (running Linux) and secondary Virtex FPGA (booted via SelMap interface).

**State Machine**:

The strategy manages 11 states with dual-FPGA boot orchestration:

.. mermaid::

   stateDiagram-v2
       [*] --> unknown
       unknown --> powered_off: Initialize
       powered_off --> booting_zynq: Power on
       booting_zynq --> booted_zynq: Wait for boot

       booted_zynq --> update_zynq_boot_files: Check files needed
       update_zynq_boot_files --> update_zynq_boot_files: Restart if files uploaded
       update_zynq_boot_files --> update_virtex_boot_files: Zynq ready

       update_virtex_boot_files --> trigger_selmap_boot: Files uploaded
       trigger_selmap_boot --> wait_for_virtex_boot: Run SelMap script

       wait_for_virtex_boot --> wait_for_virtex_boot: Poll IIO device (30s)
       wait_for_virtex_boot --> wait_for_virtex_boot: Poll JESD status (120s)
       wait_for_virtex_boot --> booted_virtex: JESD complete

       booted_virtex --> shell: Activate shell
       shell --> soft_off: Graceful shutdown
       soft_off --> [*]

       note right of update_zynq_boot_files
           Self-transition for boot file restart
       end note

       note right of wait_for_virtex_boot
           Polls IIO and JESD completion
       end note

**Hardware Requirements**:

- Power control for both FPGAs
- Serial console access to Zynq (ADIShellDriver)
- SSH access to Zynq after boot
- SelMap interface connected from Zynq to Virtex for secondary FPGA programming
- Kuiper release files for both Zynq and Virtex bitstreams

**Configuration Example**:

.. code-block:: yaml

    targets:
      dual_fpga:
        resources:
          VesyncOutlet:
            outlet_names: 'Dual FPGA Power'
            username: 'your_email@example.com'
            password: 'your_password'

          SerialPort:
            port: '/dev/ttyUSB0'
            baudrate: 115200

          NetworkInterface:
            hostname: 'zynq.local'
            username: 'root'
            password: 'analog'

          KuiperDLDriver:
            release_version: '2024.r1'

        drivers:
          VesyncPowerDriver: {}
          ADIShellDriver:
            prompt: 'root@.*:.*#'
            login_prompt: 'login:'
            username: 'root'
            password: 'analog'
          SSHDriver:
            hostname: 'zynq.local'
            username: 'root'
            password: 'analog'

        strategies:
          BootSelMap:
            reached_linux_marker: 'analog'
            ethernet_interface: 'eth0'
            iio_jesd_driver_name: 'axi-ad9081-rx-hpc'
            pre_boot_boot_files: null
            post_boot_boot_files: null

**Usage Example**:

.. code-block:: python

    env = Environment("target.yaml")
    target = env.get_target("dual_fpga")
    strategy = target.get_strategy("BootSelMap")

    # Boot and wait for shell access
    # The strategy automatically transitions through all intermediate states
    strategy.transition("shell")

    # Verify both FPGAs are booted
    shell = target.get_driver("ADIShellDriver")
    shell.run_command("cat /proc/device-tree/chosen/fpga/axi-ad9081-rx-hpc/status")

    # Graceful shutdown
    strategy.transition("soft_off")

Note:
   The strategy automatically transitions through all intermediate states
   (powered_off → booting_zynq → booted_zynq → update_zynq_boot_files →
   update_virtex_boot_files → trigger_selmap_boot → wait_for_virtex_boot →
   booted_virtex → shell). You only need to request the final state.

**Advanced: Pre/Post Boot Files**:

The strategy supports optional pre-boot and post-boot file copying:

.. code-block:: python

    # In target configuration:
    # BootSelMap:
    #   pre_boot_boot_files: {'local_path': '/boot/remote_path'}
    #   post_boot_boot_files: {'local_path': '/boot/remote_path'}

    # Pre-boot files are copied before Zynq boot
    # Post-boot files are copied after Zynq boots but before Virtex boot

**Configuration Details**:

The BootSelMap strategy requires careful configuration of boot files for both
the Zynq (primary) and Virtex (secondary) FPGAs:

- **pre_boot_boot_files**: Files uploaded to Zynq before Virtex configuration.
  Dictionary format: ``{local_path: remote_path}``

  Example files:
  - Zynq device tree blob (system.dtb)
  - Zynq boot files (BOOT.BIN, image.ub)

  These files are uploaded via SSH, then the Zynq is rebooted to apply them.

- **post_boot_boot_files**: Files uploaded after Zynq boots with new device tree.
  Dictionary format: ``{local_path: remote_path}``

  Example files:
  - Virtex bitstream (.bin)
  - Virtex device tree overlay (.dtbo)
  - SelMap boot script (selmap_dtbo.sh)

  These files are used to configure the Virtex FPGA via SelMap interface.

- **ethernet_interface**: Network interface name on target (e.g., "eth0").
  Used to discover target IP address for SSH connections.

- **iio_jesd_driver_name**: IIO device name to poll after Virtex boot.
  Example: "axi-ad9081-rx-hpc" for AD9081 transceiver.
  Strategy polls this device to verify Virtex has booted successfully.

**Troubleshooting**:

*Zynq boots but Virtex doesn't configure*:
   - Check pre_boot_boot_files and post_boot_boot_files are correctly specified
   - Verify .dtbo and .bin files exist at specified paths
   - Check SelMap script exists: ``/boot/ci/selmap_dtbo.sh``
   - Run script manually: ``cd /boot/ci && ./selmap_dtbo.sh -d vu11p.dtbo -b vu11p.bin``

*IIO JESD device not found (wait_for_virtex_boot timeout)*:
   - Increase timeout if device takes longer than 30s to appear
   - Check device tree is correct for your hardware
   - Verify Virtex bitstream matches Zynq device tree configuration
   - Run ``dmesg | grep iio`` to see IIO driver messages

*JESD state machine doesn't reach opt_post_running_stage*:
   - Check JESD clock configuration in device tree
   - Verify AD9081 (or similar) transceiver is properly configured
   - Check for JESD sync errors: ``iio_attr -d <device> jesd204_fsm_error``
   - Typical JESD states: link_setup → clocks → link → opt_post_running_stage

*Files uploaded but boot still fails*:
   - Strategy restarts after uploading pre_boot_boot_files
   - Check serial console for Zynq boot errors after restart
   - Verify uploaded files are valid (not corrupted)
   - Ensure sufficient space on /boot partition

*"Permission denied" when uploading files via SSH*:
   - Verify SSH key is configured correctly
   - Check target filesystem is mounted read-write
   - Ensure sufficient disk space on target
   - Try manual SSH: ``scp localfile root@<device>:/boot/``

*Restart loop with pre_boot_boot_files*:
   - Strategy uploads files, restarts, and checks again
   - If files are different, it restarts again (infinite loop possible)
   - Ensure local files don't change between boots
   - Check _copied_pre_boot_files flag is being set correctly

BootRPI Strategy
----------------

**Purpose**: Manage Raspberry Pi devices primarily via SSH, with optional power control, serial console, and SD card mux support.

**Use Case**: General-purpose RPI management for testing and automation. Works with minimal hardware (SSH only) or full setups with power control and serial console. The strategy uses a cascading priority for reboot and shutdown operations, falling back through available drivers.

**State Machine**:

.. mermaid::

   stateDiagram-v2
       [*] --> unknown
       unknown --> off: Initialize
       off --> booting: Power on / reboot

       booting --> booted: Wait for SSH connectivity

       note right of booting
           Reboot priority: power > serial > SSH
       end note

       booted --> shell: SSH session ready

       note right of booted
           Retries SSH connection with timeout
       end note

       shell --> soft_off: Graceful shutdown
       soft_off --> [*]

       note right of off
           Shutdown priority: power > serial > SSH
       end note

**Reboot/Shutdown Priority**:

The strategy cascades through available drivers for power operations:

1. **Power driver** (e.g., VeSync, CyberPower) -- hard power cycle
2. **Serial console** (ADIShellDriver) -- ``reboot`` / ``poweroff`` command
3. **SSH** (SSHDriver) -- ``sudo reboot`` / ``sudo poweroff`` command

When no power driver is available and the device is in ``unknown`` state, the strategy skips the off/booting cycle and connects directly via SSH, assuming the device is already running.

**Hardware Requirements**:

- SSH access (SSHDriver) -- **required**
- Power control (PowerProtocol) -- optional, enables hard power cycling
- Serial console (ADIShellDriver) -- optional, provides boot monitoring and fallback reboot
- SD card mux (USBSDMuxDriver) -- optional, for SD card management

**Configuration Example (SSH only)**:

.. code-block:: yaml

    targets:
      rpi:
        resources:
          NetworkService:
            address: 10.0.0.149
            username: root
            password: analog

        drivers:
          SSHDriver: {}
          BootRPI:
            ssh_boot_timeout: 60

**Configuration Example (with power and serial)**:

.. code-block:: yaml

    targets:
      rpi:
        resources:
          NetworkService:
            address: 10.0.0.149
            username: root
            password: analog

          VesyncOutlet:
            outlet_names: 'RPI Power'
            username: 'your_email@example.com'
            password: 'your_password'
            delay: 5.0

          RawSerialPort:
            port: /dev/ttyUSB0
            speed: 115200

        drivers:
          SSHDriver: {}
          VesyncPowerDriver: {}
          SerialDriver: {}
          ADIShellDriver:
            prompt: 'root@.*:.*#'
            login_prompt: 'login:'
            username: 'root'
            password: 'analog'
          BootRPI:
            ssh_boot_timeout: 120
            power_off_delay: 5

**Usage Example**:

.. code-block:: python

    env = Environment("rpi.yaml")
    target = env.get_target("rpi")
    strategy = target.get_driver("BootRPI")

    # Connect to the RPI
    strategy.transition("shell")

    # Run commands via SSH
    ssh = target.get_driver("SSHDriver")
    stdout, stderr, returncode = ssh.run("uname -a")
    print(stdout)

    # Transfer files
    ssh.put("/local/path/config.txt", "/remote/path/config.txt")

    # Graceful shutdown
    strategy.transition("soft_off")

**Attributes**:

- ``ssh_boot_timeout`` (int): Seconds to wait for SSH connectivity after boot (default: 120)
- ``power_off_delay`` (int): Seconds to wait after power off before power on (default: 2)

**Troubleshooting**:

*SSH connection times out during boot*:
   - Increase ``ssh_boot_timeout`` for slower devices
   - Verify the RPI's IP address is correct in the NetworkService resource
   - Check network connectivity: ``ping <device-ip>``
   - Ensure SSH server is running on the RPI

*Device powers off but doesn't come back*:
   - Without a power driver, ``sudo poweroff`` shuts down the RPI permanently
   - Add a power driver (VeSync, CyberPower, HomeAssistant) for reliable power cycling
   - Or use serial console as a fallback for reboot commands

*Permission denied on SSH commands*:
   - Verify username and password in NetworkService resource
   - Check SSH key configuration if using key-based auth
   - Ensure the user has sudo privileges for reboot/poweroff commands

*Strategy enters "broken state"*:
   - The ``@never_retry`` decorator marks the strategy as broken after any failure
   - Create a new target/strategy instance to recover
   - Check logs for the original exception that caused the broken state

Best Practices
--------------

**1. State Awareness**

Always understand the current state before transitioning:

.. code-block:: python

    # Check current state
    if strategy.status != Status.shell:
        strategy.transition("shell")

    # Avoid redundant transitions
    if strategy.status != Status.powered_off:
        strategy.transition("powered_off")

**2. Error Recovery**

Implement error handling for robust test sequences:

.. code-block:: python

    from labgrid.strategy import StrategyError

    def safe_transition(strategy, target_state, max_retries=3):
        for attempt in range(max_retries):
            try:
                strategy.transition(target_state)
                return True
            except StrategyError as e:
                print(f"Transition failed (attempt {attempt+1}): {e}")
                if attempt < max_retries - 1:
                    # Reset to known state
                    try:
                        strategy.transition(Status.powered_off)
                    except:
                        pass
                    time.sleep(5)
        return False

**3. Driver Lifecycle Management**

Understand that strategies activate/deactivate drivers automatically. Do not manually activate drivers that are managed by the strategy:

.. code-block:: python

    # Good - Let strategy manage power driver
    strategy.transition("shell")

    # Bad - Don't double-activate
    strategy.transition("shell")
    power = target.get_driver("VesyncPowerDriver")  # Already active

**4. Timeout Configuration**

Set appropriate timeouts for slow hardware:

.. code-block:: python

    # In shell driver configuration
    ADIShellDriver:
      prompt: 'root@.*:.*#'
      login_prompt: 'login:'
      username: 'root'
      password: 'analog'
      login_timeout: 120  # Increase for slow boots
      post_login_settle_time: 5  # Extra time after login

**5. Cleanup on Failure**

Always attempt graceful shutdown in test cleanup:

.. code-block:: python

    def test_device_functionality():
        try:
            strategy.transition("shell")
            # Run tests
            shell.run_command("some_test_command")
        finally:
            # Cleanup even if test fails
            try:
                strategy.transition("soft_off")
            except:
                pass  # Power off if soft off fails

**6. Logging and Debugging**

Enable debug logging to understand strategy behavior:

.. code-block:: python

    import logging

    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger("labgrid")
    logger.setLevel(logging.DEBUG)

    strategy.transition("shell")  # Now see detailed debug output

Custom Strategy Development
-----------------------------

Creating custom strategies follows the labgrid plugin pattern. A strategy must:

1. Inherit from ``labgrid.strategy.Strategy``
2. Define required/optional bindings
3. Implement a state machine with an enum
4. Provide a ``transition()`` method
5. Register with ``@target_factory.reg_driver``

**Minimal Example**:

.. code-block:: python

    import enum
    import attr
    from labgrid.factory import target_factory
    from labgrid.step import step
    from labgrid.strategy import Strategy, StrategyError, never_retry

    class MyStatus(enum.Enum):
        unknown = 0
        state_a = 1
        state_b = 2

    @target_factory.reg_driver
    @attr.s(eq=False)
    class MyStrategy(Strategy):
        """Custom strategy template."""

        bindings = {
            "power": "PowerProtocol",
            "shell": "ADIShellDriver",
        }

        status = attr.ib(default=MyStatus.unknown)

        @never_retry
        @step()
        def transition(self, status, *, step):
            if not isinstance(status, MyStatus):
                status = MyStatus[status]

            if status == MyStatus.state_a:
                self.target.activate(self.power)
                self.power.on()
            elif status == MyStatus.state_b:
                self.transition(MyStatus.state_a)
                self.target.activate(self.shell)
            else:
                raise StrategyError(f"no transition to {status}")

            self.status = status

**Advanced Pattern - Hooks**:

.. code-block:: python

    @attr.s(eq=False)
    class HookedStrategy(Strategy):
        """Strategy with before/after hooks."""

        status = attr.ib(default=Status.unknown)
        _hooks = attr.ib(factory=dict, init=False)

        def register_hook(self, state, hook_fn):
            """Register a callable to run after transitioning to state."""
            if state not in self._hooks:
                self._hooks[state] = []
            self._hooks[state].append(hook_fn)

        @never_retry
        @step()
        def transition(self, status, *, step):
            # ... transition logic ...

            # Run hooks
            if status in self._hooks:
                for hook in self._hooks[status]:
                    hook()

BootFabric Strategy
-------------------

**Purpose**: Boot logic-only Xilinx FPGAs (Virtex/Artix/Kintex) with Microblaze soft processors via JTAG.

**Use Case**: Useful for FPGA-based systems without SoC (no ARM cores), where the processor is implemented in FPGA fabric. Common with ADI high-speed data converter evaluation boards (AD9081, AD9371, etc.) on Xilinx FPGA development boards like VCU118.

**State Machine**:

.. mermaid::

   stateDiagram-v2
       [*] --> unknown
       unknown --> powered_off: Initialize
       powered_off --> powered_on: Power on FPGA
       powered_on --> flash_fpga: Flash bitstream and kernel via JTAG
       flash_fpga --> booted: Start kernel execution and wait for boot
       booted --> shell: Activate shell access
       shell --> soft_off: Graceful shutdown
       soft_off --> [*]

       note right of flash_fpga
           Flash bitstream, download kernel, start execution
       end note

       note right of booted
           Wait for kernel boot marker (e.g., "login:")
       end note

**Configuration Example**:

.. code-block:: yaml

   targets:
     vcu118:
       resources:
         RawSerialPort:
           port: "/dev/ttyUSB0"
           speed: 115200

         XilinxDeviceJTAG:
           root_target: 1
           microblaze_target: 3
           bitstream_path: "/builds/system_top.bit"
           kernel_path: "/builds/simpleImage.vcu118.strip"

         XilinxVivadoTool:
           vivado_path: "/tools/Xilinx/Vivado"
           version: "2023.2"

         NetworkPowerPort:
           model: "gude"
           host: "192.168.1.100"
           index: 1

       drivers:
         SerialDriver: {}
         ADIShellDriver: {}
         XilinxJTAGDriver: {}
         NetworkPowerDriver: {}

         BootFabric:
           reached_boot_marker: "login:"
           wait_for_boot_timeout: 120
           verify_iio_device: "axi-ad9081-rx-hpc"

**Usage Example**:

.. code-block:: python

   from labgrid import Environment

   # Load environment
   env = Environment("vcu118.yaml")
   target = env.get_target("vcu118")

   # Get strategy and boot
   strategy = target.get_driver("BootFabric")
   strategy.transition("shell")

   # Run commands
   shell = target.get_driver("ADIShellDriver")
   stdout, _, _ = shell.run("cat /proc/cpuinfo")
   print(stdout)

   # Shutdown
   strategy.transition("soft_off")

**Attributes**:

- ``reached_boot_marker`` (str): String to expect in console when boot complete (default: "login:")
- ``wait_for_boot_timeout`` (int): Seconds to wait for boot marker (default: 120)
- ``verify_iio_device`` (str, optional): IIO device name to verify after boot

**Troubleshooting**:

*Bitstream flash fails*:
   - Verify JTAG cable is connected
   - Check bitstream file exists and path is correct
   - Run ``xsdb -interactive`` to verify xsdb works
   - Ensure FPGA is powered on

*Kernel download fails*:
   - Verify kernel file exists and path is correct
   - Ensure bitstream was flashed first
   - Check Microblaze target ID matches your hardware (run ``xsdb``, then ``targets``)

*Boot timeout*:
   - Increase ``wait_for_boot_timeout``
   - Check serial console is properly connected
   - Verify kernel is compatible with bitstream design

*IIO device not found*:
   - Check kernel has appropriate IIO drivers compiled
   - Verify device tree matches your hardware
   - Run ``dmesg`` to see kernel boot messages

SoftwareProvisioningStrategy
----------------------------

**Purpose**: Provision software on a target: install packages, clone repositories, run builds, and run tests. Orthogonal to the boot strategies — run it after any boot strategy has reached a shell state.

**State Machine**:

.. mermaid::

   stateDiagram-v2
       [*] --> unknown
       unknown --> connected: Activate SoftwareInstallerDriver
       connected --> software_installed: Install packages
       software_installed --> repos_cloned: Clone repositories
       repos_cloned --> built: Run build steps
       built --> tested: Run test steps
       tested --> [*]

       note right of software_installed
           Auto-detects package manager:
           apt-get / dnf / opkg / pacman / apk
       end note

**Required Resources and Drivers**

- ``SoftwareInstallerDriver``, which itself requires ``CommandProtocol`` + ``FileTransferProtocol`` bindings (typically ``ADIShellDriver`` or ``SSHDriver``).

**Configuration Example**

.. code-block:: yaml

    targets:
      netdevice:
        resources:
          NetworkService:
            address: '10.0.0.23'
            username: 'root'
            password: 'analog'

        drivers:
          SSHDriver: {}
          SoftwareInstallerDriver: {}

          SoftwareProvisioningStrategy:
            packages:
              - git
              - build-essential
              - cmake
            repos:
              - url:    'https://github.com/analogdevicesinc/libiio'
                dest:   '/opt/libiio'
                branch: 'main'
              - ['https://github.com/analogdevicesinc/libad9361-iio', '/opt/libad9361']
            build_steps:
              - cmd: 'cmake -S . -B build && cmake --build build -j4'
                dir: '/opt/libiio'
            test_steps:
              - cmd: 'ctest --test-dir build'
                dir: '/opt/libiio'

**Attributes**

- ``packages`` (list[str]): Package names to install via the detected package manager.
- ``repos`` (list[dict | tuple]): Each entry is either ``{'url': ..., 'dest': ..., 'branch': ...}`` or a positional tuple ``(url, dest[, branch])``.
- ``build_steps`` (list[dict | tuple]): Each entry is ``{'cmd': ..., 'dir': ...}`` or ``(cmd, dir)``. Run with a 1-hour timeout.
- ``test_steps`` (list[dict | tuple]): Same shape as ``build_steps``. ``dir`` is optional.

**Usage Example**

.. code-block:: python

    # After any boot strategy has reached a shell state:
    provision = target.get_driver("SoftwareProvisioningStrategy")

    provision.transition("software_installed")   # packages
    provision.transition("repos_cloned")         # + repos
    provision.transition("built")                # + builds
    provision.transition("tested")               # + tests

**Notes**

- Each transition cascades through the prior states, so ``transition("tested")`` from ``unknown`` runs everything end-to-end.
- ``packages``, ``repos``, ``build_steps``, and ``test_steps`` all default to empty lists, so the strategy is a no-op until configured.

State Transition Reference
---------------------------

This section provides quick reference tables for valid state transitions in each strategy.

**BootSelMap State Transitions**:

.. list-table::
   :header-rows: 1
   :widths: 30 30 40

   * - From State
     - To State
     - Actions Performed
   * - unknown
     - powered_off
     - Initialize, power off
   * - powered_off
     - booting_zynq
     - Power on Zynq
   * - booting_zynq
     - booted_zynq
     - Wait for Zynq boot
   * - booted_zynq
     - update_zynq_boot_files
     - Upload Zynq files via SSH (if configured)
   * - update_zynq_boot_files
     - update_zynq_boot_files
     - Restart if boot files uploaded
   * - update_zynq_boot_files
     - update_virtex_boot_files
     - Zynq ready for next stage
   * - update_virtex_boot_files
     - trigger_selmap_boot
     - Virtex files uploaded
   * - trigger_selmap_boot
     - wait_for_virtex_boot
     - Run SelMap script
   * - wait_for_virtex_boot
     - booted_virtex
     - Verify IIO device and JESD completion
   * - booted_virtex
     - shell
     - Activate shell driver
   * - shell
     - soft_off
     - Graceful shutdown
   * - soft_off
     - (end)
     - Both FPGAs powered down

**BootFabric State Transitions**:

.. list-table::
   :header-rows: 1
   :widths: 30 30 40

   * - From State
     - To State
     - Actions Performed
   * - unknown
     - powered_off
     - Initialize
   * - powered_off
     - powered_on
     - Power on FPGA
   * - powered_on
     - flash_fpga
     - Flash bitstream via JTAG
   * - flash_fpga
     - booted
     - Download kernel and start execution
   * - booted
     - shell
     - Wait for boot marker and activate shell
   * - shell
     - soft_off
     - Graceful shutdown
   * - soft_off
     - (end)
     - FPGA powered down

**BootZynq7000JTAGRecovery State Transitions**:

.. list-table::
   :header-rows: 1
   :widths: 30 30 40

   * - From State
     - To State
     - Actions Performed
   * - unknown
     - powered_off
     - Deactivate shell + TFTP, power off
   * - powered_off
     - powered_on
     - Cold-cycle (off + 5 s + on)
   * - powered_on
     - jtag_bootstrap
     - xsdb: ps7_init + optional bitstream + dow u-boot.elf + con
   * - jtag_bootstrap
     - uboot_prompt
     - Activate TFTP + shell, wait for autoboot, send space, set U-Boot prompt
   * - uboot_prompt
     - tftp_recovery_kernel
     - dhcp + setenv + tftpboot kernel/dtb/initramfs + bootm
   * - tftp_recovery_kernel
     - linux_recovery
     - Wait for recovery_login_marker, login via ADIShellDriver
   * - linux_recovery
     - sd_flash_done
     - shell.run("wget URL | dd of=/dev/mmcblk0 ... && echo SD_FLASH_OK")
   * - sd_flash_done
     - soft_off
     - Try ``poweroff`` then hard power cut
   * - soft_off
     - sd_boot_verified
     - Cold-cycle, then ``console.expect`` ``verify_boot_login_marker``
       (no boot-mode switches change — BootROM just reads the
       freshly-written SD this time)
   * - sd_boot_verified
     - (end)
     - SD boot confirmed; recovery verified end-to-end

**BootRPI State Transitions**:

.. list-table::
   :header-rows: 1
   :widths: 30 30 40

   * - From State
     - To State
     - Actions Performed
   * - unknown
     - off
     - Deactivate drivers, shutdown via cascade
   * - unknown
     - booted
     - Skip off/booting (no power driver), connect SSH directly
   * - off
     - booting
     - Power on or reboot via cascade
   * - booting
     - booted
     - Wait for SSH connectivity (retry loop)
   * - booted
     - shell
     - SSH session ready for commands and file transfer
   * - any
     - soft_off
     - Graceful shutdown via cascade, deactivate power

See Also
~~~~~~~~

- :doc:`../api/strategies` - Complete API reference for all strategies
- :doc:`drivers` - Information about available drivers
- :doc:`resources` - Resource configuration reference
- :doc:`../examples/advanced/full-boot-cycle` - Complete boot workflow example
- Labgrid documentation: https://labgrid.readthedocs.io/
