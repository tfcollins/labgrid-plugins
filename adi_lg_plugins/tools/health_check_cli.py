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
    drivers: list[str] | None = None


def _log_step(step: int, total: int, msg: str) -> None:
    """Emit formatted step progress to stderr and logger."""
    timestamp = time.strftime("%H:%M:%S")
    formatted = f"[{timestamp}] [{step}/{total}] {msg}"
    logger.info("[%d/%d] %s", step, total, msg)
    sys.stderr.write(f"{formatted}\n")
    sys.stderr.flush()


def _log_info(msg: str) -> None:
    """Emit indented progress detail to stderr and logger."""
    timestamp = time.strftime("%H:%M:%S")
    formatted = f"[{timestamp}]        {msg}"
    logger.info("%s", msg)
    sys.stderr.write(f"{formatted}\n")
    sys.stderr.flush()


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
    fetch_drivers: bool = False,
    timeout: float = 600.0,
) -> HealthCheckResult:
    """Run an automated boot health check on `place_name`."""
    start_time = time.monotonic()
    coord = resolve_coordinator(coord)
    os.environ["LG_COORDINATOR"] = coord
    api = _resolve_api(coord)

    # 1. Discover place
    _log_step(1, 7, f"Discovering target place '{place_name}' on coordinator {coord}...")
    places, _ = list_live_places(coord)
    place: Place | None = None
    for p in places:
        if p.name == place_name:
            place = p
            break

    if place is None:
        _log_info(f"Place '{place_name}' not found among live coordinator places")
        return HealthCheckResult(
            place=place_name,
            status="error",
            error_message=f"Place '{place_name}' not found among live coordinator places",
            duration=time.monotonic() - start_time,
        )

    _log_info(
        f"Place found: carrier={place.carrier or 'none'}, "
        f"daughter-board={place.daughter_board or 'none'}, strategy={place.boot_strategy}"
    )

    # 2. Resolve golden image
    _log_step(2, 7, "Resolving golden boot image...")
    resolved_image = image
    if not resolved_image and place.daughter_board:
        resolved_image = _get_catalog_image(api, place.daughter_board)
    _log_info(f"Target golden boot image: {resolved_image or '(default catalog image)'}")

    # 3. Check acquisition status
    _log_step(3, 7, f"Checking acquisition status and acquiring place '{place_name}'...")
    if _is_place_acquired(coord, place_name):
        _log_info(f"Place '{place_name}' is currently acquired by another user or job")
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
        _log_info(f"Place '{place_name}' acquired successfully on coordinator {coord}")
    except Exception as e:
        _log_info(f"Failed to acquire place '{place_name}': {e}")
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
        # 5. Render environment yaml and initialize target
        _log_step(4, 7, "Rendering Labgrid environment config and initializing drivers...")
        render_env_to(place, env_path)

        from labgrid import Environment

        env = Environment(str(env_path))
        target = env.get_target("main")

        if resolved_image:
            try:
                kuiper_res = target.get_resource("KuiperRelease")
                kuiper_res.release_version = resolved_image
                _log_info(f"Pinned Kuiper image {resolved_image} on KuiperRelease resource")
            except Exception as e:
                logger.info("KuiperRelease resource not present or could not pin: %s", e)

        strategy_name = place.boot_strategy
        strategy = target.get_driver(strategy_name)
        _log_info(f"Target drivers bound. Boot strategy: {strategy_name}")

        # 6. Execute boot transition
        _log_step(5, 7, f"Executing boot transition to 'shell' via {strategy_name}...")
        _log_info(
            "Cold power-cycling DUT, provisioning boot files / U-Boot, and awaiting Linux shell prompt..."
        )
        strategy.transition("shell")
        _log_info("Target successfully booted and reached Linux shell prompt!")

        # 7. Resolve DUT IP address
        _log_step(6, 7, "Resolving live DUT IP address (waiting for DHCP lease)...")
        uri = resolve_uri(target, wait=90.0)
        ip_addr = uri[3:] if uri.startswith("ip:") else uri
        _log_info(f"Live DUT IP address resolved: {ip_addr}")

        # 8. Verify iiod service
        _log_step(7, 7, f"Verifying IIO daemon (iiod) on {uri} (port 30431)...")
        verify_iio_context(uri, timeout=60.0)
        iiod_ok = True
        _log_info("libIIO context responsive and verified healthy!")

        # 9. Sanity check: uname
        uname_str = None
        for drv_name in ("ADIShellDriver", "ShellDriver"):
            try:
                sh = target.get_driver(drv_name)
                out, _, rc = sh.run("uname -a")
                if rc == 0 and out:
                    uname_str = out[0].strip()
                    _log_info(f"System kernel: {uname_str}")
                    break
            except Exception:
                pass

        # 10. Query discovered IIO device drivers if requested
        drivers_list: list[str] | None = None
        if fetch_drivers:
            _log_info("Querying discovered IIO device drivers from DUT (/sys/bus/iio)...")
            cmd = 'for d in /sys/bus/iio/devices/iio:device*; do [ -f "$d/name" ] && cat "$d/name"; done'
            for drv_name in ("ADIShellDriver", "ShellDriver"):
                try:
                    sh = target.get_driver(drv_name)
                    out, _, rc = sh.run(cmd)
                    if rc == 0 and out:
                        drivers_list = [line.strip() for line in out if line.strip()]
                        _log_info(
                            f"Discovered {len(drivers_list)} IIO driver(s): {', '.join(drivers_list)}"
                        )
                        break
                except Exception as e:
                    logger.debug("Failed querying IIO drivers: %s", e)

        duration = time.monotonic() - start_time
        _log_info(f"✓ Health check completed successfully in {duration:.1f}s")
        return HealthCheckResult(
            place=place_name,
            status="passed",
            boot_strategy=strategy_name,
            image=resolved_image,
            ip_address=ip_addr,
            iiod_reachable=iiod_ok,
            duration=duration,
            uname=uname_str,
            drivers=drivers_list,
        )

    except ProvisionError as e:
        duration = time.monotonic() - start_time
        _log_info(f"✗ Boot verification error after {duration:.1f}s: {e}")
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
        _log_info(f"✗ Unexpected health check error after {duration:.1f}s: {e}")
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
                _log_info("Tearing down: powering off DUT...")
                strategy.transition("powered_off")
                _log_info("DUT powered off")
            except Exception as e:
                logger.warning("Power off after health check failed: %s", e)

        if target is not None:
            try:
                target.cleanup()
            except Exception:
                pass

        _release_place(coord, place_name)
        _log_info(f"Released place '{place_name}' on coordinator {coord}")
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
@click.option(
    "--drivers",
    "-d",
    "fetch_drivers",
    is_flag=True,
    default=False,
    help="Query and return list of IIO device drivers discovered on the DUT (e.g. ad9361-phy, cf-ad9361-lpc)",
)
@click.option("--timeout", default=600.0, type=float, help="Overall timeout in seconds")
@click.option("--json", "json_out", is_flag=True, help="Emit result as JSON")
def health_check_cmd(place, coord, image, power_down, fetch_drivers, timeout, json_out):
    """Run an automated boot health check on a deployed board."""
    res = run_health_check(
        place,
        coord=coord,
        image=image,
        power_down=power_down,
        fetch_drivers=fetch_drivers,
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
            if res.drivers:
                console.print(f"  • Drivers Found ({len(res.drivers)}):")
                for drv in res.drivers:
                    console.print(f"    - {drv}")
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
