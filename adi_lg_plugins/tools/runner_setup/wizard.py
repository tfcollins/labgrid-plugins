"""Interactive terminal wizard for setting up a hardware runner."""

from __future__ import annotations

import os
import socket
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .auth import (
    is_gh_authenticated,
    list_scope_runners,
    login_gh_interactive,
    mint_registration_token,
    verify_scope_admin,
)
from .deps import build_ser2net_461, run_dependency_checks
from .hardware import (
    check_coordinator_reachability,
    scan_sdmux_devices,
    scan_serial_devices,
    validate_direct_env,
)
from .models import GitHubScope, HardwareMode, RunnerConfig
from .runner import (
    configure_runner,
    download_and_extract_runner,
    install_runner_dependencies,
)
from .service import get_runner_service_status, install_and_start_runner_service

console = Console()


def run_wizard() -> None:
    """Run interactive runner setup wizard."""
    console.print(
        Panel.fit(
            "[bold cyan]ADI Hardware CI Runner Setup Wizard[/bold cyan]\n"
            "Easily configure, register, and service a GitHub Actions runner for hardware testing.",
            border_style="cyan",
        )
    )

    # 1. Mode selection
    console.print("\n[bold]Step 1: Hardware Architecture Mode[/bold]")
    console.print(
        "  [1] [cyan]Exporter Style[/cyan]: Coordinates via labgrid coordinator (gRPC/REST)."
    )
    console.print(
        "  [2] [cyan]Direct Hardware[/cyan]: DUT is physically attached to this host directly."
    )
    choice = Prompt.ask("Select mode", choices=["1", "2"], default="1")
    mode = HardwareMode.EXPORTER if choice == "1" else HardwareMode.DIRECT

    # 2. Prerequisites & Dependency check
    console.print(f"\n[bold]Step 2: Checking Prerequisites ({mode.value} mode)...[/bold]")
    checks = run_dependency_checks(mode)

    table = Table(title="Prerequisites Check", show_header=True, header_style="bold")
    table.add_column("Component", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Details")

    has_failures = False
    ser2net_broken = False
    for c in checks:
        if c.passed:
            status = "[green]PASS[/green]"
        else:
            status = "[red]FAIL[/red]"
            has_failures = True
            if "ser2net" in c.name.lower():
                ser2net_broken = True
        table.add_row(c.name, status, c.message)

    console.print(table)
    if has_failures:
        console.print(
            "[yellow]Warning: Some checks did not pass. Review remediations above.[/yellow]"
        )

    if ser2net_broken and mode == HardwareMode.EXPORTER:
        if Confirm.ask(
            "ser2net is missing or 4.6.0. Would you like to build and install ser2net 4.6.1 into $HOME/opt/ser2net-4.6.1 now?"
        ):
            console.print("[cyan]Building ser2net 4.6.1 from source...[/cyan]")
            bin_path = build_ser2net_461()
            console.print(f"[green]ser2net 4.6.1 installed at {bin_path}[/green]")
            os.environ["PATH"] = f"{bin_path.parent}:{os.environ.get('PATH', '')}"

    # 3. Hardware / Coordinator Configuration
    coordinator = ""
    direct_env_file = None

    if mode == HardwareMode.EXPORTER:
        console.print("\n[bold]Step 3: Coordinator Connection[/bold]")
        default_coord = os.environ.get("LG_COORDINATOR", "10.0.0.41:20408")
        coordinator = Prompt.ask("Coordinator address (host:20408)", default=default_coord)
        console.print(f"Testing connectivity to [cyan]{coordinator}[/cyan]...")
        reach = check_coordinator_reachability(coordinator)
        if reach["grpc_reachable"]:
            console.print(f" [green]✓[/green] gRPC port {reach['grpc_port']} is reachable")
        else:
            console.print(
                f" [yellow]![/yellow] Warning: gRPC port {reach['grpc_port']} not reachable"
            )
        if reach["rest_reachable"]:
            console.print(f" [green]✓[/green] REST bridge port {reach['rest_port']} is reachable")
        else:
            console.print(
                f" [yellow]![/yellow] Warning: REST bridge {reach['rest_api']} not reachable"
            )
    else:
        console.print("\n[bold]Step 3: Direct Hardware Devices & Environment[/bold]")
        serials = scan_serial_devices()
        sdmux = scan_sdmux_devices()
        console.print(f"Detected serial devices: {len(serials)}")
        for s in serials[:3]:
            console.print(f"  - {s}")
        if len(serials) > 3:
            console.print(f"  ... and {len(serials) - 3} more")
        console.print(f"Detected SD mux devices: {len(sdmux)}")

        env_default = os.environ.get("LG_DIRECT_ENV", "")
        while True:
            env_input = Prompt.ask("Path to labgrid direct environment YAML", default=env_default)
            env_path = Path(env_input).expanduser().resolve()
            if validate_direct_env(env_path):
                direct_env_file = env_path
                console.print(f" [green]✓[/green] Validated env config at {env_path}")
                break
            if Confirm.ask(
                f"Warning: {env_path} does not exist or is not a valid labgrid config. Use it anyway?"
            ):
                direct_env_file = env_path
                break

    # 4. GitHub Scope & Authentication
    console.print("\n[bold]Step 4: GitHub Scope & Authentication[/bold]")
    scope_str = Prompt.ask("Enter GitHub scope (e.g. repo:owner/repo or org:orgname)")
    scope = GitHubScope.parse(scope_str)

    token = ""
    if is_gh_authenticated():
        console.print(" [green]✓[/green] GitHub CLI (gh) is authenticated")
        try:
            verify_scope_admin(scope)
            console.print(f" [green]✓[/green] Admin access confirmed on {scope.raw}")
            console.print(f"Minting registration token for [cyan]{scope.raw}[/cyan]...")
            token = mint_registration_token(scope)
            console.print(" [green]✓[/green] Registration token acquired")
        except Exception as e:
            console.print(f"[yellow]Could not automatically mint token: {e}[/yellow]")

    if not token:
        console.print("gh CLI authentication not ready or token minting failed.")
        if Confirm.ask("Would you like to run 'gh auth login' now?"):
            login_gh_interactive()
            try:
                token = mint_registration_token(scope)
                console.print(" [green]✓[/green] Registration token acquired")
            except Exception as e:
                console.print(f"[red]Error minting token: {e}[/red]")

    if not token:
        token = Prompt.ask(
            "Please paste GitHub runner registration token manually (Settings -> Actions -> Runners -> New runner)",
            password=True,
        )

    # 5. Runner Naming and Service
    console.print("\n[bold]Step 5: Runner Details[/bold]")
    hostname = socket.gethostname().split(".")[0]
    default_name = f"{hostname}-{scope.slug}"
    runner_name = Prompt.ask("Runner name", default=default_name)

    default_label = "hw-lab" if mode == HardwareMode.EXPORTER else "hw-direct"
    labels_input = Prompt.ask("Runner labels (comma-separated)", default=default_label)
    labels = [lbl.strip() for lbl in labels_input.split(",") if lbl.strip()]

    default_dir = Path.home() / f"actions-runner-{scope.slug}"
    dir_input = Prompt.ask("Install directory", default=str(default_dir))
    install_dir = Path(dir_input).expanduser().resolve()

    install_service = Confirm.ask("Install and start systemd service automatically?", default=True)

    config = RunnerConfig(
        mode=mode,
        scope=scope,
        name=runner_name,
        labels=labels,
        install_dir=install_dir,
        token=token,
        install_service=install_service,
        coordinator=coordinator,
        direct_env_file=direct_env_file,
    )

    # 6. Confirmation & Execution
    console.print(
        "\n"
        + Panel.fit(
            f"[bold]Summary of Actions:[/bold]\n"
            f" • Mode: [cyan]{config.mode.value}[/cyan]\n"
            f" • Scope: [cyan]{config.scope.raw}[/cyan] ({config.scope.url})\n"
            f" • Runner Name: [cyan]{config.name}[/cyan]\n"
            f" • Labels: [cyan]{', '.join(['self-hosted', *config.labels])}[/cyan]\n"
            f" • Directory: [cyan]{config.install_dir}[/cyan]\n"
            + (f" • Coordinator: [cyan]{config.coordinator}[/cyan]\n" if config.coordinator else "")
            + (
                f" • Direct Env: [cyan]{config.direct_env_file}[/cyan]\n"
                if config.direct_env_file
                else ""
            )
            + f" • Systemd Service: [cyan]{'Yes (sudo ./svc.sh)' if config.install_service else 'No'}[/cyan]",
            title="Confirmation",
            border_style="green",
        )
    )

    if not Confirm.ask("Proceed with runner installation?", default=True):
        console.print("[yellow]Setup aborted by user.[/yellow]")
        return

    console.print("\n[bold]Executing setup...[/bold]")
    with console.status("Downloading runner package..."):
        download_and_extract_runner(config.install_dir)
    console.print(" [green]✓[/green] Runner package extracted")

    with console.status("Installing runner dependencies..."):
        install_runner_dependencies(config.install_dir)
    console.print(" [green]✓[/green] Dependencies installed")

    with console.status(f"Configuring runner as '{config.name}'..."):
        configure_runner(config)
    console.print(" [green]✓[/green] Runner configured and .env written")

    if config.install_service:
        with console.status("Installing and starting systemd service..."):
            install_and_start_runner_service(config.install_dir)
        console.print(" [green]✓[/green] Systemd service installed and started")

    # 7. Verification
    console.print("\n[bold]Step 6: Verifying Runner Online...[/bold]")
    time.sleep(3)
    code, status_out = get_runner_service_status(config.install_dir)
    if code == 0:
        console.print(" [green]✓[/green] Local service status: active")
    else:
        console.print(f" [yellow]![/yellow] Service status output: {status_out}")

    runners = list_scope_runners(config.scope)
    matching = [r for r in runners if r.get("name") == config.name]
    if matching:
        r_info = matching[0]
        st = r_info.get("status", "unknown")
        color = "green" if st == "online" else "yellow"
        console.print(
            f" [{color}]✓[/{color}] GitHub reports runner [bold]{config.name}[/bold] is [{color}]{st}[/{color}]"
        )
    else:
        console.print(
            " [cyan]i[/cyan] Runner registered; waiting for first heartbeat to show in GitHub API."
        )

    console.print(
        Panel(
            "[bold green]Hardware runner setup completed successfully![/bold green]",
            border_style="green",
        )
    )
