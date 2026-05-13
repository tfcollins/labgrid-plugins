"""Coordinator-tier hardware smoke for zc706-tagged places.

Confirms the per-place CI job can acquire its assigned place via the
coordinator and that labgrid loads the env. Does NOT exercise
BootZynq7000JTAGRecovery itself: that strategy requires local xsdb +
direct JTAG/serial wiring, not a coordinator RemotePlace.

The full SD-recovery flow is exercised by
``tests/test_zynq7000_recovery_hw.py`` against
``examples/zynq7000_recovery/lg_zc706_recovery.yaml`` on a host that
owns the JTAG cable.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.hardware


@pytest.fixture(scope="module")
def hw_target(hw_targets):
    place = os.environ.get("LG_PLACE")
    if not place:
        pytest.skip("LG_PLACE not set; CI matrix injects this per place")
    if place not in hw_targets:
        pytest.skip(f"{place!r} not in acquired targets ({sorted(hw_targets)})")
    return hw_targets[place]


def test_place_acquired_via_coordinator(hw_target):
    """The place was acquired and labgrid produced a Target object."""
    assert hw_target is not None


def test_serial_driver_resolvable(hw_target):
    """The remote SerialPort surfaced as a SerialDriver binding.

    Catches exporter-side misconfigurations where the place has no
    serial resource exposed, which would block the real recovery flow.
    """
    driver = hw_target.get_driver("SerialDriver", activate=False)
    assert driver is not None, "SerialDriver did not resolve on the place"
