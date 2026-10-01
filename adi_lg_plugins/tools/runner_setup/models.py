"""Data models and schemas for runner setup."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class HardwareMode(str, Enum):
    """Runner hardware setup mode."""

    EXPORTER = "exporter"
    DIRECT = "direct"


class ScopeType(str, Enum):
    """GitHub runner scope type."""

    REPO = "repo"
    ORG = "org"


@dataclass(frozen=True)
class GitHubScope:
    """Represents a validated GitHub scope (e.g. repo:owner/name or org:orgname)."""

    raw: str
    scope_type: ScopeType
    target: str

    @classmethod
    def parse(cls, value: str) -> GitHubScope:
        value = value.strip()
        if value.startswith("repo:"):
            target = value[len("repo:") :].strip()
            if "/" not in target or len(target.split("/")) != 2:
                raise ValueError(
                    f"invalid repo scope format '{value}'; expected 'repo:owner/repository'"
                )
            return cls(raw=value, scope_type=ScopeType.REPO, target=target)
        if value.startswith("org:"):
            target = value[len("org:") :].strip()
            if not target or "/" in target:
                raise ValueError(f"invalid org scope format '{value}'; expected 'org:orgname'")
            return cls(raw=value, scope_type=ScopeType.ORG, target=target)

        # Heuristic if prefix omitted
        if "/" in value:
            return cls(raw=f"repo:{value}", scope_type=ScopeType.REPO, target=value)
        raise ValueError(
            f"invalid scope '{value}'; must start with 'repo:owner/repo' or 'org:orgname'"
        )

    @property
    def slug(self) -> str:
        """Slug for directory and runner naming."""
        if self.scope_type == ScopeType.ORG:
            return f"org-{self.target}"
        return f"repo-{self.target.replace('/', '-')}"

    @property
    def url(self) -> str:
        """GitHub base URL for the scope."""
        return f"https://github.com/{self.target}"

    @property
    def registration_token_endpoint(self) -> str:
        """GitHub REST API endpoint to mint a runner registration token."""
        if self.scope_type == ScopeType.ORG:
            return f"/orgs/{self.target}/actions/runners/registration-token"
        return f"/repos/{self.target}/actions/runners/registration-token"

    @property
    def list_runners_endpoint(self) -> str:
        """GitHub REST API endpoint to list runners in this scope."""
        if self.scope_type == ScopeType.ORG:
            return f"/orgs/{self.target}/actions/runners"
        return f"/repos/{self.target}/actions/runners"


@dataclass
class RunnerConfig:
    """Configuration for setting up a GitHub Actions runner."""

    mode: HardwareMode
    scope: GitHubScope
    name: str = ""
    labels: list[str] = field(default_factory=list)
    install_dir: Path = field(default_factory=lambda: Path(os.path.expanduser("~/actions-runner")))
    token: str = ""
    install_service: bool = True
    dry_run: bool = False
    non_interactive: bool = False

    # Exporter-specific
    coordinator: str = ""

    # Direct-specific
    direct_env_file: Path | None = None

    def __post_init__(self) -> None:
        if not self.name:
            hostname = socket.gethostname().split(".")[0]
            self.name = f"{hostname}-{self.scope.slug}"
        if not self.labels:
            default_label = "hw-lab" if self.mode == HardwareMode.EXPORTER else "hw-direct"
            self.labels = [default_label]


@dataclass
class CheckItem:
    """Diagnostic check result."""

    name: str
    passed: bool
    message: str
    remediation: str = ""
