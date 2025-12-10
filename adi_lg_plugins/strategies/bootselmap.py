"""Strategy to boot SelMap based dual FPGA design."""
import enum
import time

import attr

from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError, never_retry
from labgrid.factory import target_factory

class Status(enum.Enum):
    unknown = 0
    powered_off = 1
    booting_zynq = 2
    booted_zynq = 3
    update_virtex_boot_files = 4
    trigger_selmap_boot = 5
    wait_for_virtex_boot = 6
    booted_virtex = 7
    shell = 8
    soft_off = 9

@target_factory.reg_driver
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
            self.shell.console.expect(self.hostname)  # Adjust prompt as needed
            self.shell.bypass_login = False
            self.target.deactivate(self.shell)
            self.logger.debug("DEBUG Zynq Booted")
        elif status == Status.update_virtex_boot_files:
            self.transition(Status.booted_zynq)
            self.target.activate(self.shell)
            address = self.shell.get_ip_addresses("eth0")
            assert address, "No IP address found on eth0"
            ip = str(address[0].ip)
            self.target.deactivate(self.shell)

            # Check the same as SSHDriver
            assert self.ssh.networkservice.address == ip, "IP address mismatch between ShellDriver and SSHDriver"

            self.target.activate(self.ssh)
            self.ssh.wait_for_connection()

            # self.ssh.put()



            self.logger.debug("DEBUG Virtex Boot files updated")


        elif status == Status.shell:
            self.transition(Status.booted)
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