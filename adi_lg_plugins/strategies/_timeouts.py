"""POSIX deadlines for blocking boot-stage I/O, with nested alarm restoration."""

import faulthandler
import signal
import threading
import time
from contextlib import contextmanager

from labgrid.strategy import StrategyError


@contextmanager
def stage_deadline(name, seconds):
    seconds = float(seconds)
    if seconds <= 0:
        raise ValueError("Stage timeout must be positive")
    if threading.current_thread() is not threading.main_thread() or not hasattr(signal, "SIGALRM"):
        raise StrategyError("Boot stage deadlines require the POSIX main thread")
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_delay, previous_interval = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()
    previous_expires_first = bool(previous_delay and previous_delay <= seconds)

    def expired(signum, frame):
        if previous_expires_first and callable(previous_handler):
            previous_handler(signum, frame)
        try:
            faulthandler.dump_traceback()
        except (OSError, ValueError, RuntimeError):
            pass
        raise StrategyError(f"Timed out during boot stage '{name}' after {seconds:g}s")

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(
        signal.ITIMER_REAL, min(seconds, previous_delay) if previous_delay else seconds
    )
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        remaining = previous_delay - (time.monotonic() - started)
        if previous_delay and remaining > 0:
            signal.setitimer(signal.ITIMER_REAL, remaining, previous_interval)
