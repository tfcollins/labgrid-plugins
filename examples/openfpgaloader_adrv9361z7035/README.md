# openFPGALoader on ADRV9361-Z7035

This example adds **explicit PL-only SRAM programming** to the `lablp` setup.
It does not replace the place's normal `BootFPGASoCTFTP` strategy:
openFPGALoader does not initialize the Zynq PS7 or DDR, load U-Boot/Linux, or
start either ARM core.

## Exporter prerequisites

Install `openFPGALoader` on the exporter that owns the JTAG USB probe and add a
labgrid `USBDebugger` resource matching that exact probe. The coordinator must
publish it as `NetworkUSBDebugger` with stable USB bus/device or serial identity.
Do not expose an unbound generic USB device when multiple FTDI probes are fitted.

The process user needs udev permission for the probe. Configure a tool override
when the binary is not on `PATH`:

```yaml
tools:
  openFPGALoader: /usr/local/bin/openFPGALoader
```

## Configuration

`lg_adrv9361z7035.yaml` uses an explicit cable and FPGA part because upstream
openFPGALoader has no `adrv9361-z7035` named board. Confirm both values against
the fitted probe and FPGA package before programming.

Confirm the probe bus/device numbers, replace `/path/to/system_top.bit`, acquire the place, then request only the
`programmed` state:

```bash
export LG_COORDINATOR=10.0.0.41:20408
labgrid-client -p lablp acquire
LG_ENV=lg_adrv9361z7035.yaml labgrid-client -t main transition programmed
labgrid-client -p lablp release
```

`programmed` proves the tool returned successfully; it does not prove Linux or
IIO readiness. Transitioning to `shell` additionally requires the configured
UART marker. The driver uses `--write-sram`; flash writes are disabled unless
both the environment and the caller explicitly opt in.

For the production board boot, keep using the coordinator's existing
`BootFPGASoCTFTP` environment.
