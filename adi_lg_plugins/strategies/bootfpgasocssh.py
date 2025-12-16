import enum
import time

import attr
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError, never_retry


class Status(enum.Enum):
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
    hostname = attr.ib(default="analog")

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        # self.hostname =
        print(f"Hostname set to: {self.hostname}")
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
        if not isinstance(status, Status):
            status = Status[status]

        self.logger.debug(
            f"Transitioning to {status} (Existing status: {self.status}) {status == Status.shell}"
        )

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
            self.logger.debug("DEBUG Powered off")
        elif status == Status.booting:
            self.transition(Status.powered_off)
            if self.power:
                self.target.activate(self.power)
                time.sleep(5)
                self.power.on()
            self.logger.debug("DEBUG Booting...")
        elif status == Status.booted:
            self.transition(Status.booting)
            if self.power:
                self.shell.bypass_login = True
                self.target.activate(self.shell)
                # Check kernel start
                self.shell.console.expect("Linux", timeout=30)
                # Check device prompt
                self.shell.console.expect(self.hostname)  # Adjust prompt as needed
                self.shell.bypass_login = False
                self.target.deactivate(self.shell)
            self.logger.debug("DEBUG Booted")

        elif status == Status.update_boot_files:
            self.transition(Status.booted)

            # Get IP address from shell
            self.target.activate(self.shell)
            addresses = self.shell.get_ip_addresses("eth0")
            assert addresses, "No IP address found on eth0"
            ip = str(addresses[0].ip)
            self.target.deactivate(self.shell)

            if self.ssh.networkservice.address != ip:
                self.logger.warning(
                    f"IP address mismatch between ShellDriver ({ip}) and SSHDriver ({self.ssh.networkservice.address})"
                )
                self.logger.warning("Updating SSHDriver IP address to match ShellDriver")
                self.ssh.networkservice.address = ip  # Update

            self.target.activate(self.ssh)

            if self.kuiper:
                if self.kuiper._boot_files:
                    for local_path in self.kuiper._boot_files:
                        remote_path = "/boot/"
                        self.logger.info(f"Uploading {local_path} to {remote_path} via SSH")
                        self.ssh.put(local_path, remote_path)
                else:
                    self.logger.warning("No boot files found in KuiperDLDriver to upload")
            else:
                self.logger.warning("KuiperDLDriver not available; no boot files to upload")

            # self.ssh.put("/tmp/testfile.txt", "/tmp/testfile.txt")

            self.target.deactivate(self.ssh)

            # Use SSH to update boot files here
            self.logger.debug("DEBUG Boot files updated via SSH")

        elif status == Status.reboot:
            self.transition(Status.update_boot_files)
            self.target.activate(self.shell)
            try:
                self.shell.run("reboot")
            except Exception as e:
                self.logger.info(f"DEBUG Reboot command exception (expected): {e}")
            self.target.deactivate(self.shell)
            self.logger.debug("DEBUG Rebooted")

        elif status == Status.booting_new:
            self.transition(Status.reboot)

            self.shell.bypass_login = True
            self.target.activate(self.shell)
            # Check kernel start
            self.shell.console.expect("Linux", timeout=30)
            # Check device prompt
            self.logger.info(f"DEBUG Expecting hostname prompt: {self.hostname}")
            self.shell.console.expect(self.hostname)  # Adjust prompt as needed
            self.target.deactivate(self.shell)
            self.shell.bypass_login = False
            self.logger.debug("DEBUG Booting new...")

        elif status == Status.shell:
            self.transition(Status.booting_new)
            self.target.activate(self.shell)
            # Post boot stuff...
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
