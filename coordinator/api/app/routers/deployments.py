"""Authenticated deployment enrollment and status API."""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from enum import Enum

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress, field_validator

from ..auth.dependencies import current_user
from ..auth.store import User
from ..config import settings
from ..deployments.store import DeploymentEvent, DeploymentNode, DeploymentStore

router = APIRouter(tags=["deployments"], prefix="/deployments")

_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_MAC = re.compile(r"^[0-9a-f]{2}(?::[0-9a-f]{2}){5}$")


class DeploymentStage(str, Enum):
    installer_started = "installer_started"
    storage_configured = "storage_configured"
    packages_installed = "packages_installed"
    install_complete = "install_complete"
    first_boot = "first_boot"
    setup_started = "setup_started"
    runner_ready = "runner_ready"
    failed = "failed"


_PROGRESS = {
    DeploymentStage.installer_started: 5,
    DeploymentStage.storage_configured: 25,
    DeploymentStage.packages_installed: 50,
    DeploymentStage.install_complete: 75,
    DeploymentStage.first_boot: 80,
    DeploymentStage.setup_started: 90,
    DeploymentStage.runner_ready: 100,
    DeploymentStage.failed: 0,
}


def normalize_hostname(value: str) -> str:
    hostname = value.strip().lower()
    if len(hostname) > 253 or not hostname or hostname.endswith("."):
        raise ValueError("invalid hostname")
    if any(not _HOST_LABEL.fullmatch(label) for label in hostname.split(".")):
        raise ValueError("invalid hostname")
    return hostname


def _status(stage: DeploymentStage) -> str:
    if stage is DeploymentStage.failed:
        return "failed"
    if stage is DeploymentStage.runner_ready:
        return "succeeded"
    return "in_progress"


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


class InstallerEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"^[\w.:-]+$")
    hostname: str = Field(min_length=1, max_length=253)
    status: DeploymentStage
    reported_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ip_addresses: list[IPvAnyAddress] = Field(default_factory=list, max_length=16)
    mac_addresses: list[str] = Field(default_factory=list, max_length=16)
    message: str | None = Field(default=None, max_length=1024)

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, value: str) -> str:
        return normalize_hostname(value)

    @field_validator("reported_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("reported_at must include a timezone")
        return value

    @field_validator("mac_addresses")
    @classmethod
    def validate_macs(cls, values: list[str]) -> list[str]:
        normalized = [value.lower() for value in values]
        if any(not _MAC.fullmatch(value) for value in normalized):
            raise ValueError("MAC addresses must use six colon-separated octets")
        if len(set(normalized)) != len(normalized):
            raise ValueError("MAC addresses must be unique")
        return normalized


class DeploymentTimelineEntry(BaseModel):
    timestamp: str
    stage: DeploymentStage
    status: str
    message: str
    progress: int


class DeploymentSummary(BaseModel):
    hostname: str
    attempt: int
    stage: DeploymentStage
    status: str
    progress: int
    ip_addresses: list[str]
    mac_addresses: list[str]
    first_seen: str
    last_seen: str
    errors: list[str]


class DeploymentDetail(DeploymentSummary):
    timeline: list[DeploymentTimelineEntry]


class DeploymentEventAccepted(BaseModel):
    id: int
    hostname: str
    attempt: int
    status: DeploymentStage
    reported_at: str


def _store(request: Request) -> DeploymentStore:
    return request.app.state.deployment_store


def require_deployment_token(authorization: str | None = Header(default=None)) -> None:
    expected = settings.deployment_token
    if not expected:
        raise HTTPException(status_code=503, detail="deployment enrollment is not configured")
    scheme, separator, supplied = (authorization or "").partition(" ")
    valid = separator == " " and scheme.lower() == "bearer"
    candidate = supplied if valid else ""
    try:
        matches = secrets.compare_digest(candidate.encode("utf-8"), expected.encode("utf-8"))
    except UnicodeError:
        matches = False
    if not (valid and matches):
        raise HTTPException(
            status_code=401,
            detail="invalid deployment token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _timeline(event: DeploymentEvent) -> DeploymentTimelineEntry:
    stage = DeploymentStage(event.stage)
    return DeploymentTimelineEntry(
        timestamp=_iso(event.event_at),
        stage=stage,
        status=_status(stage),
        message=event.message or stage.value.replace("_", " "),
        progress=_PROGRESS[stage],
    )


def _summary(node: DeploymentNode, events: list[DeploymentEvent]) -> DeploymentSummary:
    stage = DeploymentStage(node.current_stage)
    return DeploymentSummary(
        hostname=node.hostname,
        attempt=node.attempt,
        stage=stage,
        status=_status(stage),
        progress=_PROGRESS[stage],
        ip_addresses=node.ip_addresses,
        mac_addresses=node.mac_addresses,
        first_seen=_iso(node.first_seen_at),
        last_seen=_iso(node.last_seen_at),
        errors=[
            event.message or "deployment failed" for event in events if event.stage == "failed"
        ],
    )


@router.post(
    "/events",
    response_model=DeploymentEventAccepted,
    status_code=201,
    dependencies=[Depends(require_deployment_token)],
)
async def record_installer_event(payload: InstallerEventIn, request: Request):
    event = await _store(request).record_event(
        hostname=payload.hostname,
        event_id=payload.event_id,
        stage=payload.status.value,
        event_at=payload.reported_at.timestamp(),
        ip_addresses=[str(address) for address in payload.ip_addresses],
        mac_addresses=payload.mac_addresses,
        message=payload.message,
        details=None,
    )
    return DeploymentEventAccepted(
        id=event.id,
        hostname=event.hostname,
        attempt=event.attempt,
        status=DeploymentStage(event.stage),
        reported_at=_iso(event.event_at),
    )


@router.get("", response_model=list[DeploymentSummary])
async def list_deployments(request: Request, _user: User = Depends(current_user)):
    result = []
    for node in await _store(request).list_nodes():
        result.append(_summary(node, await _store(request).history(node.hostname) or []))
    return result


@router.get("/{hostname}", response_model=DeploymentDetail)
async def get_deployment(hostname: str, request: Request, _user: User = Depends(current_user)):
    try:
        normalized = normalize_hostname(hostname)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    node = await _store(request).get_node(normalized)
    if node is None:
        raise HTTPException(status_code=404, detail="deployment node not found")
    events = await _store(request).history(normalized) or []
    return DeploymentDetail(
        **_summary(node, events).model_dump(), timeline=[_timeline(e) for e in events]
    )


@router.get("/{hostname}/history", response_model=list[DeploymentTimelineEntry])
async def deployment_history(hostname: str, request: Request, _user: User = Depends(current_user)):
    try:
        normalized = normalize_hostname(hostname)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    events = await _store(request).history(normalized)
    if events is None:
        raise HTTPException(status_code=404, detail="deployment node not found")
    return [_timeline(event) for event in events]
