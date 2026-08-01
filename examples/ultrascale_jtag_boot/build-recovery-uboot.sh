#!/usr/bin/env bash
# Build the exact ADI ZU11EG U-Boot used by the fixed-JTAG production handoff.
# This is intentionally a recovery-only adaptation: it trusts psu_init's MMIO
# and UART setup when the legacy secure PM calls are unavailable, and submits
# the genuine FSBL XilPM object loaded by BootZynqMPJTAG at 0x00200000.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKDIR="${1:-$HOME/u-boot-xlnx-adi-zu11eg-recovery}"
OUT="${2:-/tmp/recovery/u-boot-adi-zu11eg-recovery.bin}"
UBOOT_REPO="${UBOOT_REPO:-https://github.com/analogdevicesinc/u-boot-xlnx.git}"
UBOOT_COMMIT="${UBOOT_COMMIT:-d244ce5869648a5046e98b917ff4d7ca3fd81dfd}"
DEFCONFIG="${DEFCONFIG:-adi_zynqmp_adrv9009_zu11eg_adrv2crr_fmc_defconfig}"
CROSS_COMPILE="${CROSS_COMPILE:-/tools/Xilinx/2025.1/Vitis/gnu/aarch64/lin/aarch64-linux/bin/aarch64-linux-gnu-}"
BUILD_DIR="${BUILD_DIR:-$WORKDIR/build-recovery}"
PATCH="$SCRIPT_DIR/recovery-uboot.patch"

export PATH="/usr/bin:/bin:$(dirname "$CROSS_COMPILE")"
export CROSS_COMPILE

if [[ ! -d "$WORKDIR/.git" ]]; then
    git clone --filter=blob:none "$UBOOT_REPO" "$WORKDIR"
fi

if [[ -f "$WORKDIR/.git/shallow" ]]; then
    git -C "$WORKDIR" fetch --unshallow origin
fi
git -C "$WORKDIR" fetch origin "$UBOOT_COMMIT"
git -C "$WORKDIR" checkout --detach "$UBOOT_COMMIT"
git -C "$WORKDIR" reset --hard "$UBOOT_COMMIT"
git -C "$WORKDIR" clean -fdx

git -C "$WORKDIR" apply --check "$PATCH"
git -C "$WORKDIR" apply "$PATCH"

make -C "$WORKDIR" O="$BUILD_DIR" HOSTCC=/usr/bin/gcc \
    HOSTCFLAGS='-Wall -Wstrict-prototypes -O2 -fomit-frame-pointer -fcommon -std=gnu11' \
    "$DEFCONFIG"
make -C "$WORKDIR" O="$BUILD_DIR" HOSTCC=/usr/bin/gcc \
    HOSTCFLAGS='-Wall -Wstrict-prototypes -O2 -fomit-frame-pointer -fcommon -std=gnu11' \
    -j"$(nproc)"

install -D -m 0644 "$BUILD_DIR/u-boot.bin" "$OUT"
sha256sum "$OUT"
strings "$OUT" | grep -E "^U-Boot 2018\.01(-[0-9]+)?-gd244ce5869-dirty" >/dev/null
printf 'Recovery U-Boot: %s\n' "$OUT"
