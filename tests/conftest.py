import pytest


def pytest_addoption(parser):
    """Add command-line options."""
    parser.addoption(
        "--lg-config",
        action="store",
        default=None,
        help="Path to a real Labgrid YAML configuration file for E2E testing.",
    )


@pytest.fixture
def lg_config(request):
    """Fixture to retrieve the Labgrid configuration file path."""
    return request.config.getoption("--lg-config")
