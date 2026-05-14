"""Smoke test: boot mini2 (ZCU102 + AD9081) to shell and assert the kernel responds.

Consumed by the .github/workflows/hardware-smoke.yml nightly job via the
hw-matrix reusable workflow. Assumes the workflow's acquire-place composite
has already acquired the 'mini2' place on the coordinator.

Run locally with:
    pytest -v --run-hardware --lg-config tests/coordinator/env_remote_mini2.yaml \\
        tests/hw/test_smoke_mini2.py
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.hardware


@pytest.fixture(scope="module")
def in_shell(strategy):
    strategy.transition("shell")
    yield


def test_boot_to_shell(strategy, in_shell):
    """End-to-end: the BootFPGASoC strategy reaches its 'shell' state."""
    assert str(strategy.status).endswith("shell"), (
        f"strategy did not reach shell state; final status={strategy.status}"
    )


def test_shell_responsive(target, in_shell):
    """uname -r on the booted target returns a non-empty kernel version."""
    shell = target.get_driver("ADIShellDriver")
    stdout, _, returncode = shell.run("uname -r")
    assert returncode == 0
    assert stdout, "uname -r returned empty output"
