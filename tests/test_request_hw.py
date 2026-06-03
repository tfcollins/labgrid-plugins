from __future__ import annotations

import os

import pytest

from adi_lg_plugins.request import request


@pytest.mark.hardware
def test_request_adrv9002_uri_end_to_end():
    """Boot adrv9002-zcu102 via the request core and confirm a usable URI.

    Requires --run-hardware and a reachable coordinator. Validates the full
    lifecycle: match -> reserve -> acquire -> boot -> URI -> release.
    """
    if not (os.environ.get("LG_COORDINATOR") or os.environ.get("ADI_LG_COORDINATOR")):
        pytest.skip("no coordinator configured (LG_COORDINATOR / ADI_LG_COORDINATOR)")

    with request(part="adrv9002", carrier="zcu102", wait=1800) as board:
        assert board.uri and board.uri.startswith("ip:")
        assert board.place
        assert board.tags.get("daughter-board") == "adrv9002"
