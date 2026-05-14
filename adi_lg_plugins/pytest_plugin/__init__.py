"""pytest plugin: HW-CI markers + collection export.

Registers two markers usable in any project that pip-installs
``adi-labgrid-plugins``:

* ``@pytest.mark.iio_hardware([daughter, ...])``
* ``@pytest.mark.iio_carrier([carrier, ...])``

Auto-registered via the ``pytest11`` entry point in ``pyproject.toml``;
no per-project ``conftest.py`` plumbing needed.

When run with ``--hw-ci-export-markers=<path>``, the plugin writes a
JSON dict ``{test_id: {iio_hardware: [...], iio_carrier: [...]}}``
after collection. This is what
:mod:`adi_lg_plugins.hw_ci.markers` consumes to drive the matrix.
"""

from __future__ import annotations

import json
from pathlib import Path

_MARKER_NAMES = ("iio_hardware", "iio_carrier")


def pytest_addoption(parser):
    group = parser.getgroup("hw-ci")
    group.addoption(
        "--hw-ci-export-markers",
        dest="hw_ci_export_markers",
        default=None,
        metavar="PATH",
        help=(
            "After collection, write a JSON dict of "
            "{test_id: {iio_hardware: [...], iio_carrier: [...]}} to "
            "PATH. Used by `adi-lg-hw-ci discover`."
        ),
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "iio_hardware(daughter_boards): names of daughter-board / "
        "chip families this test exercises (e.g. ['ad9081', "
        "'ad9081_tdd']). Matches the coordinator place tag "
        "`daughter-board`.",
    )
    config.addinivalue_line(
        "markers",
        "iio_carrier(carriers): optional narrowing — names of FPGA "
        "carriers this test only runs on (e.g. ['zcu102']). Matches "
        "the coordinator place tag `carrier`. Absent means any "
        "carrier carrying the marked daughter-board.",
    )


def _marker_args(item, name) -> list[str]:
    """Flatten args of all instances of marker `name` on `item`."""
    out: list[str] = []
    for mark in item.iter_markers(name=name):
        if not mark.args:
            continue
        first = mark.args[0]
        if isinstance(first, (list, tuple, set, frozenset)):
            out.extend(str(x) for x in first)
        else:
            # Allow @pytest.mark.iio_hardware("ad9081") shorthand
            out.append(str(first))
    # de-dupe preserving order
    seen: set[str] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def pytest_collection_finish(session):
    """Emit the marker-export JSON if the option was given."""
    path = session.config.getoption("hw_ci_export_markers")
    if not path:
        return
    out: dict[str, dict[str, list[str]]] = {}
    for item in session.items:
        iio_hw = _marker_args(item, "iio_hardware")
        if not iio_hw:
            continue  # only export tests with the gating marker
        out[item.nodeid] = {
            "iio_hardware": iio_hw,
            "iio_carrier": _marker_args(item, "iio_carrier"),
        }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(out, sort_keys=True, indent=2))
