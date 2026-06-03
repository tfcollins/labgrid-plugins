"""harvest_markers should resolve module-level literal `name = ...` bindings.

pyadi-iio writes the overwhelming majority of its markers as
``hardware = "adxl380"`` (or a list) at module scope, then
``@pytest.mark.iio_hardware(hardware)``. The AST harvester must read those
without importing the module (importing pyadi-iio dlopens libiio).
"""

from __future__ import annotations

from pathlib import Path

from adi_lg_plugins.hw_ci.markers import harvest_markers


def _write(tmp_path: Path, name: str, body: str) -> None:
    (tmp_path / name).write_text(body)


def _parts(markers) -> set[str]:
    return {h for spec in markers.values() for h in spec.iio_hardware}


def test_resolves_module_level_string_variable(tmp_path):
    _write(
        tmp_path,
        "test_a.py",
        "import pytest\n"
        'hardware = "adxl380"\n\n'
        "@pytest.mark.iio_hardware(hardware)\n"
        "def test_x():\n"
        "    pass\n",
    )
    assert _parts(harvest_markers(tmp_path)) == {"adxl380"}


def test_resolves_module_level_list_variable(tmp_path):
    _write(
        tmp_path,
        "test_b.py",
        "import pytest\n"
        'hardware = ["ad4030-24", "ad4630-24"]\n\n'
        "@pytest.mark.iio_hardware(hardware)\n"
        "def test_x():\n"
        "    pass\n",
    )
    assert _parts(harvest_markers(tmp_path)) == {"ad4030-24", "ad4630-24"}


def test_reassignment_uses_binding_in_effect_at_each_function(tmp_path):
    # pyadi-iio reuses `hardware = ...` between test groups in one file.
    _write(
        tmp_path,
        "test_c.py",
        "import pytest\n"
        'hardware = "ad4030-24"\n\n'
        "@pytest.mark.iio_hardware(hardware)\n"
        "def test_first():\n"
        "    pass\n\n"
        'hardware = "adaq4224"\n\n'
        "@pytest.mark.iio_hardware(hardware)\n"
        "def test_second():\n"
        "    pass\n",
    )
    m = harvest_markers(tmp_path)
    by_name = {k.split("::")[-1]: sorted(v.iio_hardware) for k, v in m.items()}
    assert by_name["test_first"] == ["ad4030-24"]
    assert by_name["test_second"] == ["adaq4224"]


def test_extra_marker_arg_is_ignored(tmp_path):
    # pyadi-iio uses @pytest.mark.iio_hardware(hardware, True)
    _write(
        tmp_path,
        "test_d.py",
        "import pytest\n"
        'hardware = "cn0511"\n\n'
        "@pytest.mark.iio_hardware(hardware, True)\n"
        "def test_x():\n"
        "    pass\n",
    )
    assert _parts(harvest_markers(tmp_path)) == {"cn0511"}


def test_unresolvable_variable_is_skipped(tmp_path):
    _write(
        tmp_path,
        "test_e.py",
        "import os\n"
        "import pytest\n"
        'hardware = os.environ["BOARD"]  # not a literal -> cannot harvest\n\n'
        "@pytest.mark.iio_hardware(hardware)\n"
        "def test_x():\n"
        "    pass\n",
    )
    assert harvest_markers(tmp_path) == {}  # gracefully omitted, no crash


def test_string_literal_still_works(tmp_path):
    _write(
        tmp_path,
        "test_f.py",
        "import pytest\n\n"
        '@pytest.mark.iio_hardware("ad9081")\n'
        '@pytest.mark.iio_carrier(["zcu102"])\n'
        "def test_x():\n"
        "    pass\n",
    )
    m = harvest_markers(tmp_path)
    assert _parts(m) == {"ad9081"}
    assert sorted(next(iter(m.values())).iio_carrier) == ["zcu102"]
