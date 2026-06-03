from __future__ import annotations


def test_public_api_exports():
    from adi_lg_plugins.request import (
        BoardUnavailable,
        Lease,
        NoBoardSource,
        NoMatchingBoard,
        ProvisionError,
        RequestError,
        provision_or_reuse,
        request,
    )

    assert callable(request)
    assert issubclass(NoMatchingBoard, RequestError)
    assert issubclass(BoardUnavailable, RequestError)
    assert issubclass(ProvisionError, RequestError)
    assert issubclass(NoBoardSource, RequestError)
    assert callable(provision_or_reuse)
    lease = Lease(place="p", carrier="zcu102", uri="ip:1.2.3.4")
    assert lease.uri == "ip:1.2.3.4"
    assert lease.console is None
