"""Power control via labgrid-client subprocess.

We shell out to `labgrid-client power <action>` so every power-protocol
driver (NetworkPowerPort, USBPowerPort, NetworkUSBPowerPort, YKUSH, etc.)
works without us reimplementing the driver logic. The LG_HOSTNAME env
var is set to our api_name so the client identity matches the gRPC
connection that acquired the place.
"""

from __future__ import annotations

import asyncio
import getpass
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..auth.dependencies import current_user
from ..auth.store import User
from ..config import settings
from ..places.store import PlaceAcquisitionStore

logger = logging.getLogger(__name__)
router = APIRouter(tags=["power"])

_VALID_ACTIONS = {"on", "off", "cycle", "get"}


class PowerResult(BaseModel):
    action: str
    place: str
    resource: str | None
    stdout: str
    state: str | None = None  # parsed "on"/"off" for get


def _place_store(request: Request) -> PlaceAcquisitionStore:
    return request.app.state.place_acq_store


def _parse_get_state(stdout: str) -> str | None:
    """Parse the on/off state from `labgrid-client power get` output.
    Upstream prints `power [<name>] for place <p> is on` / `is off`.
    Older formats also use `<name>: on` / `<name>: off`."""
    for line in stdout.splitlines():
        low = line.strip().lower()
        if low.endswith(" is on") or low.endswith(": on") or low == "on":
            return "on"
        if low.endswith(" is off") or low.endswith(": off") or low == "off":
            return "off"
    return None


@router.post("/places/{name}/power/{action}", response_model=PowerResult)
async def power_control(
    name: str,
    action: str,
    request: Request,
    user: User = Depends(current_user),
    resource: str | None = None,
):
    if action not in _VALID_ACTIONS:
        raise HTTPException(status_code=400, detail=f"invalid action: {action}")

    acq = await _place_store(request).get(name)
    if acq is None:
        raise HTTPException(status_code=409, detail="place not acquired")
    if acq.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="not the owner")

    # The labgrid-client subprocess connects with identity "<hostname>/<username>".
    # We override the hostname via LG_HOSTNAME to settings.api_name so the
    # subprocess identity is "<api_name>/<container-user>". Then we issue an
    # allow_place from the gRPC connection (which IS the holder) so the
    # subprocess is authorized to operate on the place.
    subprocess_identity = f"{settings.api_name}/{getpass.getuser()}"
    try:
        await request.app.state.coordinator.allow_place(name, subprocess_identity)
    except Exception as e:
        logger.warning("allow_place(%s, %s) failed: %s", name, subprocess_identity, e)

    env = dict(os.environ)
    env["LG_HOSTNAME"] = settings.api_name
    env["LG_CROSSBAR"] = settings.coordinator_address

    cmd = ["labgrid-client", "-x", settings.coordinator_address, "-p", name, "power", action]
    if resource:
        cmd.extend(["--name", resource])

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=30)
    except asyncio.TimeoutError:
        proc.kill()
        raise HTTPException(status_code=504, detail="labgrid-client timed out") from None

    stdout = stdout_b.decode("utf-8", errors="replace").strip()
    stderr = stderr_b.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        logger.warning("power %s %s failed: %s", action, name, stderr or stdout)
        raise HTTPException(status_code=502, detail=stderr or stdout or "labgrid-client failed")

    state = _parse_get_state(stdout) if action == "get" else None
    return PowerResult(action=action, place=name, resource=resource, stdout=stdout, state=state)
