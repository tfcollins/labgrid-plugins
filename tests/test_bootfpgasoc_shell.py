from unittest.mock import MagicMock

import pytest
from labgrid.strategy import Strategy, StrategyError

from adi_lg_plugins.strategies.bootfpgasoc import BootFPGASoC, Status


@pytest.fixture(autouse=True)
def light_post_init(monkeypatch):
    def _post_init(self):
        Strategy.__attrs_post_init__(self)
        for name in type(self).bindings:
            if not hasattr(self, name):
                setattr(self, name, None)

    monkeypatch.setattr(BootFPGASoC, "__attrs_post_init__", _post_init)


def _strategy(returncode=0):
    target = MagicMock()
    target.bind.side_effect = lambda item: setattr(item, "target", target)
    strategy = BootFPGASoC(target, "boot")
    strategy.status = Status.booted
    strategy.shell = MagicMock()
    strategy.shell.run.return_value = ([], [], returncode)
    return strategy


def test_shell_transition_restarts_iiod_after_driver_probe():
    strategy = _strategy()

    strategy.transition(Status.shell)

    command = strategy.shell.run.call_args.args[0]
    assert "systemctl restart iiod.service" in command
    assert strategy.status is Status.shell


def test_shell_transition_fails_when_iiod_cannot_restart():
    strategy = _strategy(returncode=1)
    strategy.shell.run.return_value = ([], ["unit failed"], 1)

    with pytest.raises(StrategyError, match="unit failed"):
        strategy.transition(Status.shell)


def test_shell_transition_can_leave_iiod_untouched():
    strategy = _strategy()
    strategy.restart_iiod_on_shell = False

    strategy.transition(Status.shell)

    strategy.shell.run.assert_not_called()
