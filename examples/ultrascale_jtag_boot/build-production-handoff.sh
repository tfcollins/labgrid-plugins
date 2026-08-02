#!/usr/bin/env bash
# Build the raw EL3 -> non-secure EL2 production-U-Boot handoff.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CROSS_COMPILE="${CROSS_COMPILE:-/tools/Xilinx/2025.1/Vitis/gnu/aarch64/lin/aarch64-none/bin/aarch64-none-elf-}"
OUT="${1:-$SCRIPT_DIR/build/el3-to-uboot-el2}"
mkdir -p "$(dirname "$OUT")"

"${CROSS_COMPILE}gcc" -nostdlib -nostartfiles \
    -Wl,-Ttext=0x00100000 -Wl,-e,_start \
    -o "$OUT.elf" "$SCRIPT_DIR/el3-to-uboot-el2.S"
"${CROSS_COMPILE}objcopy" -j .text -O binary "$OUT.elf" "$OUT.bin"

entry="$(${CROSS_COMPILE}readelf -h "$OUT.elf" | awk '/Entry point address/ {print $4}')"
[ "$entry" = "0x100000" ] || {
    echo "unexpected entry point: $entry" >&2
    exit 1
}
size="$(stat -c %s "$OUT.bin")"
[ "$size" -gt 0 ] && [ "$size" -le 4096 ] || {
    echo "unexpected raw handoff size: $size bytes" >&2
    exit 1
}
printf 'ELF: %s\nBIN: %s\nENTRY: %s\nBYTES: %s\n' "$OUT.elf" "$OUT.bin" "$entry" "$size"
