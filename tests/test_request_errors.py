from __future__ import annotations

from adi_lg_plugins.request import errors


def test_exit_codes_are_distinct_and_above_test_runner_codes():
    codes = {errors.EXIT_NO_MATCH, errors.EXIT_UNAVAILABLE, errors.EXIT_PROVISION}
    assert codes == {10, 11, 12}  # distinct, and clear of typical pytest codes (0-5)


def test_exception_hierarchy():
    for cls in (errors.NoMatchingBoard, errors.BoardUnavailable, errors.ProvisionError):
        assert issubclass(cls, errors.RequestError)


def test_provision_error_carries_console_tail():
    e = errors.ProvisionError("boot failed", console_tail="...panic...")
    assert str(e) == "boot failed"
    assert e.console_tail == "...panic..."


def test_provision_error_console_tail_defaults_empty():
    assert errors.ProvisionError("x").console_tail == ""
