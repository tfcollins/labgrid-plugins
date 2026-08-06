"""Strategy to boot SelMap based dual FPGA design."""

import enum
import os
import subprocess
import time

import attr
import iio
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError

from ._compat import never_retry


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
    iio_jesd_data_mode = attr.ib(default="DATA")
    # iio_jesd_link_mode_attr = attr.ib(default="jesd204_link_mode")
    iio_jesd_link_mode_attr = attr.ib(default="jesd204_fsm_state")
    pre_boot_boot_files = attr.ib(default=None)
    post_boot_boot_files = attr.ib(default=None)
    boot_log = attr.ib(default="", init=False)

    target_dut_folder = attr.ib(default="/boot/ci")
    local_kernel_filename = attr.ib(default=None)
    local_device_tree_filename = attr.ib(default=None)
    selmap_boot_script_name = attr.ib(default="selmap_dtbo.sh")
    local_overlay_filename = attr.ib(default=None)
    local_bitstream_filename = attr.ib(default=None)
    pre_load_commands = attr.ib(default=None)

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self._copied_pre_boot_files = False
        self._copied_post_boot_files = False

        # Override if environment variable is set
        self.local_kernel_filename = os.environ.get(
            "LG_SM_KERNEL", self.local_kernel_filename
        )
        self.local_device_tree_filename = os.environ.get("LG_SM_DT", self.local_device_tree_filename
        )
        self.local_bitstream_filename = os.environ.get(
            "LG_SM_BITSTREAM", self.local_bitstream_filename
        )
        self.local_overlay_filename = os.environ.get("LG_SM_DTBO", self.local_overlay_filename)

        # Check if files exist
        if self.local_bitstream_filename and not os.path.isfile(self.local_bitstream_filename):
            raise StrategyError(
                f"Local bitstream file {self.local_bitstream_filename} does not exist"
            )
        self.logger.info(f"Using local bitstream file: {self.local_bitstream_filename}")
        if self.local_overlay_filename and not os.path.isfile(self.local_overlay_filename):
            raise StrategyError(f"Local overlay file {self.local_overlay_filename} does not exist")
        self.logger.info(f"Using local overlay file: {self.local_overlay_filename}")
        if self.pre_boot_boot_files:
            for local_path in self.pre_boot_boot_files.keys():
                if not os.path.isfile(local_path):
                    raise StrategyError(f"Local pre-boot file {local_path} does not exist")
                self.logger.info(f"Using local pre-boot file: {local_path}")
        if self.post_boot_boot_files:
            for local_path in self.post_boot_boot_files.keys():
                if not os.path.isfile(local_path):
                    raise StrategyError(f"Local post-boot file {local_path} does not exist")
                self.logger.info(f"Using local post-boot file: {local_path}")

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
            if self.ssh.networkservice.address != ip:
                self.logger.info(f"Syncing SSHDriver IP to {ip}")
                self.ssh.networkservice.address = ip

            if self.local_kernel_filename:
                if not os.path.isfile(self.local_kernel_filename):
                    raise StrategyError(
                        f"Local kernel file {self.local_kernel_filename} does not exist"
                    )
                remote_kernel_path = os.path.join(
                    "/boot", os.path.basename(self.local_kernel_filename)
                )
                self.logger.info(
                    f"Uploading Zynq kernel file {self.local_kernel_filename} to {remote_kernel_path}..."
                )
                self.target.activate(self.ssh)
                self.ssh.put(self.local_kernel_filename, remote_kernel_path)
                self.target.deactivate(self.ssh)

            if self.local_device_tree_filename:
                if not os.path.isfile(self.local_device_tree_filename):
                    raise StrategyError(
                        f"Local device tree file {self.local_device_tree_filename} does not exist"
                    )
                remote_dt_path = os.path.join(
                    "/boot", os.path.basename(self.local_device_tree_filename)
                )
                self.logger.info(
                    f"Uploading Zynq device tree file {self.local_device_tree_filename} to {remote_dt_path}..."
                )
                self.target.activate(self.ssh)
                self.ssh.put(self.local_device_tree_filename, remote_dt_path)
                self.target.deactivate(self.ssh)

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
                    self.ssh.run("sync")
                    time.sleep(5)  # Allow time for the files to be written
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
            self.logger.info(f"Detected IP address on {self.ethernet_interface}: {address[0].ip}")
            # Check if the IP address is reachable via ping
            ip = str(address[0].ip)
            # Subprocess based ping
            response = subprocess.call(["ping", "-c", "1", "-W", "2", ip], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.logger.info(f"Ping response code for {ip}: {response}")
            if response != 0:
                self.logger.warning(f"IP address {ip} is not reachable via ping")
            self.target.deactivate(self.shell)

            # Check the same as SSHDriver
            if self.ssh.networkservice.address != ip:
                self.logger.info(f"Syncing SSHDriver IP to {ip}")
                self.ssh.networkservice.address = ip

            # Copy required files to the target device for Virtex boot
            if self.local_bitstream_filename:
                if not os.path.isfile(self.local_bitstream_filename):
                    raise StrategyError(
                        f"Local bitstream file {self.local_bitstream_filename} does not exist"
                    )
                remote_bitstream_path = os.path.join(
                    self.target_dut_folder, os.path.basename(self.local_bitstream_filename)
                )
                self.logger.info(
                    f"Uploading Virtex bitstream file {self.local_bitstream_filename} to {remote_bitstream_path}..."
                )
                self.target.activate(self.ssh)
                self.ssh.run(f"mkdir -p {self.target_dut_folder}")
                self.ssh.put(self.local_bitstream_filename, remote_bitstream_path)
                self.target.deactivate(self.ssh)

            if self.local_overlay_filename:
                if not os.path.isfile(self.local_overlay_filename):
                    raise StrategyError(
                        f"Local overlay file {self.local_overlay_filename} does not exist"
                    )
                remote_overlay_path = os.path.join(
                    self.target_dut_folder, os.path.basename(self.local_overlay_filename)
                )
                self.logger.info(
                    f"Uploading Virtex overlay file {self.local_overlay_filename} to {remote_overlay_path}..."
                )
                self.target.activate(self.ssh)
                self.ssh.run(f"mkdir -p {self.target_dut_folder}")
                self.ssh.put(self.local_overlay_filename, remote_overlay_path)
                self.target.deactivate(self.ssh)

            # Copy extras
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
            if self.pre_load_commands:
                if isinstance(self.pre_load_commands, str):
                    self.pre_load_commands = [self.pre_load_commands]
                for cmd in self.pre_load_commands:
                    self.logger.info(f"Executing pre-load command: {cmd}")
                    stdout, stderr, returncode = self.ssh.run(cmd)
                    if returncode != 0:
                        stdout_str = "\n".join(stdout) if isinstance(stdout, list) else str(stdout)
                        stderr_str = "\n".join(stderr) if isinstance(stderr, list) else str(stderr)
                        self.logger.error(f"Pre-load command '{cmd}' failed with return code {returncode}")
                        self.logger.error(f"stdout:\n{stdout_str}")
                        self.logger.error(f"stderr:\n{stderr_str}")
                        raise StrategyError(
                            f"Pre-load command '{cmd}' failed with return code {returncode}"
                        )
            time.sleep(2)
            out = self.ssh.run(
                f"cd {self.target_dut_folder} && ./selmap_dtbo.sh -d {os.path.basename(self.local_overlay_filename)} -b {os.path.basename(self.local_bitstream_filename)}"
            )
            print(f"SelMap boot trigger output:\n{out}")
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
            driver_up_delay = 120
            for t in range(driver_up_delay):
                stdout, stderr, returncode = self.shell.run(
                    f"iio_attr -d {self.iio_jesd_driver_name} jesd204_fsm_state", timeout=4
                )
                if isinstance(stdout, list):
                    stdout = "\n".join(stdout)
                stdout = str(stdout).strip()
                if "could not find device" in stdout:
                    self.logger.info(
                        f"Still waiting for IIO JESD device... ({t + 1}/{driver_up_delay})"
                    )
                else:
                    self.logger.info(f"IIO JESD device found: {stdout}")
                    found_device = True
                    break
                time.sleep(1)

            if not found_device:
                # Get dmesg output for debugging
                dmesg_output, _, _ = self.shell.run("dmesg", timeout=10)
                if isinstance(dmesg_output, list):
                    dmesg_output = "\n".join(dmesg_output)
                dmesg_output = str(dmesg_output).strip()
                self.logger.warning("-" * 40)
                self.logger.warning("DEBUG: dmesg output")
                self.logger.warning("-" * 40)
                self.logger.warning(f"\n{dmesg_output}\n")
                self.logger.warning("-" * 40)
                raise StrategyError(
                    "Virtex did not boot successfully within timeout (device not found)"
                )

            # Device available, restart iiod so remote works
            time.sleep(5)
            self.logger.info("Restarting IIOD service to ensure remote access...")
            self.shell.run("systemctl restart iiod.service")
            time.sleep(3)

            jesd_finished = False
            self.logger.info("Waiting for JESD FSM to reach post_running_stage...")
            data_mode_ready = False
            fsm_links_up_delay = 200

            ctx = iio.Context(f"ip:{self.ssh.networkservice.address}")
            if not ctx:
                raise StrategyError("Failed to create IIO context for checking JESD link modes")
            dev = ctx.find_device(self.iio_jesd_driver_name)
            if not dev:
                raise StrategyError(
                    f"Failed to find IIO device {self.iio_jesd_driver_name} for checking JESD link modes"
                )

            # Check for JESD FSM state and link modes
            for t in range(fsm_links_up_delay):
                jesd204_fsm_state = dev.attrs[self.iio_jesd_link_mode_attr].value
                self.logger.info(
                    f"JESD FSM state: {jesd204_fsm_state} ({t + 1}/{fsm_links_up_delay})"
                )
                if "opt_post_running_stage" in jesd204_fsm_state or "link" in jesd204_fsm_state:
                    jesd_finished = True
                    data_mode_ready = True
                    self.logger.info(
                        "JESD FSM reached post_running_stage and links are in DATA mode"
                    )
                    break
                time.sleep(1)

            if not jesd_finished:
                raise StrategyError("Virtex JESD did not finish successfully within timeout")
            if not data_mode_ready:
                raise StrategyError("Virtex JESD links are not in DATA mode")

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

    def _parse_jesd_link_modes(self, output: str) -> list[str]:
        """Parse JESD link mode output from iio_attr."""
        modes: list[str] = []
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            value = line
            for sep in (":", "="):
                if sep in value:
                    value = value.split(sep, 1)[1].strip()
                    break
            tokens = [token.strip() for token in value.replace(",", " ").split() if token.strip()]
            modes.extend(tokens)
        return modes

    def check_jesd_links_data_mode(self, timeout: int = 4) -> bool:
        """
        Check JESD link modes and return True when all linked modes are DATA.

        Returns False when no modes are found or if any mode is not DATA.
        """
        stdout, _, return_code = self.shell.run(
            f"iio_attr -d {self.iio_jesd_driver_name} {self.iio_jesd_link_mode_attr}",
            timeout=timeout,
        )
        if return_code != 0:
            return False

        if isinstance(stdout, list):
            stdout = "\n".join(stdout)
        stdout = str(stdout).strip()

        link_modes = self._parse_jesd_link_modes(stdout)
        if not link_modes:
            self.logger.warning("No JESD link modes detected for %s", self.iio_jesd_driver_name)
            return False

        self.logger.info("JESD link modes: %s", ", ".join(link_modes))
        return all(mode.upper() == self.iio_jesd_data_mode for mode in link_modes)
