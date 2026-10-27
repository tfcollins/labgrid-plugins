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
from adi_lg_plugins.hw_ci import power as power_types
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


def _ask_power() -> tuple[str, dict[str, str]]:
    """Ask for a power type by category, then that type's fields.

    Returns the type key and the template context for its ``power_*`` fields;
    optional fields left blank are omitted so the fragment's default applies.
    """
    console.print("[bold]Power control[/bold]")
    for category in power_types.CATEGORIES:
        keys = ", ".join(t.key for t in power_types.types_in(category))
        console.print(f"  {category}: {keys}")
    category = Prompt.ask(
        "Power category", choices=list(power_types.CATEGORIES), default=power_types.PLUG
    )
    in_category = [t.key for t in power_types.types_in(category)]
    power = Prompt.ask(
        "Power type",
        choices=in_category,
        default="vesync" if "vesync" in in_category else in_category[0],
    )
    context = {}
    for f in power_types.POWER_TYPES[power].fields:
        choices = power_types.choices_for(f.choices) if f.choices else None
        if f.default is None:
            context[f.var] = _ask_required(f"  {f.prompt}", choices=choices)
            continue
        answer = Prompt.ask(f"  {f.prompt}", choices=choices, default=f.default)
        if answer not in (None, ""):
            context[f.var] = answer
    return power, context


def _ask_required(prompt: str, **kwargs) -> str:
    """Ask until the answer is non-blank (the field has no default to fall back on)."""
    while True:
        answer = (Prompt.ask(prompt, **kwargs) or "").strip()
        if answer:
            return answer
        console.print("    [red]required - this field has no default[/red]")


def _ask_secret(prompt: str) -> str:
    """Ask for a token/password without echoing it.

    Hidden input shows nothing while typing or pasting, so confirm how much arrived.
    """
    secret = _ask_required(f"{prompt} (input hidden)", password=True)
    console.print(f"    [dim]received {len(secret)} characters[/dim]")
    return secret


@netbox_group.command(name="add-hardware")
@click.option("--netbox-url", envvar="NETBOX_URL", default=None, help="NetBox base URL")
@click.option("--netbox-token", envvar="NETBOX_TOKEN", default=None, help="NetBox API token")
@click.option(
    "--netbox-ca-bundle",
    envvar="NETBOX_CA_BUNDLE",
    type=click.Path(exists=True),
    default=None,
    help="Verify NetBox's TLS certificate against this CA bundle (e.g. an internal CA)",
)
@click.option(
    "--netbox-verify",
    is_flag=True,
    help="Verify NetBox's TLS certificate against Python's CA bundle (default: not verified)",
)
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
    netbox_url,
    netbox_token,
    netbox_ca_bundle,
    netbox_verify,
    coord,
    coord_user,
    coord_password,
    exporter_configs_dir,
    dry_run,
):
    """Interactively register a new board: NetBox + exporter host + labgrid place."""
    try:
        exporter_configs_dir = exporter_configs_dir or provision.find_exporter_configs_dir()
        # Check the optional `netbox` extra before asking anything; a dry run
        # never talks to NetBox, so it only needs the template renderer.
        provision._require_jinja2()
        if not dry_run:
            client._require_pynetbox()
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
    boot_strategy = Prompt.ask(
        "Boot strategy",
        choices=KNOWN_BOOT_STRATEGIES,
        default=provision.template_strategy(template_path),
    )
    power, power_context = _ask_power()
    power_type = power_types.POWER_TYPES[power]
    runner_label = Prompt.ask("GitHub runner label", default=f"hw-{carrier.lower()}")
    site_slug = Prompt.ask("NetBox site slug (must already exist)")
    ssh_target = Prompt.ask("Exporter host SSH target (user@host)")
    if "@" not in ssh_target:
        raise click.ClickException("SSH target must be in `user@host` form")
    ssh_user, ssh_host = ssh_target.split("@", 1)

    # Templates name their resource group <CARRIER>_<CHIP> from these fields
    # and include the power fragment named by `power`, so fill them from the
    # answers above instead of asking twice.
    context = {
        "carrier": carrier,
        "chip": daughter_board,
        "power": power,
        **power_context,
    }
    try:
        var_names = sorted(
            provision.discover_template_vars(template_path)
            - set(context)
            - provision.EXPORTER_RUNTIME_VARS
            - {f.var for t in power_types.POWER_TYPES.values() for f in t.fields}
        )
        required = provision.required_template_vars(template_path)
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e

    console.print(
        f"[bold]Template fields for {template_key}:[/bold] {', '.join(var_names) or '(none)'}"
    )
    # Required fields first, so they're not lost among the defaulted ones.
    for var in sorted(var_names, key=lambda v: v not in required):
        secret = "password" in var
        if var in required:
            context[var] = _ask_required(f"  {var} (required)", password=secret)
            continue
        answer = Prompt.ask(f"  {var} (blank = template default)", default="", password=secret)
        if answer:
            context[var] = answer

    console.print("\n[bold]Plan[/bold]")
    console.print(
        f"  NetBox device: {name}  (carrier={carrier}, chip={daughter_board}, site={site_slug})"
    )
    console.print(f"  Exporter: {ssh_target} -> systemd unit labgrid-exporter-{name}")
    power_tags = provision.power_tags(power)
    console.print(
        f"  Coordinator place: {name}  "
        f"(tags: daughter-board={daughter_board.lower()}, carrier={carrier.lower()}, "
        f"boot-strategy={boot_strategy}, runner={runner_label}, "
        + ", ".join(f"{k}={v}" for k, v in power_tags.items())
        + ")"
    )
    console.print(f"  Power: {power_type.label} ({power}), via {' + '.join(power_type.drivers)}")
    if power_type.credentials:
        console.print(
            "    credentials from "
            f"{provision.EXPORTER_ENV_FILE} on the exporter host: "
            + ", ".join(
                c.env + ("" if c.required else " (optional)") for c in power_type.credentials
            )
        )
    if power_type.reach == "client":
        console.print("    [yellow]the client (test runner) must reach this device[/yellow]")
    if power_type.note:
        console.print(f"    {power_type.note}")

    try:
        rendered_path, groups = provision.render_and_validate(
            template_path, context, exporter_configs_dir
        )
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e
    # The systemd unit runs `labgrid-exporter -n <name>`, so the coordinator
    # sees these resources under exporter <name>, not the SSH host name.
    match_patterns = [f"{name}/{group}/*" for group in groups]
    console.print(f"  Rendered + validated exporter config: {rendered_path}")
    console.print(f"  Resource group(s): {', '.join(groups)}")
    console.print(f"  Place match(es): {', '.join(match_patterns)}")

    if dry_run:
        console.print("\n[yellow]Dry run - no NetBox/SSH/coordinator changes made.[/yellow]")
        return

    if not Confirm.ask("\nProceed?", default=True):
        raise click.Abort()

    if not netbox_url:
        netbox_url = _ask_required("NetBox URL")
    if not netbox_token:
        netbox_token = _ask_secret("NetBox API token")

    coord_resolved = resolve_coordinator(coord)
    if not coord_user:
        coord_user = _ask_required("Coordinator API username")
    if not coord_password:
        coord_password = _ask_secret("Coordinator API password")

    # 1. NetBox: register the device (source of truth for inventory).
    # Lab NetBoxes commonly sit behind an internal CA, so checking is opt-in.
    verify = netbox_ca_bundle or netbox_verify
    if verify is False:
        console.print(
            "[dim]NetBox TLS certificate not verified "
            "(--netbox-verify or --netbox-ca-bundle to check it)[/dim]"
        )
    try:
        with client.reported_errors(netbox_url):
            nb = client.connect(netbox_url, netbox_token, verify=verify)
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
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e
    console.print(
        f"[green]NetBox device ready:[/green] {netbox_url.rstrip('/')}/dcim/devices/{device.id}/"
    )

    # 2. Exporter host: deploy + verify the systemd service.
    try:
        exporter_bin = provision.check_prerequisites(ssh_host)
        provision.deploy_exporter(
            ssh_host, ssh_user, name, rendered_path, coord_resolved, exporter_bin=exporter_bin
        )
        provision.verify_exporter_active(ssh_host, name)
        missing_env = provision.missing_power_env(ssh_host, power)
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e
    console.print(f"[green]labgrid-exporter-{name} is active on {ssh_host}[/green]")
    if missing_env:
        console.print(
            f"[yellow]Warning: {', '.join(missing_env)} not set in "
            f"{provision.EXPORTER_ENV_FILE} on {ssh_host} - power control will fail "
            f"until they are set and labgrid-exporter-{name} is restarted.[/yellow]"
        )

    # 3. Coordinator: create the place, match the live resources, tag it.
    api = _resolve_api(coord_resolved)
    try:
        cookie = coord_mod.login(api, coord_user, coord_password)
        create_place(api, cookie, name)
        for pattern in match_patterns:
            add_match(api, cookie, name, pattern)
        set_place_tags(
            api,
            cookie,
            name,
            {
                "daughter-board": daughter_board.lower(),
                "carrier": carrier.lower(),
                "boot-strategy": boot_strategy,
                "runner": runner_label,
                **power_tags,
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
