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
import os
from pathlib import Path

import pytest

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
    adi = parser.getgroup("adi-hardware")
    adi.addoption(
        "--adi-part",
        dest="adi_part",
        default=None,
        help="Part to self-request when no URI is provided (e.g. adrv9002).",
    )
    adi.addoption(
        "--adi-carrier",
        dest="adi_carrier",
        default=None,
        help="Optional carrier narrowing for a self-requested board.",
    )
    adi.addoption(
        "--adi-uri",
        dest="adi_uri",
        default=None,
        help="Use a pre-booted board at this libIIO URI (skip self-request).",
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


def pytest_collection_modifyitems(config, items):
    """Per-shard narrowing: deselect items whose markers don't match.

    Pytest's ``-m`` expression is boolean over marker *names*, not
    marker arguments — ``-m "iio_hardware and ad9081"`` looks for two
    separate markers, so a test wearing only
    ``@pytest.mark.iio_hardware(["ad9081"])`` never matches.

    Instead the v2 reusable workflow exports two env vars per shard:

    * ``HW_DAUGHTER=<daughter-board>`` (required)
    * ``HW_CARRIER=<carrier>``         (optional)

    This hook reads those and skips items whose ``iio_hardware`` args
    don't include the daughter, OR whose ``iio_carrier`` args are set
    but don't include the carrier. Items without ``iio_hardware`` at
    all are left alone for the top-level ``-m iio_hardware`` filter
    to deselect.

    Setting neither env var is a no-op — useful for ad-hoc local runs.
    """
    target_daughter = os.environ.get("HW_DAUGHTER", "").strip()
    target_carrier = os.environ.get("HW_CARRIER", "").strip()
    if not target_daughter and not target_carrier:
        return

    for item in items:
        iio_hw = _marker_args(item, "iio_hardware")
        if not iio_hw:
            # Untouched — top-level -m iio_hardware will exclude it.
            continue

        if target_daughter and target_daughter not in iio_hw:
            item.add_marker(
                pytest.mark.skip(
                    reason=f"hw-ci: daughter-board {target_daughter!r} not in {iio_hw}"
                )
            )
            continue

        if target_carrier:
            iio_carr = _marker_args(item, "iio_carrier")
            if iio_carr and target_carrier not in iio_carr:
                item.add_marker(
                    pytest.mark.skip(reason=f"hw-ci: carrier {target_carrier!r} not in {iio_carr}")
                )


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


def _board_sources(get_option, environ):
    """Resolve ``(uri, part, carrier, coord)`` from pytest options then env.

    Pure function of its inputs (a ``get_option(name)`` callable and an
    ``os.environ``-like mapping) so the precedence is unit-tested without a
    live pytest config. Options take precedence over environment variables.
    """
    uri = get_option("adi_uri") or environ.get("IIO_URI")
    part = get_option("adi_part") or environ.get("ADI_PART")
    carrier = get_option("adi_carrier") or environ.get("ADI_CARRIER")
    coord = environ.get("LG_COORDINATOR") or environ.get("ADI_LG_COORDINATOR")
    return uri, part, carrier, coord


@pytest.fixture(scope="session")
def adi_board(pytestconfig):
    """A booted board handle (a request ``Lease``) for hardware tests.

    Dual-mode: reuse a pre-booted board if ``--adi-uri`` / ``$IIO_URI`` is set
    (release nothing), else self-request one by ``--adi-part`` / ``$ADI_PART``
    (released at session end). With neither configured the test is skipped.
    """
    from adi_lg_plugins.request.errors import NoBoardSource
    from adi_lg_plugins.request.provision import provision_or_reuse

    uri, part, carrier, coord = _board_sources(pytestconfig.getoption, os.environ)
    try:
        with provision_or_reuse(part, carrier, uri=uri, coord=coord) as lease:
            yield lease
    except NoBoardSource as e:
        pytest.skip(str(e))


@pytest.fixture(scope="session")
def adi_uri(adi_board):
    """Just the libIIO URI string — sugar for ``adi.adrv9002(uri=adi_uri)``."""
    return adi_board.uri
