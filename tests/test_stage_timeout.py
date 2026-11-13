"""Exercise blocked I/O and alarm restoration without touching hardware."""

import signal
import threading

import pytest
from labgrid.strategy import StrategyError

from adi_lg_plugins.strategies._timeouts import stage_deadline


def test_blocked_stage_fails_and_restores_signal_handler():
    original = signal.getsignal(signal.SIGALRM)
    with pytest.raises(StrategyError, match="activate power.*0.05"):
        with stage_deadline("activate power", 0.05):
            threading.Event().wait()
    assert signal.getsignal(signal.SIGALRM) == original
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def test_inner_deadline_does_not_extend_an_outer_deadline():
    with pytest.raises(StrategyError, match="outer"):
        with stage_deadline("outer", 0.05):
            with stage_deadline("inner", 2):
                threading.Event().wait()


def test_successful_stage_preserves_prior_alarm():
    original = signal.getsignal(signal.SIGALRM)
    try:
        signal.setitimer(signal.ITIMER_REAL, 10)
        with stage_deadline("quick stage", 1):
            pass
        remaining, interval = signal.getitimer(signal.ITIMER_REAL)
        assert 9 < remaining <= 10
        assert interval == 0
        assert signal.getsignal(signal.SIGALRM) == original
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
