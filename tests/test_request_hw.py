"""End-to-end hardware smoke test for the request layer (uri mode).

Requires a live coordinator (LG_COORDINATOR or --coord via env) with at least
one free board whose daughter-board tag matches REQUEST_PART. Run with:

    pytest tests/test_request_hw.py --run-hardware -v

Set ADI_LG_TEST_PART to override the part (default: ad9361).
"""

import os

import pytest

from adi_lg_plugins.request import request

REQUEST_PART = os.environ.get("ADI_LG_TEST_PART", "ad9361")


@pytest.mark.hardware
def test_request_boots_board_and_returns_uri():
    with request(part=REQUEST_PART, wait=1800) as board:
        assert board.uri and board.uri.startswith("ip:")
        assert board.place
        # libiio is an optional runtime dep; only assert a live context if present.
        try:
            import iio
        except ImportError:
            pytest.skip("libiio not installed; URI returned but not exercised")
        ctx = iio.Context(board.uri)
        assert ctx.devices, "no IIO devices found on booted board"
