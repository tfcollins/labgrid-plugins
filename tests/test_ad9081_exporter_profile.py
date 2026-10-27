from pathlib import Path

import pytest
import yaml
from labgrid.remote.config import ResourceConfig

EXAMPLES = (
    Path("examples/lg_ad9081_zcu102_exporter.yaml"),
    Path("examples/lg_ad9081_zcu102_mini2_exporter.yaml"),
)


@pytest.mark.parametrize("config_path", EXAMPLES)
def test_example_loads_in_labgrid_exporter(config_path):
    """labgrid-exporter renders the file as Jinja (``#`` statements, ``##`` comments)."""
    config = ResourceConfig(
        str(config_path), {"env": {}, "isolated": False, "hostname": "h", "name": "n"}
    )

    assert config.data == yaml.safe_load(config_path.read_text())


@pytest.mark.parametrize("config_path", EXAMPLES)
def test_zcu102_ad9081_uses_122p88_mhz_vcxo_profile(config_path):
    document = yaml.safe_load(config_path.read_text())
    resources = next(iter(document.values()))
    release = resources["KuiperRelease"]

    assert release["BOOTBIN_path"].endswith("/m8_l4/BOOT.BIN")
    assert release["device_tree_path"].endswith("/m8_l4/m8_l4_vcxo122p88/system.dtb")
    assert "/m4_l8/" not in release["device_tree_path"]
