import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from ..auth.dependencies import current_user
from ..auth.store import User
from ..config import settings
from ..env_gen import generate_env_yaml
from ..models import (
    AddMatchRequest,
    CreatePlaceRequest,
    PlaceModel,
    SetCommentRequest,
    SetTagsRequest,
)
from ..places.store import PlaceAcquisitionStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["places"])


def _get_client(request: Request):
    return request.app.state.coordinator


def _place_store(request: Request) -> PlaceAcquisitionStore:
    return request.app.state.place_acq_store


async def _hydrate_owner(request: Request, p):
    acq = await _place_store(request).get(p.name)
    if acq is None:
        p.acquired_username = None
    else:
        u = await request.app.state.auth_store.get_user_by_id(acq.user_id)
        p.acquired_username = u.username if u else None
    return p


@router.get("/places", response_model=list[PlaceModel])
async def list_places(request: Request):
    places = _get_client(request).get_places()
    return [await _hydrate_owner(request, p) for p in places]


@router.get("/places/{name}", response_model=PlaceModel)
async def get_place(name: str, request: Request):
    place = _get_client(request).get_place(name)
    if place is None:
        raise HTTPException(status_code=404, detail=f"Place '{name}' not found")
    return await _hydrate_owner(request, place)


@router.post("/places", status_code=201)
async def create_place(
    body: CreatePlaceRequest, request: Request, _user: User = Depends(current_user)
):
    await _get_client(request).add_place(body.name)
    return {"name": body.name}


@router.delete("/places/{name}", status_code=204)
async def delete_place(name: str, request: Request, _user: User = Depends(current_user)):
    await _get_client(request).delete_place(name)


@router.post("/places/{name}/acquire")
async def acquire_place(
    name: str,
    request: Request,
    user: User = Depends(current_user),
):
    place_store = _place_store(request)
    try:
        await place_store.acquire(name, user.id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    try:
        await _get_client(request).acquire_place(name)
    except Exception as e:
        await place_store.force_release(name)
        raise HTTPException(status_code=502, detail=f"labgrid acquire failed: {e}") from e
    return {"acquired": name, "user": user.username}


@router.post("/places/{name}/release")
async def release_place(
    name: str,
    request: Request,
    user: User = Depends(current_user),
    force: bool = False,
):
    place_store = _place_store(request)
    client = _get_client(request)

    if force:
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="force release requires admin")
        await place_store.force_release(name)
    else:
        try:
            await place_store.release(name, user_id=user.id)
        except PermissionError as e:
            raise HTTPException(status_code=403, detail="not the owner") from e

    # Tell labgrid to release. If we (the API gRPC connection) hold the lock,
    # call release_place(name) without fromuser — labgrid validates the
    # caller's session identity. Pass fromuser only when force-releasing a
    # lock held by some other identity.
    lg_place = client.get_place(name)
    holder = lg_place.acquired if lg_place else None
    fromuser: str | None = None
    if (
        force
        and holder
        and not holder.endswith("/" + settings.api_name)
        and holder != settings.api_name
    ):
        fromuser = holder

    try:
        await client.release_place(name, fromuser=fromuser)
    except Exception as e:
        # Don't lie to the caller about success: surface the failure so they
        # can retry or escalate. The DB row is already gone, so this is a
        # divergence the user needs to know about.
        logger.warning("labgrid release failed for %s: %s", name, e)
        raise HTTPException(
            status_code=502,
            detail=f"DB record cleared but labgrid release failed: {e}",
        ) from e
    return {"released": name}


@router.put("/places/{name}/tags")
async def set_place_tags(
    name: str, body: SetTagsRequest, request: Request, _user: User = Depends(current_user)
):
    await _get_client(request).set_place_tags(name, body.tags)

    # Automatically synchronize catalog if new board or carrier tags are added
    catalog = getattr(request.app.state, "catalog", None)
    if catalog is not None:
        db_board = body.tags.get("daughter-board")
        carrier = body.tags.get("carrier")
        if db_board:
            from ..catalog import BoardCarrier, BoardEntry, save_catalog

            resolved = catalog.lookup(db_board)
            updated = False
            if resolved is None:
                carriers = {}
                if carrier:
                    carriers[carrier] = BoardCarrier()
                entry = BoardEntry(image="2023_R2_P1", carriers=carriers)
                catalog.boards[db_board] = entry
                updated = True
            else:
                canonical_key, entry = resolved
                if carrier and carrier not in entry.carriers:
                    entry.carriers[carrier] = BoardCarrier()
                    updated = True

            if updated:
                try:
                    save_catalog(catalog, settings.board_catalog_path)
                    logger.info("Automatically updated catalog for new board/carrier: %s", db_board)
                except Exception as e:
                    logger.error("Failed to automatically save board catalog: %s", e)

    return {"name": name, "tags": body.tags}


@router.put("/places/{name}/comment")
async def set_place_comment(
    name: str, body: SetCommentRequest, request: Request, _user: User = Depends(current_user)
):
    await _get_client(request).set_place_comment(name, body.comment)
    return {"name": name, "comment": body.comment}


@router.post("/places/{name}/matches")
async def add_place_match(
    name: str, body: AddMatchRequest, request: Request, _user: User = Depends(current_user)
):
    await _get_client(request).add_place_match(name, body.pattern, body.rename)
    return {"name": name, "pattern": body.pattern}


@router.delete("/places/{name}/matches")
async def delete_place_match(
    name: str, body: AddMatchRequest, request: Request, _user: User = Depends(current_user)
):
    await _get_client(request).delete_place_match(name, body.pattern, body.rename)
    return {"name": name, "pattern": body.pattern}


@router.get("/places/{name}/env-yaml")
async def get_env_yaml(name: str, request: Request, tier: str = "shell"):
    """Generate a labgrid client env yaml for this place."""
    client = _get_client(request)
    place = client.get_place(name)
    if place is None:
        raise HTTPException(status_code=404, detail=f"Place '{name}' not found")

    try:
        resources = _matched_resources(client, place)
        content = generate_env_yaml(place, resources, tier)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    return Response(
        content=content.encode("utf-8"),
        media_type="application/x-yaml; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}.yaml"'},
    )


def _matched_resources(client, place) -> list:
    """Return all resources matching the place's match rules."""
    all_resources = client.get_resources()
    matched = []
    for r in all_resources:
        for m in place.matches:
            exp_ok = m.exporter == "*" or m.exporter == r.exporter
            grp_ok = m.group == "*" or m.group == r.group
            cls_ok = m.cls == "*" or m.cls == r.cls
            name_ok = not m.name or m.name == r.name
            if exp_ok and grp_ok and cls_ok and name_ok:
                matched.append(r)
                break
    return matched
