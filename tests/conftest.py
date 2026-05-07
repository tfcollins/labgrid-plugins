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
    "test_zynq7000_recovery_hw.py",
    "test_vpk180_reflash_hw.py",
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
    parser.addoption(
        "--run-destructive",
        action="store_true",
        default=False,
        help=(
            "Also run hardware tests that overwrite persistent storage on the DUT "
            "(e.g. SD card flashing). Implies --run-hardware."
        ),
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "hardware: mark test as requiring real hardware")
    config.addinivalue_line(
        "markers",
        "destructive: mark test as overwriting persistent state on the DUT "
        "(requires --run-destructive)",
    )


def pytest_collection_modifyitems(config, items):
    skip_hardware = pytest.mark.skip(reason="need --run-hardware option to run")
    skip_destructive = pytest.mark.skip(
        reason="need --run-destructive option to run (overwrites DUT storage)"
    )
    run_hw = config.getoption("--run-hardware") or config.getoption("--run-destructive")
    run_destructive = config.getoption("--run-destructive")
    for item in items:
        if "hardware" in item.keywords and not run_hw:
            item.add_marker(skip_hardware)
        if "destructive" in item.keywords and not run_destructive:
            item.add_marker(skip_destructive)


@pytest.fixture
def lg_config(request):
    """Fixture to retrieve the Labgrid configuration file path."""
    return request.config.getoption("--lg-config")
