# BootZynq7000JTAGRecovery example

Reference setup for the `BootZynq7000JTAGRecovery` strategy. Used on
ADRV9371-ZC706 with Vivado 2023.2; adapt paths/values for your board.

## What's in this directory

- `init` — `/init` for the recovery initramfs. Mounts pseudo-filesystems,
  brings `eth0` up via DHCP, prints `recovery login:`, accepts any
  username/password, then `exec /bin/sh -i` with `PS1=root@recovery:/#`
  so labgrid's ADIShellDriver can drive it.
- `udhcpc-default.script` — busybox `udhcpc` hook for IP / route / DNS
  configuration. Install as `/etc/udhcpc/default.script` (executable).
- `build_cpio.py` — Python cpio-archive builder. Required because the
  recovery initramfs needs `/dev/console` (char 5:1) baked in; standard
  `find . | cpio -o -H newc` can't create device nodes without root,
  but this builder writes the cpio bytes directly.
- `lg_zc706_recovery.yaml` — example labgrid environment.

## Building the initramfs (host side)

```bash
# 1. Cross-compile static busybox for ARMv7 (Cortex-A9).
#    Use any arm-none-linux-gnueabihf toolchain.
export CROSS_COMPILE=/path/to/arm-none-linux-gnueabihf-
export ARCH=arm
cd busybox-1.36.1
make defconfig
sed -i 's/^# CONFIG_STATIC is not set/CONFIG_STATIC=y/' .config
make -j$(nproc) busybox

# 2. Build the rootfs tree.
mkdir -p rootfs/{bin,sbin,etc/udhcpc,proc,sys,dev,tmp}
cp busybox rootfs/bin/busybox
for app in sh ash dd mount umount wget udhcpc ifconfig ip route cat echo \
           ls mkdir mknod ln rm cp mv chmod chown sleep sync poweroff halt \
           reboot mdev dmesg sed grep cut awk printf test '[' true false env \
           hostname ping mktemp base64 tee find head tail wc tr md5sum touch \
           dirname basename date readlink xargs sort uniq tar gunzip rx rz; do
    ln -sf busybox rootfs/bin/$app
done
ln -sf ../bin/busybox rootfs/sbin/init
ln -sf ../bin/busybox rootfs/sbin/udhcpc
ln -sf ../bin/busybox rootfs/sbin/poweroff
ln -sf ../bin/busybox rootfs/sbin/halt
ln -sf ../bin/busybox rootfs/sbin/ifconfig
cp examples/zynq7000_recovery/init rootfs/init
chmod +x rootfs/init
cp examples/zynq7000_recovery/udhcpc-default.script rootfs/etc/udhcpc/default.script
chmod +x rootfs/etc/udhcpc/default.script

# 3. Build the cpio (with /dev/console + companions baked in).
python3 examples/zynq7000_recovery/build_cpio.py rootfs initramfs.cpio
gzip -9 -c initramfs.cpio > initramfs.cpio.gz

# 4. Wrap as U-Boot uImage so `bootm` can load it.
mkimage -A arm -O linux -T ramdisk -C gzip \
        -n "ZC706-recovery" \
        -d initramfs.cpio.gz uInitrd.recovery

# 5. Stage on the TFTP server. The strategy will TFTP this from U-Boot.
cp uInitrd.recovery /var/lib/tftpboot/
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
