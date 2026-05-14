"""AST-based marker harvest (adi_lg_plugins.hw_ci.markers.harvest_markers).

Discovery happens without importing the caller's test modules — the
runner that does discovery doesn't have a working DUT toolchain, so
this is the only viable harvest path. These tests verify every
literal-form decoration recognised by ``_extract_marker_args`` and
that non-literal markers are silently ignored.
"""

from __future__ import annotations

from adi_lg_plugins.hw_ci.markers import harvest_markers


def _write(root, rel, body):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_list_form(tmp_path):
    _write(
        tmp_path,
        "test_a.py",
        """
import pytest

@pytest.mark.iio_hardware(["ad9081", "ad9081_tdd"])
def test_x():
    pass
""",
    )
    out = harvest_markers(tmp_path)
    assert set(out) == {"test_a.py::test_x"}
    spec = out["test_a.py::test_x"]
    assert spec.iio_hardware == frozenset({"ad9081", "ad9081_tdd"})
    assert spec.iio_carrier == frozenset()


def test_single_string_shorthand(tmp_path):
    _write(
        tmp_path,
        "test_a.py",
        """
import pytest

@pytest.mark.iio_hardware("ad9081")
def test_x():
    pass
""",
    )
    out = harvest_markers(tmp_path)
    assert out["test_a.py::test_x"].iio_hardware == frozenset({"ad9081"})


def test_tuple_form(tmp_path):
    _write(
        tmp_path,
        "test_a.py",
        """
import pytest

@pytest.mark.iio_hardware(("ad9081", "ad9081_tdd"))
def test_x():
    pass
""",
    )
    out = harvest_markers(tmp_path)
    assert out["test_a.py::test_x"].iio_hardware == frozenset({"ad9081", "ad9081_tdd"})


def test_carrier_marker_captured(tmp_path):
    _write(
        tmp_path,
        "test_a.py",
        """
import pytest

@pytest.mark.iio_hardware(["ad9081"])
@pytest.mark.iio_carrier(["zcu102"])
def test_x():
    pass
""",
    )
    spec = harvest_markers(tmp_path)["test_a.py::test_x"]
    assert spec.iio_hardware == frozenset({"ad9081"})
    assert spec.iio_carrier == frozenset({"zcu102"})


def test_carrier_without_hardware_is_dropped(tmp_path):
    """A test marked only with iio_carrier (no iio_hardware) is excluded."""
    _write(
        tmp_path,
        "test_a.py",
        """
import pytest

@pytest.mark.iio_carrier(["zcu102"])
def test_x():
    pass
""",
    )
    assert harvest_markers(tmp_path) == {}


def test_unmarked_test_dropped(tmp_path):
    _write(
        tmp_path,
        "test_a.py",
        """
import pytest

@pytest.mark.iio_hardware(["ad9081"])
def test_marked():
    pass

def test_unmarked():
    pass
""",
    )
    out = harvest_markers(tmp_path)
    assert "test_a.py::test_marked" in out
    assert "test_a.py::test_unmarked" not in out


def test_dynamic_argument_dropped_gracefully(tmp_path):
    """A computed marker arg can't be statically harvested — silently drop.

    The test still runs under pytest at hw-execution time; it just
    won't appear in the discovery matrix. Documented in the v2 guide.
    """
    _write(
        tmp_path,
        "test_a.py",
        """
import pytest

DAUGHTERS = ["ad9081"]

@pytest.mark.iio_hardware(DAUGHTERS)
def test_x():
    pass
""",
    )
    assert harvest_markers(tmp_path) == {}


def test_recursive_walk_into_subdirs(tmp_path):
    _write(
        tmp_path,
        "a/test_a.py",
        """
import pytest

@pytest.mark.iio_hardware(["ad9081"])
def test_a():
    pass
""",
    )
    _write(
        tmp_path,
        "b/nested/test_b.py",
        """
import pytest

@pytest.mark.iio_hardware(["adrv9009"])
def test_b():
    pass
""",
    )
    out = harvest_markers(tmp_path)
    assert set(out) == {"a/test_a.py::test_a", "b/nested/test_b.py::test_b"}


def test_non_test_files_ignored(tmp_path):
    """Only test_*.py files are walked — conftest.py etc. are skipped."""
    _write(
        tmp_path,
        "conftest.py",
        """
import pytest

@pytest.mark.iio_hardware(["adrv9371"])
def test_should_not_be_picked_up():
    pass
""",
    )
    assert harvest_markers(tmp_path) == {}


def test_syntax_error_file_skipped(tmp_path):
    _write(tmp_path, "test_broken.py", "def foo(:\n")
    _write(
        tmp_path,
        "test_good.py",
        """
import pytest

@pytest.mark.iio_hardware(["ad9081"])
def test_x():
    pass
""",
    )
    out = harvest_markers(tmp_path)
    assert set(out) == {"test_good.py::test_x"}


def test_async_def_supported(tmp_path):
    _write(
        tmp_path,
        "test_a.py",
        """
import pytest

@pytest.mark.iio_hardware(["ad9081"])
async def test_x():
    pass
""",
    )
    out = harvest_markers(tmp_path)
    assert out["test_a.py::test_x"].iio_hardware == frozenset({"ad9081"})


def test_non_pytest_mark_decorator_ignored(tmp_path):
    """A bare @iio_hardware() (no pytest.mark prefix) is not recognised."""
    _write(
        tmp_path,
        "test_a.py",
        """
def iio_hardware(daughters):
    def deco(fn): return fn
    return deco

@iio_hardware(["ad9081"])
def test_x():
    pass
""",
    )
    assert harvest_markers(tmp_path) == {}
