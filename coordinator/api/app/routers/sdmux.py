"""SD-mux control via labgrid-client subprocess.

We shell out to `labgrid-client sd-mux <action>` so every SD mux driver
(USBSDMuxDriver, USBSDWireDriver) works without us reimplementing it.
The LG_HOSTNAME env var is set to our api_name so the client identity
matches the gRPC connection that acquired the place; we issue an
allow_place from the gRPC side first so the subprocess is authorized.
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
router = APIRouter(tags=["sdmux"])

_VALID_ACTIONS = {"dut", "host", "off", "client", "get"}


class SDMuxResult(BaseModel):
    action: str
    place: str
    resource: str | None
    stdout: str
    mode: str | None = None  # parsed from `get`


def _place_store(request: Request) -> PlaceAcquisitionStore:
    return request.app.state.place_acq_store


def _parse_mode(stdout: str) -> str | None:
    """`labgrid-client sd-mux get` prints just `dut` / `host` / `off` /
    `client` on its own line. Return the first known token."""
    for line in stdout.splitlines():
        token = line.strip().lower()
        if token in {"dut", "host", "off", "client"}:
            return token
    return None


@router.post("/places/{name}/sdmux/{action}", response_model=SDMuxResult)
async def sdmux_control(
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

    # Authorize the subprocess identity (same dance as the power router).
    subprocess_identity = f"{settings.api_name}/{getpass.getuser()}"
    try:
        await request.app.state.coordinator.allow_place(name, subprocess_identity)
    except Exception as e:
        logger.warning("allow_place(%s, %s) failed: %s", name, subprocess_identity, e)

    env = dict(os.environ)
    env["LG_HOSTNAME"] = settings.api_name
    env["LG_CROSSBAR"] = settings.coordinator_address

    cmd = ["labgrid-client", "-x", settings.coordinator_address, "-p", name, "sd-mux", action]
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
        logger.warning("sd-mux %s %s failed: %s", action, name, stderr or stdout)
        raise HTTPException(status_code=502, detail=stderr or stdout or "labgrid-client failed")

    mode = _parse_mode(stdout) if action == "get" else None
    return SDMuxResult(action=action, place=name, resource=resource, stdout=stdout, mode=mode)
