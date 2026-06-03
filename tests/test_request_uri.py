from __future__ import annotations

import pytest

from adi_lg_plugins.request.errors import ProvisionError
from adi_lg_plugins.request.uri import resolve_uri


class FakeNet:
    def __init__(self, address):
        self.address = address


class FakeShell:
    """Minimal fake for ADIShellDriver / ShellDriver."""

    def __init__(self, stdout=None, rc=0):
        self._stdout = stdout or []
        self._rc = rc

    def run(self, cmd):
        return (self._stdout, [], self._rc)


class FakeTarget:
    def __init__(
        self, net=None, raise_on_get_resource=False, shell=None, raise_on_get_driver=False
    ):
        self._net = net
        self._raise_resource = raise_on_get_resource
        self._shell = shell
        self._raise_driver = raise_on_get_driver

    def get_resource(self, cls):
        if self._raise_resource:
            raise Exception(f"no resource {cls}")
        return self._net

    def get_driver(self, name):
        if self._raise_driver:
            raise Exception(f"no driver {name}")
        return self._shell


# ── Shell-first path ─────────────────────────────────────────────────────────


def test_resolve_uri_uses_live_shell_ip():
    """Shell returns a live IP → resolve_uri uses it, ignoring static NetworkService."""
    shell = FakeShell(stdout=["10.0.0.211"], rc=0)
    tg = FakeTarget(net=FakeNet("192.168.1.1"), shell=shell)
    assert resolve_uri(tg) == "ip:10.0.0.211"


def test_resolve_uri_shell_strips_whitespace():
    """Shell output with trailing whitespace/newline is trimmed."""
    shell = FakeShell(stdout=["10.0.0.211\n"], rc=0)
    tg = FakeTarget(net=FakeNet("192.168.1.1"), shell=shell)
    assert resolve_uri(tg) == "ip:10.0.0.211"


def test_resolve_uri_shell_rc_nonzero_falls_back_to_static():
    """rc != 0 from shell → fall back to NetworkService.address."""
    shell = FakeShell(stdout=["10.0.0.211"], rc=1)
    tg = FakeTarget(net=FakeNet("192.168.1.1"), shell=shell)
    assert resolve_uri(tg) == "ip:192.168.1.1"


def test_resolve_uri_shell_empty_output_falls_back_to_static():
    """Empty shell stdout → fall back to NetworkService.address."""
    shell = FakeShell(stdout=[], rc=0)
    tg = FakeTarget(net=FakeNet("192.168.1.1"), shell=shell)
    assert resolve_uri(tg) == "ip:192.168.1.1"


def test_resolve_uri_no_shell_driver_falls_back_to_static():
    """No shell driver at all → fall back to NetworkService.address."""
    tg = FakeTarget(net=FakeNet("192.168.1.1"), raise_on_get_driver=True)
    assert resolve_uri(tg) == "ip:192.168.1.1"


# ── Static-address fallback path ─────────────────────────────────────────────


def test_resolve_uri_returns_ip_form():
    """Legacy: no shell, static NetworkService only."""
    tg = FakeTarget(net=FakeNet("10.0.0.57"), raise_on_get_driver=True)
    assert resolve_uri(tg) == "ip:10.0.0.57"


def test_resolve_uri_missing_resource_raises_provision_error():
    """Both shell absent AND NetworkService absent → ProvisionError."""
    tg = FakeTarget(raise_on_get_resource=True, raise_on_get_driver=True)
    with pytest.raises(ProvisionError):
        resolve_uri(tg)


def test_resolve_uri_no_address_raises_provision_error():
    """Shell fails AND NetworkService has empty address → ProvisionError."""
    tg = FakeTarget(net=FakeNet(""), raise_on_get_driver=True)
    with pytest.raises(ProvisionError):
        resolve_uri(tg)
