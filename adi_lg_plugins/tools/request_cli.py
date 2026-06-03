"""``adi-lg request`` — the generic hardware-request CLI surface.

A thin wrapper over :func:`adi_lg_plugins.request.request`: acquire + boot a
board by part, export its interfaces (``IIO_URI`` / ``LG_PLACE`` /
``LG_CARRIER``) into a child command's environment, run the command, and
release the board. Request-layer exceptions map to stable exit codes so CI can
tell an infra problem from a real test failure.
"""

from __future__ import annotations

import os
import subprocess
import sys

import click
from rich.console import Console

from adi_lg_plugins.request import (
    BoardUnavailable,
    NoMatchingBoard,
    ProvisionError,
    request,
)
from adi_lg_plugins.request.errors import (
    EXIT_NO_MATCH,
    EXIT_PROVISION,
    EXIT_UNAVAILABLE,
)

console = Console()


def _run_child(run_cmd: str, env: dict) -> int:
    """Run the user command with the board's interfaces in its environment."""
    return subprocess.call(run_cmd, shell=True, env=env)  # noqa: S602 - user cmd by design


@click.command(name="request")
@click.option("--part", required=True, help="Part / daughter-board, e.g. adrv9002")
@click.option("--carrier", default=None, help="Optional carrier filter, e.g. zcu102")
@click.option(
    "--mode",
    type=click.Choice(["uri", "flash"]),
    default="uri",
    help="uri: boot Linux and export IIO_URI (default). flash: not yet available.",
)
@click.option("--bootfile", default=None, help="Pin an image version (default: catalog default)")
@click.option(
    "--wait", default=1800, type=int, help="Seconds to wait for a free board (0=fail fast)"
)
@click.option(
    "--power-down",
    "power_down",
    is_flag=True,
    default=False,
    help="Power the board off after release (default: leave powered for the next user)",
)
@click.option("--coord", default=None, help="Coordinator host:port (default: $LG_COORDINATOR)")
@click.option(
    "--run",
    "run_cmd",
    default=None,
    help="Command to run with IIO_URI / LG_PLACE / LG_CARRIER exported",
)
def request_cmd(part, carrier, mode, bootfile, wait, power_down, coord, run_cmd):
    """Request a board by part, boot it, run a command against it, and release it."""
    if mode == "flash":
        raise click.ClickException("flash mode is not available yet (uri mode only)")

    try:
        with request(
            part=part,
            carrier=carrier,
            mode=mode,
            bootfile=bootfile,
            wait=wait,
            coord=coord,
            power_down=power_down,
        ) as board:
            if not run_cmd:
                console.print(board.uri or board.place)
                return
            env = os.environ.copy()
            if board.uri:
                env["IIO_URI"] = board.uri
            env["LG_PLACE"] = board.place
            if board.carrier:
                env["LG_CARRIER"] = board.carrier
            console.print(f"[green]Booted {board.place} -> {board.uri}[/green]")
            rc = _run_child(run_cmd, env)
            sys.exit(rc)
    except NoMatchingBoard as e:
        console.print(f"[bold red]No matching board: {e}[/bold red]")
        sys.exit(EXIT_NO_MATCH)
    except BoardUnavailable as e:
        console.print(f"[bold red]Board unavailable: {e}[/bold red]")
        sys.exit(EXIT_UNAVAILABLE)
    except ProvisionError as e:
        console.print(f"[bold red]Provisioning failed: {e}[/bold red]")
        if getattr(e, "console_tail", ""):
            console.print(e.console_tail)
        sys.exit(EXIT_PROVISION)
