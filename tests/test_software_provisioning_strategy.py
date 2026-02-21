import pytest
from unittest.mock import MagicMock, call
from adi_lg_plugins.strategies.software_provisioning import SoftwareProvisioningStrategy, Status
from labgrid.strategy import StrategyError

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

def test_transition_repos_cloned_invalid(provisioning_strategy):
    provisioning_strategy.repos = ["invalid_string_format"]
    
    with pytest.raises(ValueError, match="Invalid repo configuration"):
        provisioning_strategy.transition(Status.repos_cloned)

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

def test_transition_built_invalid(provisioning_strategy):
    provisioning_strategy.build_steps = ["invalid"]
    with pytest.raises(ValueError, match="Invalid build step configuration"):
        provisioning_strategy.transition(Status.built)

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

def test_transition_tested_invalid(provisioning_strategy):
    provisioning_strategy.test_steps = ["invalid"]
    with pytest.raises(ValueError, match="Invalid test step configuration"):
        provisioning_strategy.transition(Status.tested)

def test_transition_unknown_error(provisioning_strategy):
    with pytest.raises(StrategyError, match="can not transition to Status.unknown"):
        provisioning_strategy.transition(Status.unknown)

def test_transition_driver_failure(provisioning_strategy, mock_installer_driver):
    provisioning_strategy.packages = ["pkg1"]
    mock_installer_driver.install_package.side_effect = Exception("Install failed")
    
    with pytest.raises(Exception, match="Install failed"):
        provisioning_strategy.transition(Status.software_installed)

def test_transition_skip_same_status(provisioning_strategy, mock_installer_driver):
    # Manually set status
    provisioning_strategy.status = Status.software_installed
    
    # Try to transition to same status
    provisioning_strategy.transition(Status.software_installed)
    assert not mock_installer_driver.install_package.called

def test_transition_recursive(provisioning_strategy, mock_installer_driver):
    # Test that requesting 'tested' triggers all previous steps
    provisioning_strategy.packages = ["pkg1"]
    provisioning_strategy.repos = [("url", "dest")]
    provisioning_strategy.build_steps = [("make", "dir")]
    provisioning_strategy.test_steps = [("test", "dir")]
    
    # Mock status updates to simulate progress if needed, but the recursive call 
    # structure in Strategy simply calls transition(prev_state) first.
    # Since we are mocking the driver methods, they don't change state.
    # The Strategy base class or our implementation handles the recursion.
    # Our implementation:
    # elif status == Status.tested:
    #      self.transition(Status.built) ...
    
    provisioning_strategy.transition(Status.tested)
    
    # Check that all methods were called
    assert mock_installer_driver.install_package.called
    assert mock_installer_driver.clone_repo.called
    assert mock_installer_driver.run_build.called
    assert mock_installer_driver.run_test.called
    
    # Check final status
    assert provisioning_strategy.status == Status.tested

def test_transition_connected(provisioning_strategy):
    provisioning_strategy.transition(Status.connected)
    # verify installer activated
    # strategy.target.activate is a mock
    provisioning_strategy.target.activate.assert_called_with(provisioning_strategy.installer)
    assert provisioning_strategy.status == Status.connected
