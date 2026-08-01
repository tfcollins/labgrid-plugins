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

    #: How many times to retry a busy ``pumount`` before the lazy-unmount
    #: fallback.  Each retry syncs and waits ``unmount_retry_delay`` seconds.
    unmount_retries = attr.ib(default=3)
    unmount_retry_delay = attr.ib(default=2.0)

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
        mnt = self._mount_dir()
        if self.mounted:
            if self._is_mountpoint(mnt):
                self.logger.debug("Already mounted; skipping.")
                return
            self.logger.warning("%s is no longer mounted; clearing stale driver state.", mnt)
            self.mounted = False
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
        """Unmount the mass storage device partition.

        A freshly-written USB mass-storage mount is frequently still busy
        when teardown runs (a lingering writer, udev/blkid probe, or the
        kernel flushing the FAT dirty bits), so a bare ``pumount`` races and
        fails with ``target is busy``.  On a shared CI board that stranded
        the place in a broken state.  This retries ``pumount`` a few times
        (syncing + waiting between attempts) and, if the mountpoint is still
        busy, falls back to a lazy unmount so the device is always detached.
        """
        if not self.mounted:
            return
        mnt = self._mount_dir()
        if not self._is_mountpoint(mnt):
            self.logger.info("%s is already unmounted; clearing driver state.", mnt)
            self.mounted = False
            return

        last_exc = None
        for attempt in range(1, self.unmount_retries + 1):
            self._remote_run(["sync"], check=False)
            try:
                self._remote_check(["pumount", self.mount_label])
            except subprocess.CalledProcessError as e:
                last_exc = e
                # It may already be gone (another writer released + something
                # else unmounted it) — re-check before treating as a failure.
                if not self._is_mountpoint(mnt):
                    self.logger.info(
                        "%s unmounted despite pumount error on attempt %d.",
                        mnt,
                        attempt,
                    )
                    self.mounted = False
                    return
                self.logger.warning(
                    "pumount %s busy (attempt %d/%d): %s",
                    self.mount_label,
                    attempt,
                    self.unmount_retries,
                    e,
                )
                if attempt < self.unmount_retries:
                    time.sleep(self.unmount_retry_delay)
                continue
            if not self._is_mountpoint(mnt):
                self.mounted = False
                return
            self.logger.warning(
                "%s still a mount point after pumount (attempt %d/%d).",
                mnt,
                attempt,
                self.unmount_retries,
            )
            if attempt < self.unmount_retries:
                time.sleep(self.unmount_retry_delay)

        # Last resort: a lazy unmount detaches the filesystem as soon as it
        # is no longer busy, so the shared board is never left stranded.
        self.logger.warning(
            "Falling back to lazy unmount of %s after %d busy attempt(s).",
            mnt,
            self.unmount_retries,
        )
        self._remote_run(["sync"], check=False)
        lazy = self._remote_run(["umount", "-l", mnt], check=False)
        if lazy.returncode == 0 and not self._is_mountpoint(mnt):
            self.mounted = False
            return
        # Truly stuck — surface the original pumount error for diagnosis.
        if last_exc is not None:
            self.logger.error("Failed to unmount %s: %s", self.mount_label, last_exc)
            raise last_exc
        raise RuntimeError(f"Unmount failed; {mnt} is still a mount point.")

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
