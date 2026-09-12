"""Keep editorial diagram assets accessible and synchronized with Sphinx pages."""

from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).parents[1]
DIAGRAMS = ROOT / "docs/source/_static/diagrams"
PAGE_ASSETS = {
    "docs/source/developer-guide/architecture.rst": "exporter-execution",
    "docs/source/user-guide/access-topology.rst": "artifact-handoff",
    "docs/source/user-guide/hw-request.rst": "hardware-request-flow",
}


def test_diagram_assets_are_paired_accessible_svg():
    expected = {
        DIAGRAMS / f"{stem}-{theme}.svg"
        for stem in PAGE_ASSETS.values()
        for theme in ("light", "dark")
    }
    assert set(DIAGRAMS.glob("*.svg")) == expected

    for path in expected:
        root = ElementTree.parse(path).getroot()
        assert root.tag.endswith("svg")
        assert root.attrib["role"] == "img"
        assert root.attrib.get("aria-labelledby") == "title desc"
        children = list(root)
        assert any(child.tag.endswith("title") and child.text for child in children)
        assert any(child.tag.endswith("desc") and child.text for child in children)
        assert "shadow" not in path.read_text().lower()


def test_sphinx_pages_reference_both_themes_and_attribution():
    for page, stem in PAGE_ASSETS.items():
        text = (ROOT / page).read_text()
        assert f"/_static/diagrams/{stem}-light.svg" in text
        assert f"/_static/diagrams/{stem}-dark.svg" in text
        assert ":class: diagram-light" in text
        assert ":class: diagram-dark" in text
        assert "cathrynlavery/diagram-design" in text
