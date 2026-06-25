"""Importing adi_lg_plugins must register all Tick drivers/resource/strategy."""

from labgrid.factory import target_factory

import adi_lg_plugins  # noqa: F401  (import side effects register the classes)


def test_tick_classes_are_registered():
    assert "TickArtifacts" in target_factory.resources
    for name in (
        "TickFpgaManagerDriver",
        "TickOverlayDriver",
        "TickModuleDriver",
        "BootTickFPGASSH",
    ):
        assert name in target_factory.drivers, name
