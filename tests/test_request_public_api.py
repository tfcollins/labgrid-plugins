from __future__ import annotations


def test_public_api_exports():
    from adi_lg_plugins.request import (
        BoardUnavailable,
        Lease,
        NoMatchingBoard,
        ProvisionError,
        RequestError,
        request,
    )

    assert callable(request)
    assert issubclass(NoMatchingBoard, RequestError)
    assert issubclass(BoardUnavailable, RequestError)
    assert issubclass(ProvisionError, RequestError)
    lease = Lease(place="p", carrier="zcu102", uri="ip:1.2.3.4")
    assert lease.uri == "ip:1.2.3.4"
    assert lease.console is None
