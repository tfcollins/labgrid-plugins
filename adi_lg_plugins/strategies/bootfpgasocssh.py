import enum
import ipaddress
import os
import time

import attr
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError, never_retry


class Status(enum.Enum):
    """Boot strategy state machine states for SSH-based boot.

    Attributes:
        unknown: Initial state before any operations.
        powered_off: Device is powered off.
        booting: Device powered on, initial boot in progress.
        booted: Linux kernel has booted, waiting for shell access.
        update_boot_files: Copying boot files to device via SSH.
        reboot: Device is rebooting with new boot files.
        booting_new: Device booting after file update.
        shell: Interactive shell session available.
        soft_off: Device being shut down gracefully.
    """

    unknown = 0
    powered_off = 1
    booting = 2
    booted = 3
    update_boot_files = 4
    reboot = 5
    booting_new = 6
    shell = 7
    soft_off = 8


@target_factory.reg_driver
@attr.s(eq=False)
class BootFPGASoCSSH(Strategy):
    """Strategy to boot an FPGA SoC device using ShellDriver and SSHDriver.

    This strategy manages the boot process of an FPGA SoC device by utilizing
    both the ShellDriver for initial boot interactions and the SSHDriver for
    file transfers and updates. It handles transitions through various states
    including powering off, booting, updating boot files, and entering a shell.

    Power control is optional and can be managed via a power driver if provided.
    """

    bindings = {
        "power": {"PowerProtocol", None},
        "shell": "ADIShellDriver",
        "ssh": "SSHDriver",
        "kuiper": {"KuiperDLDriver", None},
    }

    status = attr.ib(default=Status.unknown)

    reached_linux_marker = attr.ib(default="analog")
    wait_for_linux_prompt_timeout = attr.ib(default=60)
    boot_log = attr.ib(default="", init=False)

    debug_write_boot_log = attr.ib(default=False)

    # update_boot_files polls the DUT's shell for an IPv4 address on eth0
    # before initiating the SSH upload. DHCPv4 typically lands within a
    # few seconds after the shell login prompt but can be slower on cold
    # boots / Kuiper kernels where IPv6 SLAAC completes first.
    ipv4_poll_timeout = attr.ib(default=60.0)
    ipv4_poll_interval = attr.ib(default=3.0)

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self.logger.info("BootFPGASoCSSH strategy initialized")
        if self.kuiper:
            self.target.activate(self.kuiper)
            self.logger.info("KuiperDLDriver activated")
            # self.kuiper.download_release()
            self.kuiper.get_boot_files_from_release()
            self.target.deactivate(self.kuiper)

    @never_retry
    @step()
    def transition(self, status, *, step):
        """Transition the strategy to a new state.

        This method manages state transitions for SSH-based boot. It handles
        power control, shell driver activation, SSH file transfer, and device
        reboot sequences.

        Args:
            status (Status or str): Target state to transition to. Can be a Status enum
                value or its string representation (e.g., "shell", "booted").
            step: Labgrid step decorator context (injected automatically).

        Raises:
            StrategyError: If the transition is invalid or fails.

        Example:
            >>> strategy.transition("shell")  # Transition to shell state
            >>> strategy.transition("update_boot_files")  # Update boot files via SSH

        Note:
            This strategy uses SSH for file transfers, unlike BootFPGASoC which
            uses SD card mux. Power control is optional in this strategy.
        """
        if not isinstance(status, Status):
            status = Status[status]

        self.logger.info(f"Transitioning to {status} (Existing status: {self.status})")

        if status == Status.unknown:
            raise StrategyError(f"can not transition to {status}")
        elif status == self.status:
            step.skip("nothing to do")
            return  # nothing to do
        elif status == Status.powered_off:
            self.target.deactivate(self.shell)
            if self.power:
                self.target.activate(self.power)
                self.power.off()
            self.logger.info("Device powered off")
        elif status == Status.booting:
            self.transition(Status.powered_off)
            if self.power:
                self.target.activate(self.power)
                self.logger.info("Powering on device...")
                time.sleep(5)
                self.power.on()
            self.logger.info("Device powered on, booting...")
        elif status == Status.booted:
            self.transition(Status.booting)
            self.boot_log = ""  # Reset boot log for this boot
            if self.power:
                self.logger.info("Waiting for Linux boot...")
                self.shell.bypass_login = True
                self.target.activate(self.shell)
                # Check kernel start
                _, before, _, _ = self.shell.console.expect("Linux", timeout=30)
                if before:
                    self.boot_log += before.decode("utf-8", errors="replace")
                self.shell.bypass_login = False
                self.target.deactivate(self.shell)
            self.logger.info("Initial boot successful")

        elif status == Status.update_boot_files:
            self.transition(Status.booted)

            self.logger.info("Identifying device IP for SSH file transfer...")
            # Get IP address from shell. DHCPv4 often lags the shell login
            # prompt by several seconds (kernel brings eth0 up before
            # udhcpc / NM gets a v4 lease, and IPv6 SLAAC lands first), so
            # poll up to ipv4_poll_timeout seconds before giving up.
            # Without this poll we'd reliably fail on cold boots where the
            # first read after login sees only the link-local IPv6.
            self.target.activate(self.shell)
            addresses = []
            ipv4 = []
            deadline = time.time() + self.ipv4_poll_timeout
            while time.time() < deadline:
                addresses = self.shell.get_ip_addresses("eth0") or []
                ipv4 = [a for a in addresses if isinstance(a.ip, ipaddress.IPv4Address)]
                if ipv4:
                    break
                seen = [str(a.ip) for a in addresses] if addresses else []
                self.logger.info(
                    f"eth0 has no IPv4 yet (got {seen}); polling..."
                )
                time.sleep(self.ipv4_poll_interval)
            # Require IPv4. SSHDriver passes the resource address to ssh as a
            # plain string and uses it (unquoted) in the control-socket path:
            # a raw IPv6 ends up parsed as host:port (first colon wins),
            # truncating the address and breaking scp uploads. Until the
            # underlying driver brackets IPv6 properly, pick the first IPv4
            # address; bail with a clear message if there isn't one.
            if not ipv4:
                raise StrategyError(
                    f"No IPv4 address found on eth0 after {self.ipv4_poll_timeout:.0f}s; "
                    f"only IPv6 addresses were returned ({[str(a.ip) for a in addresses]}). "
                    "The SSH file-transfer step does not currently support IPv6."
                )
            ip = str(ipv4[0].ip)
            self.target.deactivate(self.shell)

            if self.ssh.networkservice.address != ip:
                self.logger.info(f"Updating SSHDriver IP address to {ip}")
                self._override_networkservice_address(self.ssh.networkservice, ip)

            self.target.activate(self.ssh)

            if self.kuiper:
                if self.kuiper._boot_files:
                    self.logger.info(
                        f"Uploading {len(self.kuiper._boot_files)} boot files via SSH..."
                    )
                    for local_path in self.kuiper._boot_files:
                        remote_path = "/boot/"
                        self.logger.info(
                            f"Uploading {os.path.basename(local_path)} to {remote_path}..."
                        )
                        self.ssh.put(local_path, remote_path)
                else:
                    self.logger.warning("No boot files found in KuiperDLDriver to upload")
            else:
                self.logger.warning("KuiperDLDriver not available; no boot files to upload")

            self.target.deactivate(self.ssh)
            self.logger.info("Boot files updated via SSH successfully")

        elif status == Status.reboot:
            self.transition(Status.update_boot_files)
            self.target.activate(self.shell)
            self.logger.info("Triggering device reboot...")
            try:
                self.shell.run("reboot")
            except Exception as e:
                self.logger.debug(f"Reboot command exception (expected): {e}")
            self.target.deactivate(self.shell)
            self.logger.info("Reboot command sent")

        elif status == Status.booting_new:
            self.transition(Status.reboot)
            self.boot_log = ""  # Reset boot log for this boot (new kernel)

            self.logger.info(f"Waiting for Linux boot and '{self.reached_linux_marker}' prompt...")
            self.shell.bypass_login = True
            self.target.activate(self.shell)
            # Check kernel start
            try:
                _, before, _, _ = self.shell.console.expect("Linux", timeout=30)
                if before:
                    self.boot_log += before.decode("utf-8", errors="replace")
                # Check device prompt
                _, before, _, _ = self.shell.console.expect(
                    self.reached_linux_marker, timeout=self.wait_for_linux_prompt_timeout
                )
                if before:
                    self.boot_log += before.decode("utf-8", errors="replace")
                self.target.deactivate(self.shell)
                self.shell.bypass_login = False
                self.logger.info("Device booted with new files successfully")
            except Exception as e:
                if self.debug_write_boot_log:
                    uart_log_filename = f"uart_log_{int(time.time())}.txt"
                    with open(uart_log_filename, "wb") as f:
                        f.write(self.shell.console._expect.before)
                        self.logger.info(f"Wrote log file to {uart_log_filename}")
                raise e

        elif status == Status.shell:
            self.transition(Status.booting_new)
            self.logger.info("Preparing interactive shell...")
            self.target.activate(self.shell)
            # Post boot stuff...
            self.logger.info("Shell access ready")
        elif status == Status.soft_off:
            self.transition(Status.shell)
            try:
                self.shell.run("poweroff")
                self.shell.console.expect("Power down", timeout=30)
                self.target.deactivate(self.shell)
                time.sleep(10)
            except Exception as e:
                self.logger.debug(f"DEBUG Soft off failed: {e}")
                time.sleep(5)
                self.target.deactivate(self.shell)
            self.target.activate(self.power)
            self.power.off()
            self.logger.debug("DEBUG Soft powered off")
        else:
            raise StrategyError(f"no transition found from {self.status} to {status}")
        self.status = status

    @staticmethod
    def _override_networkservice_address(networkservice, ip: str) -> None:
        """Point a (possibly remote) NetworkService at a new IP.

        Setting ``networkservice.address`` alone is not enough when the
        resource came in via a RemotePlace: labgrid's RemotePlaceManager
        polls the coordinator every ``ManagedResource.timeout`` seconds and
        rewrites every attribute from ``resource._remote_entry.args`` back
        onto the live resource (see
        labgrid/resource/remote.py:RemotePlaceManager.poll). Without also
        updating the cached entry, the next poll reverts the address back
        to the exporter's stale record before SSHDriver's on_activate reads
        it — and the control socket ends up wired to the wrong IP.

        Note: ``ResourceEntry.args`` is a *property* that returns a fresh
        copy of ``self.data["params"]`` each call, so mutating
        ``remote_entry.args[...]`` is a no-op. We have to touch the backing
        store at ``remote_entry.data["params"]["address"]`` instead.
        """
        networkservice.address = ip
        remote_entry = getattr(networkservice, "_remote_entry", None)
        if remote_entry is None:
            return
        # ResourceEntry.data["params"] is the dict that ResourceEntry.args
        # (the property) returns a copy of, and that RemotePlaceManager.poll
        # reads via .args on every tick.
        data = getattr(remote_entry, "data", None)
        if isinstance(data, dict):
            params = data.get("params")
            if isinstance(params, dict):
                params["address"] = ip
