import json

from adi_lg_plugins.hw_ci.cli import _emit_matrix


def test_writes_github_output_and_returns_nothing(tmp_path, monkeypatch, capsys):
    gh_out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_out))
    matrix = {"include": [{"part": "ad9361"}]}

    _emit_matrix(matrix, count=1, missing=["daq3"], kind="request-matrix", github_output=True)

    written = gh_out.read_text()
    assert f"matrix={json.dumps(matrix)}" in written
    assert "count=1" in written
    err = capsys.readouterr().err
    assert "::warning::" in err
    assert "daq3" in err


def test_no_github_output_when_flag_false(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "gh_output"))
    _emit_matrix({"include": []}, count=0, missing=[], kind="noos-matrix", github_output=False)
    assert not (tmp_path / "gh_output").exists()
    out = capsys.readouterr().out
    assert '"include"' in out  # the matrix is still printed to stdout


def test_warns_when_github_output_requested_but_env_unset(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _emit_matrix({"include": []}, count=0, missing=[], kind="request-matrix", github_output=True)
    assert "$GITHUB_OUTPUT is unset" in capsys.readouterr().err
