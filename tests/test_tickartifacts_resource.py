"""Unit tests for the TickArtifacts resource: defaults and field presence."""

from adi_lg_plugins.resources.tickartifacts import TickArtifacts


def _artifacts():
    # labgrid's Resource/BindingMixin takes (target, name) positionally; target=None is fine unbound.
    return TickArtifacts(
        None,
        "tick",
        bitstream_path="/run/tick.bit",
        overlay_dtbo_path="/run/tick.dtbo",
        module_ko_path="/run/axi_timed_command_scheduler.ko",
    )


def test_required_paths_are_stored():
    a = _artifacts()
    assert a.bitstream_path == "/run/tick.bit"
    assert a.overlay_dtbo_path == "/run/tick.dtbo"
    assert a.module_ko_path == "/run/axi_timed_command_scheduler.ko"


def test_target_side_defaults():
    a = _artifacts()
    assert a.firmware_name == "tick.bit"
    assert a.overlay_name == "tick"
    assert a.remote_dir == "/tmp/tick"
