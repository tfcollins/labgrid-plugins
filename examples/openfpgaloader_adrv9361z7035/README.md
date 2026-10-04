# openFPGALoader on ADRV9361-Z7035

This example adds **explicit PL-only SRAM programming** to the `lablp` setup.
It does not replace the place's normal `BootFPGASoCTFTP` strategy:
openFPGALoader does not initialize the Zynq PS7 or DDR, load U-Boot/Linux, or
start either ARM core.

## Exporter prerequisites

Install `openFPGALoader` on the exporter that owns the JTAG USB probe. The
driver accepts either labgrid's `USBDebugger`/`NetworkUSBDebugger` resource or
the plugin's established `XilinxDeviceJTAG` resource. Configure an exact USB
bus/device or serial identity; never rely on the first matching FTDI probe.

The process user needs udev permission for the probe. Configure a tool override
when the binary is not on `PATH`:

```yaml
tools:
  openFPGALoader: /usr/local/bin/openFPGALoader
```

## Configuration

`lg_adrv9361z7035.yaml` records the verified `digilent_hs2` profile and USB
location `1:5`. Recheck the bus/device after USB re-enumeration. Upstream
openFPGALoader does not currently include XC7Z035 IDCODE `0x23732093`; use a
build containing the `zynq`/`xc7z035` mapping and require `--detect` to print
`model xc7z035` before programming.

Confirm the probe bus/device numbers, replace `/path/to/system_top.bit`, acquire the place, then request only the
`programmed` state:

```bash
export LG_COORDINATOR=10.0.0.41:20408
labgrid-client -p lablp acquire
LG_ENV=lg_adrv9361z7035.yaml python - <<'PY'
from labgrid import Environment
env = Environment("lg_adrv9361z7035.yaml")
env.get_target("main").get_driver("BootOpenFPGALoader").transition("programmed")
PY
labgrid-client -p lablp release
```

`programmed` proves the programming command returned successfully; require a
second `detect()` call containing `xc7z035` or an application-specific
register/datapath check as independent evidence. Transitioning to `shell`
additionally requires the configured UART marker. The driver uses
`--write-sram`; flash writes are disabled unless both the environment and the
caller explicitly opt in.

For the production board boot, keep using the coordinator's existing
`BootFPGASoCTFTP` environment.
