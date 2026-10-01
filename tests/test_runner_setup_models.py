import pytest

from adi_lg_plugins.tools.runner_setup.models import (
    GitHubScope,
    HardwareMode,
    RunnerConfig,
    ScopeType,
)


def test_github_scope_repo():
    scope = GitHubScope.parse("repo:analogdevicesinc/labgrid-plugins")
    assert scope.scope_type == ScopeType.REPO
    assert scope.target == "analogdevicesinc/labgrid-plugins"
    assert scope.slug == "repo-analogdevicesinc-labgrid-plugins"
    assert scope.url == "https://github.com/analogdevicesinc/labgrid-plugins"
    assert (
        scope.registration_token_endpoint
        == "/repos/analogdevicesinc/labgrid-plugins/actions/runners/registration-token"
    )
    assert scope.list_runners_endpoint == "/repos/analogdevicesinc/labgrid-plugins/actions/runners"


def test_github_scope_org():
    scope = GitHubScope.parse("org:analogdevicesinc")
    assert scope.scope_type == ScopeType.ORG
    assert scope.target == "analogdevicesinc"
    assert scope.slug == "org-analogdevicesinc"
    assert scope.url == "https://github.com/analogdevicesinc"
    assert (
        scope.registration_token_endpoint
        == "/orgs/analogdevicesinc/actions/runners/registration-token"
    )
    assert scope.list_runners_endpoint == "/orgs/analogdevicesinc/actions/runners"


def test_github_scope_bare_repo():
    scope = GitHubScope.parse("tfcollins/labgrid-plugins")
    assert scope.scope_type == ScopeType.REPO
    assert scope.target == "tfcollins/labgrid-plugins"
    assert scope.slug == "repo-tfcollins-labgrid-plugins"


def test_github_scope_invalid():
    with pytest.raises(ValueError, match="invalid"):
        GitHubScope.parse("invalid-scope-format")

    with pytest.raises(ValueError, match="invalid repo"):
        GitHubScope.parse("repo:invalid")

    with pytest.raises(ValueError, match="invalid org"):
        GitHubScope.parse("org:invalid/extra")


def test_runner_config_defaults():
    scope = GitHubScope.parse("repo:foo/bar")
    cfg = RunnerConfig(mode=HardwareMode.EXPORTER, scope=scope)
    assert "repo-foo-bar" in cfg.name
    assert cfg.labels == ["hw-lab"]

    cfg_direct = RunnerConfig(mode=HardwareMode.DIRECT, scope=scope)
    assert cfg_direct.labels == ["hw-direct"]
