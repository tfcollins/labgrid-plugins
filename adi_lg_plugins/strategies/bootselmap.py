"""Strategy to boot SelMap based dual FPGA design."""
import enum
import time
import os

import attr

from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError, never_retry
from labgrid.factory import target_factory

class Status(enum.Enum):
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

    def __attrs_post_init__(self):
        super().__attrs_post_init__()    
        self._copied_pre_boot_files = False
        self._copied_post_boot_files = False

    @never_retry
    @step()
    def transition(self, status, *, step):
        if not isinstance(status, Status):
            status = Status[status]

        self.logger.debug(f"Transitioning to {status} (Existing status: {self.status}) {status == Status.shell}")

        if status == Status.unknown:
            raise StrategyError(f"can not transition to {status}")
        elif status == self.status:
            step.skip("nothing to do")
            return  # nothing to do
        elif status == Status.powered_off:
            self.target.deactivate(self.shell)
            self.target.activate(self.power)
            self.power.off()
            self.logger.debug("DEBUG Powered off")
        elif status == Status.booting_zynq:
            self.transition(Status.powered_off)
            self.target.activate(self.power)
            time.sleep(5)
            self.power.on()
            self.logger.debug("DEBUG Booting Zynq...")
        elif status == Status.booted_zynq:
            self.transition(Status.booting_zynq)
            self.shell.bypass_login = True
            self.target.activate(self.shell)
            # Check kernel start
            self.shell.console.expect("Linux", timeout=30)
            # Check device prompt
            self.shell.console.expect(self.reached_linux_marker, timeout=30)
            self.shell.bypass_login = False
            self.target.deactivate(self.shell)
            time.sleep(5)
            self.logger.debug("DEBUG Zynq Booted")


        elif status == Status.update_zynq_boot_files:
            self.transition(Status.booted_zynq)
            self.target.activate(self.shell)
            address = self.shell.get_ip_addresses(self.ethernet_interface)
            assert address, f"No IP address found on {self.ethernet_interface}"
            ip = str(address[0].ip)
            self.target.deactivate(self.shell)

            # Check the same as SSHDriver
            if self.ssh.networkservice.address == ip:
                self.logger.debug("DEBUG IP address matches between ShellDriver and SSHDriver")
                self.logger.debug(f"Changing SSHDriver IP from {self.ssh.networkservice.address} to {ip}")
                self.ssh.networkservice.address = ip

            if not self._copied_pre_boot_files:
                if self.pre_boot_boot_files:
                    self.target.activate(self.ssh)
                    print(self.pre_boot_boot_files)
                    for local_path, remote_path in self.pre_boot_boot_files.items():
                        if os.path.isfile(local_path) is False:
                            raise StrategyError(f"Local boot file {local_path} does not exist")
                        folder_in_boot_path = '/'.join(remote_path.split('/')[:-1])
                        if folder_in_boot_path and folder_in_boot_path != '/boot':
                            self.ssh.run(f"mkdir -p {folder_in_boot_path}")
                        self.logger.debug(f"DEBUG Uploading Zynq boot file {local_path} to {remote_path}")
                        self.ssh.put(local_path, remote_path)
                    self.target.deactivate(self.ssh)
                    self._copied_pre_boot_files = True
                    # Restart to apply new boot files
                    self.logger.info("DEBUG Restarting to apply new Zynq boot files")
                    self.transition(Status.powered_off)
                    self.transition(Status.booting_zynq)
                    self.transition(Status.booted_zynq)
                    self.status = Status.powered_off
                    return # Exit here to restart the boot process

                # raise StrategyError("DEBUG Stopping here after Zynq boot files update")

            self.logger.debug("DEBUG Zynq Boot files updated")


        elif status == Status.update_virtex_boot_files:
            self.transition(Status.update_zynq_boot_files)
            self.target.activate(self.shell)
            address = self.shell.get_ip_addresses(self.ethernet_interface)
            assert address, f"No IP address found on {self.ethernet_interface}"
            ip = str(address[0].ip)
            self.target.deactivate(self.shell)

            # Check the same as SSHDriver
            if self.ssh.networkservice.address == ip:
                self.logger.debug("DEBUG IP address matches between ShellDriver and SSHDriver")
                self.logger.debug(f"Changing SSHDriver IP from {self.ssh.networkservice.address} to {ip}")
                self.ssh.networkservice.address = ip

            if not self._copied_post_boot_files:
                if self.post_boot_boot_files:
                    self.target.activate(self.ssh)
                    print(self.post_boot_boot_files)
                    for local_path, remote_path in self.post_boot_boot_files.items():
                        if os.path.isfile(local_path) is False:
                            raise StrategyError(f"Local boot file {local_path} does not exist")
                        folder_in_boot_path = '/'.join(remote_path.split('/')[:-1])
                        if folder_in_boot_path and folder_in_boot_path != '/boot':
                            self.ssh.run(f"mkdir -p {folder_in_boot_path}")
                        self.logger.debug(f"DEBUG Uploading Virtex boot file {local_path} to {remote_path}")
                        self.ssh.put(local_path, remote_path)
                    self.target.deactivate(self.ssh)
                    self._copied_post_boot_files = True

                # raise StrategyError("DEBUG Stopping here after Virtex boot files update")


            self.logger.debug("DEBUG Virtex Boot files updated")

        elif status == Status.trigger_selmap_boot:
            self.transition(Status.update_virtex_boot_files)

            self.target.activate(self.ssh)
            self.ssh.run("cd /boot/ci && ./selmap_dtbo.sh -d vu11p.dtbo -b vu11p.bin")
            self.target.deactivate(self.ssh)

        elif status == Status.wait_for_virtex_boot:
            self.transition(Status.trigger_selmap_boot)
            self.shell.bypass_login = True
            self.target.activate(self.shell)
            # Check for device to register
            found_device = False
            for t in range(30):
                self.logger.info(f"DEBUG Checking for IIO JESD device... {t+1}/30")
                stdout, stderr, returncode = self.shell.run(f"iio_attr -d {self.iio_jesd_driver_name} jesd204_fsm_state", timeout=4)
                if "could not find device" in stdout:
                    self.logger.info(f"DEBUG IIO JESD device not found yet")
                else:
                    self.logger.info(f"DEBUG IIO JESD device found {stdout}, {stderr}, {returncode}")
                    found_device = True
                    break
                time.sleep(1)

            if not found_device:
                raise StrategyError("Virtex did not boot successfully within timeout")

            jesd_finished = False
            for t in range(120):
                self.logger.info(f"DEBUG Checking for JESD to finish... {t+1}/30")
                stdout, stderr, returncode = self.shell.run(f"iio_attr -d {self.iio_jesd_driver_name} jesd204_fsm_state", timeout=4)
                if "opt_post_running_stage" in stdout:
                   jesd_finished = True
                   self.logger.info(f"DEBUG JESD Booted fully")
                   break
                else:
                    self.logger.info(f"DEBUG JESD not finished yet: {stdout}, {stderr}, {returncode}")
                time.sleep(1)

            if not jesd_finished:
                raise StrategyError("Virtex JESD did not finish successfully within timeout")

            # Restart IIOD
            self.shell.run("systemctl restart iiod.service")

            self.shell.bypass_login = False
            self.target.deactivate(self.shell)
            self.logger.debug("DEBUG Virtex Booted")


        elif status == Status.shell:
            self.transition(Status.wait_for_virtex_boot)
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
            raise StrategyError(
                f"no transition found from {self.status} to {status}"
            )
        self.status = status