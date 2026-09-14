"""Keep the Sphinx landing page navigation and styling synchronized."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs" / "source" / "index.rst"
CSS = ROOT / "docs" / "source" / "_static" / "custom.css"


def test_homepage_navigation_targets_exist():
    source = INDEX.read_text(encoding="utf-8")
    targets = (
        "getting-started/index",
        "yaml-reference/index",
        "user-guide/index",
        "user-guide/onboarding-a-consumer-repo",
        "user-guide/onboarding-a-lab-host",
        "developer-guide/index",
        "user-guide/access-topology",
        "api/index",
    )

    for target in targets:
        assert f":link: {target}" in source or f"button-ref:: {target}" in source
        assert (ROOT / "docs" / "source" / f"{target}.rst").is_file()


def test_homepage_design_classes_have_styles():
    source = INDEX.read_text(encoding="utf-8")
    stylesheet = CSS.read_text(encoding="utf-8")
    classes = (
        "homepage-hero",
        "homepage-headline",
        "homepage-card",
        "homepage-feature-grid",
        "homepage-flow-step",
        "homepage-capability",
        "homepage-final-cta",
    )

    for class_name in classes:
        assert class_name in source
        assert f".{class_name}" in stylesheet

    # Docutils normalizes repeated hyphens when it emits class names.
    normalized_modifiers = (
        "homepage-card-green",
        "homepage-card-blue",
        "homepage-card-orange",
        "homepage-card-purple",
        "homepage-card-cyan",
        "homepage-card-pink",
        "homepage-flow-step-client",
        "homepage-flow-step-exporter",
        "homepage-flow-step-dut",
        "homepage-capability-power",
        "homepage-capability-boot",
        "homepage-capability-ci",
    )
    for class_name in normalized_modifiers:
        assert f".{class_name}" in stylesheet


def test_homepage_supports_dark_mode_and_reduced_motion():
    stylesheet = CSS.read_text(encoding="utf-8")

    assert 'body[data-theme="dark"]' in stylesheet
    assert "@media (prefers-color-scheme: dark)" in stylesheet
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet


def test_iphone_layout_preserves_content_width_and_touch_targets():
    stylesheet = CSS.read_text(encoding="utf-8")

    assert "@media (max-width: 30rem)" in stylesheet
    assert ".content-icon-container" in stylesheet
    assert "env(safe-area-inset-left)" in stylesheet
    assert "env(safe-area-inset-right)" in stylesheet
    assert "min-height: 2.75rem" in stylesheet
    assert ".table-wrapper" in stylesheet
    assert "overflow-x: auto" in stylesheet
    assert ".topology-matrix th:first-child" in stylesheet


def test_iphone_graphics_keep_readable_internal_padding():
    stylesheet = CSS.read_text(encoding="utf-8")

    # Sphinx's generic ``.container`` sets horizontal padding to zero, so the
    # hero and final CTA need explicit overrides at the phone breakpoint.
    assert "padding: 1.25rem 1.25rem 1.15rem !important" in stylesheet
    assert "padding: 1.25rem !important" in stylesheet
    assert "padding: 1rem 1.25rem 0.35rem" in stylesheet
    assert "padding: 1.1rem 1.25rem" in stylesheet
    assert "padding: 1rem !important" in stylesheet
