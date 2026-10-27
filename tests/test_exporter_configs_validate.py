"""Unit tests for exporter_configs/validate.py.

validate.py lives outside the installed package (it is run from a checkout),
so it is loaded by path the same way `adi-lg netbox add-hardware` loads it.
"""

from __future__ import annotations

from pathlib import Path

from adi_lg_plugins.tools.netbox import provision

EXPORTER_CONFIGS_DIR = Path(__file__).resolve().parents[1] / "exporter_configs"
validate = provision._load_validate_module(EXPORTER_CONFIGS_DIR)

_GROUP = """\
ZCU102_AD9081:
  NetworkService:
    cls: NetworkService
    address: "10.0.0.5"
"""


def test_validate_config_accepts_double_hash_comments(tmp_path):
    config = tmp_path / "resources.yaml"
    config.write_text("## labgrid line comment\n" + _GROUP)

    assert validate.validate_config(str(config)) == []


def test_validate_config_flags_single_hash_comment_lines(tmp_path):
    """labgrid renders exporter configs with ``#`` as a Jinja line-statement prefix."""
    config = tmp_path / "resources.yaml"
    config.write_text("# Exporter template: ZCU102 SoC\n" + _GROUP)

    issues = validate.validate_config(str(config))

    assert len(issues) == 1
    assert "##" in issues[0]
