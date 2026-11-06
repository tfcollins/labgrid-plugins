"""Read-only NetBox lookup for the place detail page.

A place is matched to the NetBox device of the same name: ``adi-lg netbox
add-hardware`` registers each board under its place name. Only an exact,
unique name match counts - a near miss would show another board's rack,
outlet and console as this place's.

Failures never raise into the API: an unreachable NetBox, a bad token or an
unexpected payload is logged and reported as "not matched" (or the last good
answer, while it is cached).
"""

from __future__ import annotations

import asyncio
import logging
import re
import ssl
import time
from typing import Any

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# NetBox 4.5+ accepts "Bearer nbt_<key>.<token>" for v2 tokens and
# "Token <token>" for v1 ones - the same scheme pynetbox uses for add-hardware.
_HEADER_PREFIX = re.compile(r"^(?:authorization:\s*)?(?:bearer|token)(?:\s+|$)", re.IGNORECASE)


def auth_header(raw_token: str) -> str:
    """The Authorization header value for a token as pasted (prefix and quotes dropped)."""
    token = _HEADER_PREFIX.sub("", raw_token.strip().strip("\"'").strip())
    return f"Bearer {token}" if token.startswith("nbt_") else f"Token {token}"


class NetBoxPowerConnection(BaseModel):
    port_name: str
    connected_device: str | None = None
    connected_outlet: str | None = None


class NetBoxConsoleConnection(BaseModel):
    port_name: str
    connected_device: str | None = None
    connected_port: str | None = None


class NetBoxDeviceInfo(BaseModel):
    id: int
    name: str
    display: str | None = None
    url: str
    status: str | None = None
    site: str | None = None
    location: str | None = None
    rack: str | None = None
    rack_url: str | None = None
    position: float | None = None
    face: str | None = None
    device_type: str | None = None
    manufacturer: str | None = None
    role: str | None = None
    primary_ip: str | None = None
    comments: str | None = None
    power_connections: list[NetBoxPowerConnection] = Field(default_factory=list)
    console_connections: list[NetBoxConsoleConnection] = Field(default_factory=list)


class PlaceNetBoxResponse(BaseModel):
    configured: bool = True
    matched: bool = False
    device: NetBoxDeviceInfo | None = None


def _name(obj: Any) -> str | None:
    return obj.get("name") if isinstance(obj, dict) else None


def _choice(obj: Any) -> str | None:
    """A NetBox choice field: ``{"value": ..., "label": ...}``, or a bare value."""
    if isinstance(obj, dict):
        return obj.get("value")
    return str(obj) if obj else None


def _peer(port: dict) -> tuple[str | None, str | None]:
    """(device, port) at the far end of the cable on ``port``, if it is cabled."""
    peers = port.get("link_peers") or []
    if not peers or not isinstance(peers[0], dict):
        return None, None
    return _name(peers[0].get("device")), peers[0].get("name")


class NetBoxClient:
    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        public_url: str | None = None,
        ttl_seconds: int = 60,
        verify: bool = True,
        ca_bundle: str | None = None,
    ):
        self.url = url.rstrip("/") if url else None
        self.token = token
        self.public_url = public_url.rstrip("/") if public_url else self.url
        self.ttl_seconds = ttl_seconds
        self.verify: bool | ssl.SSLContext = (
            ssl.create_default_context(cafile=ca_bundle) if verify and ca_bundle else verify
        )
        self._cache: dict[str, tuple[float, PlaceNetBoxResponse]] = {}
        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.url and self.token)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.url,
                headers={"Authorization": auth_header(self.token), "Accept": "application/json"},
                timeout=5.0,
                verify=self.verify,
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def get_place_info(self, place_name: str) -> PlaceNetBoxResponse:
        if not self.is_configured:
            return PlaceNetBoxResponse(configured=False, matched=False, device=None)

        now = time.monotonic()
        cached = self._cache.get(place_name)
        if cached and now - cached[0] < self.ttl_seconds:
            return cached[1]

        try:
            res = await self._fetch_device(place_name)
        except Exception as e:
            logger.warning("NetBox lookup failed for place '%s': %s", place_name, e)
            if cached:
                return cached[1]
            return PlaceNetBoxResponse(configured=True, matched=False, device=None)
        self._cache[place_name] = (now, res)
        return res

    async def _fetch_device(self, place_name: str) -> PlaceNetBoxResponse:
        client = self._get_client()
        resp = await client.get("/api/dcim/devices/", params={"name": place_name})
        resp.raise_for_status()
        results = resp.json().get("results", [])

        if len(results) != 1:
            if results:
                logger.warning(
                    "NetBox has %d devices named '%s' (one per site?); not picking one",
                    len(results),
                    place_name,
                )
            return PlaceNetBoxResponse(configured=True, matched=False, device=None)

        raw = results[0]
        dev_id = raw["id"]
        base = self.public_url
        rack = raw.get("rack") if isinstance(raw.get("rack"), dict) else None
        dtype = raw.get("device_type") if isinstance(raw.get("device_type"), dict) else {}
        ip = raw.get("primary_ip")

        power, console = await self._fetch_connections(client, dev_id)

        return PlaceNetBoxResponse(
            configured=True,
            matched=True,
            device=NetBoxDeviceInfo(
                id=dev_id,
                name=raw.get("name") or place_name,
                display=raw.get("display"),
                url=f"{base}/dcim/devices/{dev_id}/",
                status=_choice(raw.get("status")),
                site=_name(raw.get("site")),
                location=_name(raw.get("location")),
                rack=_name(rack),
                rack_url=f"{base}/dcim/racks/{rack['id']}/" if rack and rack.get("id") else None,
                position=raw.get("position"),
                face=_choice(raw.get("face")),
                device_type=dtype.get("model"),
                manufacturer=_name(dtype.get("manufacturer")),
                role=_name(raw.get("role")),
                primary_ip=ip.get("address") if isinstance(ip, dict) else None,
                comments=raw.get("comments") or None,
                power_connections=power,
                console_connections=console,
            ),
        )

    async def _fetch_connections(
        self, client: httpx.AsyncClient, device_id: int
    ) -> tuple[list[NetBoxPowerConnection], list[NetBoxConsoleConnection]]:
        """The device's power and console ports and what each is cabled to.

        Best effort: a failure here still shows the device, just without its cabling.
        """
        power_resp, console_resp = await asyncio.gather(
            client.get("/api/dcim/power-ports/", params={"device_id": device_id}),
            client.get("/api/dcim/console-ports/", params={"device_id": device_id}),
            return_exceptions=True,
        )

        def ports(resp, endpoint: str) -> list[dict]:
            if isinstance(resp, httpx.Response) and resp.status_code == 200:
                return resp.json().get("results", [])
            logger.warning("NetBox %s for device %s failed: %s", endpoint, device_id, resp)
            return []

        power = []
        for port in ports(power_resp, "power-ports"):
            dev, outlet = _peer(port)
            power.append(
                NetBoxPowerConnection(
                    port_name=port.get("name", "Power"),
                    connected_device=dev,
                    connected_outlet=outlet,
                )
            )
        console = []
        for port in ports(console_resp, "console-ports"):
            dev, peer_port = _peer(port)
            console.append(
                NetBoxConsoleConnection(
                    port_name=port.get("name", "Console"),
                    connected_device=dev,
                    connected_port=peer_port,
                )
            )
        return power, console
