"""Keep the execution/access topology matrix aligned with public entry points."""

from __future__ import annotations

import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


ROOT = Path(__file__).parents[1]
MATRIX = ROOT / "docs" / "source" / "user-guide" / "access-topology.rst"
STYLES = ROOT / "docs" / "source" / "_static" / "custom.css"
ROW_RE = re.compile(r"^   \* - ``([^`]+)``$", re.MULTILINE)


def _registered_classes(group: str) -> set[str]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    return {spec.rsplit(":", 1)[1] for spec in project["entry-points"][group].values()}


def _matrix_rows(text: str, start_label: str, end_label: str | None) -> list[str]:
    section = text.split(start_label, 1)[1]
    if end_label is not None:
        section = section.split(end_label, 1)[0]
    return ROW_RE.findall(section)


def test_transport_matrices_cover_each_registered_class_exactly_once():
    text = MATRIX.read_text()
    drivers = _matrix_rows(
        text,
        ".. _driver-transport-matrix:",
        ".. _strategy-transport-matrix:",
    )
    strategies = _matrix_rows(text, ".. _strategy-transport-matrix:", None)

    expected_drivers = _registered_classes("labgrid.drivers")
    expected_strategies = _registered_classes("labgrid.strategies")

    assert len(drivers) == len(set(drivers)), "duplicate driver transport-matrix row"
    assert len(strategies) == len(set(strategies)), "duplicate strategy transport-matrix row"
    assert set(drivers) == expected_drivers
    assert set(strategies) == expected_strategies

    driver_section = text.split(".. _driver-transport-matrix:", 1)[1].split(
        ".. _strategy-transport-matrix:", 1
    )[0]
    assert "\n     - No." not in driver_section


def test_transport_guide_defines_each_execution_boundary():
    text = MATRIX.read_text()
    for term in (
        "**Client**",
        "**Exporter path**",
        "**Client LAN path**",
        "**DUT return path**",
        "**Client-local requirement**",
    ):
        assert term in text

    assert 'extra["proxy"]' in text
    assert "ProxyJump" in text


def test_transport_matrices_have_accessible_semantic_color_classes():
    text = MATRIX.read_text()
    styles = STYLES.read_text()

    for class_name in (
        "topology-driver-matrix",
        "topology-strategy-matrix",
        "topology-exporter-label",
        "topology-network-label",
        "topology-local-label",
    ):
        assert class_name in text
        assert f".{class_name}" in styles

    # Color supplements the existing text labels; it must not be the only key.
    for label in ("Exporter path", "Network path", "Local placement"):
        assert label in text

    assert 'body[data-theme="dark"]' in styles
