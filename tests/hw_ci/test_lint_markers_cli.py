from adi_lg_plugins.hw_ci.cli import main


def _write(tmp_path, body):
    d = tmp_path / "hw"
    d.mkdir()
    (d / "test_x.py").write_text("import pytest\n" + body, encoding="utf-8")
    return str(d)


def test_lint_markers_clean_exit_zero(tmp_path, capsys):
    root = _write(tmp_path, '@pytest.mark.iio_hardware(["ad9081"])\ndef test_a():\n    pass\n')
    rc = main(["lint-markers", "--test-root", root])
    assert rc == 0


def test_lint_markers_reports_and_exits_one(tmp_path, capsys):
    root = _write(tmp_path, "@pytest.mark.iio_hardware(PART)\ndef test_a():\n    pass\n")
    rc = main(["lint-markers", "--test-root", root])
    assert rc == 1
    err = capsys.readouterr().err
    assert "test_x.py:2:" in err
    assert "string literal" in err
