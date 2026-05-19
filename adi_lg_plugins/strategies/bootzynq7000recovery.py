"""Strategy to recover a Zynq-7000 board with a corrupted SD card.

Bootstraps U-Boot directly into DDR over JTAG, TFTP-loads a recovery Linux
(kernel + DTB + initramfs — rootfs in RAM), then streams a fresh SD-card
image over HTTP and ``dd``s it to ``/dev/mmcblk0``.

The strategy automates the host-side wiring by default. Minimal caller
responsibilities:

- ``ps7_init.tcl`` + ``u-boot.elf`` (+ optional FSBL) at host paths readable
  by xsdb. Extract these from a known-good ``BOOT.BIN`` with
  ``bootgen -arch zynq -read BOOT.BIN``.
- **FPGA bitstream** at ``bitstream_path``. Required when the recovery kernel
  has device-tree nodes for FPGA-fabric peripherals (``axi_clkgen``,
  ``axi_jesd204_*``, ``axi_adxcvr``, custom IPs). With an unprogrammed FPGA,
  the kernel's AXI probe of those addresses hangs indefinitely. The driver
  re-flashes the bitstream over JTAG before downloading U-Boot.
- Recovery ``kernel`` + ``dtb`` inside the ``TFTPServerResource.root``
  directory.
- The SD image to flash, either as a local path (``sd_image_path``, served
  automatically) or a pre-existing URL (``sd_image_url``).

Per-board file setup:

- ADI's "Kuiper-full" SD image is multi-board and ships BOOT.BIN /
  uImage / devicetree under named subdirectories (one per board); the
  FAT root is empty of those files. The Zynq-7000 BootROM only reads
  ``BOOT.BIN`` at the root, so a bare ``dd`` of Kuiper-full produces a
  silent boot failure.
- Setting ``board_variant=<subdir-name>`` (e.g.
  ``zynq-zc706-adv7511-adrv937x``) tells the strategy to mount FAT
  partition 1 after the dd, copy the per-board files up to the root,
  sync, and unmount — all from inside the recovery initramfs.
- For images that already have ``BOOT.BIN`` at root, leave
  ``board_variant=None``.
- For tweaks that don't fit the board-variant pattern, add entries to
  ``post_flash_commands`` (a list of shell snippets run sequentially).

Automation defaults (``auto_build_initramfs=True``, ``auto_serve_http=True``):

- The recovery ``uInitrd.recovery`` is auto-built into the TFTP root on
  first run via :func:`adi_lg_plugins.recovery.build_recovery_initramfs`
  (cross-compiling a static busybox once and caching it under
  ``recovery_cache_dir``; supply ``busybox_static_path`` to skip the
  compile entirely).
- The SD image at ``sd_image_path`` is served over HTTP on
  ``http_serve_port`` (ephemeral by default) for the lifetime of the
  ``sd_flash_done`` phase; the URL is composed using the local routable
  IP and substituted into the recovery command.

Set either knob to ``False`` for fully-explicit mode where the caller
hand-stages every artifact and runs their own HTTP server.

See ``examples/zynq7000_recovery/`` for a working per-board YAML.
"""

import enum
import os
import time

import attr
from labgrid.factory import target_factory
from labgrid.step import step
from labgrid.strategy import Strategy, StrategyError, never_retry

# Pulled in lazily inside the auto-build path to keep import cost low.
# Re-exported here as a module-level constant only because the strategy
# attribute uses it as a default sentinel.
_DEFAULT_BUSYBOX_URL = "https://busybox.net/downloads/busybox-1.36.1.tar.bz2"


class Status(enum.Enum):
    """Boot strategy state machine states for the SD recovery flow."""

    unknown = 0
    powered_off = 1
    powered_on = 2
    jtag_bootstrap = 3
    uboot_prompt = 4
    tftp_recovery_kernel = 5
    linux_recovery = 6
    sd_flash_done = 7
    soft_off = 8
    # Optional post-flash check: cold-cycle, let BootROM read the
    # freshly-flashed SD, wait for the normal Kuiper login prompt.
    sd_boot_verified = 9
    # Normal-CI boot path for boards whose MIO boot-mode strap is set to
    # JTAG: cold-cycle, JTAG-bootstrap U-Boot, drive U-Boot to fatload
    # kernel+dtb from SD, bootm. No recovery cascade — assumes the SD is
    # already populated (caller has run sd_flash_done previously, or the
    # board has a known-good image). Reuses the retry-wrapped JTAG load
    # and the SD-boot drive-out logic from sd_boot_verified.
    shell = 10


@target_factory.reg_driver
@attr.s(eq=False)
class BootZynq7000JTAGRecovery(Strategy):
    """Recover a Zynq-7000 board with a corrupted SD card.

    Workflow:
        1. Cold-cycle power.
        2. JTAG-bootstrap U-Boot into DDR via xsdb (``ps7_init.tcl`` +
           optional FPGA ``bitstream`` + ``u-boot.elf``).
        3. Interrupt U-Boot autoboot on serial.
        4. TFTP-load recovery kernel/DTB/initramfs; ``bootm`` into RAM-rooted
           Linux.
        5. From Linux userspace, ``wget <sd_image_url> | dd of=/dev/mmcblk0``.
        6. (optional) ``sd_boot_verified``: cold-cycle and confirm the
           freshly-flashed SD boots all the way to a normal login prompt —
           no boot-mode switches change, BootROM just reads the
           freshly-written ``BOOT.BIN`` this time.

    Stop at ``sd_flash_done`` if you just want the flash, or transition all
    the way to ``sd_boot_verified`` to also assert the resulting SD is
    bootable. ``soft_off`` leaves the board powered down regardless.

    Generic across Zynq-7000 boards; board-specific values (memory addresses,
    DTB filename, ``ps7_init.tcl`` path) are all attributes.
    """

    bindings = {
        "power": "PowerProtocol",
        "jtag": "XilinxJTAGDriver",
        "shell": "ADIShellDriver",
        "tftp_server": "TFTPServerResource",
        "tftp_driver": "TFTPServerDriver",
        "ssh": {"SSHDriver", None},
    }

    status = attr.ib(default=Status.unknown)

    # JTAG bootstrap inputs (paths on the host that runs xsdb)
    ps7_init_tcl = attr.ib(default=None)
    uboot_elf = attr.ib(default=None)
    fsbl_elf = attr.ib(default=None)
    bitstream_path = attr.ib(default=None)
    a9_target_name = attr.ib(default="*Cortex-A9 MPCore #0")

    # Recovery image inputs (filenames inside tftp_root_folder)
    recovery_kernel = attr.ib(default=None)
    recovery_dtb = attr.ib(default=None)
    recovery_initramfs = attr.ib(default="uInitrd.recovery")
    recovery_login_marker = attr.ib(default="recovery login:")

    # SD flash inputs
    sd_image_url = attr.ib(default=None)
    sd_device = attr.ib(default="/dev/mmcblk0")
    download_cmd_template = attr.ib(default='wget -q -O - "{url}"')

    # Post-flash board-variant copy. ADI's "Kuiper-full" SD image ships per
    # board BOOT.BIN/uImage/devicetree under named subdirectories
    # (zynq-zc706-adv7511-adrv937x, zynqmp-zcu102-rev10-adrv937x, ...);
    # BootROM only reads BOOT.BIN at the FAT root.
    #
    # Two ways to drive the post-dd copy:
    #
    #   simple — all files live under one subdir:
    #     board_variant: "zynq-zc706-adv7511-adrv9371"
    #     board_variant_files: ("BOOT.BIN", "uImage", "devicetree.dtb")  # default
    #
    #   complex — files span multiple subdirs (Kuiper-full ZC706, where
    #   uImage is shared in zynq-common/ and devicetree.dtb is one level
    #   deeper than BOOT.BIN):
    #     board_variant_paths:
    #       BOOT.BIN:       "zynq-zc706-adv7511-adrv937x/BOOT.BIN"
    #       uImage:         "zynq-common/uImage"
    #       devicetree.dtb: "zynq-zc706-adv7511-adrv937x/zynq-zc706-adv7511-adrv9371/devicetree.dtb"
    #
    # When ``board_variant_paths`` is set it takes precedence and the
    # ``board_variant`` / ``board_variant_files`` pair is ignored.
    # When neither is set the post-dd copy is skipped entirely (use for
    # pre-cooked per-board images where BOOT.BIN is already at FAT root).
    board_variant = attr.ib(default=None)
    board_variant_files = attr.ib(default=("BOOT.BIN", "uImage", "devicetree.dtb"))
    board_variant_paths = attr.ib(default=None)  # dict[target, fat_source] | None
    sd_boot_partition = attr.ib(default=1)
    # Mount point inside the recovery initramfs — must exist as an empty
    # dir (the strategy ``mkdir -p`` it first to be safe).
    sd_mount_point = attr.ib(default="/mnt")

    # Arbitrary post-flash shell commands executed in the recovery
    # initramfs after the dd + board_variant copy succeed (one
    # ``shell.run`` per entry, in order). Use for one-off image-shape
    # tweaks that don't fit the board_variant pattern.
    post_flash_commands = attr.ib(factory=list)
    post_flash_timeout = attr.ib(default=120)

    # --- Automation knobs --------------------------------------------------
    # When True (default), the strategy will:
    #   - build the recovery initramfs (cross-compiling busybox once,
    #     cached at ``recovery_cache_dir``) into ``tftp_server.root/
    #     recovery_initramfs`` before the tftp_recovery_kernel phase, if
    #     that file doesn't already exist.
    #   - serve ``sd_image_path`` over HTTP for the lifetime of the
    #     sd_flash_done phase and substitute the URL into the recovery
    #     command, if ``sd_image_url`` isn't already set.
    # Set False for pure-explicit mode where the caller hand-stages the
    # initramfs in the TFTP root and runs their own HTTP server.
    auto_build_initramfs = attr.ib(default=True)
    auto_serve_http = attr.ib(default=True)

    # Used by auto_build_initramfs. Pre-built static ARM busybox if the
    # caller already has one (skips the cross-compile entirely); otherwise
    # the strategy invokes ensure_busybox_static() which compiles + caches.
    busybox_static_path = attr.ib(default=None)
    busybox_source_url = attr.ib(default=None)  # None = library default
    cross_compile = attr.ib(default=None)  # None = autodetect on PATH
    recovery_cache_dir = attr.ib(default=None)  # None = ~/.cache/...

    # Used by auto_serve_http. Local filesystem path to the SD image; the
    # strategy serves its parent directory over HTTP on ``http_serve_port``
    # (0 picks a free ephemeral port). The board reaches back through
    # ``http_serve_address`` — autodetected by routing to the target's
    # IP if None.
    sd_image_path = attr.ib(default=None)
    http_serve_port = attr.ib(default=0)
    http_serve_address = attr.ib(default=None)

    # U-Boot env (Zynq-7000 = arm32: bootm + zImage + uInitrd)
    uboot_prompt = attr.ib(default="zynq-uboot>|U-Boot>|=>")
    kernel_addr = attr.ib(default="0x2080000")
    dtb_addr = attr.ib(default="0x2000000")
    initramfs_addr = attr.ib(default="0x4000000")
    # Default uses ``rdinit=/init`` (the cpio's own ``/init`` script) rather
    # than ``rdinit=/sbin/init``: with an initramfs rootfs the kernel uses
    # ``rootfs`` directly and ``/sbin/init`` symlinks are inconsistent
    # across busybox configurations. No ``root=`` because the kernel uses
    # the unpacked initramfs as rootfs.
    bootargs = attr.ib(default="console=ttyPS0,115200 earlyprintk loglevel=8 rdinit=/init")

    # Robustness
    jtag_bootstrap_retries = attr.ib(default=2)
    wait_for_uboot_prompt_timeout = attr.ib(default=60)
    wait_for_recovery_linux_timeout = attr.ib(default=180)
    wait_for_sd_flash_timeout = attr.ib(default=1800)

    # sd_boot_verified: drive the freshly-flashed SD through a real
    # boot sequence and assert it reaches userspace.
    #
    # The strategy JTAG-loads U-Boot, interrupts autoboot, then has
    # U-Boot ``fatload`` the kernel+dtb from the SD's FAT boot
    # partition and ``bootm`` them. This avoids two real-world snags
    # on Zynq-7000 dev boards:
    #
    #   - boot-mode pins set to JTAG: BootROM doesn't try SD, so a
    #     cold-power-only test produces no UART output regardless of
    #     SD content.
    #   - U-Boot environment configured for TFTP boot: the default
    #     autoboot script doesn't fatload from SD; we drive it
    #     explicitly.
    #
    # The end state still depends on the SD's content (kernel + dtb +
    # rootfs) being correct — the SD is what's actually booted.
    verify_kernel_name = attr.ib(default="uImage")
    verify_dtb_name = attr.ib(default="devicetree.dtb")
    verify_bootargs = attr.ib(
        default=(
            "console=ttyPS0,115200 root=/dev/mmcblk0p2 rw earlyprintk rootfstype=ext4 rootwait"
        )
    )
    verify_boot_login_marker = attr.ib(default="(analog|raspberrypi|kuiper).*login:")
    wait_for_verify_boot_timeout = attr.ib(default=180)

    def __attrs_post_init__(self):
        super().__attrs_post_init__()
        # Stash for the HTTP-serve context manager; populated when the
        # sd_flash_done phase opens its own server (auto_serve_http path).
        self._http_ctx = None
        self.logger.info("BootZynq7000JTAGRecovery strategy initialized")

    def _ensure_recovery_initramfs(self) -> None:
        """Auto-build uInitrd.recovery into the TFTP root if absent.

        Skipped when ``auto_build_initramfs`` is False or the destination
        file already exists. Cross-compiles busybox on first run (cached
        in ``recovery_cache_dir``); subsequent runs are a few seconds.
        """
        if not self.auto_build_initramfs:
            return
        tftp_root = self.tftp_server.root
        target = os.path.join(tftp_root, self.recovery_initramfs)
        if os.path.exists(target):
            self.logger.info("recovery initramfs already staged at %s", target)
            return

        # Local import keeps module load cheap and avoids dragging
        # urllib/tarfile in for non-auto users.
        from adi_lg_plugins.recovery import build_recovery_initramfs
        from adi_lg_plugins.recovery.busybox import ensure_busybox_static

        busybox = self.busybox_static_path or ensure_busybox_static(
            cache_dir=self.recovery_cache_dir,
            source_url=self.busybox_source_url or _DEFAULT_BUSYBOX_URL,
            cross_compile=self.cross_compile,
        )
        self.logger.info("building recovery initramfs at %s (busybox=%s)", target, busybox)
        sizes = build_recovery_initramfs(busybox=busybox, output=target)
        self.logger.info(
            "recovery initramfs ready: cpio=%dB gz=%dB uimage=%dB",
            sizes["cpio"],
            sizes["gz"],
            sizes.get("uimage", 0),
        )

    def _ensure_sd_image_url(self) -> None:
        """Spin up the HTTP server for the local SD image, if needed.

        No-op when ``sd_image_url`` is already set explicitly, or when
        ``auto_serve_http`` is False. Stores the running server in
        ``self._http_ctx`` so ``_teardown_http_server`` can close it on
        soft_off / failure.
        """
        if self.sd_image_url or not self.auto_serve_http:
            return
        if not self.sd_image_path:
            raise StrategyError(
                "BootZynq7000JTAGRecovery: set sd_image_url or sd_image_path, "
                "or disable auto_serve_http"
            )
        if not os.path.isfile(self.sd_image_path):
            raise StrategyError(f"sd_image_path does not exist: {self.sd_image_path}")

        from adi_lg_plugins.recovery.http import local_ip_for, serve_directory

        directory = os.path.dirname(os.path.abspath(self.sd_image_path))
        filename = os.path.basename(self.sd_image_path)
        ctx = serve_directory(directory, port=self.http_serve_port)
        # Entering the context starts the daemon thread; we keep it alive
        # by stashing the ctx manager and __exit__-ing it in teardown.
        _bind, port = ctx.__enter__()
        self._http_ctx = ctx

        # Figure out the IP the board reaches us at. The TFTP server
        # binding gives the lab-side IP already; reuse it so we don't
        # surprise users with a different interface.
        host = self.http_serve_address or self.tftp_server.get_ip() or local_ip_for("8.8.8.8")
        self.sd_image_url = f"http://{host}:{port}/{filename}"
        self.logger.info("serving %s as %s", self.sd_image_path, self.sd_image_url)

    def _teardown_http_server(self) -> None:
        ctx = self._http_ctx
        if ctx is None:
            return
        self._http_ctx = None
        try:
            ctx.__exit__(None, None, None)
        except Exception as e:  # pragma: no cover - cleanup is best-effort
            self.logger.warning("HTTP server teardown raised: %s", e)

    def _resolve_board_variant_paths(self) -> dict[str, str] | None:
        """Return {target_filename: fat_source_path} or None if no copy needed.

        Explicit ``board_variant_paths`` wins. Otherwise expand
        ``board_variant`` + ``board_variant_files`` into a flat
        ``{f: f"{board_variant}/{f}"}`` mapping. Returns ``None`` when
        neither is configured so the caller can skip the copy step.
        """
        if self.board_variant_paths:
            return dict(self.board_variant_paths)
        if self.board_variant:
            return {f: f"{self.board_variant}/{f}" for f in self.board_variant_files}
        return None

    def _build_board_variant_cmd(self, paths: dict[str, str]) -> str:
        """Compose the post-dd Kuiper-multi → root copy one-liner.

        Mounts the FAT boot partition, copies each ``paths[target]``
        source file up to the partition root as ``target``, syncs, and
        unmounts. Emits ``BOARD_VARIANT_COPY_OK`` on success so the
        caller can assert against output rather than just exit code.
        """
        partition = f"{self.sd_device}p{self.sd_boot_partition}"
        mount = self.sd_mount_point
        copies = " && ".join(f'cp "{mount}/{src}" "{mount}/{dst}"' for dst, src in paths.items())
        # The kernel keeps a per-block-device page cache. The post-dd
        # whole-disk write (to ``sd_device``) doesn't invalidate the
        # partition's own cache (``{sd_device}p{N}``) — they're distinct
        # device entities. So even after sync + drop_caches +
        # ``blockdev --flushbufs sd_device``, mounting the partition
        # still sees the pre-dd FAT, ``cp`` updates only that cache,
        # and umount discards everything.
        #
        # The fix: invalidate BOTH the whole-disk and the partition
        # caches, re-read the partition table (which also drops the
        # partitions' buffers), then mount with ``-o sync`` so writes
        # land synchronously regardless of any remaining cache games.
        return (
            f"mkdir -p {mount} && "
            "sync && "
            "echo 3 > /proc/sys/vm/drop_caches 2>/dev/null || true && "
            f"blockdev --flushbufs {self.sd_device} 2>/dev/null || true && "
            f"blockdev --flushbufs {partition} 2>/dev/null || true && "
            f"blockdev --rereadpt {self.sd_device} 2>/dev/null || "
            f"partprobe {self.sd_device} 2>/dev/null || true && "
            "sleep 1 && "
            f"mount -t vfat -o rw,sync {partition} {mount} && "
            f"{copies} && "
            "sync && "
            f"umount {mount} && "
            "sync && "
            f"blockdev --flushbufs {partition} 2>/dev/null || true && "
            f"blockdev --flushbufs {self.sd_device} 2>/dev/null || true && "
            "echo BOARD_VARIANT_COPY_OK"
        )

    def _run_post_flash(self) -> None:
        """Run board-variant copy (if configured) + post_flash_commands."""
        paths = self._resolve_board_variant_paths()
        if paths is not None:
            cmd = self._build_board_variant_cmd(paths)
            self.logger.info(
                "Copying %d board-variant file(s) to FAT root: %s",
                len(paths),
                ", ".join(f"{src} -> {dst}" for dst, src in paths.items()),
            )
            stdout, stderr, returncode = self.shell.run(cmd, timeout=self.post_flash_timeout)
            stdout_str = "\n".join(stdout) if isinstance(stdout, list) else str(stdout)
            stderr_str = "\n".join(stderr) if isinstance(stderr, list) else str(stderr)
            if returncode != 0 or "BOARD_VARIANT_COPY_OK" not in stdout_str:
                raise StrategyError(
                    f"board_variant copy failed (rc={returncode}): {stderr_str or stdout_str}"
                )

        for extra in self.post_flash_commands:
            self.logger.info(f"Post-flash command: {extra}")
            stdout, stderr, returncode = self.shell.run(extra, timeout=self.post_flash_timeout)
            if returncode != 0:
                stderr_str = "\n".join(stderr) if isinstance(stderr, list) else str(stderr)
                stdout_str = "\n".join(stdout) if isinstance(stdout, list) else str(stdout)
                raise StrategyError(
                    f"post_flash_commands entry failed (rc={returncode}): "
                    f"{extra}\n{stderr_str or stdout_str}"
                )

    def _require(self, name: str) -> str:
        """Fetch a required attr or raise StrategyError naming the field."""
        value = getattr(self, name)
        if not value:
            raise StrategyError(f"BootZynq7000JTAGRecovery requires '{name}' to be configured")
        return value

    def _cold_cycle(self) -> None:
        """Off → settle → on. Clears residual board state."""
        self.target.activate(self.power)
        self.power.off()
        time.sleep(5)
        self.power.on()

    def _jtag_load_uboot_with_retry(self) -> None:
        """JTAG-bootstrap U-Boot, retrying with a cold-cycle on failure.

        FT232H / Digilent JTAG enumeration is intermittent right after
        a fresh power-on (the cable's USB descriptor occasionally fails
        to refresh before xsdb queries targets, giving "no targets
        found"). Match the retry behavior of the jtag_bootstrap state
        so callers that drive ``sd_boot_verified`` or ``shell`` survive
        the same transient.
        """
        self.target.activate(self.jtag)
        attempts = int(self.jtag_bootstrap_retries) + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                self.logger.info(f"JTAG bootstrap attempt {attempt}/{attempts}...")
                self.jtag.load_zynq_uboot(
                    ps7_init_tcl=self._require("ps7_init_tcl"),
                    uboot_elf=self._require("uboot_elf"),
                    a9_target_name=self.a9_target_name,
                    bitstream_path=self.bitstream_path,
                    fsbl_elf=self.fsbl_elf,
                )
                return
            except Exception as e:
                last_error = e
                self.logger.error(f"JTAG bootstrap attempt {attempt}/{attempts} failed: {e}")
                if attempt >= attempts:
                    raise StrategyError(f"JTAG bootstrap exhausted retries: {e}") from e
                self.logger.info("Cold-cycling power before retry...")
                self._cold_cycle()
        # Should be unreachable; loop always returns or raises.
        raise StrategyError(f"JTAG bootstrap exhausted retries: {last_error}")

    def _drive_uboot_to_sd_linux(self) -> None:
        """At a JTAG-loaded U-Boot prompt, fatload kernel+dtb from SD and bootm.

        Assumes self.shell is already active and at the U-Boot prompt.
        Waits for ``verify_boot_login_marker`` (Linux login) on success;
        raises StrategyError on timeout.
        """
        partition = f"0:{self.sd_boot_partition}"
        commands = [
            "mmc rescan",
            f"fatload mmc {partition} {self.kernel_addr} {self.verify_kernel_name}",
            f"fatload mmc {partition} {self.dtb_addr} {self.verify_dtb_name}",
            f"setenv bootargs {self.verify_bootargs}",
        ]
        self.logger.info("Driving U-Boot to load kernel/dtb from SD...")
        for cmd in commands:
            self.logger.info(f"U-Boot: {cmd}")
            self.shell.run_uboot(f"{cmd}\n", timeout=60)
            self.shell._check_prompt_uboot()

        bootm = f"bootm {self.kernel_addr} - {self.dtb_addr}"
        self.logger.info(f"Booting from SD: {bootm}")
        self.shell.console.sendline(bootm)
        self.logger.info(
            f"Waiting for SD-boot login marker '{self.verify_boot_login_marker}' "
            f"(timeout {self.wait_for_verify_boot_timeout}s)..."
        )
        try:
            self.shell.console.expect(
                self.verify_boot_login_marker,
                timeout=self.wait_for_verify_boot_timeout,
            )
        except Exception as e:
            captured = b""
            try:
                captured = self.shell.console._expect.before or b""
            except Exception:
                pass
            self.logger.error(
                "SD-boot did not reach the expected login (%d bytes captured).",
                len(captured),
            )
            if captured:
                self.logger.error("UART tail: %r", captured[-1000:])
            raise StrategyError(
                f"SD did not reach the expected login prompt within "
                f"{self.wait_for_verify_boot_timeout}s"
            ) from e

    def _build_sd_flash_cmd(self) -> str:
        """Compose the streaming download | dd one-liner for the recovery shell."""
        sd_image_url = self._require("sd_image_url")
        download_cmd = self.download_cmd_template.format(url=sd_image_url)
        return (
            f'test -b "{self.sd_device}" && '
            f'{download_cmd} | dd of="{self.sd_device}" bs=4M conv=fsync && '
            f"sync && echo SD_FLASH_OK"
        )

    @never_retry
    @step()
    def transition(self, status, *, step):
        if not isinstance(status, Status):
            status = Status[status]

        self.logger.info(f"Transitioning to {status} (Current: {self.status})")

        if status == Status.unknown:
            raise StrategyError(f"can not transition to {status}")

        if status == self.status:
            step.skip("nothing to do")
            return

        if status == Status.powered_off:
            self.target.deactivate(self.shell)
            if self.tftp_driver:
                self.target.deactivate(self.tftp_driver)
            self._teardown_http_server()
            self.target.activate(self.power)
            self.power.off()
            self.logger.info("Device powered off")

        elif status == Status.powered_on:
            self.transition(Status.powered_off)
            self.logger.info("Cold-cycling power...")
            self._cold_cycle()
            self.logger.info("Device powered on")

        elif status == Status.jtag_bootstrap:
            self.transition(Status.powered_on)
            ps7_init_tcl = self._require("ps7_init_tcl")
            uboot_elf = self._require("uboot_elf")

            self.target.activate(self.jtag)
            attempts = int(self.jtag_bootstrap_retries) + 1
            last_error: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    self.logger.info(f"JTAG bootstrap attempt {attempt}/{attempts}...")
                    self.jtag.load_zynq_uboot(
                        ps7_init_tcl=ps7_init_tcl,
                        uboot_elf=uboot_elf,
                        a9_target_name=self.a9_target_name,
                        bitstream_path=self.bitstream_path,
                        fsbl_elf=self.fsbl_elf,
                    )
                    break
                except Exception as e:
                    last_error = e
                    self.logger.error(f"JTAG bootstrap attempt {attempt}/{attempts} failed: {e}")
                    if attempt >= attempts:
                        raise StrategyError(f"JTAG bootstrap exhausted retries: {e}") from e
                    self.logger.info("Cold-cycling power before retry...")
                    self._cold_cycle()
            else:  # pragma: no cover - loop always breaks or raises
                raise StrategyError(f"JTAG bootstrap exhausted retries: {last_error}")
            self.logger.info("U-Boot bootstrapped via JTAG")

        elif status == Status.uboot_prompt:
            self.transition(Status.jtag_bootstrap)
            self.target.activate(self.tftp_driver)
            self.shell.bypass_login = True
            self.target.activate(self.shell)

            attempts = 2
            for attempt in range(1, attempts + 1):
                try:
                    self.logger.info("Waiting for U-Boot autoboot prompt...")
                    self.shell.console.expect(
                        "Hit any key to stop autoboot",
                        timeout=self.wait_for_uboot_prompt_timeout,
                    )
                    break
                except Exception as e:
                    captured = b""
                    try:
                        captured = self.shell.console._expect.before or b""
                    except Exception:
                        pass
                    self.logger.error(
                        "Attempt %d/%d: no autoboot prompt within %ss (%d bytes captured).",
                        attempt,
                        attempts,
                        self.wait_for_uboot_prompt_timeout,
                        len(captured),
                    )
                    if captured:
                        self.logger.error("Captured UART tail: %r", captured[-400:])
                    if attempt >= attempts or len(captured) > 0:
                        raise e
                    self.logger.info("Re-bootstrapping U-Boot via JTAG before retry...")
                    self.target.deactivate(self.shell)
                    self._cold_cycle()
                    self.jtag.load_zynq_uboot(
                        ps7_init_tcl=self.ps7_init_tcl,
                        uboot_elf=self.uboot_elf,
                        a9_target_name=self.a9_target_name,
                        bitstream_path=self.bitstream_path,
                        fsbl_elf=self.fsbl_elf,
                    )
                    self.shell.bypass_login = True
                    self.target.activate(self.shell)

            self.logger.info("Stopping autoboot...")
            self.shell.console.sendline(" ")
            time.sleep(2)
            self._original_prompt = self.shell.prompt
            self.shell.prompt = self.uboot_prompt
            self.shell.console.sendline("\n")
            self.shell._check_prompt_uboot()
            self.logger.info("U-Boot prompt reached")

        elif status == Status.tftp_recovery_kernel:
            self.transition(Status.uboot_prompt)
            kernel = self._require("recovery_kernel")
            dtb = self._require("recovery_dtb")
            initramfs = self._require("recovery_initramfs")
            # Auto-build the initramfs into the TFTP root on first run.
            # No-op when the file already exists or auto_build is off.
            self._ensure_recovery_initramfs()

            commands = [
                "setenv autoload no",
                "dhcp",
                f"setenv serverip {self.tftp_server.get_ip()}",
                f"setenv tftpdstport {self.tftp_driver.resource.port}",
                f"setenv tftpport {self.tftp_driver.resource.port}",
                f"setenv bootargs {self.bootargs}",
                f"tftpboot {self.kernel_addr} {kernel}",
                f"tftpboot {self.dtb_addr} {dtb}",
                f"tftpboot {self.initramfs_addr} {initramfs}",
            ]
            self.logger.info("Configuring U-Boot for recovery TFTP boot...")
            for cmd in commands:
                self.logger.info(f"U-Boot: {cmd}")
                self.shell.run_uboot(f"{cmd}\n", timeout=60)
                self.shell._check_prompt_uboot()

            bootm = f"bootm {self.kernel_addr} {self.initramfs_addr} {self.dtb_addr}"
            self.logger.info(f"Launching recovery kernel: {bootm}")
            self.shell.console.sendline(bootm)

        elif status == Status.linux_recovery:
            self.transition(Status.tftp_recovery_kernel)
            self.logger.info(f"Waiting for recovery login marker '{self.recovery_login_marker}'...")
            self.shell.console.expect(
                self.recovery_login_marker,
                timeout=self.wait_for_recovery_linux_timeout,
            )
            # Restore original prompt and re-activate shell with login.
            if hasattr(self, "_original_prompt"):
                self.shell.prompt = self._original_prompt
            self.shell.bypass_login = False
            self.target.deactivate(self.shell)
            self.target.activate(self.shell)
            self.logger.info("Recovery Linux shell ready")

        elif status == Status.sd_flash_done:
            self.transition(Status.linux_recovery)
            # Stand up an HTTP server for sd_image_path if the caller
            # didn't pre-set sd_image_url. No-op for explicit mode.
            self._ensure_sd_image_url()
            # Inline ``shell.run`` rather than ``shell.run_script`` — the latter
            # pushes the script via XMODEM, which expects a stable post-transfer
            # prompt return that busybox ``rx`` over a raw initramfs console
            # didn't deliver reliably in testing.
            cmd = self._build_sd_flash_cmd()
            self.logger.info(
                f"Streaming SD image to {self.sd_device} (timeout {self.wait_for_sd_flash_timeout}s)..."
            )
            try:
                stdout, stderr, returncode = self.shell.run(
                    cmd, timeout=self.wait_for_sd_flash_timeout
                )
            finally:
                # Always tear down the HTTP server; leaving it dangling
                # would hold the port and block subsequent runs.
                self._teardown_http_server()
            stdout_str = "\n".join(stdout) if isinstance(stdout, list) else str(stdout)
            stderr_str = "\n".join(stderr) if isinstance(stderr, list) else str(stderr)
            if returncode != 0 or "SD_FLASH_OK" not in stdout_str:
                raise StrategyError(
                    f"SD flash failed (rc={returncode}): {stderr_str or stdout_str}"
                )
            # Run board-variant copy + any user post-flash commands. Must
            # happen after the dd succeeds so the freshly-written FAT is
            # what we're mounting / editing.
            self._run_post_flash()
            self.logger.info("SD card reflashed successfully")

        elif status == Status.soft_off:
            self.transition(Status.sd_flash_done)
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
            self._teardown_http_server()
            self.target.activate(self.power)
            self.power.off()
            self.logger.info("Device powered off")

        elif status == Status.sd_boot_verified:
            self.transition(Status.soft_off)
            # Cold-cycle from soft_off; chip is otherwise already off.
            self.logger.info("Cold-cycling for SD-boot verification...")
            self._cold_cycle()

            # JTAG-load U-Boot. Many ADI dev-bench setups leave the
            # boot-mode pins on JTAG, so a cold-power-only test
            # produces zero UART output even with a perfect SD. By
            # using JTAG we always reach a known U-Boot state, and
            # the actual boot below still depends on the SD content.
            self._jtag_load_uboot_with_retry()

            self.shell.bypass_login = True
            self.target.activate(self.shell)
            self.logger.info("Waiting for U-Boot autoboot prompt...")
            self.shell.console.expect(
                "Hit any key to stop autoboot",
                timeout=self.wait_for_uboot_prompt_timeout,
            )
            self.shell.console.sendline(" ")
            time.sleep(2)
            self._original_prompt = self.shell.prompt
            self.shell.prompt = self.uboot_prompt
            self.shell.console.sendline("\n")
            self.shell._check_prompt_uboot()

            # Drive U-Boot to fatload from the SD and bootm. This proves
            # the freshly-flashed SD content is correct: the kernel +
            # dtb come from the SD, and root= points at /dev/mmcblk0p2
            # so the rootfs comes from there too.
            self._drive_uboot_to_sd_linux()
            self.logger.info("SD card boots normally — recovery verified")

        elif status == Status.shell:
            # Normal CI boot path for JTAG-only-strap boards. Cold-cycle,
            # JTAG-bootstrap U-Boot, drive U-Boot to SD-boot Linux, wait
            # for login. Assumes a previously-flashed SD; does NOT cascade
            # through the recovery flow.
            self.transition(Status.powered_off)
            self.logger.info("Cold-cycling power for shell boot...")
            self._cold_cycle()
            self._jtag_load_uboot_with_retry()

            self.shell.bypass_login = True
            self.target.activate(self.shell)
            # Race-tolerant prompt grab: xsdb may return after U-Boot has
            # already passed its autoboot countdown (especially when the
            # board's saved bootcmd is a quick-fail like a TFTP boot with
            # an unreachable server). Send space+CR immediately to break
            # autoboot if still counting, then wait for the U-Boot prompt
            # regardless of whether we caught autoboot or arrived post-fail.
            self.logger.info("Sending break + waiting for U-Boot prompt...")
            self.shell.console.sendline(" ")
            time.sleep(0.5)
            self.shell.console.sendline("")
            self._original_prompt = self.shell.prompt
            self.shell.prompt = self.uboot_prompt
            self.shell.console.expect(
                self.uboot_prompt,
                timeout=self.wait_for_uboot_prompt_timeout,
            )
            self.shell._check_prompt_uboot()

            self._drive_uboot_to_sd_linux()
            # _drive_uboot_to_sd_linux leaves self.shell.prompt set to the
            # U-Boot value (Zynq>) and bypass_login=True from the U-Boot
            # work. Subsequent shell.run() calls would then time out
            # waiting for Zynq> while the board sits at the Linux prompt
            # (root@analog:~#). Mirror linux_recovery's cleanup so the
            # ADIShellDriver does a fresh login + prompt match.
            if hasattr(self, "_original_prompt"):
                self.shell.prompt = self._original_prompt
            self.shell.bypass_login = False
            self.target.deactivate(self.shell)
            self.target.activate(self.shell)
            self.logger.info("Linux up via JTAG-bootstrap + SD-boot")

        else:
            raise StrategyError(f"no transition found from {self.status} to {status}")

        self.status = status
