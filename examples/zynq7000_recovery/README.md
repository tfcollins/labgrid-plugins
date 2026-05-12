# BootZynq7000JTAGRecovery example

Reference labgrid environment for `BootZynq7000JTAGRecovery`. Used on
ADRV9371-ZC706 with Vivado 2023.2; adapt the IPs, paths, and HA entity
for your bench.

The only file kept here is `lg_zc706_recovery.yaml` — everything else
(init script, udhcpc hook, cpio builder, applet symlinks, mkimage wrap)
lives in `adi_lg_plugins.recovery` so it ships with the package.

## End-to-end recipe

```bash
# 1. Install an ARM cross-toolchain (one-time, system-wide).
#    Ubuntu/Debian:  sudo apt install gcc-arm-linux-gnueabihf
#    or use the Arm GNU toolchain release tarball.

# 2. Extract the JTAG bootstrap inputs from a known-good BOOT.BIN.
#    Yields fsbl.elf, u-boot.elf, system_top.bit. The bitstream is
#    required when the recovery DTB references FPGA fabric peripherals
#    (axi_clkgen, axi_jesd204_*, axi_adxcvr, ...); without it the kernel
#    hangs probing AXI addresses.
bootgen -arch zynq -read /path/to/BOOT.BIN
# Also: generate ps7_init.tcl from your design's .xsa (Vivado emits it).

# 3. Adapt lg_zc706_recovery.yaml — point ps7_init_tcl, uboot_elf,
#    bitstream_path, sd_image_path at your files, and replace the
#    HomeAssistant URL/token/entity with your own.

# 4. Run the recovery. The strategy:
#      - cross-compiles busybox on first run (cached in ~/.cache/...)
#      - builds uInitrd.recovery into the TFTP root if missing
#      - opens an ephemeral HTTP server for sd_image_path
#      - JTAG-bootstraps U-Boot, TFTPs recovery, dd's the image
python3 -c "
import adi_lg_plugins  # registers entry-point drivers
from labgrid import Environment
t = Environment('lg_zc706_recovery.yaml').get_target('main')
t.get_strategy().transition('sd_flash_done')
"
```

That's it — the user only invokes `transition('sd_flash_done')`. If you
already have a cross-compiled busybox or you want to stage every artifact
by hand, you can also call the lower-level helpers directly:

```bash
adi-lg build-recovery-initramfs \
    --busybox /path/to/static/busybox \
    --out /var/lib/tftpboot/uInitrd.recovery
```

Expected log highlights:

```
JTAG bootstrap attempt 1/2...
Zynq U-Boot bootstrap completed
U-Boot prompt reached
Waiting for recovery login marker 'recovery login:'...
Recovery Linux shell ready
Streaming SD image to /dev/mmcblk0 (timeout 1800s)...
SD card reflashed successfully
```

## Customizing the initramfs

The defaults in `adi_lg_plugins.recovery` cover the common case. To
inspect or override:

```python
from adi_lg_plugins.recovery import (
    DEFAULT_APPLETS,
    DEFAULT_DEV_NODES,
    build_cpio,
    build_recovery_initramfs,
    stage_recovery_rootfs,
)

# One-shot with overrides.
build_recovery_initramfs(
    busybox="/path/to/busybox",
    output="uInitrd.recovery",
    applets=DEFAULT_APPLETS + ("crond",),  # add extras
    image_name="my-custom-recovery",
)

# Or stage manually, hand-edit, then pack.
stage_recovery_rootfs("/path/to/busybox", "rootfs")
# ... edit rootfs/init or drop in extra files ...
build_cpio("rootfs", "initramfs.cpio", dev_nodes=DEFAULT_DEV_NODES)
```

The bundled `/init` and `udhcpc-default.script` live under
`adi_lg_plugins/recovery/templates/` — read them there if you want to
see exactly what the kernel ends up running, or pass a custom rootfs
into `build_cpio()` for a from-scratch flow.

## Tuning per board

- `kernel_addr`, `dtb_addr`, `initramfs_addr` — DDR load addresses;
  defaults are conservative for a 1 GB Zynq-7000. Push `initramfs_addr`
  higher if your recovery initramfs is large (the area between kernel
  and ramdisk must not overlap kernel decompression scratch space).
- `uboot_prompt` — match your U-Boot's actual prompt (e.g. `Zynq>` for
  the Xilinx-shipped one, `=>` for upstream U-Boot).
- `download_cmd_template` — defaults to `wget -q -O - "{url}"`; switch
  to `curl -fsSL --retry 3 "{url}"` if your rootfs has curl.
- `recovery_login_marker` — must match what `/init` prints just before
  reading the username. The bundled template prints `recovery login:`.
