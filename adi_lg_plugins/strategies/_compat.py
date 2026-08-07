"""labgrid compatibility shims for adi_lg_plugins strategies.

Upstream labgrid does not ship the ``never_retry`` strategy decorator that
the ADI boot strategies rely on (it originated in the previously-used
labgrid fork). This module provides a self-contained equivalent so the
package works against upstream labgrid.
"""

from __future__ import annotations

import functools

from labgrid.strategy import StrategyError


def never_retry(func):
    """Strategy-method decorator that latches the first failure.

    Stores the original exception on ``strategy.broken`` and raises a
    ``StrategyError`` from it. Every subsequent call re-raises rather than
    re-running the (often side-effecting, non-idempotent) transition.

    Self-contained: it does not require labgrid to pre-define ``broken``
    on the strategy (read via ``getattr``; upstream ``Strategy`` is a
    non-slotted attrs class, so the attribute is freely settable).
    """

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        broken = getattr(self, "broken", None)
        if broken is not None:
            raise StrategyError(f"{self.__class__.__name__} is in broken state: {broken}") from broken
        try:
            return func(self, *args, **kwargs)
        except Exception as e:
            self.broken = e
            raise StrategyError(f"{self.__class__.__name__} is in broken state: {e}") from e

    return wrapper
