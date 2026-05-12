"""Hardware tests for the BootZynq7000JTAGRecovery strategy.

Requires:
    --run-hardware
    --lg-env <path to a labgrid YAML that binds BootZynq7000JTAGRecovery>
      (see examples/zynq7000_recovery/lg_zc706_recovery.yaml for the shape
      of that YAML).
    An HTTP server hosting the SD image referenced by ``sd_image_url`` in
    the YAML, e.g. ``python3 -m http.server 8080 --directory <dir>``.

Skipped at collect time when ``--lg-env`` is missing (see conftest.py).

Non-destructive smokes run by default with ``--run-hardware``:
    test_strategy_metadata
    test_jtag_bootstrap_only
    test_uboot_prompt_reached
    test_recovery_initramfs_responsive

The full re-flash + verify exercise is gated behind an additional opt-in
marker ``destructive`` (also requires ``--run-destructive``):
    test_full_sd_flash_e2e

Run all (including destructive):
    nox -s tests -- tests/test_zynq7000_recovery_hw.py \\
        --run-hardware --run-destructive --lg-env <yaml>
"""

import time

import pytest

pytestmark = pytest.mark.hardware


@pytest.fixture(scope="module")
def in_uboot_prompt(strategy):
    """Walk to ``uboot_prompt`` once per module; non-destructive."""
    strategy.transition("uboot_prompt")
    yield
    # Best-effort cleanup; don't fail a test on shutdown.
    try:
        strategy.transition("powered_off")
    except Exception:
        pass


@pytest.fixture(scope="module")
def in_recovery_linux(strategy):
    """Walk to ``linux_recovery`` once per module; non-destructive.

    Strategy is left at the recovery shell so individual tests can poke
    ``ADIShellDriver``. Powers off in teardown.
    """
    strategy.transition("linux_recovery")
    yield
    try:
        strategy.transition("powered_off")
    except Exception:
        pass


def test_strategy_metadata(strategy):
    """Cheap pre-flight: every required attribute is configured."""
    from adi_lg_plugins.strategies.bootzynq7000recovery import Status

    assert strategy.status == Status.unknown
    # Inputs required by every code path.
    assert strategy.ps7_init_tcl, "ps7_init_tcl must be configured in YAML"
    assert strategy.uboot_elf, "uboot_elf must be configured in YAML"
    assert strategy.recovery_kernel, "recovery_kernel must be configured in YAML"
    assert strategy.recovery_dtb, "recovery_dtb must be configured in YAML"
    assert strategy.recovery_initramfs, "recovery_initramfs must be configured in YAML"
    assert strategy.sd_image_url, "sd_image_url must be configured in YAML"


def test_jtag_bootstrap_only(strategy):
    """``jtag_bootstrap`` brings U-Boot up in DDR via xsdb.

    Non-destructive: we never touch the SD card. Verifies the most novel
    piece of new code (XilinxJTAGDriver.load_zynq_uboot end-to-end).
    """
    from adi_lg_plugins.strategies.bootzynq7000recovery import Status

    strategy.transition("jtag_bootstrap")
    assert strategy.status == Status.jtag_bootstrap


def test_uboot_prompt_reached(strategy, in_uboot_prompt):
    """After ``uboot_prompt``, the serial console must be parked at U-Boot.

    Confirms the autoboot interrupt + prompt-regex match logic works for
    this board's U-Boot build.
    """
    from adi_lg_plugins.strategies.bootzynq7000recovery import Status

    assert strategy.status == Status.uboot_prompt


def test_recovery_initramfs_responsive(target, in_recovery_linux):
    """The busybox recovery shell must run basic commands.

    Catches missing applet symlinks (mktemp, rx, base64, …) and confirms
    eth0 came up so the dd phase will have a network path to the image.
    """
    shell = target.get_driver("ADIShellDriver")

    out, _, rc = shell.run("uname -a")
    assert rc == 0, f"uname failed in recovery shell: {out}"
    assert any("Linux" in line for line in out), f"unexpected uname output: {out}"

    out, _, rc = shell.run("ifconfig eth0")
    assert rc == 0, f"ifconfig eth0 failed: {out}"
    assert any("inet addr" in line for line in out), (
        f"eth0 has no IPv4 — DHCP didn't run or interface name differs: {out}"
    )

    # Applets the strategy's dd one-liner actually invokes.
    for applet in ("dd", "wget", "sync"):
        out, _, rc = shell.run(f"which {applet}")
        assert rc == 0 and out, f"recovery rootfs is missing busybox applet: {applet}"


def test_recovery_sd_device_present(target, in_recovery_linux, strategy):
    """The configured ``sd_device`` exists and is a block device."""
    shell = target.get_driver("ADIShellDriver")
    out, _, rc = shell.run(f"test -b {strategy.sd_device} && echo OK")
    assert rc == 0 and any("OK" in line for line in out), (
        f"sd_device {strategy.sd_device} missing from recovery rootfs: {out}"
    )


@pytest.mark.destructive
def test_full_sd_flash_e2e(strategy):
    """Full pipeline through ``sd_flash_done``. **OVERWRITES THE SD CARD.**

    Gated by ``@pytest.mark.destructive`` so it doesn't fire on a routine
    ``--run-hardware`` run. Opt in with ``--run-destructive``.
    """
    from adi_lg_plugins.strategies.bootzynq7000recovery import Status

    t0 = time.time()
    strategy.transition("sd_flash_done")
    elapsed = time.time() - t0

    assert strategy.status == Status.sd_flash_done
    # Sanity check: a real ~10 GB image takes minutes over LAN. Sub-second
    # success means the dd command short-circuited (e.g., sd_device missing
    # but `&&` chain silently passed).
    assert elapsed > 60, (
        f"sd_flash_done returned suspiciously fast ({elapsed:.1f}s) — "
        "real flash takes minutes; check SD_FLASH_OK was actually emitted"
    )


def test_soft_off(strategy):
    """``soft_off`` powers the board down cleanly after a flash."""
    from adi_lg_plugins.strategies.bootzynq7000recovery import Status

    strategy.transition("soft_off")
    assert strategy.status == Status.soft_off
