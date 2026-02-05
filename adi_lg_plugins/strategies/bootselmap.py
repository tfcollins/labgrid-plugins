"""Strategy to boot SelMap based dual FPGA design."""

import enum
import os
import time

import attr
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError, never_retry


class Status(enum.Enum):
    """Boot strategy state machine states for dual FPGA SelMap boot.

    Attributes:
        unknown: Initial state before any operations.
        powered_off: Both FPGAs are powered off.
        booting_zynq: Primary Zynq FPGA is booting.
        booted_zynq: Zynq FPGA has booted Linux successfully.
        update_zynq_boot_files: Updating Zynq boot files before booting.
        update_virtex_boot_files: Updating Virtex bitstream files.
        trigger_selmap_boot: Triggering SelMap boot of secondary Virtex FPGA.
        wait_for_virtex_boot: Waiting for Virtex FPGA boot to complete.
        booted_virtex: Secondary Virtex FPGA has booted successfully.
        shell: Interactive shell session available on Zynq.
        soft_off: Device being shut down gracefully.
    """

    unknown = 0
    powered_off = 1
    booting_zynq = 2
    booted_zynq = 3
    update_zynq_boot_files = 4
    update_virtex_boot_files = 5
    trigger_selmap_boot = 6
    wait_for_virtex_boot = 7
    booted_virtex = 8
    shell = 9
    soft_off = 10


@target_factory.reg_driver
@attr.s(eq=False)
class BootSelMap(Strategy):
    """BootSelMap - Strategy to boot SelMap based dual FPGA design.

    This strategy does not replace the kernel. It focuses on booting the secondary
    FPGA via the SelMap interface after the primary FPGA has booted Linux.

    """

    bindings = {
        "power": "PowerProtocol",
        "shell": "ADIShellDriver",
        "ssh": "SSHDriver",
        # "sdmux": "USBSDMuxDriver",
        # 'mass_storage': 'MassStorageDriver',
    }

    status = attr.ib(default=Status.unknown)
    reached_linux_marker = attr.ib(default="analog")
    ethernet_interface = attr.ib(default=None)
    iio_jesd_driver_name = attr.ib(default="axi-ad9081-rx-hpc")
    pre_boot_boot_files = attr.ib(default=None)
    post_boot_boot_files = attr.ib(default=None)
    boot_log = attr.ib(default="", init=False)

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self._copied_pre_boot_files = False
        self._copied_post_boot_files = False

    @never_retry
    @step()
    def transition(self, status, *, step):
        """Transition the strategy to a new state.

        This method manages state transitions for dual FPGA SelMap boot. It handles
        booting the primary Zynq FPGA, updating boot files for both FPGAs, and
        triggering the SelMap boot of the secondary Virtex FPGA.

        Args:
            status (Status or str): Target state to transition to. Can be a Status enum
                value or its string representation (e.g., "shell", "booted_virtex").
            step: Labgrid step decorator context (injected automatically).

        Raises:
            StrategyError: If the transition is invalid or fails.

        Example:
            >>> strategy.transition("booted_zynq")  # Boot primary Zynq FPGA
            >>> strategy.transition("trigger_selmap_boot")  # Boot secondary Virtex FPGA
            >>> strategy.transition("shell")  # Get shell access

        Note:
            This strategy manages a complex dual-FPGA system where the primary
            Zynq FPGA boots Linux and then triggers the secondary Virtex FPGA
            boot via the SelMap interface.
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
            self.target.activate(self.power)
            self.power.off()
            self.logger.info("System powered off")
        elif status == Status.booting_zynq:
            self.transition(Status.powered_off)
            self.target.activate(self.power)
            self.logger.info("Powering on Zynq (primary FPGA)...")
            time.sleep(5)
            self.power.on()
            self.logger.info("Zynq powered on, booting Linux...")
        elif status == Status.booted_zynq:
            self.transition(Status.booting_zynq)
            self.boot_log = ""  # Reset boot log for this boot
            self.shell.bypass_login = True
            self.target.activate(self.shell)
            # Check kernel start
            self.logger.info(f"Waiting for Linux boot and '{self.reached_linux_marker}' prompt...")
            _, before, _, _ = self.shell.console.expect("Linux", timeout=30)
            if before:
                self.boot_log += before.decode("utf-8", errors="replace")
            # Check device prompt
            _, before, _, _ = self.shell.console.expect(self.reached_linux_marker, timeout=30)
            if before:
                self.boot_log += before.decode("utf-8", errors="replace")
            self.shell.bypass_login = False
            self.target.deactivate(self.shell)
            time.sleep(5)
            self.logger.info("Zynq (primary FPGA) booted successfully")

        elif status == Status.update_zynq_boot_files:
            self.transition(Status.booted_zynq)
            self.logger.info("Updating Zynq boot files via SSH...")
            self.target.activate(self.shell)
            address = self.shell.get_ip_addresses(self.ethernet_interface)
            assert address, f"No IP address found on {self.ethernet_interface}"
            ip = str(address[0].ip)
            self.target.deactivate(self.shell)

            # Check the same as SSHDriver
            if self.ssh.networkservice.address == ip:
                self.logger.info(f"Syncing SSHDriver IP to {ip}")
                self.ssh.networkservice.address = ip

            if not self._copied_pre_boot_files:
                if self.pre_boot_boot_files:
                    self.target.activate(self.ssh)
                    for local_path, remote_path in self.pre_boot_boot_files.items():
                        if os.path.isfile(local_path) is False:
                            raise StrategyError(f"Local boot file {local_path} does not exist")
                        folder_in_boot_path = "/".join(remote_path.split("/")[:-1])
                        if folder_in_boot_path and folder_in_boot_path != "/boot":
                            self.ssh.run(f"mkdir -p {folder_in_boot_path}")
                        self.logger.info(
                            f"Uploading Zynq boot file {local_path} to {remote_path}..."
                        )
                        self.ssh.put(local_path, remote_path)
                    self.target.deactivate(self.ssh)
                    self._copied_pre_boot_files = True
                    # Restart to apply new boot files
                    self.logger.info("Restarting Zynq to apply new boot files...")
                    self.transition(Status.powered_off)
                    self.transition(Status.booting_zynq)
                    self.transition(Status.booted_zynq)
                    self.status = Status.powered_off
                    return  # Exit here to restart the boot process

            self.logger.info("Zynq boot files updated successfully")

        elif status == Status.update_virtex_boot_files:
            self.transition(Status.update_zynq_boot_files)
            self.logger.info("Updating Virtex (secondary FPGA) bitstream files...")
            self.target.activate(self.shell)
            address = self.shell.get_ip_addresses(self.ethernet_interface)
            assert address, f"No IP address found on {self.ethernet_interface}"
            ip = str(address[0].ip)
            self.target.deactivate(self.shell)

            # Check the same as SSHDriver
            if self.ssh.networkservice.address == ip:
                self.ssh.networkservice.address = ip

            if not self._copied_post_boot_files:
                if self.post_boot_boot_files:
                    self.target.activate(self.ssh)
                    for local_path, remote_path in self.post_boot_boot_files.items():
                        if os.path.isfile(local_path) is False:
                            raise StrategyError(f"Local boot file {local_path} does not exist")
                        folder_in_boot_path = "/".join(remote_path.split("/")[:-1])
                        if folder_in_boot_path and folder_in_boot_path != "/boot":
                            self.ssh.run(f"mkdir -p {folder_in_boot_path}")
                        self.logger.info(
                            f"Uploading Virtex boot file {local_path} to {remote_path}..."
                        )
                        self.ssh.put(local_path, remote_path)
                    self.target.deactivate(self.ssh)
                    self._copied_post_boot_files = True

            self.logger.info("Virtex boot files updated successfully")

        elif status == Status.trigger_selmap_boot:
            self.transition(Status.update_virtex_boot_files)
            self.logger.info("Triggering SelMap boot for secondary Virtex FPGA...")
            self.target.activate(self.ssh)
            self.ssh.run("cd /boot/ci && ./selmap_dtbo.sh -d vu11p.dtbo -b vu11p.bin")
            self.target.deactivate(self.ssh)
            self.logger.info("SelMap boot trigger script executed")

        elif status == Status.wait_for_virtex_boot:
            self.transition(Status.trigger_selmap_boot)
            self.shell.bypass_login = True
            self.target.activate(self.shell)
            # Check for device to register
            found_device = False
            self.logger.info(
                f"Waiting for IIO JESD device ({self.iio_jesd_driver_name}) to appear..."
            )
            for t in range(30):
                stdout, stderr, returncode = self.shell.run(
                    f"iio_attr -d {self.iio_jesd_driver_name} jesd204_fsm_state", timeout=4
                )
                if "could not find device" in stdout:
                    self.logger.info(f"Still waiting for IIO JESD device... ({t + 1}/30)")
                else:
                    self.logger.info(f"IIO JESD device found: {stdout.strip()}")
                    found_device = True
                    break
                time.sleep(1)

            if not found_device:
                raise StrategyError(
                    "Virtex did not boot successfully within timeout (device not found)"
                )

            jesd_finished = False
            self.logger.info("Waiting for JESD FSM to reach post_running_stage...")
            for t in range(120):
                stdout, stderr, returncode = self.shell.run(
                    f"iio_attr -d {self.iio_jesd_driver_name} jesd204_fsm_state", timeout=4
                )
                if "opt_post_running_stage" in stdout:
                    jesd_finished = True
                    self.logger.info("JESD FSM reached post_running_stage")
                    break
                else:
                    if t % 10 == 0:
                        self.logger.info(f"JESD FSM state: {stdout.strip()} ({t + 1}/120)")
                time.sleep(1)

            if not jesd_finished:
                raise StrategyError("Virtex JESD did not finish successfully within timeout")

            # Restart IIOD
            self.logger.info("Restarting IIOD service...")
            self.shell.run("systemctl restart iiod.service")

            self.shell.bypass_login = False
            self.target.deactivate(self.shell)
            self.logger.info("Virtex (secondary FPGA) booted successfully")

        elif status == Status.shell:
            self.transition(Status.wait_for_virtex_boot)
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
