"""Tests for the adi_lg_plugins.pytest_plugin marker plugin.

We test it the way it's meant to be invoked — by spawning a pytest
subprocess against a tiny generated test module and reading the JSON
the plugin exports.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run_pytest(tmp_path: Path, test_body: str, *, marker: str = "iio_hardware"):
    """Run pytest --collect-only with our plugin against a tmp test file.

    Returns the parsed export-JSON dict.
    """
    test_file = tmp_path / "test_x.py"
    test_file.write_text(test_body)
    export = tmp_path / "out.json"
    # The plugin auto-registers via the pytest11 entry point in
    # pyproject.toml — no explicit -p needed (and passing both would
    # register it twice and ValueError).
    proc = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "--collect-only", "--quiet", "--no-header",
            f"--hw-ci-export-markers={export}",
            "-m", marker,
            str(test_file),
        ],
        capture_output=True, text=True, cwd=tmp_path,
    )
    # rc=5 (no tests collected) is OK; rc=0 is OK; anything else is a
    # genuine failure we want to surface.
    assert proc.returncode in (0, 5), (
        f"pytest failed unexpectedly:\nstdout={proc.stdout}\n"
        f"stderr={proc.stderr}"
    )
    if not export.exists():
        return {}
    return json.loads(export.read_text())


def test_marker_args_captured_from_list_form(tmp_path):
    body = """
import pytest

@pytest.mark.iio_hardware(["ad9081", "ad9081_tdd"])
def test_x(): pass
"""
    out = _run_pytest(tmp_path, body)
    assert "test_x.py::test_x" in out
    entry = out["test_x.py::test_x"]
    assert entry["iio_hardware"] == ["ad9081", "ad9081_tdd"]
    assert entry["iio_carrier"] == []


def test_marker_args_shorthand_single_string(tmp_path):
    body = """
import pytest

@pytest.mark.iio_hardware("ad9081")
def test_x(): pass
"""
    out = _run_pytest(tmp_path, body)
    assert out["test_x.py::test_x"]["iio_hardware"] == ["ad9081"]


def test_carrier_marker_captured(tmp_path):
    body = """
import pytest

@pytest.mark.iio_hardware(["ad9081"])
@pytest.mark.iio_carrier(["zcu102"])
def test_x(): pass
"""
    out = _run_pytest(tmp_path, body)
    entry = out["test_x.py::test_x"]
    assert entry["iio_hardware"] == ["ad9081"]
    assert entry["iio_carrier"] == ["zcu102"]


def test_unmarked_test_excluded(tmp_path):
    """Tests without iio_hardware shouldn't even appear in the export."""
    body = """
import pytest

@pytest.mark.iio_hardware(["ad9081"])
def test_marked(): pass

def test_unmarked(): pass
"""
    out = _run_pytest(tmp_path, body)
    assert "test_x.py::test_marked" in out
    assert "test_x.py::test_unmarked" not in out


def test_no_marked_tests_writes_empty_dict(tmp_path):
    body = """
def test_x(): pass
"""
    out = _run_pytest(tmp_path, body)
    assert out == {}
