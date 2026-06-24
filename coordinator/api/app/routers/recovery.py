"""Manual board recovery via the BootZynq7000JTAGRecovery strategy.

Mirrors routers/power.py: ownership-gated, authorizes our labgrid-client
subprocess identity via allow_place, then shells out — here to `adi-lg
recover`, which runs the recovery strategy's transition() against a boot-tier
env yaml we generate for the place. Recovery is DESTRUCTIVE (it reflashes the
SD card) and long-running, so the request blocks for up to RECOVER_TIMEOUT.
"""

from __future__ import annotations

import asyncio
import getpass
import logging
import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..auth.dependencies import current_user
from ..auth.store import User
from ..config import settings
from ..env_gen import generate_env_yaml, resolve_strategy
from ..places.store import PlaceAcquisitionStore
from .places import _matched_resources

logger = logging.getLogger(__name__)
router = APIRouter(tags=["recover"])

RECOVERY_STRATEGY = "BootZynq7000JTAGRecovery"
RECOVER_TIMEOUT = 1800  # seconds; the SD reflash can take many minutes
_VALID_STATES = {"sd_flash_done", "sd_boot_verified"}


class RecoverResult(BaseModel):
    place: str
    state: str
    stdout: str
    ok: bool = True


def _place_store(request: Request) -> PlaceAcquisitionStore:
    return request.app.state.place_acq_store


@router.post("/places/{name}/recover", response_model=RecoverResult)
async def recover_place(
    name: str,
    request: Request,
    user: User = Depends(current_user),
    state: str = "sd_flash_done",
):
    if state not in _VALID_STATES:
        raise HTTPException(status_code=400, detail=f"invalid state: {state}")

    acq = await _place_store(request).get(name)
    if acq is None:
        raise HTTPException(status_code=409, detail="place not acquired")
    if acq.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="not the owner")

    client = request.app.state.coordinator
    place = client.get_place(name)
    if place is None:
        raise HTTPException(status_code=404, detail=f"Place '{name}' not found")

    resources = _matched_resources(client, place)
    if resolve_strategy(place.tags, {r.cls for r in resources}) != RECOVERY_STRATEGY:
        raise HTTPException(
            status_code=422, detail=f"place '{name}' does not resolve to {RECOVERY_STRATEGY}"
        )
    try:
        env_yaml = generate_env_yaml(place, resources, tier="boot")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    # Authorize the labgrid-client subprocess identity (same trick as power.py).
    subprocess_identity = f"{settings.api_name}/{getpass.getuser()}"
    try:
        await client.allow_place(name, subprocess_identity)
    except Exception as e:
        logger.warning("allow_place(%s, %s) failed: %s", name, subprocess_identity, e)

    env = dict(os.environ)
    env["LG_HOSTNAME"] = settings.api_name
    env["LG_CROSSBAR"] = settings.coordinator_address

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as fh:
        fh.write(env_yaml)
        config_path = fh.name
    try:
        cmd = [
            "adi-lg",
            "recover",
            "--config",
            config_path,
            "--target",
            "main",
            "--state",
            state,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=RECOVER_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            raise HTTPException(status_code=504, detail="recovery timed out") from None
    finally:
        try:
            os.unlink(config_path)
        except OSError:
            pass

    stdout = stdout_b.decode("utf-8", errors="replace").strip()
    stderr = stderr_b.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        logger.warning("recover %s failed: %s", name, stderr or stdout)
        raise HTTPException(status_code=502, detail=stderr or stdout or "adi-lg recover failed")
    return RecoverResult(place=name, state=state, stdout=stdout)
