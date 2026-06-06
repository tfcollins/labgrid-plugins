"""Hardware verification for remote (coordinator) driver execution.

These prove the refactored host-side drivers actually drive the exporter with
**zero manual SSH** when a client acquires the place through a coordinator.
Point ``--lg-config`` at a *RemotePlace* env (not a runner-local exporter) so
the remote code path (``extra['proxy']`` -> sshmanager -> staged file on the
exporter) is the one exercised end-to-end:

    nox -s tests -- --run-hardware --lg-config <remote_place_env.yaml> \
        tests/test_remote_exec_hw.py

Hardware scope: AD9081 + ZCU102 only. Do NOT target Versal/VPK180 (shelved).
Each test skips cleanly when the acquired place lacks the relevant driver.
"""

import os
import subprocess
import tempfile

import pytest
from labgrid import Environment

# Boards that must never be exercised by this suite (chronic wedge issues).
_FORBIDDEN_HINTS = ("vpk180", "versal")


@pytest.fixture
def target(lg_config):
    if not lg_config:
        pytest.skip("No labgrid config provided via --lg-config")
    env = Environment(lg_config)
    target = env.get_target("main")
    name = (getattr(target, "name", "") or "").lower()
    if any(h in name for h in _FORBIDDEN_HINTS):
        pytest.skip(f"Refusing to run on shelved board: {target.name}")
    return target


def _get_driver(target, name):
    try:
        drv = target.get_driver(name)
    except Exception:
        pytest.skip(f"Place has no {name}")
    target.activate(drv)
    return drv


@pytest.mark.hardware
class TestMassStorageRemote:
    """Mount + stage a file on the exporter and read it back over one ssh conn."""

    def test_copy_file_round_trips_on_exporter(self, target):
        drv = _get_driver(target, "MassStorageDriver")
        if not drv._is_remote:
            pytest.skip("MassStorageDriver bound to a local resource; not a remote test")

        marker = "adi-remote-exec-verify-7f3a"
        rel_dst = "adi_remote_exec_verify.txt"
        drv.mount_partition()
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
                f.write(marker)
                src = f.name
            try:
                drv.copy_file(src, rel_dst)
                remote_path = os.path.join(drv._mount_dir(), rel_dst)
                # Read it back ON THE EXPORTER over the reused connection.
                res = subprocess.run(
                    drv._remote_prefix() + ["cat", remote_path],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                assert res.returncode == 0, res.stderr
                assert marker in res.stdout
            finally:
                os.unlink(src)
        finally:
            drv.unmount_partition()


@pytest.mark.hardware
class TestXilinxJTAGRemote:
    """Stage a generated TCL to the exporter and run it via xsdb remotely."""

    def test_connect_disconnect_over_remote_xsdb(self, target):
        drv = _get_driver(target, "XilinxJTAGDriver")
        if not drv._is_remote:
            pytest.skip("XilinxJTAGDriver bound to a local resource; not a remote test")

        # connect_jtag raises ExecutionError on a non-zero xsdb exit; reaching
        # the end means the staged TCL executed on the exporter.
        drv.connect_jtag()
        drv.disconnect_jtag()
