from __future__ import annotations

import pytest

from adi_lg_plugins.request.errors import ProvisionError
from adi_lg_plugins.request.uri import resolve_uri


class FakeNet:
    def __init__(self, address):
        self.address = address


class FakeTarget:
    def __init__(self, net=None, raise_on_get=False):
        self._net = net
        self._raise = raise_on_get

    def get_resource(self, cls):
        if self._raise:
            raise Exception(f"no resource {cls}")
        return self._net


def test_resolve_uri_returns_ip_form():
    tg = FakeTarget(net=FakeNet("10.0.0.57"))
    assert resolve_uri(tg) == "ip:10.0.0.57"


def test_resolve_uri_missing_resource_raises_provision_error():
    tg = FakeTarget(raise_on_get=True)
    with pytest.raises(ProvisionError):
        resolve_uri(tg)


def test_resolve_uri_no_address_raises_provision_error():
    tg = FakeTarget(net=FakeNet(""))
    with pytest.raises(ProvisionError):
        resolve_uri(tg)
