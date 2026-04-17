"""BootFPGASoC strategy exercised against the 'mini2' remote place.

Shared session / exporter / target plumbing is in conftest.py.
"""

from __future__ import annotations

import time

import pytest
from conftest import assert_bindings_populated, assert_linux_uname

pytestmark = pytest.mark.hardware


@pytest.fixture(scope="module")
def hw_target(hw_targets):
    print("Available hardware targets:", hw_targets)
    if "mini2" not in hw_targets:
        pytest.skip("mini2 place not available in this session")
    return hw_targets["mini2"]


@pytest.fixture(scope="module")
def boot_strategy(hw_target):
    return hw_target.get_driver("BootFPGASoC")


def test_strategy_resolves(boot_strategy):
    """BootFPGASoC has all required resource bindings."""
    assert_bindings_populated(boot_strategy, ("power", "shell", "sdmux", "mass_storage", "kuiper"))


def test_boot_to_shell_runs_uname(hw_target, in_shell):
    """Full SoC boot (via SD card refresh) reaches Linux shell."""
    assert_linux_uname(hw_target)


def test_boot_to_shell_eth0_has_ip(hw_target, in_shell):
    """eth0 acquires an IPv4 address within 20s post-boot.

    Query eth0 directly (not via default-route lookup) since DHCP finishes
    asynchronously after userspace comes up and the default route may not
    yet be installed.
    """
    shell = hw_target.get_driver("ADIShellDriver")
    deadline = time.time() + 20
    last_err = None
    while time.time() < deadline:
        try:
            addresses = shell.get_ip_addresses(device="eth0")
        except Exception as e:
            last_err = e
            time.sleep(1)
            continue
        if addresses:
            return
        last_err = "no IP addresses on eth0 yet"
        time.sleep(1)
    pytest.fail(f"eth0 did not acquire an IP within 20s; last: {last_err}")
