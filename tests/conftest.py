import pytest

# Tests that use labgrid's built-in `strategy` fixture crash at collection
# when no --lg-env is provided (labgrid hook accesses env.config which is None).
# Exclude these modules unless --run-hardware is given via collect_ignore_glob.
collect_ignore_glob = [
    "test_soc_strat.py",
    "test_soc_strat_custom.py",
    "test_soc_strat_tftp.py",
    "test_rpi_hw.py",
    "test_vpk180_hw.py",
]


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
