import pytest

from adi_lg_plugins.request.errors import ProvisionError
from adi_lg_plugins.request.uri import resolve_uri


class FakeResource:
    def __init__(self, address):
        self.address = address


class FakeTarget:
    def __init__(self, resource):
        self._resource = resource

    def get_resource(self, name):
        if self._resource is None:
            raise Exception(f"no resource {name}")
        return self._resource


def test_resolve_uri_builds_ip_uri():
    tg = FakeTarget(FakeResource("10.0.0.57"))
    assert resolve_uri(tg) == "ip:10.0.0.57"


def test_resolve_uri_missing_network_raises():
    with pytest.raises(ProvisionError):
        resolve_uri(FakeTarget(None))


def test_resolve_uri_missing_address_raises():
    with pytest.raises(ProvisionError):
        resolve_uri(FakeTarget(FakeResource(None)))
