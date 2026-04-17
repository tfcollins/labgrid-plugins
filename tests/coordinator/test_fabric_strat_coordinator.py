"""BootFabric strategy exercised against the 'nuc' remote place.

Shared session / exporter / target plumbing is in conftest.py.
"""

from __future__ import annotations

import pytest
from conftest import assert_bindings_populated, assert_linux_uname

pytestmark = pytest.mark.hardware


@pytest.fixture(scope="module")
def hw_target(hw_targets):
    if "nuc" not in hw_targets:
        pytest.skip("nuc place not available in this session")
    return hw_targets["nuc"]


@pytest.fixture(scope="module")
def boot_strategy(hw_target):
    return hw_target.get_driver("BootFabric")


def test_strategy_resolves(boot_strategy):
    """BootFabric has its required resource bindings."""
    assert_bindings_populated(boot_strategy, ("jtag",))


def test_boot_to_shell_runs_uname(hw_target, in_shell):
    """Full Fabric boot (via JTAG bitstream + kernel) reaches Linux shell."""
    assert_linux_uname(hw_target)
