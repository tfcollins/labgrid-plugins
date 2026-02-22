import pytest


def pytest_addoption(parser):
    """Add command-line options."""
    parser.addoption(
        "--lg-config",
        action="store",
        default=None,
        help="Path to a real Labgrid YAML configuration file for E2E testing.",
    )
    parser.addoption(
        "--run-hardware",
        action="store_true",
        default=False,
        help="Run tests that require real hardware.",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "hardware: mark test as requiring real hardware")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-hardware"):
        # --run-hardware given in cli: do not skip hardware tests
        return
    skip_hardware = pytest.mark.skip(reason="need --run-hardware option to run")
    for item in items:
        if "hardware" in item.keywords:
            item.add_marker(skip_hardware)


@pytest.fixture
def lg_config(request):
    """Fixture to retrieve the Labgrid configuration file path."""
    return request.config.getoption("--lg-config")
