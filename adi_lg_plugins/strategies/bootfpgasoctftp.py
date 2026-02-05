import enum
import os
import shutil
import time

import attr
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError, never_retry


class Status(enum.Enum):
    """Boot strategy state machine states for TFTP-based boot."""

    unknown = 0
    powered_off = 1
    update_boot_files = 2
    booting = 3
    booted = 4
    shell = 5
    soft_off = 6


@target_factory.reg_driver
@attr.s(eq=False)
class BootFPGASoCTFTP(Strategy):
    """Strategy to boot an FPGA SoC device using ShellDriver and TFTP.

    This strategy manages the boot process of an FPGA SoC device by utilizing
    both the ShellDriver for initial boot interactions and TFTP for kernel loading.
    It depends on a `TFTPServerResource` to provide the server IP address.
    It handles transitions through various states including powering off, booting,
    updating boot files, and entering a shell.
    """

    bindings = {
        "power": "PowerProtocol",
        "shell": "ADIShellDriver",
        "ssh": {"SSHDriver", None},
        "kuiper": {"KuiperDLDriver", None},
        "tftp_server": "TFTPServerResource",
        "tftp_driver": "TFTPServerDriver",
    }

    status = attr.ib(default=Status.unknown)

    reached_linux_marker = attr.ib(default="analog")
    wait_for_linux_prompt_timeout = attr.ib(default=60)
    tftp_root_folder = attr.ib(default="/var/lib/tftpboot")

    # Memory addresses for boot components
    kernel_addr = attr.ib(default="0x30000000")
    dtb_addr = attr.ib(default="0x2A000000")
    # bitstream_addr = attr.ib(default="0x80000000") # Unused currently but good to have
    bootargs = attr.ib(
        default="console=ttyPS0,115200 root=/dev/mmcblk0p2 rw earlycon earlyprintk rootfstype=ext4 rootwait"
    )

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self.logger.info("BootFPGASoCTFTP strategy initialized")

        if self.tftp_driver:
            self.tftp_root_folder = self.tftp_driver.resource.root
            self.logger.info(f"Using managed TFTP server with root: {self.tftp_root_folder}")

        if self.kuiper:
            self.target.activate(self.kuiper)
            self.logger.info("KuiperDLDriver activated")
            self.kuiper.get_boot_files_from_release()
            self.target.deactivate(self.kuiper)

    @never_retry
    @step()
    def transition(self, status, *, step):
        if not isinstance(status, Status):
            status = Status[status]

        self.logger.info(f"Transitioning to {status} (Existing status: {self.status})")

        if status == Status.unknown:
            raise StrategyError(f"can not transition to {status}")

        if status == self.status:
            step.skip("nothing to do")
            return

        if status == Status.powered_off:
            self.target.deactivate(self.shell)
            if self.tftp_driver:
                self.target.deactivate(self.tftp_driver)
            if self.power:
                self.target.activate(self.power)
                self.power.off()
            self.logger.info("Device powered off")

        elif status == Status.update_boot_files:
            self.transition(Status.powered_off)
            if self.tftp_driver:
                self.target.activate(self.tftp_driver)

            if not self.kuiper:
                self.logger.warning("No KuiperDLDriver attached, skipping boot file update check")
            else:
                self.logger.info(f"Preparing TFTP boot files in {self.tftp_root_folder}...")
                for boot_file in self.kuiper._boot_files:
                    self.logger.info(f"Copying {os.path.basename(boot_file)} to TFTP root...")
                    if not os.path.exists(boot_file):
                        raise StrategyError(f"Boot file {boot_file} does not exist")
                    target = os.path.join(self.tftp_root_folder, os.path.basename(boot_file))
                    shutil.copyfile(boot_file, target)
                self.logger.info("TFTP boot files prepared successfully")

        elif status == Status.booting:
            self.transition(Status.update_boot_files)
            if self.power:
                self.target.activate(self.power)
                self.logger.info("Powering on device...")
                time.sleep(5)
                self.power.on()
            self.logger.info("Device powered on, booting...")

        elif status == Status.booted:
            self.transition(Status.booting)
            self.shell.bypass_login = True
            self.target.activate(self.shell)

            # Stop autoboot
            self.logger.info("Waiting for U-Boot autoboot prompt...")
            self.shell.console.expect("Hit any key to stop autoboot", timeout=30)
            self.logger.info("Stopping autoboot...")
            self.shell.console.sendline(" ")
            time.sleep(2)

            org_prompt = self.shell.prompt
            # Temporarily set prompt to U-Boot prompt match
            self.shell.prompt = "ZynqMP>.*"
            self.shell.console.sendline("\n")
            self.shell._check_prompt_uboot()

            # U-Boot commands configuration
            commands = [
                "setenv autoload no",
                "dhcp",
                f"setenv serverip {self.tftp_server.get_ip()}",
                f"setenv tftpdstport {self.tftp_driver.resource.port}",
                f"setenv tftpport {self.tftp_driver.resource.port}",
                "printenv tftpdstport",
                f"ping {self.tftp_server.get_ip()}",
                # Default bootargs if not set
                f"setenv bootargs {self.bootargs}",
                f"tftpboot {self.kernel_addr} Image",
                f"tftpboot {self.dtb_addr} system.dtb",
            ]

            self.logger.info("Configuring U-Boot for TFTP boot...")
            for cmd in commands:
                self.logger.info(f"U-Boot: {cmd}")
                self.shell.run_uboot(f"{cmd}\n", timeout=60)  # Increased timeout for TFTP
                self.shell._check_prompt_uboot()

            # Boot the kernel
            # booti will start the kernel, so we don't expect the U-Boot prompt to return
            self.logger.info("Starting kernel execution (booti)...")
            self.shell.console.sendline(f"booti {self.kernel_addr} - {self.dtb_addr}")

            # Check if we reached Linux prompt
            self.logger.info(f"Waiting for Linux boot and '{self.reached_linux_marker}' prompt...")
            self.shell.prompt = org_prompt
            self.shell.console.expect(
                self.reached_linux_marker, timeout=self.wait_for_linux_prompt_timeout
            )
            self.shell.bypass_login = False
            self.target.deactivate(self.shell)
            self.logger.info("Device booted successfully via TFTP")

        elif status == Status.shell:
            self.transition(Status.booted)
            self.logger.info("Preparing interactive shell...")
            self.target.activate(self.shell)
            self.logger.info("Shell access ready")

        elif status == Status.soft_off:
            self.transition(Status.shell)
            try:
                self.logger.info("Triggering soft power off...")
                self.shell.run("poweroff")
                self.shell.console.expect("Power down", timeout=30)
                self.target.deactivate(self.shell)
                time.sleep(10)
            except Exception as e:
                self.logger.debug(f"Soft off failed: {e}")
                time.sleep(5)
                self.target.deactivate(self.shell)

            if self.power:
                self.target.activate(self.power)
                self.power.off()
            self.logger.info("Device powered off")

        else:
            raise StrategyError(f"no transition found from {self.status} to {status}")

        self.status = status
