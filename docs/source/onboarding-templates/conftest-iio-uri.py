"""Template — copy into <consumer-repo>/test/hw/conftest.py (adapt to your suite).

Provides an ``iio_uri`` fixture for the labgrid-plugins **uri-mode** hw-request flow.
``adi-lg request --run 'pytest ...'`` boots a matching board out of band and exports
``IIO_URI`` to the child pytest; this conftest reads it, waits for iiod to be ready, and
hands tests a usable libIIO URI.

This is the minimal path that suits the ``hw-request.yml`` flow (the board is already
booted by ``adi-lg request``). For the heavier ``hw-matrix`` flow that boots the board
*inside* conftest via a labgrid env (``$LG_ENV``) and discovers the DUT's DHCP IP, see
``pyadi-iio/test/hw/conftest.py`` for the full discover + retry implementation.
"""

from __future__ import annotations

import os
import time

import iio  # pylibiio — install via your test deps (e.g. `pip install pylibiio`)
import pytest


def pytest_addoption(parser):
    g = parser.getgroup("hw")
    g.addoption(
        "--iio-uri-override",
        # IIO_URI is exported by `adi-lg request` (the low-config hw-request flow):
        # it boots a board out of band and hands the URI to the child test command.
        # IIO_URI_OVERRIDE is the manual / laptop knob.
        default=os.environ.get("IIO_URI_OVERRIDE") or os.environ.get("IIO_URI"),
        help="libIIO URI to point tests at (e.g. ip:10.0.0.132). "
        "Defaults to $IIO_URI_OVERRIDE, then $IIO_URI.",
    )


@pytest.fixture(scope="session")
def iio_uri(request) -> str:
    """A libIIO URI with a reachable iiod, or skip if none was provided."""
    uri = request.config.getoption("--iio-uri-override")
    if not uri:
        pytest.skip(
            "no IIO_URI / --iio-uri-override set; run via "
            "`adi-lg request --part <board> --run 'pytest ...'`"
        )
    # eth0 DHCP completing does NOT mean iiod is ready — IIO drivers can take another
    # 5-15s to probe (longer on cold boots). Poll until a context opens cleanly.
    deadline = time.time() + 120
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            iio.Context(uri)
            return uri
        except Exception as e:  # noqa: BLE001 - any libiio error means "not ready yet"
            last_err = e
            time.sleep(3)
    raise RuntimeError(f"iiod not reachable at {uri!r} after 120s: {last_err}")
