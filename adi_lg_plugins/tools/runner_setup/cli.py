"""Click CLI command implementation for runner setup."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .auth import (
    is_gh_authenticated,
    mint_registration_token,
    verify_scope_admin,
)
from .deps import run_dependency_checks
from .models import GitHubScope, HardwareMode, RunnerConfig
from .runner import (
    configure_runner,
    download_and_extract_runner,
    install_runner_dependencies,
)
from .service import install_and_start_runner_service
from .wizard import run_wizard

console = Console()


@click.command(name="setup-runner")
@click.option(
    "--mode",
    type=click.Choice(["exporter", "direct"], case_sensitive=False),
    help="Hardware setup mode (exporter or direct).",
)
@click.option(
    "--scope",
    "-s",
    help="GitHub scope: repo:OWNER/REPO or org:ORGNAME.",
)
@click.option(
    "--name",
    "-n",
    help="Runner name (default: <hostname>-<scope-slug>).",
)
@click.option(
    "--labels",
    "-l",
    help="Comma-separated runner labels (e.g. 'hw-lab,zcu102').",
)
@click.option(
    "--dir",
    "install_dir",
    type=click.Path(path_type=Path),
    help="Runner installation directory.",
)
@click.option(
    "--coord",
    "-c",
    help="Coordinator host:port for exporter mode (default: $LG_COORDINATOR).",
)
@click.option(
    "--env-file",
    "-e",
    type=click.Path(path_type=Path),
    help="Labgrid direct environment YAML for direct mode.",
)
@click.option(
    "--token",
    "-t",
    help="GitHub runner registration token (bypasses gh auth).",
)
@click.option(
    "--service/--no-service",
    default=True,
    help="Install and start runner as a systemd service (default: True).",
)
@click.option(
    "--non-interactive",
    "--unattended",
    is_flag=True,
    help="Run without interactive prompts (fails if required options missing).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview actions without downloading or installing.",
)
@click.option(
    "--check-only",
    is_flag=True,
    help="Only perform prerequisite checks and exit.",
)
def setup_runner_cmd(
    mode: str | None,
    scope: str | None,
    name: str | None,
    labels: str | None,
    install_dir: Path | None,
    coord: str | None,
    env_file: Path | None,
    token: str | None,
    service: bool,
    non_interactive: bool,
    dry_run: bool,
    check_only: bool,
) -> None:
    """Setup, configure, and service a GitHub Actions hardware runner.

    Supports both 'exporter' (coordinator-backed) and 'direct' (attached DUT) modes.
    Run interactively without arguments or pass CLI options for automated provisioning.
    """
    hw_mode = HardwareMode(mode.lower()) if mode else None

    # Handle --check-only
    if check_only:
        target_mode = hw_mode or HardwareMode.EXPORTER
        checks = run_dependency_checks(target_mode)
        table = Table(title=f"Prerequisites Check ({target_mode.value} mode)")
        table.add_column("Component")
        table.add_column("Status", justify="center")
        table.add_column("Details")
        has_fail = False
        for c in checks:
            status = "[green]PASS[/green]" if c.passed else "[red]FAIL[/red]"
            if not c.passed:
                has_fail = True
            table.add_row(c.name, status, c.message)
        console.print(table)
        sys.exit(1 if has_fail else 0)

    # Determine if we should run the interactive wizard
    is_interactive = not non_interactive and sys.stdin.isatty() and not (scope and hw_mode)
    if is_interactive:
        run_wizard()
        return

    # Non-interactive / parameterized mode validation
    if not hw_mode:
        raise click.UsageError("--mode [exporter|direct] is required in non-interactive mode.")
    if not scope:
        raise click.UsageError("--scope (repo:OWNER/REPO or org:ORG) is required.")

    gh_scope = GitHubScope.parse(scope)
    coord_val = coord or os.environ.get("LG_COORDINATOR", "")

    if hw_mode == HardwareMode.EXPORTER and not coord_val:
        raise click.UsageError(
            "--coord <host:20408> or $LG_COORDINATOR is required for exporter mode."
        )
    if hw_mode == HardwareMode.DIRECT and not env_file:
        raise click.UsageError("--env-file <path.yaml> is required for direct mode.")

    parsed_labels = [lbl.strip() for lbl in labels.split(",") if lbl.strip()] if labels else []
    dest_dir = (
        install_dir.expanduser().resolve()
        if install_dir
        else Path.home() / f"actions-runner-{gh_scope.slug}"
    )

    # Resolve token
    reg_token = token or ""
    if not reg_token:
        if dry_run:
            reg_token = "DRY_RUN_TOKEN"
        else:
            if not is_gh_authenticated():
                raise click.ClickException(
                    "gh CLI is not authenticated and no --token provided. "
                    "Run 'gh auth login' or pass --token <REGISTRATION_TOKEN>."
                )
            verify_scope_admin(gh_scope)
            reg_token = mint_registration_token(gh_scope)

    runner_cfg = RunnerConfig(
        mode=hw_mode,
        scope=gh_scope,
        name=name or "",
        labels=parsed_labels,
        install_dir=dest_dir,
        token=reg_token,
        install_service=service,
        dry_run=dry_run,
        non_interactive=non_interactive,
        coordinator=coord_val,
        direct_env_file=env_file,
    )

    console.print(
        Panel.fit(
            f"[bold]Runner Configuration:[/bold]\n"
            f" • Mode: [cyan]{runner_cfg.mode.value}[/cyan]\n"
            f" • Scope: [cyan]{runner_cfg.scope.raw}[/cyan]\n"
            f" • Name: [cyan]{runner_cfg.name}[/cyan]\n"
            f" • Labels: [cyan]{', '.join(['self-hosted', *runner_cfg.labels])}[/cyan]\n"
            f" • Directory: [cyan]{runner_cfg.install_dir}[/cyan]\n"
            + (
                f" • Coordinator: [cyan]{runner_cfg.coordinator}[/cyan]\n"
                if runner_cfg.coordinator
                else ""
            )
            + (
                f" • Direct Env: [cyan]{runner_cfg.direct_env_file}[/cyan]\n"
                if runner_cfg.direct_env_file
                else ""
            )
            + f" • Install Service: [cyan]{runner_cfg.install_service}[/cyan]\n"
            + (" • [yellow]DRY RUN ACTIVE[/yellow]\n" if runner_cfg.dry_run else ""),
            title="Setup Hardware Runner",
            border_style="cyan",
        )
    )

    if dry_run:
        console.print("[yellow]Dry-run complete: no changes were made to the system.[/yellow]")
        return

    # Execute installation
    console.print("[bold]Downloading and extracting runner...[/bold]")
    download_and_extract_runner(runner_cfg.install_dir, dry_run=dry_run)

    console.print("[bold]Installing runner dependencies...[/bold]")
    install_runner_dependencies(runner_cfg.install_dir, dry_run=dry_run)

    console.print(f"[bold]Configuring runner '{runner_cfg.name}'...[/bold]")
    configure_runner(runner_cfg)

    if runner_cfg.install_service:
        console.print("[bold]Installing and starting systemd service...[/bold]")
        install_and_start_runner_service(runner_cfg.install_dir, dry_run=dry_run)

    console.print("[bold green]Runner setup completed successfully![/bold green]")


def main() -> None:
    """Entry point for standalone script."""
    setup_runner_cmd()
