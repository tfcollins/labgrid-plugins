"""get_dut_shell picks the DUT's Linux shell on single- and two-console targets."""

from unittest.mock import MagicMock

import pytest

from adi_lg_plugins.request.uri import DUT_SHELL_NAME, get_dut_shell, resolve_uri


class _Target:
    """Minimal labgrid-like target: drivers keyed by (class, name)."""

    def __init__(self, drivers):
        self.drivers = drivers  # {(cls, name): driver}

    def get_driver(self, cls, *, name=None):
        matches = [
            d for (c, n), d in self.drivers.items() if c == cls and (name is None or n == name)
        ]
        if len(matches) != 1:
            raise LookupError(f"{len(matches)} {cls} drivers named {name!r}")
        return matches[0]


def test_prefers_named_target_shell_on_two_console_targets():
    sc, dut = MagicMock(), MagicMock()
    t = _Target({("ADIShellDriver", "sc_shell"): sc, ("ADIShellDriver", DUT_SHELL_NAME): dut})
    assert get_dut_shell(t) is dut


def test_single_unnamed_adishell():
    sh = MagicMock()
    assert get_dut_shell(_Target({("ADIShellDriver", None): sh})) is sh


def test_falls_back_to_shelldriver():
    sh = MagicMock()
    assert get_dut_shell(_Target({("ShellDriver", None): sh})) is sh


def test_raises_when_no_shell():
    with pytest.raises(LookupError):
        get_dut_shell(_Target({}))


def test_resolve_uri_reads_ip_from_target_shell():
    sc, dut = MagicMock(), MagicMock()
    dut.run.return_value = (["10.0.0.83"], [], 0)
    t = _Target({("ADIShellDriver", "sc_shell"): sc, ("ADIShellDriver", DUT_SHELL_NAME): dut})
    assert resolve_uri(t, wait=0) == "ip:10.0.0.83"
    sc.run.assert_not_called()
