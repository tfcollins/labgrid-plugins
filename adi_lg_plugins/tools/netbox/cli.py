"""`adi-lg netbox add-hardware` - interactive onboarding.

Registers a new board in NetBox, renders+validates its exporter config,
SSH-deploys it as a systemd service on the exporter host and verifies it
comes up, then creates the matching labgrid Place (create/add-match/
set-tags) on the coordinator. See
docs/source/user-guide/netbox-onboarding.rst for prerequisites.
"""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.prompt import Confirm, Prompt

from adi_lg_plugins.hw_ci import coordinator as coord_mod
from adi_lg_plugins.hw_ci.coordinator import (
    _resolve_api,
    add_match,
    create_place,
    fetch_raw_places,
    resolve_coordinator,
    set_place_tags,
)

from . import client, provision

console = Console()

# Known labgrid-plugins boot strategy classes (pyproject.toml's
# [project.entry-points."labgrid.strategies"]) - mirrors the hardcoded
# KNOWN_CLASSES allow-list style already used in exporter_configs/validate.py.
KNOWN_BOOT_STRATEGIES = [
    "BootFPGASoC",
    "BootFPGASoCSSH",
    "BootSelMap",
    "BootFabric",
    "BootFPGASoCTFTP",
    "BootRPI",
    "BootVPK180",
    "BootZynqMPJTAG",
    "BootZynq7000JTAGRecovery",
    "BootNoOSJTAG",
    "BootOpenFPGALoader",
    "BootTickFPGASSH",
]


@click.group(name="netbox")
def netbox_group():
    """NetBox inventory integration for labgrid lab hardware."""


def _discover_templates(exporter_configs_dir: Path) -> dict[str, Path]:
    templates_dir = exporter_configs_dir / "templates"
    return {p.stem: p for p in sorted(templates_dir.glob("*.yaml"))}


@netbox_group.command(name="add-hardware")
@click.option("--netbox-url", envvar="NETBOX_URL", default=None, help="NetBox base URL")
@click.option("--netbox-token", envvar="NETBOX_TOKEN", default=None, help="NetBox API token")
@click.option("--coord", default=None, help="Coordinator host:port (default: $LG_COORDINATOR)")
@click.option(
    "--coord-user", envvar="LG_API_USERNAME", default=None, help="Coordinator API username"
)
@click.option(
    "--coord-password", envvar="LG_API_PASSWORD", default=None, help="Coordinator API password"
)
@click.option(
    "--exporter-configs-dir",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    default=None,
    help="Path to the exporter_configs/ dir (default: searched upward from cwd)",
)
@click.option("--dry-run", is_flag=True, help="Render/print the plan; make no changes")
def add_hardware(
    netbox_url, netbox_token, coord, coord_user, coord_password, exporter_configs_dir, dry_run
):
    """Interactively register a new board: NetBox + exporter host + labgrid place."""
    try:
        exporter_configs_dir = exporter_configs_dir or provision.find_exporter_configs_dir()
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e

    templates = _discover_templates(exporter_configs_dir)
    if not templates:
        raise click.ClickException(f"no templates found under {exporter_configs_dir / 'templates'}")

    console.print(f"[bold]Available board templates:[/bold] {', '.join(sorted(templates))}")
    template_key = Prompt.ask(
        "Board template", choices=sorted(templates), default=sorted(templates)[0]
    )
    template_path = templates[template_key]

    name = Prompt.ask("Hardware / place / exporter name (e.g. zcu102-lab3-001)")
    carrier = Prompt.ask("Carrier (board/FPGA, e.g. zcu102, vcu118)")
    daughter_board = Prompt.ask("Daughter board / chip (e.g. ad9081)")
    boot_strategy = Prompt.ask("Boot strategy", choices=KNOWN_BOOT_STRATEGIES)
    runner_label = Prompt.ask("GitHub runner label", default=f"hw-{carrier.lower()}")
    site_slug = Prompt.ask("NetBox site slug (must already exist)")
    ssh_target = Prompt.ask("Exporter host SSH target (user@host)")
    if "@" not in ssh_target:
        raise click.ClickException("SSH target must be in `user@host` form")
    ssh_user, ssh_host = ssh_target.split("@", 1)

    try:
        var_names = sorted(provision.discover_template_vars(template_path) - {"exporter_name"})
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e

    console.print(
        f"[bold]Template fields for {template_key}:[/bold] {', '.join(var_names) or '(none)'}"
    )
    context = {"exporter_name": ssh_host}
    for var in var_names:
        answer = Prompt.ask(f"  {var} (blank = template default)", default="")
        if answer:
            context[var] = answer

    console.print("\n[bold]Plan[/bold]")
    console.print(
        f"  NetBox device: {name}  (carrier={carrier}, chip={daughter_board}, site={site_slug})"
    )
    console.print(f"  Exporter: {ssh_target} -> systemd unit labgrid-exporter-{name}")
    console.print(
        f"  Coordinator place: {name}  "
        f"(tags: daughter-board={daughter_board.lower()}, carrier={carrier.lower()}, "
        f"boot-strategy={boot_strategy}, runner={runner_label})"
    )

    try:
        rendered_path, groups = provision.render_and_validate(
            template_path, context, exporter_configs_dir
        )
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e
    console.print(f"  Rendered + validated exporter config: {rendered_path}")
    console.print(f"  Resource group(s): {', '.join(groups)}")

    if dry_run:
        console.print("\n[yellow]Dry run - no NetBox/SSH/coordinator changes made.[/yellow]")
        return

    if not Confirm.ask("\nProceed?", default=True):
        raise click.Abort()

    if not netbox_url:
        netbox_url = Prompt.ask("NetBox URL")
    if not netbox_token:
        netbox_token = Prompt.ask("NetBox API token", password=True)

    coord_resolved = resolve_coordinator(coord)
    if not coord_user:
        coord_user = Prompt.ask("Coordinator API username")
    if not coord_password:
        coord_password = Prompt.ask("Coordinator API password", password=True)

    # 1. NetBox: register the device (source of truth for inventory).
    nb = client.connect(netbox_url, netbox_token)
    client.ensure_schema(nb)
    device = client.create_or_update_device(
        nb,
        name,
        carrier=carrier,
        site_slug=site_slug,
        custom_fields={
            "carrier": carrier,
            "daughter_board": daughter_board,
            "boot_strategy": boot_strategy,
            "exporter_host": ssh_target,
            "runner_label": runner_label,
        },
    )
    console.print(
        f"[green]NetBox device ready:[/green] {netbox_url.rstrip('/')}/dcim/devices/{device.id}/"
    )

    # 2. Exporter host: deploy + verify the systemd service.
    try:
        provision.check_prerequisites(ssh_host)
        provision.deploy_exporter(ssh_host, ssh_user, name, rendered_path, coord_resolved)
        provision.verify_exporter_active(ssh_host, name)
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e
    console.print(f"[green]labgrid-exporter-{name} is active on {ssh_host}[/green]")

    # 3. Coordinator: create the place, match the live resources, tag it.
    api = _resolve_api(coord_resolved)
    try:
        cookie = coord_mod.login(api, coord_user, coord_password)
        create_place(api, cookie, name)
        for group in groups:
            add_match(api, cookie, name, f"{ssh_host}/{group}/*")
        set_place_tags(
            api,
            cookie,
            name,
            {
                "daughter-board": daughter_board.lower(),
                "carrier": carrier.lower(),
                "boot-strategy": boot_strategy,
                "runner": runner_label,
            },
        )
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e
    console.print(f"[green]Place {name!r} created, matched, and tagged on the coordinator.[/green]")

    places, _skipped = fetch_raw_places(coord_resolved)
    created = next((p for p in places if p.get("name") == name), None)
    if created:
        console.print(f"\n[bold green]Done.[/bold green] {name} tags: {created.get('tags')}")
    else:
        console.print(
            f"\n[yellow]Done, but {name!r} wasn't found in a fresh /api/places listing - "
            "double-check it on the coordinator.[/yellow]"
        )
