"""GitHub authentication and runner token minting."""

from __future__ import annotations

import json
import shutil
import subprocess

from .models import GitHubScope, ScopeType


class GitHubAuthError(RuntimeError):
    """Raised when GitHub authentication or permission check fails."""


def is_gh_authenticated() -> bool:
    """Check if gh CLI is installed and authenticated."""
    if shutil.which("gh") is None:
        return False
    res = subprocess.run(
        ["gh", "auth", "status", "-h", "github.com"],
        capture_output=True,
        text=True,
        check=False,
    )
    return res.returncode == 0


def login_gh_interactive() -> bool:
    """Run interactive gh auth login."""
    if shutil.which("gh") is None:
        raise GitHubAuthError("gh CLI is not installed on PATH.")
    res = subprocess.run(["gh", "auth", "login"], check=False)
    return res.returncode == 0


def verify_scope_admin(scope: GitHubScope) -> None:
    """Verify current authenticated gh user has admin rights on the target scope."""
    if shutil.which("gh") is None:
        raise GitHubAuthError("gh CLI is not installed.")

    if scope.scope_type == ScopeType.REPO:
        res = subprocess.run(
            ["gh", "api", f"/repos/{scope.target}", "--jq", ".permissions.admin"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            raise GitHubAuthError(
                f"Failed to access repository '{scope.target}'. Check repo name and gh credentials."
            )
        if res.stdout.strip() != "true":
            raise GitHubAuthError(
                f"Lack admin permissions on repo '{scope.target}' — admin rights are required to mint runner tokens."
            )
    elif scope.scope_type == ScopeType.ORG:
        res = subprocess.run(
            ["gh", "api", f"/orgs/{scope.target}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            raise GitHubAuthError(
                f"Failed to access organization '{scope.target}'. Check org name and gh scope (admin:org)."
            )


def mint_registration_token(scope: GitHubScope) -> str:
    """Mint a new runner registration token using gh CLI."""
    if shutil.which("gh") is None:
        raise GitHubAuthError("gh CLI is required to automatically mint runner tokens.")

    endpoint = scope.registration_token_endpoint
    res = subprocess.run(
        ["gh", "api", "-X", "POST", endpoint, "--jq", ".token"],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        raise GitHubAuthError(
            f"Failed to mint runner token for '{scope.raw}': {res.stderr.strip()}"
        )
    token = res.stdout.strip()
    if not token:
        raise GitHubAuthError(f"GitHub returned an empty runner token for '{scope.raw}'.")
    return token


def list_scope_runners(scope: GitHubScope) -> list[dict]:
    """Query list of existing runners in scope from GitHub API."""
    if shutil.which("gh") is None:
        return []
    res = subprocess.run(
        ["gh", "api", "--paginate", scope.list_runners_endpoint],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        return []
    try:
        data = json.loads(res.stdout)
        if isinstance(data, dict):
            return data.get("runners", [])
        if isinstance(data, list):
            runners = []
            for item in data:
                runners.extend(item.get("runners", []))
            return runners
    except Exception:
        return []
    return []
