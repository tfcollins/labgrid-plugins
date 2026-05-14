"""Tests for adi_lg_plugins.hw_ci.schema.validate_place."""

from __future__ import annotations

import pytest

from adi_lg_plugins.hw_ci.schema import (
    KNOWN_STRATEGIES,
    Place,
    PlaceValidationError,
    validate_place,
)

# A fixed strategy set so these tests don't depend on which Boot* classes
# happen to be registered today.
STRATS = {"BootFPGASoC", "BootFabric"}


def _raw(name="mini2", **tags):
    return {"name": name, "tags": dict(tags), "acquired": None}


def test_happy_path_dict_tags():
    p = validate_place(
        _raw(
            **{
                "carrier": "zcu102",
                "daughter-board": "ad9081",
                "boot-strategy": "BootFPGASoC",
            }
        ),
        known_strategies=STRATS,
    )
    assert isinstance(p, Place)
    assert p.name == "mini2"
    assert p.carrier == "zcu102"
    assert p.daughter_board == "ad9081"
    assert p.boot_strategy == "BootFPGASoC"
    assert p.hdl_config is None
    assert p.is_acquired is False


def test_optional_hdl_config_and_extras():
    raw = _raw(
        **{
            "carrier": "zcu102",
            "daughter-board": "ad9081",
            "boot-strategy": "BootFPGASoC",
            "hdl-config": "m8_l4",
            "board-location": "mini2",
            "site": "us-home",  # extra unknown tag → goes to extra_tags
        }
    )
    p = validate_place(raw, known_strategies=STRATS)
    assert p.hdl_config == "m8_l4"
    assert p.board_location == "mini2"
    assert p.extra_tags == {"site": "us-home"}


def test_string_tags_from_labgrid_client_show():
    """The labgrid-client `show` parser yields a comma-joined string."""
    raw = {
        "name": "bq",
        "tags": "carrier=zc706, daughter-board=adrv9371, boot-strategy=BootFPGASoC",
        "acquired": None,
    }
    p = validate_place(raw, known_strategies=STRATS)
    assert p.daughter_board == "adrv9371"


def test_acquired_passthrough():
    raw = _raw(
        **{
            "carrier": "zcu102",
            "daughter-board": "ad9081",
            "boot-strategy": "BootFPGASoC",
        }
    )
    raw["acquired"] = "ci-host/runner-42"
    p = validate_place(raw, known_strategies=STRATS)
    assert p.acquired == "ci-host/runner-42"
    assert p.is_acquired is True


def test_missing_name_rejected():
    with pytest.raises(PlaceValidationError, match="no name"):
        validate_place({"tags": {}}, known_strategies=STRATS)


@pytest.mark.parametrize(
    "missing",
    ["carrier", "daughter-board", "boot-strategy"],
)
def test_missing_required_tag_rejected(missing):
    full = {
        "carrier": "zcu102",
        "daughter-board": "ad9081",
        "boot-strategy": "BootFPGASoC",
    }
    full.pop(missing)
    with pytest.raises(PlaceValidationError, match="missing required tag"):
        validate_place(_raw(**full), known_strategies=STRATS)


def test_unknown_strategy_rejected():
    raw = _raw(
        **{
            "carrier": "zcu102",
            "daughter-board": "ad9081",
            "boot-strategy": "BootMyOwnBoard",
        }
    )
    with pytest.raises(PlaceValidationError, match="not a known strategy"):
        validate_place(raw, known_strategies=STRATS)


def test_real_strategy_registry_populated():
    """Spot-check: the live registry includes at least BootFPGASoC."""
    assert "BootFPGASoC" in KNOWN_STRATEGIES
    # Ensure these aren't accidentally dropped if someone renames things
    for required in ("BootFabric", "BootRPI", "BootFPGASoCSSH"):
        assert required in KNOWN_STRATEGIES, (
            f"strategy class {required} dropped — fix the registry "
            f"introspection in adi_lg_plugins.hw_ci.schema._strategy_registry"
        )
