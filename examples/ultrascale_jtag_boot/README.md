# UltraScale+ (ZynqMP) JTAG boot for labgrid

Boot an UltraScale+ / ZynqMP board (e.g. **ADRV9009-ZU11EG on ADRV2CRR-FMC**)
entirely over JTAG — the UltraScale+ counterpart of the Zynq-7000
`BootZynq7000JTAGRecovery` flow. Use it to recover a corrupted/blank SD card or
to bring a board up when the BootROM can't load from any boot device.

## Why ZynqMP needs a different approach than the zc706

On **Zynq-7000** (zc706) recovery is single-stage: `ps7_init.tcl` → `dow u-boot.elf`
→ `con`, and you get a U-Boot prompt. That does **not** work on ZynqMP:

- A board strapped for **JTAG boot** reads `CRL_APB.BOOT_MODE_USER (0xFF5E0200) = 0x0`.
- In that mode the BootROM does **not** load PMU firmware, and the MicroBlaze
  PMU is **not** exposed as a JTAG debug target (`dow pmufw.elf` → *Invalid
  context*).
- Xilinx **ARM Trusted Firmware (BL31) requires PMU-FW**. Without it, BL31 boots
  and then spins forever in `ipi_mb_notify` waiting on the PMU IPI mailbox, so
  full U-Boot (BL33) never runs.

The fix is the Xilinx **"mini" U-Boot SPL** (`xilinx_zynqmp_mini_*`): a single
EL3 blob that runs standalone in OCM — **no ATF, no PMU-FW** — with an
ARM DCC / JTAG-UART console readable directly by xsdb (no physical UART / baud
dependence). It comes up far enough to own the SD host controller, which is all
SD recovery needs.

## What this adds to labgrid

- **`XilinxJTAGDriver.load_zynqmp_uboot(...)`** — the xsdb sequencing:
  release the APU without PMU-FW (bootloop at RVBAR + poke
  `CRF_APB.RST_FPD_APU`), optional PL bitstream, `source psu_init.tcl` +
  `psu_init`/`psu_post_config`/…, clean the A53, `dow` the mini SPL, `con`, and
  (optionally) capture the DCC console via `readjtaguart`.
- **`stop_zynqmp_cpu(...)`** — halt A53 #0 between attempts.
- **`BootZynqMPJTAG`** strategy — wraps the above in a
  `powered_off → powered_on → jtag_bootstrap` state machine.

## One-time setup

1. **Build the mini SPL** on the exporter (or any host with Vitis 2025.1):

   ```bash
   ./build-mini-uboot.sh              # -> spl/u-boot-spl (ELF, entry 0xfffc0000)
   ```

   The script clones `u-boot-xlnx` (`xlnx_rebase_v2025.01`), creates a board SD
   device tree (`zynqmp-mini-sd1` — SD on `sdhci1`, level-shifter) and matching
   defconfig, and builds.

   > Put `/usr/bin:/bin` first on `PATH` for the build — a `~/.local/bin/as`
   > shim shadows the assembler and breaks `scripts/basic/fixdep`.

2. **Stage `psu_init.tcl`** (and optional `system_top.bit`) from your HDL
   project / XSA at paths the xsdb host can read.

3. **Cable / hw_server**: ensure the Digilent/FTDI JTAG cable is claimed by
   `hw_server` on the exporter. See the `hardware-ci-operations` skill for the
   full cable-driver + udev checklist.

## Usage

```python
from labgrid import Environment

env = Environment("lg_zu11eg_jtag_boot.yaml")
target = env.get_target("main")
strat = target.get_strategy()  # BootZynqMPJTAG

strat.transition("jtag_bootstrap")  # power-cycle + JTAG-load mini SPL
```

Then read the captured DCC console (`dcc_log_path`). A healthy boot shows:

```
U-Boot SPL 2025.01 ...
EL Level:       EL3
Trying to boot from MMC2
... arasan_sdhci mmc@ff170000 ...
```

Reaching the `arasan_sdhci` driver means the SPL owns the SD host controller
over JTAG.

## Completing an SD flash

Once the SD is reachable, finish the same way as the zc706 recovery flow, using
either a full-U-Boot `mmc write` (needs the ATF/PMU path — avoid on JTAG-boot
ZynqMP) or, preferably, a **RAM-rooted recovery Linux + `dd`**
(TFTP/JTAG-load kernel+DTB+initramfs → boot → `wget <url> | dd of=/dev/mmcblk0
bs=4M conv=fsync`). This mirrors `BootZynq7000JTAGRecovery` and avoids the
ATF/PMU-FW dependency entirely.

## Files

| file | purpose |
|------|---------|
| `build-mini-uboot.sh` | build the mini U-Boot SPL (creates SD DT + defconfig) |
| `lg_zu11eg_jtag_boot.yaml` | example labgrid env wiring `BootZynqMPJTAG` |
