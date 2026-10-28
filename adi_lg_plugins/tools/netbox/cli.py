"""`adi-lg netbox add-hardware` - interactive onboarding.

Registers a new board in NetBox, cabled to an outlet on the power device
that switches it (picked from NetBox, or added), renders+validates its
exporter config, SSH-deploys it as a systemd service on the exporter host
and verifies it comes up, then creates the matching labgrid Place
(create/add-match/set-tags) on the coordinator. Answers are saved as they are given, so a
failed run can be resumed. See docs/source/user-guide/netbox-onboarding.rst
for prerequisites.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
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
from adi_lg_plugins.tools._answers import NEW, Run, SavedAnswers, answers_dir, pick_run
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

# Saved runs live in answers_dir(_ANSWERS), one file per board name.
_ANSWERS = "netbox-add-hardware"
_COMMAND = "adi-lg netbox add-hardware"
# The furthest step a saved run finished, as listed when offering to resume it.
_PROGRESS = {"exporter": "exporter running", "netbox": "NetBox device done", "plan": "plan checked"}


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


def _coordinator(run: Run, explicit: str | None) -> str:
    """--coord or LG_COORDINATOR / ADI_LG_COORDINATOR, else the one ``run`` saved.

    The exporter a run deployed points at its coordinator, so a different one
    voids the steps it finished.
    """
    saved = run.saved.answers.get("coordinator")
    from_env = os.environ.get("LG_COORDINATOR") or os.environ.get("ADI_LG_COORDINATOR")
    try:
        resolved = resolve_coordinator(explicit or (None if from_env else saved))
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e
    if saved is not None and resolved != saved:
        run.saved.done.clear()
    run.saved.set("coordinator", "Coordinator", resolved)
    return resolved


def _progress(run: SavedAnswers) -> str:
    return next((text for step, text in _PROGRESS.items() if run.is_done(step)), "answers saved")


def _pick_run() -> Run:
    return pick_run(
        console,
        command=_COMMAND,
        directory=answers_dir(_ANSWERS),
        headers=("Board", "Template", "Saved", "Progress"),
        describe=lambda r: (r.answers.get("template", ""), r.saved_at, _progress(r)),
        new="start a new board",
    )


def _ask_power_type(run: Run) -> str:
    """Ask for a power type by category."""

    def ask_category(default):
        console.print("\n[bold]Power control[/bold]")
        return ask_choice(
            console,
            "Power category",
            [
                (c, ", ".join(t.key for t in power_types.types_in(c)))
                for c in power_types.CATEGORIES
            ],
            headers=("Category", "Types"),
            default=default,
        )

    category = run.answer(
        "power_category",
        "Power category",
        ask_category,
        default=power_types.PLUG,
        choices=power_types.CATEGORIES,
    )
    in_category = power_types.types_in(category)
    keys = [t.key for t in in_category]
    return run.answer(
        "power",
        "Power type",
        lambda default: ask_choice(
            console,
            "Power type",
            [(t.key, t.label, " + ".join(t.drivers)) for t in in_category],
            headers=("Type", "Description", "Driver"),
            default=default,
        ),
        default="vesync" if "vesync" in keys else keys[0],
        choices=keys,
    )


def _ask_power_fields(run: Run, fields, defaults: dict[str, str] | None = None) -> dict[str, str]:
    """Ask for power fields; ``defaults`` replace a field's own default (e.g. from NetBox).

    Returns the template context for them; optional fields left blank are
    omitted so the fragment's default applies.
    """
    context = {}
    for f in fields:
        if f.choices:
            ask = lambda default, f=f: ask_choice(  # noqa: E731
                console, f"  {f.prompt}", power_types.choices_for(f.choices), default=default
            )
        elif f.default is None:
            ask = lambda default, f=f: _ask_required(f"  {f.prompt}", default=default)  # noqa: E731
        else:
            ask = lambda default, f=f: Prompt.ask(  # noqa: E731
                f"  {f.prompt}", default=default, show_default=default != ""
            )
        default = (defaults or {}).get(f.var) or f.default
        answer = run.answer(f"power.{f.var}", f.prompt, ask, default=default)
        if answer not in (None, ""):
            context[f.var] = answer
    return context


def _ask_power(run: Run | None = None) -> tuple[str, dict[str, str]]:
    """Ask for a power type by category, then all of that type's fields."""
    run = run or Run(_COMMAND, console)
    power = _ask_power_type(run)
    return power, _ask_power_fields(run, power_types.POWER_TYPES[power].fields)


class _NetBox:
    """The run's NetBox connection, opened when first needed.

    Its URL and token are asked for then, unless given as options. Callers
    only read from NetBox before the plan is confirmed.
    """

    def __init__(self, run: Run, url: str | None, token: str | None, verify: bool | str):
        self.run = run
        self.url = url
        self.token = token
        self.verify = verify
        self._api = None

    def api(self):
        if self._api is None:
            # Asked again on resume (the saved URL is the default): a wrong one is
            # what most often stops a run.
            self.url = self.url or self.run.answer(
                "netbox_url",
                "NetBox URL",
                lambda default: _ask_required(
                    "NetBox URL (e.g. https://netbox.example.com)", check=_URL, default=default
                ),
                explain="The NetBox instance to register the board in (or set NETBOX_URL).",
                reask=True,
            )
            if not self.token:
                _explain(
                    "A NetBox API token that can create devices; create one under your user "
                    "profile in NetBox (or set NETBOX_TOKEN)."
                )
                self.token = _ask_token()
            # Lab NetBoxes commonly sit behind an internal CA, so checking is opt-in.
            if self.verify is False:
                console.print(
                    "[dim]NetBox TLS certificate not verified "
                    "(--netbox-verify or --netbox-ca-bundle to check it)[/dim]"
                )
            self._api = client.connect(self.url, self.token, verify=self.verify)
        return self._api

    def __call__(self, fn, *args, **kwargs):
        """``fn(api, *args, **kwargs)``; NetBox failures end the run without a traceback."""
        api = self.api()
        try:
            with client.reported_errors(self.url):
                return fn(api, *args, **kwargs)
        except RuntimeError as e:
            raise click.ClickException(str(e)) from e


@dataclass(frozen=True)
class _PowerLink:
    """The NetBox power device and outlet(s) a board's power port is cabled to."""

    device: str
    new: bool
    outlets: tuple[str, ...]
    settings: dict


def _power_settled(answers: dict) -> bool:
    """Whether saved answers already name the NetBox power device and outlet."""
    picked = answers.get("power_device")
    if picked is None:
        return False
    if picked == NEW:
        return answers.get("power") == "manual" or bool(answers.get("power_device_name"))
    return answers.get("power_netbox_outlet") is not None


def _power_link(run: Run, power: str, context: dict[str, str]) -> _PowerLink | None:
    """The NetBox power connection the answers describe; None if there is none to record."""
    answers = run.saved.answers
    picked = answers.get("power_device")
    if picked is None or power == "manual":
        return None
    power_type = power_types.POWER_TYPES[power]
    new = picked == NEW
    outlet = None if new else answers.get("power_netbox_outlet")
    if outlet in (None, NEW):
        field = power_type.outlet_field
        outlets = client.outlet_names(power_type, context.get(field.var) if field else None)
    else:
        outlets = [outlet]
    return _PowerLink(
        answers.get("power_device_name") if new else picked,
        new,
        tuple(outlets),
        client.power_settings(power_type, context),
    )


def _suggested_device_name(power: str, context: dict[str, str], board: str) -> str:
    """e.g. cyberpower-10.0.0.20, from the type and the field that identifies the device."""
    fields = power_types.POWER_TYPES[power].device_fields
    value = next((context[f.var] for f in fields if context.get(f.var)), None)
    name = f"{power}-{value}" if value else f"{board}-{power}"
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")


def _ask_power_source(
    run: Run, devices: list | None, *, site: str, board: str, taken
) -> tuple[str, dict[str, str]]:
    """Ask how the board's power is switched; returns the power type and its context.

    ``devices`` are the power devices at the board's site in NetBox; picking one
    takes its type and settings from NetBox and asks only which outlet. With
    None (a dry run, or the choice is saved) only the power type and fields are
    asked. ``taken(name)`` says another device at the site already has ``name``.
    """
    if devices is None:
        power, context = _ask_power(run)
        if run.saved.answers.get("power_device") == NEW and power != "manual":
            _ask_device_name(run, power, context, board, taken)
        return power, context

    by_name = {d.name: d for d in devices}
    if devices:
        picked = run.answer(
            "power_device",
            "Power device",
            lambda default: _ask_power_device(devices, site, default),
            choices=[*by_name, NEW],
            explain=(
                "The device that switches this board's power (PDU, smart plug, relay, ...). "
                "Pick one from NetBox to use its settings, or add a new one; the board's power "
                "port is cabled to the outlet you choose."
            ),
        )
    else:
        picked = run.given("power_device", "Power device", NEW)
    if picked == NEW:
        power, context = _ask_power(run)
        if power != "manual":
            _ask_device_name(run, power, context, board, taken)
        return power, context

    device = by_name[picked]
    known = client.power_answers(device.settings)
    if known:
        power, context = known
        power_type = power_types.POWER_TYPES[power]
        run.given("power_category", "Power category", power_type.category)
        run.given("power", "Power type", power)
        for f in power_type.device_fields:
            run.given(f"power.{f.var}", f.prompt, context.get(f.var, ""))
        console.print(
            f"  [dim]{escape(device.name)}: {escape(power_type.label)} ({power}), "
            "settings from NetBox[/dim]"
        )
    else:
        console.print(
            f"  [dim]{escape(device.name)} has no labgrid power settings in NetBox yet; "
            "your answers are saved on it.[/dim]"
        )
        power = _ask_power_type(run)
        power_type = power_types.POWER_TYPES[power]
        context = _ask_power_fields(
            run,
            power_type.device_fields,
            {"power_host": device.address} if device.address else None,
        )

    field = power_type.outlet_field
    if field is None and len(device.outlets) == 1:
        run.given("power_netbox_outlet", "Outlet on the power device", device.outlets[0].name)
    else:
        outlet = run.answer(
            "power_netbox_outlet",
            "Outlet on the power device",
            lambda default: _ask_outlet(device, board, default),
            choices=[*(o.name for o in device.outlets), NEW],
        )
        if field is not None:
            value = (
                None
                if outlet == NEW
                else client.outlet_answer(power_type, outlet, len(device.outlets))
            )
            if value is None:
                digits = re.findall(r"\d+", outlet)
                default = digits[-1] if digits and outlet != NEW else field.default
                context.update(_ask_power_fields(run, [field], {field.var: default}))
            else:
                run.given(f"power.{field.var}", field.prompt, value)
                if value:
                    context[field.var] = value
    board_fields = [f for f in power_type.fields if f.scope == "board"]
    context.update(_ask_power_fields(run, board_fields))
    return power, context


def _ask_power_device(devices: list, site: str, default: str | None) -> str:
    console.print(f"\n[bold]Power devices in NetBox at {escape(site)}[/bold]")
    rows = []
    for d in devices:
        settings = d.settings or {}
        free = sum(o.connected_to is None for o in d.outlets)
        address = next((str(v) for k, v in settings.items() if k in ("address", "host")), d.address)
        rows.append(
            (d.name, settings.get("type", "not set"), address, f"{free} of {len(d.outlets)}")
        )
    rows.append((NEW, "", "", "a power device not in NetBox yet: add it"))
    return ask_choice(
        console,
        "Power device",
        rows,
        headers=("Device", "Type", "Address", "Free outlets"),
        default=default,
    )


def _ask_outlet(device, board: str, default: str | None) -> str:
    """Pick an outlet that is free, or already feeds this board; or a new one."""
    rows = [(o.name, o.connected_to or "free") for o in device.outlets]
    rows.append((NEW, "an outlet not in NetBox yet: add it"))
    feeds = {o.name: o.connected_to for o in device.outlets}
    while True:
        outlet = ask_choice(
            console,
            f"Outlet on {escape(device.name)}",
            rows,
            headers=("Outlet", "Feeds"),
            default=default,
        )
        other = feeds.get(outlet)
        if other is None or other.startswith(f"{board} "):
            return outlet
        console.print(
            f"    [red]{escape(client.outlet_label(device.name, outlet))} already feeds "
            f"{escape(other)} - pick a free one, or remove that cable in NetBox first[/red]"
        )


def _ask_device_name(run: Run, power: str, context: dict[str, str], board: str, taken) -> str:
    def ask(default):
        while True:
            name = _ask_required("Power device name in NetBox", check=_NAME, default=default)
            if not taken(name):
                return name
            console.print(
                f"    [red]{escape(name)} is already a device in NetBox without power outlets - "
                "pick another name[/red]"
            )

    return run.answer(
        "power_device_name",
        "Power device name in NetBox",
        ask,
        default=_suggested_device_name(power, context, board),
        explain="The new power device is added to NetBox under this name, at the board's site.",
    )


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


def _ask_token() -> str:
    """Ask for the NetBox API token until it is one NetBox can parse."""
    while True:
        raw = _ask_secret("NetBox API token")
        try:
            token = client.clean_token(raw)
        except ValueError as e:
            console.print(f"    [red]{escape(str(e))}[/red]")
            continue
        if token != raw:
            console.print(
                "    [dim]removed the Authorization/Bearer/Token prefix or quotes "
                f"({len(token)} characters left)[/dim]"
            )
        return token


def _ask_secret(prompt: str) -> str:
    """Ask for a token/password without echoing it.

    Hidden input shows nothing while typing or pasting, so confirm how much arrived.
    """
    secret = _ask_required(f"{prompt} (input hidden)", password=True)
    console.print(f"    [dim]received {len(secret)} characters[/dim]")
    return secret


def _ask_field(
    question: str, *, required: bool, default: object, saved: str | None, secret: bool
) -> str:
    """Ask for one template field; "" leaves an optional one to the template.

    ``default`` is the template's own default (None: unset). With a ``saved``
    answer, Enter keeps it and "-" goes back to the template's default.
    """
    keep = "the saved one" if secret else saved
    if required:
        if saved:
            return _ask_required(
                f"  {question} (Enter for {escape(keep)})",
                password=secret,
                default=saved,
                show_default=False,
            )
        return _ask_required(f"  {question} (required)", password=secret)
    if saved:
        enter = f"Enter for {keep}, - " + (
            "to leave unset" if default is None else f"for {default}"
        )
    else:
        enter = "Enter to leave unset" if default is None else f"Enter for {default}"
    # Blank keeps the template's own default rather than passing it back in,
    # so default(none) stays null instead of becoming a string.
    answer = Prompt.ask(
        f"  {question} ({escape(enter)})",
        default=saved or "",
        show_default=False,
        password=secret,
    )
    return "" if answer == "-" else answer


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
    # Check a token given up front now, not after every question.
    if netbox_token is not None and not dry_run:
        try:
            netbox_token = client.clean_token(netbox_token)
        except ValueError as e:
            raise click.ClickException(f"--netbox-token / NETBOX_TOKEN: {e}") from e

    templates = _discover_templates(exporter_configs_dir)
    if not templates:
        raise click.ClickException(f"no templates found under {exporter_configs_dir / 'templates'}")

    run = _pick_run()
    with run.reporting():
        _onboard(
            run,
            templates,
            exporter_configs_dir,
            dry_run=dry_run,
            netbox_url=netbox_url,
            netbox_token=netbox_token,
            netbox_verify=netbox_ca_bundle or netbox_verify,
            coord=coord,
            coord_user=coord_user,
            coord_password=coord_password,
        )


def _onboard(
    run: Run,
    templates: dict[str, Path],
    exporter_configs_dir: Path,
    *,
    dry_run: bool,
    netbox_url: str | None,
    netbox_token: str | None,
    netbox_verify: bool | str,
    coord: str | None,
    coord_user: str | None,
    coord_password: str | None,
) -> None:
    def ask_template(default):
        console.print("[bold]Board templates[/bold]")
        return ask_choice(
            console,
            "Board template",
            [
                (key, provision.template_strategy(path) or "", provision.template_title(path))
                for key, path in sorted(templates.items())
            ],
            headers=("Template", "Boot strategy", "Description"),
            default=default,
        )

    template_key = run.answer(
        "template", "Board template", ask_template, default=sorted(templates)[0], choices=templates
    )
    template_path = templates[template_key]

    name = run.answer(
        "name",
        "Board name",
        lambda default: _ask_required(
            "Board name (e.g. zcu102-ad9081-lab3)", check=_NAME, default=default
        ),
        explain=(
            "A unique name for this board. It names the NetBox device, the coordinator place "
            "and the exporter service (labgrid-exporter-<name>)."
        ),
    )
    # From here on the answers are saved, in a file named after the board.
    run.save_as(name)
    carrier = run.answer(
        "carrier",
        "Carrier board",
        lambda default: _ask_required(
            "Carrier board (e.g. zcu102, zc706, vcu118)", check=_NAME, default=default
        ),
        explain=(
            "The FPGA or SoC board the ADI part is mounted on. Saved in NetBox and as the "
            "place's carrier tag; most templates also use it in the resource group name."
        ),
    )
    daughter_board = run.answer(
        "daughter_board",
        "ADI daughter board or chip",
        lambda default: _ask_required(
            "ADI daughter board or chip (e.g. ad9081, adrv9009)", check=_NAME, default=default
        ),
        explain=(
            "The ADI part under test. Saved in NetBox and as the place's daughter-board tag; "
            "most templates also use it in the resource group name."
        ),
    )

    def ask_strategy(default):
        console.print("\n[bold]Boot strategies[/bold]")
        return ask_choice(
            console,
            "Boot strategy",
            [(s, _strategy_summary(s)) for s in KNOWN_BOOT_STRATEGIES],
            headers=("Strategy", "Description"),
            default=default,
        )

    boot_strategy = run.answer(
        "boot_strategy",
        "Boot strategy",
        ask_strategy,
        default=provision.template_strategy(template_path),
        choices=KNOWN_BOOT_STRATEGIES,
    )
    runner_label = run.answer(
        "runner_label",
        "GitHub Actions runner label",
        lambda default: Prompt.ask("GitHub Actions runner label", default=default),
        default=f"hw-{carrier.lower()}",
        explain=(
            "The self-hosted GitHub Actions runner that runs this board's hardware-CI jobs "
            "(the place's runner tag)."
        ),
    )

    # The site and the board's power device are picked from what NetBox has, so
    # it is read from here on, unless the saved answers already settle both.
    # Nothing is written to NetBox before the plan is confirmed.
    netbox = _NetBox(run, netbox_url, netbox_token, netbox_verify)
    look_up = not dry_run and (run.mode != "resume" or not _power_settled(run.saved.answers))
    sites = dict(netbox(client.sites)) if look_up else None
    if sites == {}:
        raise click.ClickException(
            "NetBox has no sites - add the lab's site first (Organization > Sites); "
            "this command never creates sites"
        )

    def ask_site(default):
        if sites is None:
            return _ask_required("NetBox site slug (e.g. lab3)", check=_SLUG, default=default)
        return ask_choice(
            console,
            "NetBox site slug",
            list(sites.items()),
            headers=("Site", "Name"),
            default=default,
        )

    site_slug = run.answer(
        "site_slug",
        "NetBox site slug",
        ask_site,
        choices=sites,
        explain=(
            "The existing NetBox site the board is in (NetBox: Organization > Sites). "
            "This command never creates sites."
        ),
    )
    devices = netbox(client.power_devices, site_slug) if look_up else None
    power_names = {d.name for d in devices or ()}
    power, power_context = _ask_power_source(
        run,
        devices,
        site=site_slug,
        board=name,
        taken=lambda n: (
            look_up and n not in power_names and netbox(client.device_exists, n, site_slug)
        ),
    )
    power_type = power_types.POWER_TYPES[power]
    power_link = _power_link(run, power, power_context)
    ssh_target = run.answer(
        "ssh_target",
        "Exporter host SSH login",
        lambda default: _ask_required(
            "Exporter host SSH login (user@host)", check=_SSH_LOGIN, default=default
        ),
        explain=(
            "The Linux machine the board's serial, USB and power are connected to. The exporter "
            "service is installed there over SSH, so this user needs passwordless sudo."
        ),
    )
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
    if any(run.will_ask(f"field.{v}") for v in var_names) or not var_names:
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
        answer = run.answer(
            f"field.{var}",
            provision.TEMPLATE_FIELDS.get(var, var),
            lambda saved, var=var: _ask_field(
                questions[var],
                required=var in required,
                default=defaults.get(var),
                saved=saved,
                secret="password" in var,
            ),
        )
        if answer:
            context[var] = answer

    try:
        rendered_path, groups = provision.render_and_validate(
            template_path, context, exporter_configs_dir
        )
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e
    run.saved.mark_done("plan")
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
    if power_link is not None:
        netbox_power = [
            escape(f"{name} power port -> {client.outlet_label(power_link.device, o)}")
            + (" (new device)" if power_link.new else "")
            for o in power_link.outlets
        ]
    elif power == "manual":
        netbox_power = ["not recorded (manual power)"]
    else:
        netbox_power = ["chosen from NetBox when run without --dry-run"]

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
                ("Power in NetBox", netbox_power),
            ]
        )
    )

    if dry_run:
        console.print("\n[yellow]Dry run - no NetBox/SSH/coordinator changes made.[/yellow]")
        click.echo(run.hint("without --dry-run"))
        return

    if not Confirm.ask("\nProceed?", default=True):
        raise click.Abort()

    coord_resolved = _coordinator(run, coord)
    # Steps a resumed run already finished are skipped, so their credentials
    # aren't needed. Tokens and passwords are never saved.
    netbox_done = run.saved.is_done("netbox")
    if not netbox_done:
        netbox.api()

    if not coord_user or not coord_password:
        _explain(
            f"A coordinator API login ({coord_resolved}) that can create places, add matches "
            "and set tags (or set LG_API_USERNAME / LG_API_PASSWORD)."
        )
    coord_user = coord_user or run.answer(
        "coord_user",
        "Coordinator API username",
        lambda default: _ask_required("Coordinator API username", default=default),
        reask=True,
    )
    if not coord_password:
        coord_password = _ask_secret("Coordinator API password")

    # 1. NetBox: register the device (source of truth for inventory) and cable
    # its power. Marked done only once both are, so a failure is redone on resume.
    if netbox_done:
        console.print("[dim]NetBox device: done in an earlier run, skipped[/dim]")
    else:

        def register(nb):
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
            done = []
            if power_link is not None:
                done = client.connect_power(
                    nb,
                    device,
                    site_slug=site_slug,
                    device=power_link.device,
                    settings=power_link.settings,
                    outlets=list(power_link.outlets),
                )
            return device, done

        device, power_done = netbox(register)
        run.saved.mark_done("netbox")
        console.print(
            f"[green]NetBox device ready:[/green] {netbox.url.rstrip('/')}/dcim/devices/{device.id}/"
        )
        for line in power_done:
            console.print(f"  [dim]{escape(line)}[/dim]")

    # 2. Exporter host: deploy + verify the systemd service.
    if run.saved.is_done("exporter"):
        console.print(f"[dim]labgrid-exporter-{name}: done in an earlier run, skipped[/dim]")
    else:
        try:
            exporter_bin = provision.check_prerequisites(ssh_host)
            provision.deploy_exporter(
                ssh_host, ssh_user, name, rendered_path, coord_resolved, exporter_bin=exporter_bin
            )
            provision.verify_exporter_active(ssh_host, name)
            missing_env = provision.missing_power_env(ssh_host, power)
        except RuntimeError as e:
            raise click.ClickException(str(e)) from e
        run.saved.mark_done("exporter")
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
    # Every step is done, so there is nothing left to resume.
    run.saved.delete()

    places = fetch_raw_places(coord_resolved)
    created = next((p for p in places if p.get("name") == name), None)
    if created:
        console.print(f"\n[bold green]Done.[/bold green] {name} tags: {created.get('tags')}")
    else:
        console.print(
            f"\n[yellow]Done, but {name!r} wasn't found in a fresh /api/places listing - "
            "double-check it on the coordinator.[/yellow]"
        )
