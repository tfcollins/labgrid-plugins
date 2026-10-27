"""Board health check: boot with golden boot files and verify shell + network + iiod."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import click
from rich.console import Console

from adi_lg_plugins.hw_ci.coordinator import (
    _api_url,
    _resolve_api,
    list_live_places,
    resolve_coordinator,
)
from adi_lg_plugins.hw_ci.render_env import render_env_to
from adi_lg_plugins.hw_ci.schema import Place
from adi_lg_plugins.request.errors import ProvisionError
from adi_lg_plugins.request.match_client import _get_json
from adi_lg_plugins.request.uri import resolve_uri, verify_iio_context

logger = logging.getLogger(__name__)
console = Console()

EXIT_SUCCESS = 0
EXIT_FAILED = 1
EXIT_BUSY = 2
EXIT_NOT_FOUND = 3


@dataclass
class HealthCheckResult:
    place: str
    status: str  # "passed", "failed", "busy", "error"
    boot_strategy: str | None = None
    image: str | None = None
    ip_address: str | None = None
    iiod_reachable: bool = False
    duration: float = 0.0
    error_message: str | None = None
    uname: str | None = None


def _get_catalog_image(api_url: str, daughter_board: str) -> str | None:
    """Fetch default golden boot image from coordinator catalog."""
    try:
        url = _api_url(api_url)
        data = _get_json(f"{url.rstrip('/')}/api/catalog", timeout=5.0)
        boards = data.get("boards", {})
        if daughter_board in boards:
            return boards[daughter_board].get("image")
        # Check aliases
        for _b_name, b_info in boards.items():
            if daughter_board in b_info.get("aliases", []):
                return b_info.get("image")
    except Exception as e:
        logger.warning("Could not query catalog for golden image: %s", e)
    return None


def _labgrid_client_cmd() -> str:
    """Find labgrid-client executable in PATH or next to sys.executable."""
    cmd = shutil.which("labgrid-client")
    if cmd:
        return cmd
    neighbor = Path(sys.executable).parent / "labgrid-client"
    if neighbor.exists():
        return str(neighbor)
    return "labgrid-client"


def _is_place_acquired(coord: str, place_name: str) -> bool:
    """Check if place is acquired by another client."""
    try:
        out = subprocess.check_output(
            [_labgrid_client_cmd(), "-x", coord, "-p", place_name, "show"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=10,
        )
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("acquired:"):
                val = line[len("acquired:") :].strip()
                return val not in ("", "None", "none")
    except Exception as e:
        logger.warning("Error checking place acquisition: %s", e)
    return False


def _acquire_place(coord: str, place_name: str) -> None:
    subprocess.check_call(
        [_labgrid_client_cmd(), "-x", coord, "-p", place_name, "acquire"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        timeout=15,
    )


def _release_place(coord: str, place_name: str) -> None:
    try:
        subprocess.check_call(
            [_labgrid_client_cmd(), "-x", coord, "-p", place_name, "release"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=15,
        )
    except Exception as e:
        logger.warning("Failed to release place %s: %s", place_name, e)


def run_health_check(
    place_name: str,
    *,
    coord: str | None = None,
    image: str | None = None,
    power_down: bool = True,
    timeout: float = 600.0,
) -> HealthCheckResult:
    """Run an automated boot health check on `place_name`."""
    start_time = time.monotonic()
    coord = resolve_coordinator(coord)
    os.environ["LG_COORDINATOR"] = coord
    api = _resolve_api(coord)

    # 1. Discover place
    places, _ = list_live_places(coord)
    place: Place | None = None
    for p in places:
        if p.name == place_name:
            place = p
            break

    if place is None:
        return HealthCheckResult(
            place=place_name,
            status="error",
            error_message=f"Place '{place_name}' not found among live coordinator places",
            duration=time.monotonic() - start_time,
        )

    # 2. Resolve golden image
    resolved_image = image
    if not resolved_image and place.daughter_board:
        resolved_image = _get_catalog_image(api, place.daughter_board)

    # 3. Check acquisition status
    if _is_place_acquired(coord, place_name):
        return HealthCheckResult(
            place=place_name,
            status="busy",
            boot_strategy=place.boot_strategy,
            image=resolved_image,
            error_message=f"Place '{place_name}' is currently acquired by another user or job",
            duration=time.monotonic() - start_time,
        )

    # 4. Acquire place
    try:
        _acquire_place(coord, place_name)
    except Exception as e:
        return HealthCheckResult(
            place=place_name,
            status="error",
            boot_strategy=place.boot_strategy,
            image=resolved_image,
            error_message=f"Failed to acquire place '{place_name}': {e}",
            duration=time.monotonic() - start_time,
        )

    temp_dir = tempfile.mkdtemp(prefix="adi-lg-health-")
    env_path = Path(temp_dir) / "env.yaml"
    target = None
    strategy = None

    try:
        # 5. Render environment yaml
        render_env_to(place, env_path)

        # 6. Construct Labgrid Environment and boot target
        from labgrid import Environment

        env = Environment(str(env_path))
        target = env.get_target("main")

        if resolved_image:
            try:
                kuiper_res = target.get_resource("KuiperRelease")
                kuiper_res.release_version = resolved_image
                logger.info("Pinned Kuiper image %s for %s", resolved_image, place_name)
            except Exception as e:
                logger.info("KuiperRelease resource not present or could not pin: %s", e)

        strategy_name = place.boot_strategy
        strategy = target.get_driver(strategy_name)

        logger.info("Transitioning %s to shell using %s...", place_name, strategy_name)
        strategy.transition("shell")

        # 7. Resolve DUT IP address
        uri = resolve_uri(target, wait=90.0)
        ip_addr = uri[3:] if uri.startswith("ip:") else uri

        # 8. Verify iiod service
        verify_iio_context(uri, timeout=60.0)
        iiod_ok = True

        # 9. Sanity check: uname
        uname_str = None
        for drv_name in ("ADIShellDriver", "ShellDriver"):
            try:
                sh = target.get_driver(drv_name)
                out, _, rc = sh.run("uname -a")
                if rc == 0 and out:
                    uname_str = out[0].strip()
                    break
            except Exception:
                pass

        duration = time.monotonic() - start_time
        return HealthCheckResult(
            place=place_name,
            status="passed",
            boot_strategy=strategy_name,
            image=resolved_image,
            ip_address=ip_addr,
            iiod_reachable=iiod_ok,
            duration=duration,
            uname=uname_str,
        )

    except ProvisionError as e:
        duration = time.monotonic() - start_time
        return HealthCheckResult(
            place=place_name,
            status="failed",
            boot_strategy=place.boot_strategy,
            image=resolved_image,
            error_message=f"Boot verification error: {e}",
            duration=duration,
        )
    except Exception as e:
        duration = time.monotonic() - start_time
        return HealthCheckResult(
            place=place_name,
            status="failed",
            boot_strategy=place.boot_strategy,
            image=resolved_image,
            error_message=f"Unexpected health check error: {e}",
            duration=duration,
        )
    finally:
        # 10. Clean up
        if power_down and strategy is not None:
            try:
                strategy.transition("powered_off")
            except Exception as e:
                logger.warning("Power off after health check failed: %s", e)

        if target is not None:
            try:
                target.cleanup()
            except Exception:
                pass

        _release_place(coord, place_name)
        shutil.rmtree(temp_dir, ignore_errors=True)


@click.command(name="health-check")
@click.option("--place", "-p", required=True, help="Place name to health check (e.g. mini2)")
@click.option("--coord", "-c", default=None, help="Coordinator host:port")
@click.option("--image", "-i", default=None, help="Override golden boot image (e.g. 2023_R2_P1)")
@click.option(
    "--power-down/--no-power-down",
    default=True,
    help="Power off board after health check completes (default: True)",
)
@click.option("--timeout", default=600.0, type=float, help="Overall timeout in seconds")
@click.option("--json", "json_out", is_flag=True, help="Emit result as JSON")
def health_check_cmd(place, coord, image, power_down, timeout, json_out):
    """Run an automated boot health check on a deployed board."""
    res = run_health_check(
        place,
        coord=coord,
        image=image,
        power_down=power_down,
        timeout=timeout,
    )

    if json_out:
        click.echo(json.dumps(asdict(res), indent=2))
    else:
        if res.status == "passed":
            console.print(
                f"[bold green]✓ Health check passed for '{res.place}' in {res.duration:.1f}s[/bold green]"
            )
            console.print(f"  • Strategy: {res.boot_strategy}")
            console.print(f"  • Image: {res.image or '(default)'}")
            console.print(f"  • IP Address: {res.ip_address}")
            console.print(f"  • IIOD Reachable: {res.iiod_reachable}")
            if res.uname:
                console.print(f"  • Kernel: {res.uname}")
        elif res.status == "busy":
            console.print(
                f"[bold yellow]⚠ Place '{res.place}' is busy: {res.error_message}[/bold yellow]"
            )
        elif res.status == "error":
            console.print(f"[bold red]✗ Error: {res.error_message}[/bold red]")
        else:
            console.print(
                f"[bold red]✗ Health check failed for '{res.place}' after {res.duration:.1f}s[/bold red]"
            )
            console.print(f"  • Error: {res.error_message}")

    if res.status == "passed":
        raise SystemExit(EXIT_SUCCESS)
    elif res.status == "busy":
        raise SystemExit(EXIT_BUSY)
    elif res.status == "error":
        raise SystemExit(EXIT_NOT_FOUND)
    else:
        raise SystemExit(EXIT_FAILED)
