"""Strategy to JTAG-boot an UltraScale+ (ZynqMP) board.

This is the UltraScale+ counterpart of ``BootZynq7000JTAGRecovery``. It brings a
ZynqMP board up over JTAG using the Xilinx "mini" U-Boot SPL, which runs
standalone in OCM at EL3 -- **no ARM Trusted Firmware, no PMU firmware** -- and
exposes an ARM DCC / JTAG-UART console readable directly by xsdb.

Why this is needed (and different from Zynq-7000):

- A ZynqMP board strapped for **JTAG boot** reads ``BOOT_MODE_USER == 0x0``.
  In that mode the BootROM does not load PMU firmware and the MicroBlaze PMU is
  not exposed as a JTAG debug target.
- Xilinx ATF (BL31) requires PMU-FW; without it BL31 spins forever in
  ``ipi_mb_notify`` waiting on the PMU IPI mailbox, so full U-Boot never runs.
- The ``xilinx_zynqmp_mini_*`` SPL sidesteps all of that: it is a single EL3
  blob that comes up far enough to own the SD host controller, which is exactly
  what SD-card recovery / bring-up needs. See
  ``examples/ultrascale_jtag_boot/`` for how to build the SPL and a working
  per-board YAML.

Caller responsibilities (paths readable by the host that runs xsdb):

- ``psu_init_tcl``: the board's generated ``psu_init.tcl`` (brings up clocks,
  DDR, and the SD MIO mux). Extract it from your HDL project / XSA.
- ``spl_elf``: ``spl/u-boot-spl`` built by
  ``examples/ultrascale_jtag_boot/build-mini-uboot.sh``.
- ``bitstream_path`` (optional): PL bitstream, programmed before ``psu_init``
  when the PS init depends on the PL.

The actual xsdb sequencing lives in
``XilinxJTAGDriver.load_zynqmp_uboot`` so it can be unit-tested and reused
independently of this strategy.
"""

import enum
import time

import attr
import serial
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError, never_retry


class Status(enum.Enum):
    """State machine for the ZynqMP JTAG boot flow.

    Attributes:
        unknown: Initial state before any operation.
        powered_off: Board outlet is off.
        powered_on: Board outlet is on (mode pins sampled at POR).
        jtag_bootstrap: Mini U-Boot SPL has been JTAG-loaded and started.
        production_boot: PMUFW, PL, and production U-Boot were loaded and the
            EL3-to-EL2 handoff was started.
    """

    unknown = 0
    powered_off = 1
    powered_on = 2
    jtag_bootstrap = 3
    production_boot = 4
    recovery_linux = 5
    sd_flash_done = 6
    production_uboot_prompt = 7
    kuiper_shell = 8


@target_factory.reg_driver
@attr.s(eq=False)
class BootZynqMPJTAG(Strategy):
    """Bring up a ZynqMP board over JTAG via the mini U-Boot SPL.

    Bindings:
        power: PowerProtocol (managed outlet).
        jtag: XilinxJTAGDriver (runs xsdb locally or on the exporter).

    The optional ``shell`` binding, when present, is deactivated before the
    JTAG bootstrap so it does not hold the serial line; DCC console output is
    captured to ``dcc_log_path`` on the xsdb host instead.
    """

    bindings = {
        "power": "PowerProtocol",
        "jtag": "XilinxJTAGDriver",
        "shell": {"ADIShellDriver", None},
    }

    status = attr.ib(default=Status.unknown)

    # JTAG bootstrap inputs (paths on the host that runs xsdb).
    psu_init_tcl = attr.ib(default=None)
    spl_elf = attr.ib(default=None)
    bitstream_path = attr.ib(default=None)

    # Production handoff inputs. Raw payloads are extracted/prepared from the
    # board's production BOOT.BIN; see examples/ultrascale_jtag_boot/.
    pmufw_bin = attr.ib(default=None)
    uboot_bin = attr.ib(default=None)
    handoff_bin = attr.ib(default=None)
    bl31_bin = attr.ib(default=None)
    atf_handoff_bin = attr.ib(default=None)
    pm_config_bin = attr.ib(default=None)
    bl31_console_uart_base = attr.ib(default=None)
    bl31_console_ref_ctrl_address = attr.ib(default=None)
    bl31_console_reset_mask = attr.ib(default="0x2")
    ddr_scrub_elf = attr.ib(default=None)

    # Direct-JTAG RAM recovery Linux inputs.
    recovery_trampoline_elf = attr.ib(default=None)
    recovery_kernel_image = attr.ib(default=None)
    recovery_initramfs = attr.ib(default=None)
    recovery_dtb = attr.ib(default=None)
    recovery_marker = attr.ib(default="RECOVERY_READY")
    recovery_prompt = attr.ib(default=r"root@zu11eg-recovery:.*#")
    recovery_timeout = attr.ib(default=180)
    recovery_ddr_scrub_elf = attr.ib(default=None)
    ddr_scrub_done_address = attr.ib(default=None)
    recovery_ddr_scrub_done_address = attr.ib(default=None)
    recovery_ddr_scrub_settle_ms = attr.ib(default=30000)
    recovery_bitstream_path = attr.ib(default=None)
    recovery_post_init_mask_writes = attr.ib(factory=list)

    # Destructive SD recovery phase. The explicit URL keeps image provenance
    # and serving topology outside the serial/JTAG host split.
    sd_image_url = attr.ib(default=None)
    sd_device = attr.ib(default="/dev/mmcblk0")
    sd_download_cmd_template = attr.ib(default='wget -O - "{url}"')
    sd_flash_timeout = attr.ib(default=3600)
    sd_image_size = attr.ib(default=None)
    sd_head_sha256 = attr.ib(default=None)
    sd_tail_sha256 = attr.ib(default=None)
    sd_sample_bytes = attr.ib(default=1048576)
    post_flash_commands = attr.ib(factory=list)
    post_flash_timeout = attr.ib(default=180)

    # Target-side completion criteria for the production handoff.
    production_uboot_prompt = attr.ib(default=r"ZynqMP>")
    production_prompt_timeout = attr.ib(default=60)
    sd_boot_command = attr.ib(default="setenv partid 1; run sdboot")
    kuiper_kernel_marker = attr.ib(default="Starting kernel")
    kuiper_shell_marker = attr.ib(default=r"root@analog:.*#")
    kuiper_boot_timeout = attr.ib(default=300)
    kuiper_verify_timeout = attr.ib(default=120)
    kuiper_verify_commands = attr.ib(
        factory=lambda: [
            "i=0; until ip -4 addr show dev eth0 | grep -q 'inet '; do i=$((i+1)); test $i -lt 90 || exit 1; sleep 1; done",
            "test $(for n in /sys/bus/iio/devices/iio:device*/name; do cat \"$n\"; done | grep -c '^adrv9009-phy') -eq 2",
            "test $(dmesg | grep -c 'successfully initialized via jesd204-fsm') -ge 2",
        ]
    )

    # xsdb tuning (see XilinxJTAGDriver.load_zynqmp_uboot).
    a53_target_name = attr.ib(default="*Cortex-A53*#0*")
    apu_release_rst_value = attr.ib(default="0x380E")
    dcc_log_path = attr.ib(default=None)
    spl_settle_ms = attr.ib(default=12000)
    production_settle_ms = attr.ib(default=12000)
    pmufw_timeout_ms = attr.ib(default=10000)
    ddr_scrub_settle_ms = attr.ib(default=30000)

    jtag_url = attr.ib(default="TCP:127.0.0.1:3121")
    serial_host_override = attr.ib(default=None)
    serial_protocol_override = attr.ib(default=None)

    # Timing.
    power_off_settle_s = attr.ib(default=5)
    power_on_settle_s = attr.ib(default=8)

    def _require(self, name):
        value = getattr(self, name)
        if not value:
            raise StrategyError(f"BootZynqMPJTAG requires '{name}' to be set")
        return value

    def _require_shell(self):
        if not self.shell:
            raise StrategyError("BootZynqMPJTAG requires an ADIShellDriver for this state")
        return self.shell

    def _activate_shell_bypass(self):
        shell = self._require_shell()
        if self.serial_host_override or self.serial_protocol_override:
            console = shell.console
            port = getattr(console, "port", None)
            if port is None or not hasattr(port, "host"):
                raise StrategyError("serial_host_override requires a network serial resource")
            # Activate the managed remote resource first: RemotePlace refreshes
            # its parameters during activation and would otherwise overwrite
            # this host immediately before SerialDriver.open().
            self.target.activate(port)
            remote_entry = getattr(port, "_remote_entry", None)
            if remote_entry is not None:
                params = remote_entry.data.setdefault("params", {})
                if self.serial_host_override:
                    params["host"] = self.serial_host_override
                if self.serial_protocol_override:
                    params["protocol"] = self.serial_protocol_override
            if self.serial_host_override:
                port.host = self.serial_host_override
            if self.serial_protocol_override:
                port.protocol = self.serial_protocol_override
                # SerialDriver selects its pyserial transport class at target
                # construction time. Replace that unopened object after
                # correcting remote metadata, before the first activation.
                if self.serial_protocol_override != "raw":
                    raise StrategyError(
                        f"unsupported serial protocol override {self.serial_protocol_override!r}"
                    )
                console.serial = serial.serial_for_url("socket://", do_not_open=True)
            self.target.activate(console)
        shell.bypass_login = True
        self.target.activate(shell)
        return shell

    @never_retry
    @step()
    def transition(self, status, *, step):
        """Transition the strategy to a new state.

        Args:
            status (Status or str): target state (enum or its name, e.g.
                ``"jtag_bootstrap"``).
            step: labgrid step context (injected).

        Raises:
            StrategyError: on an invalid transition or missing inputs.

        Example:
            >>> strategy.transition("jtag_bootstrap")
        """
        if not isinstance(status, Status):
            status = Status[status]

        # Validate required inputs up-front, before @never_retry mutates any
        # state, so a missing input raises a clear error and leaves the
        # strategy reusable (rather than wedging it in "broken state").
        if status == Status.jtag_bootstrap:
            self._require("psu_init_tcl")
            self._require("spl_elf")
        elif status == Status.production_boot:
            for name in ("psu_init_tcl", "pmufw_bin", "uboot_bin"):
                self._require(name)
            if bool(self.bl31_bin) != bool(self.atf_handoff_bin):
                raise StrategyError("bl31_bin and atf_handoff_bin must be set together")
            if not self.bl31_bin and not self.handoff_bin:
                raise StrategyError(
                    "production_boot requires BL31 artifacts or a one-way handoff_bin"
                )
        elif status == Status.recovery_linux:
            for name in (
                "psu_init_tcl",
                "recovery_trampoline_elf",
                "recovery_kernel_image",
                "recovery_initramfs",
                "recovery_dtb",
            ):
                self._require(name)
            self._require_shell()
        elif status == Status.sd_flash_done:
            for name in ("sd_image_url", "sd_image_size", "sd_head_sha256", "sd_tail_sha256"):
                self._require(name)
            if int(self.sd_image_size) % int(self.sd_sample_bytes):
                raise StrategyError("sd_image_size must be a multiple of sd_sample_bytes")
            self._require_shell()
        elif status in (Status.production_uboot_prompt, Status.kuiper_shell):
            self._require_shell()

        self.logger.info(f"Transitioning to {status} (existing: {self.status})")

        if status == Status.unknown:
            raise StrategyError(f"can not transition to {status}")

        elif status == self.status:
            step.skip("nothing to do")
            return

        elif status == Status.powered_off:
            if self.shell:
                self.target.deactivate(self.shell)
            self.target.activate(self.power)
            self.power.off()
            time.sleep(self.power_off_settle_s)
            self.logger.info("Board powered off")

        elif status == Status.powered_on:
            self.transition(Status.powered_off)
            self.power.on()
            time.sleep(self.power_on_settle_s)
            self.logger.info("Board powered on")

        elif status == Status.jtag_bootstrap:
            psu_init_tcl = self._require("psu_init_tcl")
            spl_elf = self._require("spl_elf")
            self.transition(Status.powered_on)
            self.target.activate(self.jtag)
            self.logger.info("JTAG-bootstrapping ZynqMP mini U-Boot SPL...")
            self.jtag.load_zynqmp_uboot(
                psu_init_tcl=psu_init_tcl,
                spl_elf=spl_elf,
                bitstream_path=self.bitstream_path,
                a53_target_name=self.a53_target_name,
                apu_release_rst_value=self.apu_release_rst_value,
                dcc_log_path=self.dcc_log_path,
                settle_ms=self.spl_settle_ms,
                jtag_url=self.jtag_url,
            )
            self.logger.info("ZynqMP mini U-Boot SPL bootstrapped via JTAG")

        elif status == Status.production_boot:
            self.transition(Status.powered_on)
            if self.shell:
                self._activate_shell_bypass()
            self.target.activate(self.jtag)
            self.logger.info("JTAG-starting ZynqMP production U-Boot...")
            self.jtag.load_zynqmp_production_uboot(
                psu_init_tcl=self._require("psu_init_tcl"),
                pmufw_bin=self._require("pmufw_bin"),
                uboot_bin=self._require("uboot_bin"),
                handoff_bin=self.handoff_bin,
                bl31_bin=self.bl31_bin,
                atf_handoff_bin=self.atf_handoff_bin,
                pm_config_bin=self.pm_config_bin,
                bl31_console_uart_base=self.bl31_console_uart_base,
                bl31_console_ref_ctrl_address=self.bl31_console_ref_ctrl_address,
                bl31_console_reset_mask=self.bl31_console_reset_mask,
                bitstream_path=self.bitstream_path,
                ddr_scrub_elf=self.ddr_scrub_elf,
                a53_target_name=self.a53_target_name,
                apu_release_rst_value=self.apu_release_rst_value,
                pmufw_timeout_ms=self.pmufw_timeout_ms,
                ddr_scrub_settle_ms=self.ddr_scrub_settle_ms,
                settle_ms=self.production_settle_ms,
                jtag_url=self.jtag_url,
            )
            self.logger.info("ZynqMP production U-Boot started via JTAG handoff")

        elif status == Status.recovery_linux:
            self.transition(Status.powered_on)
            self._activate_shell_bypass()
            self.target.activate(self.jtag)
            self.jtag.load_zynqmp_recovery_linux(
                psu_init_tcl=self._require("psu_init_tcl"),
                trampoline_elf=self._require("recovery_trampoline_elf"),
                kernel_image=self._require("recovery_kernel_image"),
                initramfs=self._require("recovery_initramfs"),
                dtb=self._require("recovery_dtb"),
                ddr_scrub_elf=self.recovery_ddr_scrub_elf or self.ddr_scrub_elf,
                bitstream_path=self.recovery_bitstream_path or self.bitstream_path,
                a53_target_name=self.a53_target_name,
                apu_release_rst_value=self.apu_release_rst_value,
                ddr_scrub_done_address=(
                    self.recovery_ddr_scrub_done_address or self.ddr_scrub_done_address
                ),
                ddr_scrub_settle_ms=self.recovery_ddr_scrub_settle_ms,
                post_init_mask_writes=self.recovery_post_init_mask_writes,
                jtag_url=self.jtag_url,
            )
            self.shell.console.expect(self.recovery_marker, timeout=self.recovery_timeout)
            self.shell.prompt = self.recovery_prompt
            self.shell.console.expect(self.recovery_prompt, timeout=self.recovery_timeout)
            self.shell._check_prompt()
            self.shell._inject_run()
            self.logger.info("RAM-rooted ZynqMP recovery Linux shell verified")

        elif status == Status.sd_flash_done:
            self.transition(Status.recovery_linux)
            download = self.sd_download_cmd_template.format(url=self._require("sd_image_url"))
            tail_skip = int(self.sd_image_size) // int(self.sd_sample_bytes) - 1
            cmd = (
                "set -o pipefail; "
                f'test -b "{self.sd_device}" && '
                f'{download} | dd of="{self.sd_device}" bs=4M conv=fsync && '
                f"sync && blockdev --rereadpt {self.sd_device} && "
                f'head=$(dd if="{self.sd_device}" bs={int(self.sd_sample_bytes)} count=1 2>/dev/null | sha256sum | cut -d" " -f1) && '
                f'tail=$(dd if="{self.sd_device}" bs={int(self.sd_sample_bytes)} skip={tail_skip} count=1 2>/dev/null | sha256sum | cut -d" " -f1) && '
                f'test "$head" = "{self.sd_head_sha256}" && test "$tail" = "{self.sd_tail_sha256}" && echo SD_FLASH_OK'
            )
            stdout, stderr, returncode = self.shell.run(cmd, timeout=self.sd_flash_timeout)
            output = "\n".join(stdout) if isinstance(stdout, list) else str(stdout)
            error = "\n".join(stderr) if isinstance(stderr, list) else str(stderr)
            if returncode != 0 or "SD_FLASH_OK" not in output:
                raise StrategyError(f"SD flash failed (rc={returncode}): {error or output}")
            for command in self.post_flash_commands:
                out, err, rc = self.shell.run(command, timeout=self.post_flash_timeout)
                if rc:
                    detail = (
                        "\n".join(err or out) if isinstance(err or out, list) else str(err or out)
                    )
                    raise StrategyError(f"post-flash command failed (rc={rc}): {detail}")
            self.logger.info("ZynqMP SD recovery write completed")

        elif status == Status.production_uboot_prompt:
            self.transition(Status.production_boot)
            deadline = time.time() + self.production_prompt_timeout
            while time.time() < deadline:
                self.shell.console.sendline("")
                try:
                    self.shell.console.expect(self.production_uboot_prompt, timeout=0.1)
                    break
                except Exception:
                    continue
            else:
                raise StrategyError(
                    f"production U-Boot prompt {self.production_uboot_prompt!r} not observed"
                )
            self.shell.prompt = self.production_uboot_prompt
            self.shell._check_prompt_uboot()
            self.logger.info("Production U-Boot prompt verified on external UART")

        elif status == Status.kuiper_shell:
            self.transition(Status.production_uboot_prompt)
            self.shell.console.sendline(self.sd_boot_command)
            self.shell.console.expect(self.kuiper_kernel_marker, timeout=self.kuiper_boot_timeout)
            self.shell.console.expect(self.kuiper_shell_marker, timeout=self.kuiper_boot_timeout)
            self.shell.prompt = self.kuiper_shell_marker
            self.shell._check_prompt()
            self.shell._inject_run()
            for command in self.kuiper_verify_commands:
                self.shell.run_check(command, timeout=self.kuiper_verify_timeout)
            self.logger.info("Kuiper shell, Ethernet, JESD and IIO checks passed")

        else:
            raise StrategyError(f"no transition handler for {status}")

        self.status = status
