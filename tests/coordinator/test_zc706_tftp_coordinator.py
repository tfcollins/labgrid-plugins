"""Boot-to-shell coordinator test for zc706-carrier places via TFTP.

Drives ``BootFPGASoCTFTP`` to a Linux shell and runs a ``uname`` health
check, non-destructively, against whichever zc706 place the per-place CI
job acquired (selected by ``LG_PLACE``). Daughter-board agnostic — the
TFTP boot path touches only power, serial/U-Boot, and the kernel/DTB
names, nothing daughter-specific.

Shared session / exporter / target plumbing is in conftest.py.
"""

from __future__ import annotations

import os

import pytest
from conftest import assert_bindings_populated, assert_linux_uname

pytestmark = pytest.mark.hardware


@pytest.fixture(scope="module")
def hw_target(hw_targets):
    place = os.environ.get("LG_PLACE")
    if not place:
        pytest.skip("LG_PLACE not set; CI matrix injects this per place")
    if place not in hw_targets:
        pytest.skip(f"{place!r} not in acquired targets ({sorted(hw_targets)})")
    return hw_targets[place]


@pytest.fixture(scope="module")
def boot_strategy(hw_target):
    return hw_target.get_driver("BootFPGASoCTFTP")


def test_strategy_resolves(boot_strategy):
    """BootFPGASoCTFTP has all required resource bindings."""
    assert_bindings_populated(boot_strategy, ("power", "shell", "tftp_server", "tftp_driver"))


def test_boot_to_shell_runs_uname(hw_target, in_shell):
    """TFTP boot reaches a Linux shell on the zc706."""
    assert_linux_uname(hw_target)
