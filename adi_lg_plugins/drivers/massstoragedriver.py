import os
import shutil
import subprocess
import time

import attr
from labgrid.driver.common import Driver
from labgrid.factory import target_factory

from ._remote import RemoteExecMixin


@target_factory.reg_driver
@attr.s(eq=False)
class MassStorageDriver(RemoteExecMixin, Driver):
    """Mount and copy files to a USB mass storage device.

    Supports both local-only (test runner == exporter) and remote-exporter
    bindings. When the bound resource is proxied from a coordinator,
    pmount/pumount/mkdir run on the exporter host and file copies are staged
    there over a single reused ssh connection (see :class:`RemoteExecMixin`).

    Specify `partition` when the bound resource points at a whole block
    device (e.g. /dev/sdb) rather than a specific partition; its value
    is the absolute partition path on the exporter host — a raw device
    (/dev/sdb1) or a stable symlink (/dev/disk/by-partuuid/...).
    """

    bindings = {
        "mass_storage": {"MassStorageDevice"},
    }

    # RemoteExecMixin: the resource that locates the exporter host.
    _remote_binding = "mass_storage"

    partition = attr.ib(
        default=None,
        validator=attr.validators.optional(attr.validators.instance_of(str)),
    )
    mount_label = attr.ib(default="lg_mass_storage")

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        self.mounted = False

    def __del__(self):
        try:
            self.unmount_partition()
        except Exception:
            pass

    def _device_path(self):
        return self.partition or self.mass_storage.path

    def _mount_dir(self):
        return f"/media/{self.mount_label}"

    def _path_exists(self, path):
        return self._remote_run(["test", "-e", path]).returncode == 0

    def _is_mountpoint(self, path):
        return self._remote_run(["mountpoint", "-q", path]).returncode == 0

    def mount_partition(self):
        """Mount the configured partition at /media/<mount_label>."""
        if self.mounted:
            self.logger.debug("Already mounted; skipping.")
            return
        mnt = self._mount_dir()
        if self._is_mountpoint(mnt):
            self.logger.debug(f"{mnt} already mounted; treating as mounted.")
            self.mounted = True
            return
        device_path = self._device_path()
        if not self._path_exists(device_path):
            raise RuntimeError(f"Mass storage device path {device_path} does not exist.")
        try:
            self._remote_check(["pmount", device_path, self.mount_label])
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to mount {device_path}: {e}")
            raise
        time.sleep(2)
        if not self._is_mountpoint(mnt):
            raise RuntimeError(f"Mounting {device_path} failed; {mnt} is not a mount point.")
        self.logger.debug(f"Mounted {device_path} at {mnt}")
        self.mounted = True

    def unmount_partition(self):
        """Unmount the mass storage device partition."""
        if not self.mounted:
            return
        mnt = self._mount_dir()
        self._remote_run(["sync"], check=False)
        try:
            self._remote_check(["pumount", self.mount_label])
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to unmount {self.mount_label}: {e}")
            raise
        if self._is_mountpoint(mnt):
            raise RuntimeError(f"Unmount failed; {mnt} is still a mount point.")
        self.mounted = False

    def copy_file(self, src, dst):
        """Copy a local file onto the mass storage device.

        Args:
            src: source file path on the test runner host.
            dst: destination path relative to the mount point.
        """
        if not self.mounted:
            raise RuntimeError("Mass storage device is not mounted. Cannot copy file.")
        if not os.path.exists(src):
            raise FileNotFoundError(f"Source file {src} does not exist.")
        full_dst = os.path.join(self._mount_dir(), dst.lstrip("/"))
        dst_dir = os.path.dirname(full_dst)
        self._remote_check(["mkdir", "-p", dst_dir])
        if self._is_remote:
            self._remote_put(src, full_dst)
        else:
            shutil.copy(src, full_dst)
        self.logger.info(f"Copied {src} to {full_dst}")

    def update_files(self):
        """Batch-copy files listed in mass_storage.file_updates (local-only path mapping)."""
        if not self.mounted:
            raise RuntimeError("Mass storage device is not mounted. Cannot update files.")
        for src, dst in self.mass_storage.file_updates.items():
            self.copy_file(src, dst)
