from pathlib import Path

from adi_lg_plugins.hw_ci.markers import collect_marker_rejections, harvest_markers


def _write(tmp_path: Path, body: str) -> Path:
    d = tmp_path / "hw"
    d.mkdir()
    (d / "test_x.py").write_text("import pytest\n" + body, encoding="utf-8")
    return d


def test_flags_fstring_marker(tmp_path):
    root = _write(
        tmp_path,
        "PART = \"ad9081\"\n@pytest.mark.iio_hardware([f'{PART}_tdd'])\ndef test_a():\n    pass\n",
    )
    rej = collect_marker_rejections(root)
    assert len(rej) == 1
    path, lineno, reason = rej[0]
    assert path == "test_x.py"
    assert "iio_hardware" in reason and "string literal" in reason


def test_accepts_literal_and_module_binding(tmp_path):
    root = _write(
        tmp_path,
        'hardware = ["ad9081"]\n'
        "@pytest.mark.iio_hardware(hardware)\n"
        "def test_a():\n    pass\n"
        '@pytest.mark.iio_hardware(["ad7768"])\n'
        "def test_b():\n    pass\n",
    )
    assert collect_marker_rejections(root) == []


def test_ignores_non_marker_decorators(tmp_path):
    root = _write(
        tmp_path,
        "@pytest.fixture\n@some.other(thing)\n"
        '@pytest.mark.iio_hardware(["ad9081"])\n'
        "def test_a():\n    pass\n",
    )
    assert collect_marker_rejections(root) == []
    # harvest still works unchanged
    assert any(k.endswith("::test_a") for k in harvest_markers(root))
