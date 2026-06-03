"""Exceptions and CLI exit codes for the hardware-request layer."""

# Infra exit codes sit well above typical test-runner codes (0-5) so a GitHub
# Actions leg can tell an infra problem from a real test failure.
EXIT_NO_MATCH = 10  # request can never be satisfied (unknown part / no such board)
EXIT_UNAVAILABLE = 11  # matching board(s) exist but none free within `wait`
EXIT_PROVISION = 12  # boot failed


class RequestError(Exception):
    """Base class for hardware-request failures."""


class NoMatchingBoard(RequestError):
    """No place can satisfy the request (catalog/tags); do not wait."""


class BoardUnavailable(RequestError):
    """Matching boards exist but none became free within the wait window."""


class ProvisionError(RequestError):
    """Booting the acquired board failed."""

    def __init__(self, message: str, console_tail: str = ""):
        super().__init__(message)
        self.console_tail = console_tail
