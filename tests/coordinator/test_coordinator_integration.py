"""Integration tests against a running labgrid coordinator.

Smoke tier (always runs when the coordinator is reachable on
localhost:20408): spawns a labgrid-exporter subprocess loaded from
tests/integration_exporter.yaml, verifies every plugin resource class
appears across the gRPC link, and checks that drivers can be looked up
on a RemotePlace target without touching real hardware.

Hardware tier (gated by --run-hardware + --lg-config <yaml>): exercises
each driver against the real lab. Skips cleanly without the flags.
"""

from __future__ import annotations

import socket
import subprocess
import time
import uuid
from pathlib import Path

import pytest

COORDINATOR = "127.0.0.1:20408"
TEST_YAML = Path(__file__).parent / "integration_exporter.yaml"

# ---------- helpers ----------


def _coordinator_reachable() -> bool:
    s = socket.socket()
    s.settimeout(1.0)
    try:
        s.connect(("127.0.0.1", 20408))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _lc(*args: str, timeout: float = 10.0) -> str:
    """Run labgrid-client against the coordinator. Returns combined stdout."""
    return subprocess.check_output(
        ["labgrid-client", "-x", COORDINATOR, *args],
        text=True,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )


# ---------- module-level skip + fixtures ----------


pytestmark = pytest.mark.skipif(
    not _coordinator_reachable(),
    reason=f"local labgrid coordinator not reachable at {COORDINATOR} "
    "(start it with: docker compose -f coordinator/docker-compose.yml up -d)",
)


@pytest.fixture(scope="module")
def exporter():
    """Spawn labgrid-exporter against the local coordinator. Yields the
    exporter name. Tears down by terminating the subprocess."""
    name = f"pytest-{uuid.uuid4().hex[:8]}"
    proc = subprocess.Popen(
        ["labgrid-exporter", "-c", COORDINATOR, "-n", name, str(TEST_YAML)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    deadline = time.time() + 15
    seen = False
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read() if proc.stdout else ""
            pytest.fail(f"labgrid-exporter exited early ({proc.returncode}):\n{out}")
        try:
            res = _lc("resources", timeout=3)
            if name in res:
                seen = True
                break
        except subprocess.SubprocessError:
            pass
        time.sleep(0.4)

    if not seen:
        proc.terminate()
        try:
            out, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            out = proc.stdout.read() if proc.stdout else ""
        pytest.fail(
            f"exporter '{name}' never appeared in coordinator within 15s.\n"
            f"--- exporter log: ---\n{out}"
        )

    try:
        yield name
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture
def temp_place(exporter):
    """Create a place with a wildcard match for the test exporter, yield its
    name, and clean up."""
    place = f"pytest-place-{uuid.uuid4().hex[:8]}"
    _lc("-p", place, "create")
    try:
        _lc("-p", place, "add-match", f"{exporter}/test/*")
        yield place
    finally:
        try:
            _lc("-p", place, "release", timeout=5)
        except subprocess.SubprocessError:
            pass
        try:
            _lc("-p", place, "delete", timeout=5)
        except subprocess.SubprocessError:
            pass


# ---------- smoke tier ----------


# Source of truth: pyproject.toml entry points. Hardcoded here so a missing
# entry point shows up as a real test failure, not a silent skip.
PLUGIN_RESOURCE_CLASSES = [
    "VesyncOutlet",
    "MassStorageDevice",
    "KuiperRelease",
    "CyberPowerOutlet",
    "XilinxDeviceJTAG",
    "XilinxVivadoTool",
    "TFTPServerResource",
    "HomeAssistantOutlet",
]
PLUGIN_DRIVER_CLASSES = [
    "VesyncPowerDriver",
    "MassStorageDriver",
    "ADIShellDriver",
    "KuiperDLDriver",
    "CyberPowerDriver",
    "XilinxJTAGDriver",
    "TFTPServerDriver",
    "SoftwareInstallerDriver",
    "HomeAssistantPowerDriver",
]

# Resource classes the exporter yaml provides (smoke verifies every one
# round-trips via gRPC to the coordinator).
## Local-only resources (USBMassStorage) only get a Network* counterpart when
## the underlying hardware is actually present, so they're not in this list.
EXPECTED_REMOTE_RESOURCE_CLASSES = [
    "NetworkService",
    "NetworkSerialPort",
    "NetworkUSBSDMuxDevice",
    "MassStorageDevice",
    "VesyncOutlet",
    "KuiperRelease",
    "CyberPowerOutlet",
    "HomeAssistantOutlet",
    "TFTPServerResource",
]


def test_plugin_entry_points_register():
    """All plugin entry points are loadable + register with target_factory."""
    from labgrid.factory import target_factory

    target_factory.discover_plugins()

    missing_r = [r for r in PLUGIN_RESOURCE_CLASSES if r not in target_factory.resources]
    missing_d = [d for d in PLUGIN_DRIVER_CLASSES if d not in target_factory.drivers]
    assert not missing_r, f"resource entry points failed to register: {missing_r}"
    assert not missing_d, f"driver entry points failed to register: {missing_d}"


def test_exporter_appears_in_coordinator(exporter):
    out = _lc("resources")
    assert exporter in out, f"exporter '{exporter}' missing from:\n{out}"


def test_all_resources_visible_via_grpc(exporter):
    out = _lc("resources")
    missing = [c for c in EXPECTED_REMOTE_RESOURCE_CLASSES if c not in out]
    assert not missing, (
        f"expected resource classes missing from coordinator view:\n"
        f"  missing: {missing}\n"
        f"--- output: ---\n{out}"
    )


def test_can_create_place_match_acquire_release(exporter, temp_place):
    """Round-trip: place creation, match, acquire, release via labgrid-client."""
    out = _lc("places")
    assert temp_place in out

    # Acquire
    _lc("-p", temp_place, "acquire")
    out = _lc("-p", temp_place, "show")
    assert "acquired:" in out
    assert "None" not in out.split("acquired:")[1].splitlines()[0]

    # Release
    _lc("-p", temp_place, "release")


def test_drivers_can_be_constructed_for_their_resources(exporter, temp_place, monkeypatch):
    """For each plugin driver whose target resource exists in the test yaml,
    instantiate the driver against a Target+RemotePlace WITHOUT activating
    (so we exercise binding + class registration, not real hardware)."""
    from labgrid import Target
    from labgrid.factory import target_factory
    from labgrid.resource.remote import RemotePlace

    target_factory.discover_plugins()

    ## RemotePlace reads LG_COORDINATOR from the environment. Pin it to the
    ## local coordinator so the hardware-tier user's LG_COORDINATOR setting
    ## doesn't bleed into the smoke.
    monkeypatch.setenv("LG_COORDINATOR", COORDINATOR)

    _lc("-p", temp_place, "acquire")
    try:
        target = Target("integration")
        RemotePlace(target, name=temp_place)
        # Wait briefly for resources to populate.
        deadline = time.time() + 10
        while time.time() < deadline and not list(target.resources):
            time.sleep(0.2)

        ## Map driver class name -> expected resource class name in the yaml.
        ## Excluded:
        ##   VesyncPowerDriver / HomeAssistantPowerDriver — perform real
        ##     network I/O in __attrs_post_init__, so constructing them
        ##     without live credentials throws. Class registration is still
        ##     covered by test_plugin_entry_points_register; live behaviour
        ##     belongs to the hardware tier.
        ##   ADIShellDriver, XilinxJTAGDriver, SoftwareInstallerDriver — bind
        ##     to combinations not represented in the smoke yaml.
        driver_to_resource = {
            "CyberPowerDriver": "CyberPowerOutlet",
            "KuiperDLDriver": "KuiperRelease",
            "MassStorageDriver": "MassStorageDevice",
            "TFTPServerDriver": "TFTPServerResource",
        }

        resource_classnames = {type(r).__name__ for r in target.resources}
        results = {}
        for driver_name, expected_resource in driver_to_resource.items():
            if not any(expected_resource in cls for cls in resource_classnames):
                results[driver_name] = "SKIP (resource not in target)"
                continue
            try:
                drv_cls = target_factory.drivers[driver_name]
                drv_cls(target, name=None)
                results[driver_name] = "OK"
            except Exception as e:
                results[driver_name] = f"FAIL: {type(e).__name__}: {e}"

        failures = {k: v for k, v in results.items() if v.startswith("FAIL")}
        assert not failures, "Drivers failed to construct against their resources:\n" + "\n".join(
            f"  {k}: {v}" for k, v in results.items()
        )
    finally:
        _lc("-p", temp_place, "release")


@pytest.mark.hardware
def test_vesync_get_toggle_restore(hw_target):
    """Read state, toggle once, verify, restore."""

    drv = hw_target.get_driver("VesyncPowerDriver")
    initial = bool(drv.get())
    try:
        if initial:
            drv.off()
        else:
            drv.on()
        time.sleep(2)
        assert bool(drv.get()) != initial
    finally:
        if initial:
            drv.on()
        else:
            drv.off()


@pytest.mark.hardware
def test_sdmux_get_switch_restore(hw_target):
    """Read mode, flip to a different mode, restore. Skips if the SD mux
    backend isn't reachable (e.g., the exporter isn't on a host with the
    `usbsdmux` binary or the physical mux board)."""

    try:
        drv = hw_target.get_driver("USBSDMuxDriver")
    except Exception as e:
        pytest.skip(f"no USBSDMuxDriver in hw_target: {e}")
    try:
        initial = drv.get_mode()
    except subprocess.CalledProcessError as e:
        pytest.skip(f"sd mux backend unreachable on exporter: {e.stderr or e}")
    other = "host" if initial != "host" else "dut"
    try:
        drv.set_mode(other)
        time.sleep(1)
        assert drv.get_mode() == other
    finally:
        drv.set_mode(initial)


@pytest.mark.hardware
def test_serial_console_writes_and_reads(hw_target):
    """Open ConsoleProtocol, send a CR, expect any byte back within 3s."""

    try:
        drv = hw_target.get_driver("ConsoleProtocol")
    except Exception as e:
        pytest.skip(f"no ConsoleProtocol driver: {e}")
    drv.write(b"\r")
    deadline = time.time() + 3
    got = b""
    while time.time() < deadline:
        chunk = drv.read(timeout=0.5)
        if chunk:
            got += chunk
            break
    assert got, "no bytes received from serial within 3s"


@pytest.mark.hardware
def test_ssh_uname_via_adi_shell(hw_target):
    """Run `uname -a` over ADIShellDriver."""

    try:
        drv = hw_target.get_driver("ADIShellDriver")
    except Exception as e:
        pytest.skip(f"no ADIShellDriver: {e}")
    out, _err, exitcode = drv.run("uname -a")
    assert exitcode == 0, f"uname failed: {_err}"
    assert any("Linux" in line for line in out), out


@pytest.mark.hardware
def test_kuiper_release_metadata_only(hw_target):
    """Instantiate KuiperDLDriver and confirm it can resolve the release
    metadata. Does NOT trigger a full download."""

    try:
        hw_target.get_driver("KuiperDLDriver")
    except Exception as e:
        pytest.skip(f"no KuiperDLDriver: {e}")
    # The driver exposes the configured release version on its bound resource;
    # accessing it shouldn't perform IO.
    res = next(r for r in hw_target.resources if type(r).__name__ == "KuiperRelease")
    assert res.release_version, "KuiperRelease.release_version is empty"


@pytest.mark.hardware
def test_mass_storage_resource_bound(hw_target):
    """Confirm the MassStorageDevice resource was published by the exporter
    and is bound to the target. The configured /dev path lives on the
    exporter host, not the test runner, so we don't os.path.exists it
    locally — we just verify the resource is reachable across the gRPC
    link with the expected attributes."""

    res = next(
        (r for r in hw_target.resources if type(r).__name__ == "MassStorageDevice"),
        None,
    )
    if res is None:
        pytest.skip("no MassStorageDevice in hw_target")
    assert res.path, "MassStorageDevice.path is empty"
    assert res.avail or res.avail is False, "resource availability unset"
