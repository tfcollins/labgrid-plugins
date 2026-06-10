"""pin-release-refs.sh rewrites the reusable workflows' internal @main
self-references to a release tag — run on a release branch before tagging."""

from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "pin-release-refs.sh"

FAMILY = ("hw-request.yml", "noos-hw-request.yml", "matlab-hw-request.yml")

SAMPLE = """\
      - uses: tfcollins/labgrid-plugins/.github/actions/setup-uv-venv@main
        with:
          install_cmd: >-
            uv pip install --quiet --python "$VENV_DIR/bin/python"
            "adi-labgrid-plugins @ git+https://github.com/tfcollins/labgrid-plugins@main"
      - uses: actions/checkout@v4
"""


def _fixture_repo(tmp_path: Path) -> Path:
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    for name in FAMILY:
        (wf / name).write_text(SAMPLE)
    # an out-of-family workflow must NOT be touched
    (wf / "tests.yml").write_text(SAMPLE)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def test_pins_family_main_refs_to_tag(tmp_path):
    repo = _fixture_repo(tmp_path)
    subprocess.run(["bash", str(SCRIPT), "v3"], cwd=repo, check=True)
    for name in FAMILY:
        text = (repo / ".github/workflows" / name).read_text()
        assert "labgrid-plugins/.github/actions/setup-uv-venv@v3" in text
        assert "labgrid-plugins@v3" in text
        assert "@main" not in text
        assert "actions/checkout@v4" in text  # third-party pins untouched


def test_out_of_family_workflows_untouched(tmp_path):
    repo = _fixture_repo(tmp_path)
    subprocess.run(["bash", str(SCRIPT), "v3"], cwd=repo, check=True)
    assert "@main" in (repo / ".github/workflows/tests.yml").read_text()


def test_requires_tag_argument(tmp_path):
    repo = _fixture_repo(tmp_path)
    proc = subprocess.run(["bash", str(SCRIPT)], cwd=repo, capture_output=True)
    assert proc.returncode != 0
