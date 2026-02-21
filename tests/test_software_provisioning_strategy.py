import pytest
from unittest.mock import MagicMock, call
from adi_lg_plugins.strategies.software_provisioning import SoftwareProvisioningStrategy, Status

@pytest.fixture
def mock_installer_driver():
    return MagicMock()

@pytest.fixture
def provisioning_strategy(mock_installer_driver):
    target = MagicMock()
    # Mock the bind method to set the target on the item (strategy)
    def bind(item):
        item.target = target
    target.bind.side_effect = bind
    
    strategy = SoftwareProvisioningStrategy(target, "software_strat")
    strategy.installer = mock_installer_driver
    return strategy

def test_transition_software_installed(provisioning_strategy, mock_installer_driver):
    provisioning_strategy.packages = ["pkg1", "pkg2"]
    
    provisioning_strategy.transition(Status.software_installed)
    
    mock_installer_driver.install_package.assert_has_calls([
        call("pkg1"),
        call("pkg2")
    ])
    assert provisioning_strategy.status == Status.software_installed

def test_transition_repos_cloned(provisioning_strategy, mock_installer_driver):
    provisioning_strategy.repos = [
        ("http://repo1.git", "/tmp/repo1"),
        {"url": "http://repo2.git", "dest": "/tmp/repo2", "branch": "dev"}
    ]
    
    provisioning_strategy.transition(Status.repos_cloned)
    
    mock_installer_driver.clone_repo.assert_has_calls([
        call("http://repo1.git", "/tmp/repo1"),
        call("http://repo2.git", "/tmp/repo2", "dev")
    ])
    assert provisioning_strategy.status == Status.repos_cloned

def test_transition_built(provisioning_strategy, mock_installer_driver):
    provisioning_strategy.build_steps = [
        ("make", "/tmp/repo1"),
        {"cmd": "cargo build", "dir": "/tmp/repo2"}
    ]
    
    provisioning_strategy.transition(Status.built)
    
    mock_installer_driver.run_build.assert_has_calls([
        call("make", "/tmp/repo1"),
        call("cargo build", "/tmp/repo2")
    ])
    assert provisioning_strategy.status == Status.built

def test_transition_tested(provisioning_strategy, mock_installer_driver):
    provisioning_strategy.test_steps = [
        ("pytest", "/tmp/repo1"),
        {"cmd": "cargo test", "dir": "/tmp/repo2"}
    ]
    
    provisioning_strategy.transition(Status.tested)
    
    mock_installer_driver.run_test.assert_has_calls([
        call("pytest", "/tmp/repo1"),
        call("cargo test", "/tmp/repo2")
    ])
    assert provisioning_strategy.status == Status.tested
