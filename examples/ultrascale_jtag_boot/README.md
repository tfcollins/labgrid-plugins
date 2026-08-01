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

The first recovery stage uses the Xilinx **"mini" U-Boot SPL**
(`xilinx_zynqmp_mini_*`): a single EL3 blob that runs standalone in OCM — **no
ATF, no PMU-FW** — with an ARM DCC / JTAG-UART console. It comes up far enough
to own the SD host controller.

After the SD is repaired, the `production_boot` state reconstructs a production
handoff without changing the physical straps. Although XSDB cannot debug the
PMU as a normal processor, the PMU ROM can consume a raw PMUFW payload loaded
through the PSU/DAP target. The driver waits for PMU ROM sleep, wakes the loaded
firmware, requires firmware-owned `FW_IS_PRESENT`, programs the PL, and enters
production U-Boot through BL31 plus the Xilinx `XLNX` handoff table. A direct
EL3→non-secure-EL2 trampoline remains available for U-Boot builds which do not
need Xilinx PM runtime services.

## What this adds to labgrid

- **`XilinxJTAGDriver.load_zynqmp_uboot(...)`** — the xsdb sequencing:
  release the APU without PMU-FW (bootloop at RVBAR + poke
  `CRF_APB.RST_FPD_APU`), optional PL bitstream, `source psu_init.tcl` +
  `psu_init`/`psu_post_config`/…, clean the A53, `dow` the mini SPL, `con`, and
  (optionally) capture the DCC console via `readjtaguart`.
- **`stop_zynqmp_cpu(...)`** — halt A53 #0 between attempts.
- **`BootZynqMPJTAG`** strategy — wraps the above in a
  `powered_off → powered_on → jtag_bootstrap|production_boot` state machine.
- **`XilinxJTAGDriver.load_zynqmp_production_uboot(...)`** — verified PMU-ROM
  wake, optional DDR ECC scrub, XilPM configuration-object and PL loads,
  physical payload downloads, and BL31 or direct EL3→EL2 entry into U-Boot.

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

## Booting the repaired production image under fixed JTAG straps

Extract the raw, unencrypted production payloads from the selected board's
`BOOT.BIN`, then build the direct fallback handoff. Bootgen stores PMUFW before FSBL in the
combined bootloader and stores PL partition words in the opposite byte order
from that expected by XSDB. The helper also parses the legacy
`XPm_ConfigObject` from the production FSBL; the PMU must receive this object
or Linux device requests fail with `-EACCES`. It writes SHA256 metadata for
every output.

```bash
./prepare-production-boot.py /mnt/boot/BOOT.BIN /tmp/zynqmp-production
./build-production-handoff.sh /tmp/zynqmp-production/el3-to-uboot-el2
./build-recovery-uboot.sh /tmp/u-boot-adi /tmp/zynqmp-production/u-boot.bin
```

Stage the output and the board's `psu_init.tcl` on the XSDB host, configure:

```yaml
BootZynqMPJTAG:
  psu_init_tcl: /tmp/zynqmp-production/psu_init.tcl
  pmufw_bin: /tmp/zynqmp-production/pmufw.bin
  uboot_bin: /tmp/zynqmp-production/u-boot.bin
  bl31_bin: /tmp/zynqmp-production/bl31.bin
  atf_handoff_bin: /tmp/zynqmp-production/atf-handoff.bin
  pm_config_bin: /tmp/zynqmp-production/pm-config-object.bin
  bitstream_path: /tmp/zynqmp-production/system-top-xsdb.bin
  # Required only when psu_init enables DDR ECC without initializing memory:
  ddr_scrub_elf: /tmp/zynqmp-production/ddr-ecc-scrub.elf
  ddr_scrub_settle_ms: 120000
  jtag_url: TCP:exporter.example:3121
```

`pm_config_bin` is loaded at `0x00200000`. The recovery U-Boot must submit it
before driver-model probing with the ZynqMP `PM_SET_CONFIGURATION` SMC
(`0xC2000002`). This keeps the board-specific policy in the genuine FSBL object
without allowing the FSBL to enter its JTAG-mode shutdown path. Older ADI
U-Boot builds may also need a recovery-only fallback from failed secure MMIO
SMCs to direct MMIO and a fixed UART reference clock after `psu_init`; do not
apply those fallbacks unconditionally to production builds.

For ECC DDR, scrub **every range advertised by the production DT**, not only a
small recovery range. `ddr-ecc-scrub-zu11eg.S` covers this board's low 2 GiB
and high 2 GiB bank. Build it at the OCM address:

```bash
aarch64-none-elf-gcc -nostdlib -nostartfiles \
  -Wl,-Ttext=0xfffc0000 -Wl,--build-id=none \
  -o /tmp/zynqmp-production/ddr-ecc-scrub.elf ddr-ecc-scrub-zu11eg.S
```

Then transition using the normal labgrid strategy API:

```python
strat.transition("production_boot")
```

Use the higher target-verified state for normal operation. It opens UART before
the A53 resumes, interrupts U-Boot, explicitly selects SD despite fixed JTAG
straps, waits for `Starting kernel` and the Kuiper root prompt, then runs the
configured Ethernet/JESD/IIO checks:

```python
strat.transition("kuiper_shell")
```

If Vitis/XSDB is installed on the labgrid runner while `hw_server` is on a
separate exporter, set `LG_FORCE_LOCAL_XSDB=1` for the runner process and set
`jtag_url` to the exporter's endpoint (for example
`TCP:tron.local:3121`). The default keeps both processes on the exporter and
connects to `TCP:127.0.0.1:3121`.

The driver fails unless PMU firmware itself asserts readiness. Success markers
from XSDB are `PMUFW_READY`, `FPGA_STATE=FPGA is configured`, and
`PRODUCTION_UBOOT_LAUNCHED`; final success still requires a U-Boot or Linux
console marker. On a fixed-JTAG board the default U-Boot environment follows
the network/JTAG boot command; explicitly stop autoboot and run the repaired
SD path (for this ADI image: `setenv partid 1; run sdboot`). Loading through the physical PSU target avoids stale-MMU faults
when recovery Linux or BL31 ran previously.

A complete hardware proof includes `Starting kernel`, a Kuiper UART login,
network carrier/address, all JESD links in `DATA`, and an IIO inventory. Capture
emulation XML from the running board rather than copying another platform:

```bash
iio_genxml -u ip:<board-address> > context-with-wrapper.txt
# iio_genxml 0.25 wraps the XML with status lines; retain only <?xml ... </context>.
```

## End-to-end SD recovery

The mini-SPL `jtag_bootstrap` state is a quick SD-controller diagnostic. Full
recovery uses direct-JTAG RAM Linux so the card can be written:

```python
strat.transition("recovery_linux")  # requires RECOVERY_READY + root prompt
strat.transition("sd_flash_done")  # destructive: streams to /dev/mmcblk0
strat.transition("kuiper_shell")  # fresh JTAG handoff + target verification
```

Configure `recovery_trampoline_elf`, `recovery_kernel_image`,
`recovery_initramfs`, `recovery_dtb`, the low-bank recovery DDR scrubber, and an
explicit `sd_image_url`. Production uses the separate complete-bank scrubber.
`sd_flash_done` requires a block device, a pipefail-protected `wget | dd`,
`sync`, partition-table reread, the expected image size, and SHA-256 values for
the first and last sample blocks before it emits `SD_FLASH_OK`. Use
`post_flash_commands` to promote the selected Kuiper-full files into the FAT
root. The example YAML contains the verified ZU11EG paths.

The recovery kernel/DT/trampoline are board artifacts rather than vendored
binaries. Their contract is: one A53; low 2 GiB recovery memory; fixed
UART1/SD1/GEM clocks; unavailable firmware dependencies disabled; pending
SError masked; `CNTFRQ_EL0` and secure GICv2 initialized; and an initramfs which
emits `RECOVERY_READY` only after `/dev/mmcblk0` appears.

`build-recovery-uboot.sh` pins the exact ADI source commit and applies
`recovery-uboot.patch`. This adaptation is intentionally recovery-only: direct
MMIO fallback after rejected legacy secure calls, UART clock fallback to
`psu_init`, and submission of the genuine FSBL XilPM policy at `0x00200000`.
The script checks the expected version string and emits a SHA256 digest.
It also pins `SOURCE_DATE_EPOCH`, validates the exact patch digest and three-file
scope, and writes a JSON manifest beside the binary with source/toolchain and
artifact identity. Two independent output directories must produce identical
raw `u-boot.bin` files; the ELF is intentionally not published because it
embeds its build path.

If the coordinator advertises an exporter short name or RFC2217 metadata which
the runner cannot use, set `serial_host_override` and
`serial_protocol_override: raw`. The strategy applies these before opening
UART, which keeps console capture under labgrid instead of a parallel
`microcom` process.

## Files

| file | purpose |
|------|---------|
| `build-mini-uboot.sh` | build the mini U-Boot SPL (creates SD DT + defconfig) |
| `prepare-production-boot.py` | extract PMUFW, PM policy, BL31/U-Boot and convert PL |
| `ddr-ecc-scrub-zu11eg.S` | initialize both production ECC DDR banks from OCM |
| `el3-to-uboot-el2.S` | auditable EL3→non-secure-EL2 handoff source |
| `build-production-handoff.sh` | build the handoff ELF and small raw binary |
| `build-recovery-uboot.sh` | reproducibly build the fixed-JTAG recovery U-Boot |
| `recovery-uboot.patch` | narrowly scoped legacy ADI U-Boot recovery adaptation |
| `lg_zu11eg_jtag_boot.yaml` | example labgrid env wiring `BootZynqMPJTAG` |
