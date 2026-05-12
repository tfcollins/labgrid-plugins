# BootZynq7000JTAGRecovery example

Reference setup for the `BootZynq7000JTAGRecovery` strategy. Used on
ADRV9371-ZC706 with Vivado 2023.2; adapt paths/values for your board.

## What's in this directory

- `init`, `udhcpc-default.script` — copies of the templates bundled in
  `adi_lg_plugins.recovery.templates`. Kept here for offline reference;
  the strategy and CLI both pull the in-package versions.
- `build_cpio.py` — thin wrapper around `adi_lg_plugins.recovery.cpio`.
  Useful when you want to copy-paste a single file; use the module API
  in real code.
- `lg_zc706_recovery.yaml` — example labgrid environment.

## Building the initramfs

The recovery initramfs builder lives in `adi_lg_plugins.recovery`. You
provide a cross-compiled static busybox; the module bundles the `/init`
script, udhcpc hook, applet symlinks, cpio packer, and `mkimage` wrap.

### CLI

```bash
# 1. Cross-compile static busybox for ARMv7 (Cortex-A9) — one-time.
export CROSS_COMPILE=/path/to/arm-none-linux-gnueabihf-
export ARCH=arm
cd busybox-1.36.1
make defconfig
sed -i 's/^# CONFIG_STATIC is not set/CONFIG_STATIC=y/' .config
make -j$(nproc) busybox

# 2. Have the plugin assemble + cpio + gzip + mkimage in one shot.
adi-lg build-recovery-initramfs \
    --busybox $(pwd)/busybox \
    --out /var/lib/tftpboot/uInitrd.recovery
```

### Python

```python
from adi_lg_plugins.recovery import build_recovery_initramfs

sizes = build_recovery_initramfs(
    busybox="/path/to/static/busybox",
    output="/var/lib/tftpboot/uInitrd.recovery",
)
print(sizes)  # {'cpio': ..., 'gz': ..., 'uimage': ...}
```

Need a different `/init` or extra applets? Drop one level:

```python
from adi_lg_plugins.recovery import (
    DEFAULT_APPLETS,
    DEFAULT_DEV_NODES,
    build_cpio,
    stage_recovery_rootfs,
)

# Stage the standard rootfs then add your own bits before packaging.
stage_recovery_rootfs("/path/to/busybox", "rootfs", applets=DEFAULT_APPLETS + ("crond",))
# ... your customizations ...
build_cpio("rootfs", "initramfs.cpio", dev_nodes=DEFAULT_DEV_NODES)
```

## Staging the JTAG bootstrap inputs

```bash
# Extract from a known-good BOOT.BIN using Xilinx bootgen (-split).
bootgen -arch zynq -read BOOT.BIN
# Yields fsbl.elf, u-boot.elf, and system_top.bit (the FPGA bitstream).
# The bitstream is REQUIRED — without it, the recovery kernel will hang
# probing AXI peripherals that live in the FPGA fabric (axi_clkgen,
# axi_jesd204_*, axi_adxcvr, etc.).

# Generate ps7_init.tcl from the .xsa via Vivado:
#   write_hw_platform -fixed -include_bit -force <design>.xsa
#   (or just copy the one Vivado emitted next to your project)
```

## Running the strategy

```bash
# Serve the SD image over HTTP from anywhere on the same subnet:
python3 -m http.server 8080 --directory /path/to/sd-images &

# Drive the strategy via labgrid:
python3 -c "
import adi_lg_plugins  # registers entry-point drivers
from labgrid import Environment
t = Environment('lg_zc706_recovery.yaml').get_target('main')
t.get_strategy().transition('sd_flash_done')
"
```

Expected log highlights:

```
JTAG bootstrap attempt 1/2...
Zynq U-Boot bootstrap completed
U-Boot prompt reached
Configuring U-Boot for recovery TFTP boot...
Waiting for recovery login marker 'recovery login:'...
Recovery Linux shell ready
Streaming SD image to /dev/mmcblk0 (timeout 1800s)...
SD card reflashed successfully
```

## Tuning per board

- `kernel_addr`, `dtb_addr`, `initramfs_addr` — DDR load addresses; defaults
  are conservative for a 1 GB Zynq-7000. Bump `initramfs_addr` higher if
  your recovery initramfs is large (the area between kernel and ramdisk
  must not overlap kernel decompression scratch space).
- `uboot_prompt` — match your U-Boot's actual prompt (e.g. `Zynq>` for
  the Xilinx-shipped one, `=>` for upstream U-Boot).
- `download_cmd_template` — defaults to `wget -q -O - "{url}"`; switch to
  `curl -fsSL --retry 3 "{url}"` if your recovery rootfs has curl.
- `recovery_login_marker` — must match what `/init` prints just before
  reading the username. The example `init` prints `recovery login:`.

## Why a custom `build_cpio.py`

The kernel opens `/dev/console` for PID 1's stdio before exec'ing `/init`.
If that node doesn't exist in the rootfs, the init process starts with
closed file descriptors and every `echo`/`printf` vanishes silently —
boot looks like a kernel hang because no output ever reaches the serial
port. We can't add device nodes to a cpio via `find | cpio -o` without
root privileges (mknod fails), so this script emits the newc-format cpio
bytes directly.
