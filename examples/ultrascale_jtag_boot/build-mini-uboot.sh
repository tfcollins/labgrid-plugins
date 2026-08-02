#!/usr/bin/env bash
# Build the Xilinx "mini" U-Boot SPL used to JTAG-boot an UltraScale+ (ZynqMP)
# board for SD-card recovery / bring-up.
#
# WHY a mini SPL (not full U-Boot):
#   In JTAG boot mode (BOOT_MODE_USER == 0x0) the ZynqMP BootROM does not load
#   PMU firmware and the MicroBlaze PMU is not a debug target, so full U-Boot +
#   ARM Trusted Firmware (BL31) cannot run -- BL31 spins forever in
#   ipi_mb_notify waiting on the PMU IPI mailbox. The xilinx_zynqmp_mini_* SPL
#   runs standalone in OCM at EL3 (no ATF, no PMU-FW) with an ARM DCC / JTAG-UART
#   console readable directly by xsdb. This is the UltraScale+ counterpart of the
#   Zynq-7000 (zc706) FSBL->U-Boot JTAG bootstrap.
#
# Produces: spl/u-boot-spl  (ELF, entry 0xfffc0000, runs in OCM)
# Point BootZynqMPJTAG / XilinxJTAGDriver.load_zynqmp_uboot at that ELF.
#
# Usage:
#   ./build-mini-uboot.sh [WORKDIR]
# Env overrides:
#   UBOOT_BRANCH   default xlnx_rebase_v2025.01  (match your Vitis version)
#   CROSS_COMPILE  default the 2025.1 Vitis aarch64-none- prefix
#   BOARD_VARIANT  default sd1  (SD on sdhci1 @0xff170000, level-shifter)
set -euo pipefail

WORKDIR="${1:-$HOME/u-boot-xlnx-zynqmp-mini}"
UBOOT_BRANCH="${UBOOT_BRANCH:-xlnx_rebase_v2025.01}"
CROSS_COMPILE="${CROSS_COMPILE:-/tools/Xilinx/2025.1/Vitis/gnu/aarch64/lin/aarch64-none/bin/aarch64-none-elf-}"
BOARD_VARIANT="${BOARD_VARIANT:-sd1}"

# CRITICAL: put system binutils FIRST. A ~/.local/bin/as shim shadows the
# assembler and breaks scripts/basic/fixdep ("No agent session matching '--64'").
export PATH="/usr/bin:/bin:$(dirname "$CROSS_COMPILE")"
export CROSS_COMPILE

DTS_DIR_REL="arch/arm/dts"
DEFCONFIG="xilinx_zynqmp_mini_${BOARD_VARIANT}_defconfig"
DTS_NAME="zynqmp-mini-${BOARD_VARIANT}"

echo "==> workdir=$WORKDIR branch=$UBOOT_BRANCH variant=$BOARD_VARIANT"

if [ ! -d "$WORKDIR/.git" ]; then
    echo "==> cloning u-boot-xlnx ($UBOOT_BRANCH)"
    git clone --depth 1 --branch "$UBOOT_BRANCH" \
        https://github.com/Xilinx/u-boot-xlnx.git "$WORKDIR"
fi
cd "$WORKDIR"

# --- board SD variant device tree (SD1 with level shifter, sdhci1) ----------
if [ "$BOARD_VARIANT" = "sd1" ] && [ ! -f "$DTS_DIR_REL/$DTS_NAME.dts" ]; then
    echo "==> creating $DTS_DIR_REL/$DTS_NAME.dts"
    cat > "$DTS_DIR_REL/$DTS_NAME.dts" <<'DTS'
// SPDX-License-Identifier: GPL-2.0+
/* ZynqMP Mini SD1 (sdhci1 @0xff170000, removable, level-shifter) */
/dts-v1/;
/ {
	model = "ZynqMP MINI SD1";
	compatible = "xlnx,zynqmp";
	#address-cells = <2>;
	#size-cells = <2>;
	aliases {
		serial0 = &dcc;
		mmc0 = &sdhci1;
	};
	chosen { stdout-path = "serial0:115200n8"; };
	memory@0 { device_type = "memory"; reg = <0x0 0x0 0x0 0x20000000>; };
	dcc: dcc { compatible = "arm,dcc"; status = "disabled"; bootph-all; };
	clk_xin: clk-xin {
		bootph-all;          /* REQUIRED: else SPL clk_get_by_index fails (-22) */
		compatible = "fixed-clock";
		#clock-cells = <0>;
		clock-frequency = <200000000>;
	};
	amba: axi {
		compatible = "simple-bus";
		#address-cells = <2>;
		#size-cells = <2>;
		ranges;
		sdhci1: mmc@ff170000 {
			bootph-all;
			compatible = "xlnx,zynqmp-8.9a", "arasan,sdhci-8.9a";
			status = "disabled";
			no-1-8-v;
			disable-wp;
			bus-width = <4>;
			xlnx,mio-bank = <1>;
			reg = <0x0 0xff170000 0x0 0x1000>;
			clock-names = "clk_xin", "clk_ahb";
			clocks = <&clk_xin &clk_xin>;
		};
	};
};
&dcc { status = "okay"; };
&sdhci1 { status = "okay"; };
DTS
    # register the dtb next to the mini entries
    if ! grep -q "$DTS_NAME.dtb" "$DTS_DIR_REL/Makefile"; then
        sed -i "/zynqmp-mini-emmc1.dtb/a\\\tzynqmp-mini-${BOARD_VARIANT}.dtb\t\t\t\\\\" "$DTS_DIR_REL/Makefile"
    fi
fi

# --- defconfig (from emmc1, retargeted to SD1) ------------------------------
if [ "$BOARD_VARIANT" = "sd1" ] && [ ! -f "configs/$DEFCONFIG" ]; then
    echo "==> creating configs/$DEFCONFIG"
    sed -e "s/zynqmp-mini-emmc1/$DTS_NAME/" \
        -e 's/ZynqMP MINI EMMC1/ZynqMP MINI SD1/' \
        configs/xilinx_zynqmp_mini_emmc1_defconfig > "configs/$DEFCONFIG"
    cat >> "configs/$DEFCONFIG" <<'CFG'
CONFIG_SPL_ZYNQMP_ALT_BOOTMODE_ENABLED=y
CONFIG_SD1_LSHFT_MODE=y
CONFIG_SPL_MMC=y
CONFIG_SPL_LIBDISK_SUPPORT=y
CONFIG_SPL_FS_FAT=y
CONFIG_SPL_CLK=y
CONFIG_CLK=y
CFG
fi

echo "==> building"
make "$DEFCONFIG"
make -j"$(nproc)"

echo
echo "==> DONE. Mini SPL ELF:"
ls -l "$WORKDIR/spl/u-boot-spl"
"${CROSS_COMPILE}readelf" -h "$WORKDIR/spl/u-boot-spl" | grep -E "Entry point"
echo
echo "Wire it into labgrid via XilinxJTAGDriver.load_zynqmp_uboot(spl_elf=...)"
echo "or the BootZynqMPJTAG strategy's spl_elf attribute."
