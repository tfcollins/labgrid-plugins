"""Unit tests for the BootVPK180 strategy."""

from unittest.mock import MagicMock

import pytest
from labgrid.strategy import StrategyError

from adi_lg_plugins.strategies.bootvpk180 import BootVPK180, Status


def _make_strategy(**bindings):
    """Construct a BootVPK180 instance with all bindings explicitly set.

    Bypasses labgrid's normal binding-resolution machinery — the test is
    responsible for assigning every binding name (required + optional) on
    the instance. Pass MagicMock() for "binding present", None for "absent".
    """
    target = MagicMock()

    def bind(item):
        item.target = target

    target.bind.side_effect = bind

    strategy = BootVPK180(target, "bootvpk180")

    defaults = {
        "power": MagicMock(),
        "sc_shell": MagicMock(),
        "target_shell": MagicMock(),
        "sdmux": None,
        "mass_storage": None,
        "image_writer": None,
        "kuiper": None,
        "ssh": None,
    }
    defaults.update(bindings)
    for name, value in defaults.items():
        setattr(strategy, name, value)
    return strategy


# ---------- _select_update_path matrix ------------------------------------


def test_select_update_path_disabled_returns_none():
    s = _make_strategy()
    s.update_boot_files = False
    assert s._select_update_path() is None


def test_select_update_path_image_requires_full_stack():
    s = _make_strategy(sdmux=MagicMock(), mass_storage=MagicMock(), kuiper=MagicMock())
    s.update_image = True
    # image_writer missing → error
    with pytest.raises(StrategyError, match="image_writer"):
        s._select_update_path()


def test_select_update_path_boot_files_requires_kuiper():
    s = _make_strategy(sdmux=MagicMock(), mass_storage=MagicMock(), kuiper=None)
    s.update_boot_files = True
    with pytest.raises(StrategyError, match="kuiper"):
        s._select_update_path()


def test_select_update_path_boot_files_requires_a_path():
    s = _make_strategy(kuiper=MagicMock())
    s.update_boot_files = True
    with pytest.raises(StrategyError, match="sdmux.*ssh|ssh.*sdmux"):
        s._select_update_path()


def test_select_update_path_picks_sdmux():
    s = _make_strategy(sdmux=MagicMock(), mass_storage=MagicMock(), kuiper=MagicMock())
    s.update_boot_files = True
    assert s._select_update_path() == "sdmux"


def test_select_update_path_picks_ssh_when_sdmux_absent():
    s = _make_strategy(ssh=MagicMock(), kuiper=MagicMock())
    s.update_boot_files = True
    assert s._select_update_path() == "ssh"


def test_select_update_path_prefers_sdmux_when_both_present():
    s = _make_strategy(
        sdmux=MagicMock(), mass_storage=MagicMock(), ssh=MagicMock(), kuiper=MagicMock()
    )
    s.update_boot_files = True
    assert s._select_update_path() == "sdmux"


# ---------- SC alive phase ------------------------------------------------


def test_sc_alive_succeeds_first_try():
    s = _make_strategy()
    s._wait_for_sc_alive()
    s.target.activate.assert_called_once_with(s.sc_shell)


def test_sc_alive_retries_on_timeout_then_succeeds():
    s = _make_strategy()
    s.sc_login_retries = 1
    # First activation raises (login timeout); second succeeds.
    call_count = {"n": 0}

    def activate_side_effect(driver):
        if driver is s.sc_shell:
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise TimeoutError("SC silent")
        return None

    s.target.activate.side_effect = activate_side_effect
    s._wait_for_sc_alive()
    assert call_count["n"] == 2
    # cold-cycle hit power.off + power.on once between attempts
    s.power.off.assert_called_once()
    s.power.on.assert_called_once()


def test_sc_alive_exhausts_retries_then_raises():
    s = _make_strategy()
    s.sc_login_retries = 1

    def activate_side_effect(driver):
        if driver is s.sc_shell:
            raise TimeoutError("SC silent")

    s.target.activate.side_effect = activate_side_effect
    with pytest.raises(TimeoutError):
        s._wait_for_sc_alive()


# ---------- SC commands phase --------------------------------------------


def test_sc_commands_empty_is_noop():
    s = _make_strategy()
    s.sc_commands = []
    s._run_sc_commands()
    s.sc_shell.run_check.assert_not_called()


def test_sc_commands_run_in_order():
    s = _make_strategy()
    s.sc_commands = ["uname -a", "echo ready"]
    s._run_sc_commands()
    assert s.sc_shell.run_check.call_count == 2
    s.sc_shell.run_check.assert_any_call("uname -a", timeout=s.wait_for_sc_command_timeout)
    s.sc_shell.run_check.assert_any_call("echo ready", timeout=s.wait_for_sc_command_timeout)


def test_sc_commands_retry_cold_cycles_and_redoes_login():
    s = _make_strategy()
    s.sc_command_retries = 1
    s.sc_commands = ["uname -a"]

    # First run_check raises, second succeeds.
    s.sc_shell.run_check.side_effect = [RuntimeError("hung"), None]

    s._run_sc_commands()
    assert s.sc_shell.run_check.call_count == 2
    # cold-cycle ran exactly once between attempts
    s.power.off.assert_called_once()
    s.power.on.assert_called_once()
    # SC login was redone after cold-cycle
    activate_calls = [c.args[0] for c in s.target.activate.call_args_list if c.args]
    assert s.sc_shell in activate_calls


def test_sc_commands_exhaust_retries_raises():
    s = _make_strategy()
    s.sc_command_retries = 1
    s.sc_commands = ["uname -a"]
    s.sc_shell.run_check.side_effect = RuntimeError("perma-hung")
    with pytest.raises(RuntimeError):
        s._run_sc_commands()


# ---------- Versal kernel banner phase -----------------------------------


def test_versal_banner_happy_path():
    s = _make_strategy()
    s.target_shell.console.expect.return_value = (None, b"booting kernel\n", None, None)
    s._wait_for_versal_kernel()
    s.target_shell.console.expect.assert_called_once_with(
        s.kernel_banner_pattern, timeout=s.wait_for_kernel_banner_timeout
    )
    assert "booting kernel" in s.boot_log


def test_retry_defaults_are_three():
    """Per spec: SC-hang and Versal-not-reaching-Linux both default to
    3 cold-cycle retries so transient issues self-recover."""
    s = _make_strategy()
    assert s.sc_login_retries == 3
    assert s.sc_command_retries == 3
    assert s.kernel_banner_retries == 3


def test_versal_banner_phase_is_read_only():
    """Strategy must not write to the Versal UART during boot watch — that
    would interrupt U-Boot autoboot. Only console.expect() is allowed."""
    s = _make_strategy()
    s.target_shell.console.expect.return_value = (None, b"kernel\n", None, None)
    s._wait_for_versal_kernel()
    s.target_shell.console.sendline.assert_not_called()
    s.target_shell.console.write.assert_not_called()


def test_kernel_banner_pattern_is_configurable():
    """Pattern is overridable so users can pick something tighter than 'Linux'."""
    s = _make_strategy()
    s.kernel_banner_pattern = "Linux version"
    s.target_shell.console.expect.return_value = (None, b"", None, None)
    s._wait_for_versal_kernel()
    s.target_shell.console.expect.assert_called_once_with(
        "Linux version", timeout=s.wait_for_kernel_banner_timeout
    )


def test_versal_banner_zero_byte_silence_retries():
    s = _make_strategy()
    s.kernel_banner_retries = 1

    timeout_exc = TimeoutError("silent")
    # Simulate pexpect-style state: console._expect.before is empty bytes on first attempt.
    expect_state = MagicMock()
    expect_state.before = b""
    s.target_shell.console._expect = expect_state

    expect_calls = {"n": 0}

    def expect_side_effect(*args, **kwargs):
        expect_calls["n"] += 1
        if expect_calls["n"] == 1:
            raise timeout_exc
        return (None, b"now booting\n", None, None)

    s.target_shell.console.expect.side_effect = expect_side_effect
    s._wait_for_versal_kernel()
    assert expect_calls["n"] == 2
    s.power.off.assert_called_once()
    s.power.on.assert_called_once()


def test_versal_banner_retries_even_with_output_captured():
    """Versal SD boot is expected to reach Linux every time; any timeout
    (silent OR stuck-at-U-Boot-prompt) gets a cold-cycle retry until
    kernel_banner_retries is exhausted.
    """
    s = _make_strategy()
    s.kernel_banner_retries = 1  # one retry → 2 total attempts

    expect_state = MagicMock()
    expect_state.before = b"Versal U-Boot autoboot timeout, dropped to prompt\n"
    s.target_shell.console._expect = expect_state

    expect_calls = {"n": 0}

    def expect_side_effect(*args, **kwargs):
        expect_calls["n"] += 1
        if expect_calls["n"] == 1:
            # First attempt: timeout WITH output captured.
            raise TimeoutError("stuck at u-boot prompt")
        # Second attempt: succeeds.
        return (None, b"booting kernel\n", None, None)

    s.target_shell.console.expect.side_effect = expect_side_effect
    s._wait_for_versal_kernel()
    assert expect_calls["n"] == 2
    # cold-cycle ran between attempts
    s.power.off.assert_called_once()
    s.power.on.assert_called_once()


def test_versal_banner_exhausts_retries_then_raises():
    s = _make_strategy()
    s.kernel_banner_retries = 1  # 2 total attempts

    expect_state = MagicMock()
    expect_state.before = b"some output"
    s.target_shell.console._expect = expect_state
    s.target_shell.console.expect.side_effect = TimeoutError("permanent")

    with pytest.raises(TimeoutError):
        s._wait_for_versal_kernel()
    assert s.target_shell.console.expect.call_count == 2


# ---------- transition() integration --------------------------------------


def test_transition_unknown_raises():
    s = _make_strategy()
    with pytest.raises(StrategyError):
        s.transition(Status.unknown)


def test_transition_status_string_resolves():
    """Strings should map to enum values, mirroring BootFPGASoC."""
    s = _make_strategy()
    s.transition("powered_off")
    assert s.status == Status.powered_off


def test_transition_powered_off_calls_power_off():
    s = _make_strategy()
    s.transition(Status.powered_off)
    s.power.off.assert_called_once()


def test_transition_same_status_is_noop():
    s = _make_strategy()
    s.status = Status.powered_off
    s.transition(Status.powered_off)
    s.power.off.assert_not_called()


def test_transition_sd_mux_to_host_requires_sdmux_binding():
    s = _make_strategy()  # no sdmux
    # @never_retry wraps any inner exception in "is in broken state" and stores
    # the original on self.broken — check the original to verify the right error.
    with pytest.raises(StrategyError):
        s.transition(Status.sd_mux_to_host)
    assert isinstance(s.broken, StrategyError)
    assert "sdmux" in str(s.broken)


def test_transition_update_boot_files_noop_when_disabled():
    s = _make_strategy()
    s.update_boot_files = False
    s.transition(Status.update_boot_files)
    assert s.status == Status.update_boot_files
    # No SD-mux or SSH activity.
    s.target.activate.assert_not_called()


def test_transition_booted_full_happy_path():
    s = _make_strategy()
    s.sc_commands = ["uname -a"]
    # Versal banner expects two successful expects: kernel banner, then prompt.
    s.target_shell.console.expect.side_effect = [
        (None, b"Starting kernel ...\n", None, None),
        (None, b"some boot log\n", None, None),
    ]

    s.transition(Status.booted)

    assert s.status == Status.booted
    s.power.off.assert_called()
    s.power.on.assert_called()
    s.sc_shell.run_check.assert_called_once_with("uname -a", timeout=s.wait_for_sc_command_timeout)
    # Versal expected two console.expect calls (banner + prompt).
    assert s.target_shell.console.expect.call_count == 2
    # boot_log accumulated text from both phases.
    assert "Starting kernel" in s.boot_log
    assert "some boot log" in s.boot_log


def test_transition_shell_activates_target_shell():
    s = _make_strategy()
    s.target_shell.console.expect.side_effect = [
        (None, b"Starting kernel ...\n", None, None),
        (None, b"prompt\n", None, None),
    ]
    s.transition(Status.shell)
    assert s.status == Status.shell
    # target_shell activated again at shell state (after deactivate at end of booted).
    activate_targets = [c.args[0] for c in s.target.activate.call_args_list if c.args]
    assert activate_targets.count(s.target_shell) >= 2
