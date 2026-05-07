"""Hardware smoke test for the ReflashVPK180SD strategy.

Requires --run-hardware and a labgrid YAML with a fully-wired VPK180 target:
power, sc_shell + target_shell (ADIShellDriver), kuiper (KuiperDLDriver), and
tftp (TFTPServerDriver). QSPI must already contain a bootable rescue image —
see the strategy docstring for the one-time provisioning procedure.
"""

import pytest

pytestmark = pytest.mark.hardware


def test_full_reflash(strategy):
    """End-to-end: powered_off → done. Verifies the SD card was rewritten."""
    from adi_lg_plugins.strategies.reflashvpk180sd import Status

    strategy.transition("done")
    assert strategy.status == Status.done
    assert strategy.boot_log, "boot_log should capture UART output across phases"
