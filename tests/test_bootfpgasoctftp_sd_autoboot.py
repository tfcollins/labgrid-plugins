"""Unit tests for the BootFPGASoCTFTP ``sd_autoboot`` mode.

``sd_autoboot`` boards (JTAG-recovery class: no SD mux, SD already imaged
with a bootable Kuiper) JTAG-bootstrap U-Boot and then let the SD autoboot
straight to Linux. The strategy must skip the TFTP-kernel sequence in that
mode and just wait for the Linux login marker.
"""

from unittest.mock import MagicMock

import pytest
from labgrid.strategy import Strategy

from adi_lg_plugins.strategies.bootfpgasoctftp import (
    BootFPGASoCTFTP,
    Status,
    _as_bool,
)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(
        "adi_lg_plugins.strategies.bootfpgasoctftp.time.sleep", lambda *_a, **_kw: None
    )


@pytest.fixture(autouse=True)
def light_post_init(monkeypatch):
    """Construct the strategy without the real KuiperDL/TFTP preload.

    Real labgrid seeds the binding attributes (via ``Target.bind``) before
    ``__attrs_post_init__`` runs and supplies bound drivers. Under bare
    MagicMock construction those bindings don't exist, so reproduce the
    base ``Strategy`` setup (logger/step machinery) and seed the bindings
    to ``None``; the test then sets the mocks it needs.
    """

    def _post_init(self):
        Strategy.__attrs_post_init__(self)
        for name in type(self).bindings:
            if not hasattr(self, name):
                setattr(self, name, None)

    monkeypatch.setattr(BootFPGASoCTFTP, "__attrs_post_init__", _post_init)


def _make_strategy(sd_autoboot=False, **overrides):
    target = MagicMock()

    def bind(item):
        item.target = target

    target.bind.side_effect = bind

    # sd_autoboot goes through the constructor so the attrs converter runs
    # (mirroring how render_env's string tag value reaches the strategy).
    s = BootFPGASoCTFTP(
        target,
        "boot_tftp",
        ps7_init_tcl="/srv/recovery/zc706/ps7_init.tcl",
        uboot_elf="/srv/recovery/zc706/u-boot.elf",
        sd_autoboot=sd_autoboot,
    )

    s.power = MagicMock()
    s.jtag = MagicMock()
    s.shell = MagicMock()
    s.shell.prompt = "root@.*"
    s.tftp_server = MagicMock()
    s.tftp_server.get_ip.return_value = "10.0.0.1"
    s.tftp_driver = MagicMock()
    s.tftp_driver.resource.port = 3069
    s.tftp_driver.resource.root = "/tmp/tftp"
    # No KuiperDLDriver / SSH bound for these unit tests.
    s.kuiper = None
    s.ssh = None

    for k, v in overrides.items():
        setattr(s, k, v)
    return s


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, True),
        (False, False),
        (None, False),
        ("", False),
        ("true", True),
        ("True", True),
        ("  TRUE ", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("0", False),
        ("no", False),
    ],
)
def test_as_bool(value, expected):
    assert _as_bool(value) is expected


def test_sd_autoboot_attr_coerces_string_tag():
    """The attr accepts the rendered string tag value, not just a bool."""
    s = _make_strategy(sd_autoboot="true")
    assert s.sd_autoboot is True
    s2 = _make_strategy(sd_autoboot="")
    assert s2.sd_autoboot is False


def test_sd_autoboot_skips_tftp_and_waits_for_linux():
    """In sd_autoboot mode the booted transition skips the TFTP-kernel
    commands and waits for the Linux login marker instead."""
    s = _make_strategy(sd_autoboot=True, reached_linux_marker="analog")

    s.transition(Status.booted)

    assert s.status == Status.booted
    # JTAG bootstrap still ran (U-Boot loaded into DDR).
    assert s.jtag.load_zynq_uboot.called
    # No TFTP-kernel sequence in sd_autoboot mode.
    assert not s.shell.run_uboot.called
    # Waited for the kernel banner and the Linux login marker.
    expect_args = [c.args[0] for c in s.shell.console.expect.call_args_list]
    assert "Linux" in expect_args
    assert "analog" in expect_args


def test_default_path_still_uses_tftp_boot():
    """Without sd_autoboot the strategy follows the TFTP-kernel path."""
    s = _make_strategy(sd_autoboot=False)
    # Autoboot prompt expect returns an index; the U-Boot prompt branch
    # then drives run_uboot for the TFTP sequence.
    s.shell.console.expect.return_value = 1

    s.transition(Status.booted)

    assert s.status == Status.booted
    assert s.shell.run_uboot.called
