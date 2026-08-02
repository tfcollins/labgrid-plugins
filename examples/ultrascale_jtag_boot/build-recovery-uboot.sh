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
PATCH_SHA256="6ab17722541229ee7fd6732575a21038127abae46d2622a4a62fb9338e3a8ebb"
SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-1604305337}"
CROSS_COMPILE="${CROSS_COMPILE:-/tools/Xilinx/2025.1/Vitis/gnu/aarch64/lin/aarch64-linux/bin/aarch64-linux-gnu-}"
BUILD_DIR="${BUILD_DIR:-$WORKDIR/build-recovery}"
PATCH="$SCRIPT_DIR/recovery-uboot.patch"
MANIFEST="${MANIFEST:-${OUT}.manifest.json}"

export PATH="/usr/bin:/bin:$(dirname "$CROSS_COMPILE")"
export CROSS_COMPILE
export SOURCE_DATE_EPOCH

printf '%s  %s\n' "$PATCH_SHA256" "$PATCH" | sha256sum --check --status
mapfile -t PATCH_PATHS < <(sed -n 's|^+++ b/||p' "$PATCH" | sort -u)
EXPECTED_PATHS=(
    arch/arm/cpu/armv8/zynqmp/cpu.c
    board/xilinx/zynqmp/zynqmp.c
    drivers/serial/serial_zynq.c
)
[[ "${PATCH_PATHS[*]}" == "${EXPECTED_PATHS[*]}" ]] || {
    printf 'Unexpected patch scope: %s\n' "${PATCH_PATHS[*]}" >&2
    exit 1
}

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
ARTIFACT_SHA256="$(sha256sum "$OUT" | cut -d' ' -f1)"
ARTIFACT_SIZE="$(stat -c %s "$OUT")"
COMPILER_VERSION="$(${CROSS_COMPILE}gcc --version | head -n1)"
HOSTCC_VERSION="$(/usr/bin/gcc --version | head -n1)"
install -d "$(dirname "$MANIFEST")"
python3 - "$MANIFEST" <<PY
import json
import sys

manifest = {
    "source_url": ${UBOOT_REPO@Q},
    "source_commit": ${UBOOT_COMMIT@Q},
    "defconfig": ${DEFCONFIG@Q},
    "patch_sha256": ${PATCH_SHA256@Q},
    "source_date_epoch": int(${SOURCE_DATE_EPOCH@Q}),
    "cross_compiler": ${COMPILER_VERSION@Q},
    "host_compiler": ${HOSTCC_VERSION@Q},
    "artifact": ${OUT@Q},
    "artifact_size": int(${ARTIFACT_SIZE@Q}),
    "artifact_sha256": ${ARTIFACT_SHA256@Q},
    "load_address": "0x08000000",
}
with open(sys.argv[1], "w", encoding="utf-8") as stream:
    json.dump(manifest, stream, indent=2, sort_keys=True)
    stream.write("\n")
PY
printf '%s  %s\n' "$ARTIFACT_SHA256" "$OUT"
strings "$OUT" | grep -E "^U-Boot 2018\.01(-[0-9]+)?-gd244ce5869-dirty" >/dev/null
printf 'Recovery U-Boot: %s\n' "$OUT"
printf 'Manifest: %s\n' "$MANIFEST"
