import os
import shutil
import subprocess
import time

import attr

# from labgrid.driver import Driver
from labgrid.driver.common import Driver

# from labgrid.driver.mixin.powerresetmixin import PowerResetMixin
# from labgrid.driver.protocol.powerprotocol import PowerProtocol
# from .powerdriver import PowerResetMixin
# from ..protocol import PowerProtocol
from labgrid.factory import target_factory

# import logging

# from pyvesync import VeSync


@target_factory.reg_driver
@attr.s(eq=False)
class MassStorageDriver(Driver):
    """MassStorageDriver - Driver that manipulates a USB mass storage device.
    This can be used to copy/remove files from/to the device."""

    bindings = {"mass_storage": {"MassStorageDevice"}}

    def __attrs_post_init__(self):
        super().__attrs_post_init__()

        # Verify we have pmount and pumount available on the system
        for tool in ["pmount", "pumount"]:
            if not shutil.which(tool):
                raise RuntimeError(
                    f"{tool} not found in system PATH. Please install it to use MassStorageDriver."
                )

        self.mounted = False

    def __del__(self):
        try:
            self.unmount_partition()
        except Exception:
            pass

    def mount_partition(self):
        """Mount the mass storage device partition to the specified mount point."""
        if self.mounted:
            self.logger.debug("Mass storage device is already mounted, skipping mount.")
            return
        if os.path.ismount(os.path.join("/", "media", "lg_mass_storage")):
            self.logger.debug("Mount point already mounted, skipping mount.")
            self.mounted = True
            return
        device_path = self.mass_storage.path
        if not os.path.exists(device_path):
            raise RuntimeError(f"Mass storage device path {device_path} does not exist.")
        mount_cmd = ["pmount", device_path, "lg_mass_storage"]
        try:
            subprocess.run(mount_cmd, check=True)
            self.logger.debug(f"Mounted {device_path} to lg_mass_storage")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to mount {device_path} to lg_mass_storage: {e}")
            raise

        time.sleep(2)

        # Check if mount was successful
        loc = os.path.join("/", "media", "lg_mass_storage")
        if not os.path.exists(loc):
            raise RuntimeError(f"Mounting {device_path} failed, mount point not found at {loc}.")

        self.mounted = True

    def unmount_partition(self):
        """Unmount the mass storage device partition from the specified mount point."""
        if not self.mounted:
            self.logger.debug("Mass storage device is not mounted, skipping unmount.")
            return
        if not os.path.exists(os.path.join("/", "media", "lg_mass_storage")):
            self.logger.debug("Mount point does not exist, skipping unmount.")
            self.mounted = False
            return
        subprocess.run(["sync"])
        unmount_cmd = ["pumount", "lg_mass_storage"]
        try:
            subprocess.run(unmount_cmd, check=True)
            self.logger.debug("Unmounted lg_mass_storage successfully")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to unmount lg_mass_storage: {e}")
            raise

        if os.path.exists(os.path.join("/", "media", "lg_mass_storage")):
            raise RuntimeError("Unmounting failed, mount point still exists.")

        self.mounted = False

    def copy_file(self, src, dst):
        """Copy a single file to the mass storage device.

        Args:
            src: Source file path on the host system
            dst: Destination path relative to the mass storage mount point
        """
        if not self.mounted:
            raise RuntimeError("Mass storage device is not mounted. Cannot copy file.")

        self.logger.info(f"Copying file {dst} on mass storage device from {src}")
        if not os.path.exists(src):
            self.logger.error(f"Source file {src} does not exist.")
            raise FileNotFoundError(f"Source file {src} does not exist.")

        full_dst_path = os.path.join("/", "media", "lg_mass_storage", dst.lstrip("/"))
        dst_dir = os.path.dirname(full_dst_path)
        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir)
        shutil.copy(src, full_dst_path)
        self.logger.info(f"Copied {src} to {full_dst_path}")

    def update_files(self):
        """Update files on the mass storage device as per file_updates dict."""
        if not self.mounted:
            raise RuntimeError("Mass storage device is not mounted. Cannot update files.")
        for src, dst in self.mass_storage.file_updates.items():
            self.copy_file(src, dst)

    # @Driver.check_active
    # @step()
    # def on(self):
    #     for outlet in self.outlets:
    #         outlet.turn_on()
    #     self.logger.debug("Powered ON via Vesync outlet")

    # @Driver.check_active
    # @step()
    # def off(self):
    #     for outlet in self.outlets:
    #         outlet.turn_off()
    #     self.logger.debug("Powered OFF via Vesync outlet")

    # @Driver.check_active
    # @step()
    # def reset(self):
    #     self.off()
    #     self.logger.debug(
    #         "Waiting %.1f seconds before powering ON", self.vesync_outlet.delay
    #     )
    #     time.sleep(self.vesync_outlet.delay)
    #     self.on()

    # @Driver.check_active
    # @step()
    # def cycle(self):
    #     self.off()
    #     time.sleep(self.vesync_outlet.delay)
    #     self.on()

    # @Driver.check_active
    # @step()
    # def get(self):
    #     return all(outlet.is_on for outlet in self.outlets)
