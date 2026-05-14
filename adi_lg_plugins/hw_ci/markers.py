"""Harvest HW-CI markers from a caller repo via ``pytest --collect-only``.

The contract:

* Caller repo has ``adi-labgrid-plugins`` installed in its venv, which
  auto-registers the ``iio_hardware`` and ``iio_carrier`` markers
  (see :mod:`adi_lg_plugins.pytest_plugin`).
* Tests use ``@pytest.mark.iio_hardware([...])`` and optionally
  ``@pytest.mark.iio_carrier([...])``.

We spawn pytest with ``--collect-only --quiet --hw-ci-export-markers
<jsonfile>``. The plugin auto-registers via the ``pytest11`` entry
point (so a plain ``pip install adi-labgrid-plugins`` is enough — no
``-p`` flag needed). Its collection hook writes a JSON dict keyed by
test id; we read it back.

This is split out from the marker plugin itself so the harvester can
be tested without spinning up pytest end-to-end.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Mapping

from .intersect import MarkerSpec


def _resolve_pytest(pytest_bin: str | None) -> str:
    if pytest_bin:
        return pytest_bin
    bin_in_path = shutil.which("pytest")
    if not bin_in_path:
        raise FileNotFoundError(
            "no `pytest` on PATH; pass pytest_bin= or activate the caller's venv"
        )
    return bin_in_path


def harvest_markers(
    test_root: str | Path,
    *,
    marker: str = "iio_hardware",
    pytest_bin: str | None = None,
    extra_args: list[str] | None = None,
) -> dict[str, MarkerSpec]:
    """Run ``pytest --collect-only -m <marker>`` and return the markers.

    Parameters
    ----------
    test_root :
        Directory pytest should rootdir on (the caller repo).
    marker :
        Top-level marker to filter collection by. Defaults to
        ``iio_hardware``; non-iio callers can pass their own.
    pytest_bin :
        Absolute path to pytest. Defaults to ``which pytest`` so the
        caller's venv is honoured.
    extra_args :
        Forwarded to pytest (e.g. extra ``-c`` config or ``-p`` plugin
        invocations).

    Returns
    -------
    dict mapping pytest node id (e.g. ``test/hw/test_ad9081.py::test_x``)
    to its :class:`MarkerSpec`. Tests without the gating marker are
    omitted entirely.
    """
    test_root = Path(test_root)
    pytest_bin = _resolve_pytest(pytest_bin)

    with tempfile.TemporaryDirectory(prefix="hw-ci-markers-") as td:
        export = Path(td) / "markers.json"
        cmd = [
            pytest_bin,
            "--collect-only",
            "--quiet",
            "--no-header",
            # Plugin auto-registers via pytest11 entry point — no -p.
            f"--hw-ci-export-markers={export}",
            "-m", marker,
            str(test_root),
        ]
        if extra_args:
            cmd.extend(extra_args)
        # We deliberately let pytest emit to stderr — collection errors
        # bubble through. Non-zero rc is allowed only when the export
        # file exists (pytest exits 5 when no tests collected, which
        # is the expected case for repos with no marked tests).
        proc = subprocess.run(
            cmd, capture_output=True, text=True, cwd=test_root
        )
        if not export.exists():
            raise RuntimeError(
                f"pytest --collect-only did not write {export} "
                f"(rc={proc.returncode}); stdout:\n{proc.stdout}\n"
                f"stderr:\n{proc.stderr}"
            )
        raw = json.loads(export.read_text())

    out: dict[str, MarkerSpec] = {}
    for test_id, mks in raw.items():
        iio_hw = mks.get("iio_hardware") or []
        iio_carr = mks.get("iio_carrier") or []
        if not iio_hw:
            continue  # the marker filter should have already excluded this
        out[test_id] = MarkerSpec.of(iio_hw, iio_carr)
    return out
