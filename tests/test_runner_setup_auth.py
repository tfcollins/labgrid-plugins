from unittest.mock import MagicMock, patch

import pytest

from adi_lg_plugins.tools.runner_setup import auth
from adi_lg_plugins.tools.runner_setup.models import GitHubScope


@patch("shutil.which")
@patch("subprocess.run")
def test_is_gh_authenticated_true(mock_run, mock_which):
    mock_which.return_value = "/usr/bin/gh"
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_run.return_value = mock_proc

    assert auth.is_gh_authenticated() is True


@patch("shutil.which")
def test_is_gh_authenticated_missing(mock_which):
    mock_which.return_value = None
    assert auth.is_gh_authenticated() is False


@patch("shutil.which")
@patch("subprocess.run")
def test_verify_scope_admin_repo_pass(mock_run, mock_which):
    mock_which.return_value = "/usr/bin/gh"
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "true\n"
    mock_run.return_value = mock_proc

    scope = GitHubScope.parse("repo:owner/repo")
    auth.verify_scope_admin(scope)


@patch("shutil.which")
@patch("subprocess.run")
def test_verify_scope_admin_repo_fail(mock_run, mock_which):
    mock_which.return_value = "/usr/bin/gh"
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "false\n"
    mock_run.return_value = mock_proc

    scope = GitHubScope.parse("repo:owner/repo")
    with pytest.raises(auth.GitHubAuthError, match="Lack admin"):
        auth.verify_scope_admin(scope)


@patch("shutil.which")
@patch("subprocess.run")
def test_mint_registration_token_success(mock_run, mock_which):
    mock_which.return_value = "/usr/bin/gh"
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = "ABCDEFGHIJK12345\n"
    mock_run.return_value = mock_proc

    scope = GitHubScope.parse("repo:owner/repo")
    token = auth.mint_registration_token(scope)
    assert token == "ABCDEFGHIJK12345"


@patch("shutil.which")
@patch("subprocess.run")
def test_mint_registration_token_error(mock_run, mock_which):
    mock_which.return_value = "/usr/bin/gh"
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "Not Found"
    mock_run.return_value = mock_proc

    scope = GitHubScope.parse("repo:owner/repo")
    with pytest.raises(auth.GitHubAuthError, match="Failed to mint"):
        auth.mint_registration_token(scope)
