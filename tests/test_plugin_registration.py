"""Guards the upstream-labgrid plugin-registration contract.

Upstream labgrid has no entry-point plugin auto-discovery, so this package
registers its drivers/resources/strategies two ways, both exercised here:

1. ``import adi_lg_plugins`` runs every submodule's ``@reg_driver`` /
   ``@reg_resource`` decorator.
2. A labgrid env YAML with ``imports: [adi_lg_plugins]`` triggers the same
   registration via ``Environment`` (labgrid ``config.get_imports()``).

If either breaks, ADI components stop resolving by name in configs.
"""

from __future__ import annotations

import textwrap

_DRIVERS = [
    "KuiperDLDriver",
    "CloudsmithDLDriver",
    "ADIShellDriver",
    "MassStorageDriver",
    "TFTPServerDriver",
    "BootFPGASoC",
    "BootFPGASoCTFTP",
    "BootFabric",
]
_RESOURCES = ["KuiperRelease", "CloudsmithRelease", "TFTPServerResource", "XilinxDeviceJTAG"]


def test_import_registers_all_components():
    from labgrid.factory import target_factory

    import adi_lg_plugins  # noqa: F401

    missing_d = [n for n in _DRIVERS if n not in target_factory.drivers]
    missing_r = [n for n in _RESOURCES if n not in target_factory.resources]
    assert not missing_d, f"unregistered drivers/strategies: {missing_d}"
    assert not missing_r, f"unregistered resources: {missing_r}"


def test_never_retry_shim_importable():
    # Fork-only decorator must be shimmed locally (not from labgrid).
    from adi_lg_plugins.strategies._compat import never_retry

    assert callable(never_retry)


def test_imports_key_registers_via_environment(tmp_path):
    """A bare Environment honoring `imports:` registers ADI components."""
    from labgrid import Environment
    from labgrid.factory import target_factory

    cfg = tmp_path / "env.yaml"
    cfg.write_text(
        textwrap.dedent(
            """\
            imports:
              - adi_lg_plugins
            targets:
              main:
                drivers: {}
            """
        )
    )
    Environment(str(cfg))  # __attrs_post_init__ runs config.get_imports()
    assert "KuiperDLDriver" in target_factory.drivers
    assert "CloudsmithRelease" in target_factory.resources
