"""Tests for the adi_lg_plugins.pytest_plugin marker plugin.

We test it the way it's meant to be invoked — by spawning a pytest
subprocess against a tiny generated test module and reading the JSON
the plugin exports.
"""

from __future__ import annotations

import json
import os
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
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "--quiet",
            "--no-header",
            f"--hw-ci-export-markers={export}",
            "-m",
            marker,
            str(test_file),
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    # rc=5 (no tests collected) is OK; rc=0 is OK; anything else is a
    # genuine failure we want to surface.
    assert proc.returncode in (0, 5), (
        f"pytest failed unexpectedly:\nstdout={proc.stdout}\nstderr={proc.stderr}"
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


# --------------------------------------------------------------------------
# Per-shard narrowing via HW_DAUGHTER / HW_CARRIER env vars
# --------------------------------------------------------------------------


def _run_pytest_with_env(tmp_path: Path, body: str, *, env: dict[str, str]):
    """Run pytest -v -m iio_hardware against ``body`` with extra env vars.

    Returns (returncode, stdout). We don't need the JSON export here —
    we're verifying which tests pytest reports as PASSED vs SKIPPED.
    """
    test_file = tmp_path / "test_y.py"
    test_file.write_text(body)
    full_env = {**os.environ, **env}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-v",
            "--no-header",
            "-m",
            "iio_hardware",
            str(test_file),
        ],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=full_env,
    )
    return proc.returncode, proc.stdout + proc.stderr


def test_hw_daughter_narrows_to_matching_tests(tmp_path):
    body = """
import pytest

@pytest.mark.iio_hardware(["ad9081"])
def test_ad9081(): pass

@pytest.mark.iio_hardware(["adrv9009"])
def test_adrv9009(): pass

@pytest.mark.iio_hardware(["adrv9371", "ad9371"])
def test_ad9371_alias(): pass
"""
    rc, out = _run_pytest_with_env(tmp_path, body, env={"HW_DAUGHTER": "ad9081"})
    assert "PASSED" in out and "test_ad9081" in out
    assert "SKIPPED" in out and "test_adrv9009" in out
    assert "test_ad9371_alias" in out  # also skipped
    # exit-code 0 means at least one test ran successfully
    assert rc == 0, out


def test_hw_daughter_alias_match(tmp_path):
    """An iio_hardware([\"adrv9371\", \"ad9371\"]) test runs when shard = ad9371."""
    body = """
import pytest

@pytest.mark.iio_hardware(["adrv9371", "ad9371"])
def test_alias(): pass
"""
    rc, out = _run_pytest_with_env(tmp_path, body, env={"HW_DAUGHTER": "ad9371"})
    assert "PASSED" in out and "test_alias" in out
    assert rc == 0, out


def test_hw_carrier_narrows_when_marker_present(tmp_path):
    body = """
import pytest

@pytest.mark.iio_hardware(["ad9081"])
def test_any_carrier(): pass

@pytest.mark.iio_hardware(["ad9081"])
@pytest.mark.iio_carrier(["zcu102"])
def test_zcu102_only(): pass

@pytest.mark.iio_hardware(["ad9081"])
@pytest.mark.iio_carrier(["vcu118"])
def test_vcu118_only(): pass
"""
    rc, out = _run_pytest_with_env(
        tmp_path,
        body,
        env={"HW_DAUGHTER": "ad9081", "HW_CARRIER": "zcu102"},
    )
    assert "PASSED" in out and "test_any_carrier" in out
    assert "PASSED" in out and "test_zcu102_only" in out
    assert "SKIPPED" in out and "test_vcu118_only" in out
    assert rc == 0, out


def test_no_env_vars_means_no_narrowing(tmp_path):
    """Without HW_DAUGHTER / HW_CARRIER the hook is a no-op."""
    body = """
import pytest

@pytest.mark.iio_hardware(["ad9081"])
def test_a(): pass

@pytest.mark.iio_hardware(["adrv9009"])
def test_b(): pass
"""
    # Explicitly unset to avoid inherited env from the runner
    rc, out = _run_pytest_with_env(tmp_path, body, env={"HW_DAUGHTER": "", "HW_CARRIER": ""})
    # Both ran (no skips from our hook)
    assert "PASSED" in out and "test_a" in out
    assert "PASSED" in out and "test_b" in out
    assert "SKIPPED" not in out
    assert rc == 0, out


def test_unmarked_test_left_alone_when_narrowing(tmp_path):
    """Tests without iio_hardware are excluded by -m, not by our hook."""
    body = """
import pytest

def test_unmarked(): pass

@pytest.mark.iio_hardware(["ad9081"])
def test_marked(): pass
"""
    rc, out = _run_pytest_with_env(tmp_path, body, env={"HW_DAUGHTER": "ad9081"})
    assert "PASSED" in out and "test_marked" in out
    # `-m iio_hardware` removes test_unmarked from collection.
    assert "test_unmarked" not in out or "deselected" in out
    assert rc == 0, out
