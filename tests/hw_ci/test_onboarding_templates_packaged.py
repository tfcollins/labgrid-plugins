from importlib import resources
from pathlib import Path

EXPECTED = {
    "AGENTS-consumer-stub.md",
    "board-catalog-entry.yaml",
    "board-map.yaml",
    "conftest-iio-uri.py",
    "hw-request-uri.yml",
    "matlab-hw-request.yml",
    "noos-hw-request-flash.yml",
    "projects.yaml",
}


def test_templates_are_importable_resources():
    root = resources.files("adi_lg_plugins.hw_ci.onboarding_templates")
    names = {p.name for p in root.iterdir() if p.name != "__init__.py"}
    assert EXPECTED <= names, f"missing packaged templates: {EXPECTED - names}"


def test_literalincludes_point_into_the_package():
    rst = Path("docs/source/user-guide/onboarding-a-consumer-repo.rst").read_text(encoding="utf-8")
    assert "../onboarding-templates/" not in rst  # no old docs-local path remains
    for line in rst.splitlines():
        if "literalinclude::" in line and "onboarding_templates" in line:
            rel = line.split("literalinclude::", 1)[1].strip()
            target = (Path("docs/source/user-guide") / rel).resolve()
            assert target.is_file(), f"literalinclude target missing: {target}"
