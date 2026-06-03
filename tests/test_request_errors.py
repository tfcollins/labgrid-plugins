from adi_lg_plugins.request.errors import (
    EXIT_NO_MATCH,
    EXIT_PROVISION,
    EXIT_UNAVAILABLE,
    BoardUnavailable,
    NoMatchingBoard,
    ProvisionError,
    RequestError,
)


def test_exit_codes_are_distinct():
    assert len({EXIT_NO_MATCH, EXIT_UNAVAILABLE, EXIT_PROVISION}) == 3


def test_exceptions_subclass_request_error():
    for exc in (NoMatchingBoard, BoardUnavailable, ProvisionError):
        assert issubclass(exc, RequestError)
