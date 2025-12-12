import enum
import time
import pathlib

import attr

from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError, never_retry
from labgrid.factory import target_factory

class Status(enum.Enum):
    unknown = 0
    powered_off = 1
    sd_mux_to_host = 2
    update_boot_files = 3
    sd_mux_to_dut = 4
    booting = 5
    booted = 6
    shell = 7
    soft_off = 8

@target_factory.reg_driver
@attr.s(eq=False)
class BootFPGASoC(Strategy):
    bindings = {
        "power": "PowerProtocol",
        "shell": "ADIShellDriver",
        "sdmux": "USBSDMuxDriver",
        'mass_storage': 'MassStorageDriver',
        'image_writer': 'USBStorageDriver',
        "kuiper": {"KuiperDLDriver", None},
    }

    status = attr.ib(default=Status.unknown)
    reached_linux_marker = attr.ib(default="analog")
    update_image = attr.ib(default=False)

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self.logger.info("BootFPGASoC strategy initialized")
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
        elif status == Status.sd_mux_to_host:
            self.transition(Status.powered_off)
            self.target.activate(self.sdmux)
            self.sdmux.set_mode("host")
            time.sleep(5)
            self.logger.debug("DEBUG SD Mounted")
        elif status == Status.update_boot_files:
            self.transition(Status.sd_mux_to_host)
            if self.image_writer and self.update_image:
                self.logger.info("Writing image to mass storage device")
                self.target.activate(self.image_writer)
                from labgrid.driver.usbstoragedriver import Mode
                self.image_writer.write_image(mode=Mode.BMAPTOOL)
                self.target.deactivate(self.image_writer)
                self.logger.info("Image written successfully")

            self.target.activate(self.mass_storage)
            self.mass_storage.mount_partition()
            # self.mass_storage.update_files()
            for boot_file in self.kuiper._boot_files:
                self.mass_storage.copy_file(boot_file, '/')
            self.mass_storage.unmount_partition()
            self.target.deactivate(self.mass_storage)

            self.logger.debug("DEBUG Boot files updated")

        elif status == Status.sd_mux_to_dut:
            self.transition(Status.update_boot_files)
            self.sdmux.set_mode("dut")
            time.sleep(5)
            self.logger.debug("DEBUG SD Muxed to DUT")
        elif status == Status.booting:
            self.transition(Status.sd_mux_to_dut)
            self.target.activate(self.power)
            time.sleep(5)
            self.power.on()
            self.logger.debug("DEBUG Booting...")
        elif status == Status.booted:
            self.transition(Status.booting)
            self.shell.bypass_login = True
            self.target.activate(self.shell)
            # Check kernel start
            self.shell.console.expect("Linux", timeout=30)
            # Check device prompt
            self.shell.console.expect(self.reached_linux_marker, timeout=60)  # Adjust prompt as needed
            self.shell.bypass_login = False
            self.target.deactivate(self.shell)
            self.logger.debug("DEBUG Booted")
        elif status == Status.shell:
            self.transition(Status.booted)
            # self.shell.bypass_login = True
            self.target.activate(self.shell)
            # Post boot stuff...
        elif status == Status.soft_off:
            self.transition(Status.shell)
            try:
                self.shell.sendline("poweroff")
                self.shell.console.expect(".*Power down.*", timeout=30)
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