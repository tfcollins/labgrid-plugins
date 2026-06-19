from pathlib import Path

import pytest

from adi_lg_plugins.hw_ci import scaffold
from adi_lg_plugins.hw_ci._release import RECOMMENDED_PIN


def test_render_substitutes_and_pins():
    out = scaffold.render_template(
        "hw-request-uri.yml", test_root="test/hw", install_cmd='uv pip install -e ".[test]"'
    )
    assert "<TEST_ROOT>" not in out and "test/hw" in out
    assert "<YOUR_INSTALL_ARGS>" not in out
    assert f"hw-request.yml@{RECOMMENDED_PIN}" in out  # workflow pin
    assert f"labgrid-plugins.git@{RECOMMENDED_PIN}" in out  # git+https install pin


def test_render_pins_the_stub_placeholder_ref():
    # The stub's `<...>.yml@v3.5` ref must also be pinned to RECOMMENDED_PIN.
    out = scaffold.render_template("AGENTS-consumer-stub.md")
    assert f".yml@{RECOMMENDED_PIN}" in out


def test_scaffold_uri_writes_expected_files(tmp_path):
    written = scaffold.scaffold("uri", str(tmp_path), test_root="test/hw")
    rels = sorted(str(p.relative_to(tmp_path)) for p in written)
    assert rels == sorted([".github/workflows/hw-request.yml", "test/hw/conftest.py", "AGENTS.md"])


def test_scaffold_matlab_uses_hw_matlab_and_board_map_dests(tmp_path):
    rels = {str(p.relative_to(tmp_path)) for p in scaffold.scaffold("matlab", str(tmp_path))}
    assert ".github/workflows/hw-matlab.yml" in rels
    assert "test/hw_ci/board_map.yaml" in rels  # underscore dest


def test_scaffold_refuses_overwrite_without_force(tmp_path):
    scaffold.scaffold("uri", str(tmp_path), test_root="t")
    with pytest.raises(FileExistsError):
        scaffold.scaffold("uri", str(tmp_path), test_root="t")
    assert scaffold.scaffold("uri", str(tmp_path), test_root="t", force=True)


def test_next_steps_has_real_command_per_mode():
    for mode in ("uri", "flash", "matlab"):
        msg = scaffold.next_steps(mode)
        assert "gh variable set" in msg and "LG_COORDINATOR" in msg
        assert f"doctor --mode {mode}" in msg
        assert "..." not in msg  # no placeholder ellipsis shipped in guidance
    assert "MATLAB_BIN" in scaffold.next_steps("matlab")
