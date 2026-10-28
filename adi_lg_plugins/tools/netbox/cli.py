"""`adi-lg netbox add-hardware` - interactive onboarding.

Registers a new board in NetBox, renders+validates its exporter config,
SSH-deploys it as a systemd service on the exporter host and verifies it
comes up, then creates the matching labgrid Place (create/add-match/
set-tags) on the coordinator. See
docs/source/user-guide/netbox-onboarding.rst for prerequisites.
"""

from __future__ import annotations

import re
from pathlib import Path

import click
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.padding import Padding
from rich.prompt import Confirm, Prompt
from rich.table import Table

from adi_lg_plugins.hw_ci import coordinator as coord_mod
from adi_lg_plugins.hw_ci import power as power_types
from adi_lg_plugins.hw_ci.coordinator import (
    _resolve_api,
    add_match,
    create_place,
    fetch_raw_places,
    get_place,
    match_pattern,
    resolve_coordinator,
    set_place_tags,
)
from adi_lg_plugins.tools._choices import ask_choice

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


def _strategy_summary(name: str) -> str:
    """First line of a boot strategy's docstring, if the strategy is registered."""
    from labgrid.factory import target_factory

    cls = target_factory.all_classes.get(name)
    lines = (cls.__doc__ or "").strip().splitlines() if cls else []
    return lines[0].removeprefix(f"{name} - ") if lines else ""


def _plan_table(rows: list[tuple[str, list[str]]]) -> Padding:
    """Label/value rows; each value line is printed on a line of its own."""
    table = Table.grid(padding=(0, 3))
    table.add_column(style="bold")
    table.add_column(overflow="fold")
    for label, values in rows:
        table.add_row(label, "\n".join(values))
    return Padding(table, (0, 0, 0, 2))


def _ask_power() -> tuple[str, dict[str, str]]:
    """Ask for a power type by category, then that type's fields.

    Returns the type key and the template context for its ``power_*`` fields;
    optional fields left blank are omitted so the fragment's default applies.
    """
    console.print("\n[bold]Power control[/bold]")
    category = ask_choice(
        console,
        "Power category",
        [(c, ", ".join(t.key for t in power_types.types_in(c))) for c in power_types.CATEGORIES],
        headers=("Category", "Types"),
        default=power_types.PLUG,
    )
    in_category = power_types.types_in(category)
    keys = [t.key for t in in_category]
    power = ask_choice(
        console,
        "Power type",
        [(t.key, t.label, " + ".join(t.drivers)) for t in in_category],
        headers=("Type", "Description", "Driver"),
        default="vesync" if "vesync" in keys else keys[0],
    )
    context = {}
    for f in power_types.POWER_TYPES[power].fields:
        if f.choices:
            context[f.var] = ask_choice(
                console, f"  {f.prompt}", power_types.choices_for(f.choices), default=f.default
            )
            continue
        if f.default is None:
            context[f.var] = _ask_required(f"  {f.prompt}")
            continue
        answer = Prompt.ask(f"  {f.prompt}", default=f.default, show_default=f.default != "")
        if answer not in (None, ""):
            context[f.var] = answer
    return power, context


# Board, carrier and chip names end up in a systemd unit name, a place name, a
# resource group and a `<name>/<group>/*` match, so no spaces or slashes.
_NAME = (r"[A-Za-z0-9][A-Za-z0-9._-]*", "use letters, digits, '.', '_' and '-' only")
_SLUG = (r"[A-Za-z0-9_-]+", "a slug has letters, digits, '-' and '_' only")
_SSH_LOGIN = (r"[^@\s]+@[^@\s]+", "use the form user@host")
_URL = (r"https?://\S+", "include the scheme, e.g. https://netbox.example.com")


def _explain(text: str) -> None:
    """Say what the next question's answer is used for."""
    console.print(f"\n[dim]{escape(text)}[/dim]")


def _ask_required(prompt: str, *, check: tuple[str, str] | None = None, **kwargs) -> str:
    """Ask until the answer is non-blank and, given ``check`` (regex, hint), matches it."""
    while True:
        answer = (Prompt.ask(prompt, **kwargs) or "").strip()
        if not answer:
            console.print("    [red]required - this field has no default[/red]")
        elif check and not re.fullmatch(check[0], answer):
            console.print(f"    [red]{escape(check[1])}[/red]")
        else:
            return answer


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

    console.print("[bold]Board templates[/bold]")
    template_key = ask_choice(
        console,
        "Board template",
        [
            (key, provision.template_strategy(path) or "", provision.template_title(path))
            for key, path in sorted(templates.items())
        ],
        headers=("Template", "Boot strategy", "Description"),
        default=sorted(templates)[0],
    )
    template_path = templates[template_key]

    _explain(
        "A unique name for this board. It names the NetBox device, the coordinator place "
        "and the exporter service (labgrid-exporter-<name>)."
    )
    name = _ask_required("Board name (e.g. zcu102-ad9081-lab3)", check=_NAME)
    _explain(
        "The FPGA or SoC board the ADI part is mounted on. Saved in NetBox and as the "
        "place's carrier tag; most templates also use it in the resource group name."
    )
    carrier = _ask_required("Carrier board (e.g. zcu102, zc706, vcu118)", check=_NAME)
    _explain(
        "The ADI part under test. Saved in NetBox and as the place's daughter-board tag; "
        "most templates also use it in the resource group name."
    )
    daughter_board = _ask_required(
        "ADI daughter board or chip (e.g. ad9081, adrv9009)", check=_NAME
    )
    console.print("\n[bold]Boot strategies[/bold]")
    boot_strategy = ask_choice(
        console,
        "Boot strategy",
        [(s, _strategy_summary(s)) for s in KNOWN_BOOT_STRATEGIES],
        headers=("Strategy", "Description"),
        default=provision.template_strategy(template_path),
    )
    power, power_context = _ask_power()
    power_type = power_types.POWER_TYPES[power]
    _explain(
        "The self-hosted GitHub Actions runner that runs this board's hardware-CI jobs "
        "(the place's runner tag)."
    )
    runner_label = Prompt.ask("GitHub Actions runner label", default=f"hw-{carrier.lower()}")
    _explain(
        "The existing NetBox site the board is in (NetBox: Organization > Sites). "
        "This command never creates sites."
    )
    site_slug = _ask_required("NetBox site slug (e.g. lab3)", check=_SLUG)
    _explain(
        "The Linux machine the board's serial, USB and power are connected to. The exporter "
        "service is installed there over SSH, so this user needs passwordless sudo."
    )
    ssh_target = _ask_required("Exporter host SSH login (user@host)", check=_SSH_LOGIN)
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
        defaults = provision.template_field_defaults(template_path)
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e

    # Required fields first, so they're not lost among the defaulted ones.
    var_names.sort(key=lambda v: v not in required)
    questions = {v: escape(provision.TEMPLATE_FIELDS.get(v, v)) for v in var_names}
    shown_defaults = {
        v: "required" if v in required else "unset" if defaults.get(v) is None else defaults[v]
        for v in var_names
    }
    console.print(f"\n[bold]Template fields for {template_key}[/bold]")
    if var_names:
        table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False)
        for header in ("Field", "Question", "Default"):
            table.add_column(header)
        for var in var_names:
            table.add_row(var, questions[var], escape(str(shown_defaults[var])))
        console.print(table)
    else:
        console.print("  (none)")
    for var in var_names:
        secret = "password" in var
        if var in required:
            context[var] = _ask_required(f"  {questions[var]} (required)", password=secret)
            continue
        default = defaults.get(var)
        enter = "Enter to leave unset" if default is None else f"Enter for {default}"
        # Blank keeps the template's own default rather than passing it back in,
        # so default(none) stays null instead of becoming a string.
        answer = Prompt.ask(
            f"  {questions[var]} ({escape(enter)})",
            default="",
            show_default=False,
            password=secret,
        )
        if answer:
            context[var] = answer

    try:
        rendered_path, groups = provision.render_and_validate(
            template_path, context, exporter_configs_dir
        )
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e
    # The systemd unit runs `labgrid-exporter -n <name>`, so the coordinator
    # sees these resources under exporter <name>, not the SSH host name.
    match_patterns = [f"{name}/{group}/*" for group in groups]
    tags = {
        "daughter-board": daughter_board.lower(),
        "carrier": carrier.lower(),
        "boot-strategy": boot_strategy,
        "runner": runner_label,
        **provision.power_tags(power),
    }

    power_lines = [
        escape(f"{power_type.label} ({power})"),
        "via " + " + ".join(power_type.drivers),
    ]
    if power_type.credentials:
        power_lines.append(f"credentials in {provision.EXPORTER_ENV_FILE} on the exporter host:")
        power_lines += [
            f"  {c.env}" + ("" if c.required else " (optional)") for c in power_type.credentials
        ]
    if power_type.reach == "client":
        power_lines.append("[yellow]the client (test runner) must reach this device[/yellow]")
    if power_type.note:
        power_lines.append(power_type.note)

    console.print("\n[bold]Plan[/bold]")
    console.print(
        _plan_table(
            [
                ("NetBox device", [escape(f"{name} (site {site_slug})")]),
                ("Carrier / chip", [escape(f"{carrier} / {daughter_board}")]),
                ("Exporter host", [escape(ssh_target)]),
                ("Systemd unit", [escape(f"labgrid-exporter-{name}")]),
                ("Exporter config", [f"{rendered_path} (rendered + validated)"]),
                ("Resource groups", [escape(g) for g in groups]),
                ("Coordinator place", [escape(name)]),
                ("Place matches", [escape(m) for m in match_patterns]),
                ("Place tags", [escape(f"{k}={v}") for k, v in tags.items()]),
                ("Power", power_lines),
            ]
        )
    )

    if dry_run:
        console.print("\n[yellow]Dry run - no NetBox/SSH/coordinator changes made.[/yellow]")
        return

    if not Confirm.ask("\nProceed?", default=True):
        raise click.Abort()

    if not netbox_url:
        _explain("The NetBox instance to register the board in (or set NETBOX_URL).")
        netbox_url = _ask_required("NetBox URL (e.g. https://netbox.example.com)", check=_URL)
    if not netbox_token:
        _explain(
            "A NetBox API token that can create devices; create one under your user profile "
            "in NetBox (or set NETBOX_TOKEN)."
        )
        netbox_token = _ask_secret("NetBox API token")

    coord_resolved = resolve_coordinator(coord)
    if not coord_user or not coord_password:
        _explain(
            f"A coordinator API login ({coord_resolved}) that can create places, add matches "
            "and set tags (or set LG_API_USERNAME / LG_API_PASSWORD)."
        )
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

    # 3. Coordinator: create the place, match the live resources, tag it. The
    # coordinator rejects a place or match that already exists, so a re-run
    # only adds what is missing.
    api = _resolve_api(coord_resolved)
    try:
        cookie = coord_mod.login(api, coord_user, coord_password)
        place = get_place(api, name)
        if place is None:
            create_place(api, cookie, name)
        existing = {match_pattern(m) for m in (place or {}).get("matches", [])}
        for pattern in match_patterns:
            if pattern not in existing:
                add_match(api, cookie, name, pattern)
        set_place_tags(api, cookie, name, tags)
    except (RuntimeError, OSError) as e:  # OSError: coordinator API unreachable
        raise click.ClickException(str(e)) from e
    console.print(f"[green]Place {name!r} created, matched, and tagged on the coordinator.[/green]")

    places = fetch_raw_places(coord_resolved)
    created = next((p for p in places if p.get("name") == name), None)
    if created:
        console.print(f"\n[bold green]Done.[/bold green] {name} tags: {created.get('tags')}")
    else:
        console.print(
            f"\n[yellow]Done, but {name!r} wasn't found in a fresh /api/places listing - "
            "double-check it on the coordinator.[/yellow]"
        )
