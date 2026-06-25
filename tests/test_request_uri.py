from __future__ import annotations

import socket

import pytest

from adi_lg_plugins.request.errors import ProvisionError
from adi_lg_plugins.request.uri import resolve_uri, verify_iio_context


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


class FakeShellSequence:
    """FakeShell that returns successive (stdout, rc) pairs per call."""

    def __init__(self, responses):
        # responses: list of (stdout_list, rc) tuples; last entry is repeated if exhausted
        self._responses = list(responses)
        self.call_count = 0

    def run(self, cmd):
        idx = min(self.call_count, len(self._responses) - 1)
        stdout, rc = self._responses[idx]
        self.call_count += 1
        return (stdout, [], rc)


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
    assert resolve_uri(tg, wait=0) == "ip:192.168.1.1"


def test_resolve_uri_shell_empty_output_falls_back_to_static():
    """Empty shell stdout → fall back to NetworkService.address."""
    shell = FakeShell(stdout=[], rc=0)
    tg = FakeTarget(net=FakeNet("192.168.1.1"), shell=shell)
    assert resolve_uri(tg, wait=0) == "ip:192.168.1.1"


def test_resolve_uri_no_shell_driver_falls_back_to_static():
    """No shell driver at all → fall back to NetworkService.address."""
    tg = FakeTarget(net=FakeNet("192.168.1.1"), raise_on_get_driver=True)
    assert resolve_uri(tg, wait=0) == "ip:192.168.1.1"


# ── Static-address fallback path ─────────────────────────────────────────────


def test_resolve_uri_returns_ip_form():
    """Legacy: no shell, static NetworkService only."""
    tg = FakeTarget(net=FakeNet("10.0.0.57"), raise_on_get_driver=True)
    assert resolve_uri(tg, wait=0) == "ip:10.0.0.57"


def test_resolve_uri_missing_resource_raises_provision_error():
    """Both shell absent AND NetworkService absent → ProvisionError."""
    tg = FakeTarget(raise_on_get_resource=True, raise_on_get_driver=True)
    with pytest.raises(ProvisionError):
        resolve_uri(tg, wait=0)


def test_resolve_uri_no_address_raises_provision_error():
    """Shell fails AND NetworkService has empty address → ProvisionError."""
    tg = FakeTarget(net=FakeNet(""), raise_on_get_driver=True)
    with pytest.raises(ProvisionError):
        resolve_uri(tg, wait=0)


# ── verify_iio_context ────────────────────────────────────────────────────────


def test_verify_iio_context_succeeds_when_iiod_listening():
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        # returns None on success
        verify_iio_context("ip:127.0.0.1", port=port, timeout=5.0, interval=0.1)


def test_verify_iio_context_times_out_raises_provision_error():
    # bind-then-close gives us a port that is almost certainly not listening
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        port = srv.getsockname()[1]
    with pytest.raises(ProvisionError, match="boot verification failed"):
        verify_iio_context("ip:127.0.0.1", port=port, timeout=0.5, interval=0.1)


def test_verify_iio_context_non_network_uri_is_noop():
    # usb/serial URIs cannot be TCP-probed; must not raise, must not block
    verify_iio_context("usb:1.2.3", timeout=0.1)


# ── DHCP-race polling ─────────────────────────────────────────────────────────


def test_resolve_uri_polls_until_dhcp_binds():
    """Shell returns empty twice, then a live IP on the 3rd call → ip:10.0.0.66.

    Verifies that resolve_uri retries until the DHCP lease lands rather than
    immediately falling back to the stale static address.
    """
    shell = FakeShellSequence(
        [
            ([], 0),  # call 1: DHCP not yet bound
            ([], 0),  # call 2: still empty
            (["10.0.0.66"], 0),  # call 3: lease landed
        ]
    )
    tg = FakeTarget(net=FakeNet("192.168.1.1"), shell=shell)
    result = resolve_uri(tg, wait=5.0, interval=0.01)
    assert result == "ip:10.0.0.66"
    # Both ADIShellDriver and ShellDriver are tried each round; 3 rounds × 2 drivers = 6,
    # but the success on call 3 of ADIShellDriver short-circuits before ShellDriver.
    # What matters: the successful IP comes from the 3rd round.
    assert shell.call_count == 3


def test_resolve_uri_fallback_after_deadline_warns(caplog):
    """Shell always returns empty; deadline expires → falls back to static address.

    The warning must mention 'may be stale' so operators can identify the
    DHCP-race fallback path in logs.
    """
    import logging

    shell = FakeShell(stdout=[], rc=0)
    tg = FakeTarget(net=FakeNet("10.0.0.23"), shell=shell)
    with caplog.at_level(logging.WARNING, logger="adi_lg_plugins.request.uri"):
        result = resolve_uri(tg, wait=0.05, interval=0.01)
    assert result == "ip:10.0.0.23"
    assert any("may be stale" in r.message for r in caplog.records)
