"""Minimal OIDC Authorization Code client."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx


class OIDCDisabled(RuntimeError):
    pass


@dataclass
class OIDCUserInfo:
    subject: str
    username: str
    email: str | None


class OIDCClient:
    def __init__(
        self,
        *,
        issuer: str | None,
        client_id: str | None,
        client_secret: str | None,
    ):
        self.issuer = issuer.rstrip("/") if issuer else None
        self.client_id = client_id
        self.client_secret = client_secret
        self._metadata: dict | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.issuer and self.client_id and self.client_secret)

    def _require_enabled(self):
        if not self.enabled:
            raise OIDCDisabled("OIDC is not configured")

    async def discover(self) -> dict:
        self._require_enabled()
        if self._metadata is not None:
            return self._metadata
        url = f"{self.issuer}/.well-known/openid-configuration"
        async with httpx.AsyncClient() as c:
            r = await c.get(url)
            r.raise_for_status()
            self._metadata = r.json()
        return self._metadata

    def authorization_url(self, redirect_uri: str) -> tuple[str, str]:
        self._require_enabled()
        if self._metadata is None:
            raise RuntimeError("call discover() first")
        state = secrets.token_urlsafe(16)
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "scope": "openid profile email",
            "redirect_uri": redirect_uri,
            "state": state,
        }
        return f"{self._metadata['authorization_endpoint']}?{urlencode(params)}", state

    async def exchange_code(self, *, code: str, redirect_uri: str) -> OIDCUserInfo:
        self._require_enabled()
        md = await self.discover()
        async with httpx.AsyncClient() as c:
            tok = await c.post(
                md["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
            tok.raise_for_status()
            access = tok.json()["access_token"]
            ui = await c.get(
                md["userinfo_endpoint"],
                headers={"Authorization": f"Bearer {access}"},
            )
            ui.raise_for_status()
            data = ui.json()
        return OIDCUserInfo(
            subject=data["sub"],
            username=data.get("preferred_username") or data.get("email") or data["sub"],
            email=data.get("email"),
        )
