import pytest
import respx
from httpx import Response

from app.auth.oidc import OIDCClient, OIDCDisabled


def test_disabled_when_no_issuer():
    c = OIDCClient(issuer=None, client_id=None, client_secret=None)
    assert c.enabled is False
    with pytest.raises(OIDCDisabled):
        c.authorization_url("http://cb")


def test_enabled_when_configured():
    c = OIDCClient(issuer="https://idp.example/", client_id="abc", client_secret="xyz")
    assert c.enabled is True


@respx.mock
@pytest.mark.asyncio
async def test_discover_caches_metadata():
    respx.get("https://idp.example/.well-known/openid-configuration").mock(
        return_value=Response(
            200,
            json={
                "authorization_endpoint": "https://idp.example/authorize",
                "token_endpoint": "https://idp.example/token",
                "jwks_uri": "https://idp.example/jwks",
                "issuer": "https://idp.example/",
            },
        )
    )
    c = OIDCClient(issuer="https://idp.example/", client_id="abc", client_secret="xyz")
    md = await c.discover()
    assert md["authorization_endpoint"] == "https://idp.example/authorize"
    md2 = await c.discover()
    assert md2 is md  # cached


@respx.mock
@pytest.mark.asyncio
async def test_authorization_url_includes_state():
    respx.get("https://idp.example/.well-known/openid-configuration").mock(
        return_value=Response(
            200,
            json={
                "authorization_endpoint": "https://idp.example/authorize",
                "token_endpoint": "https://idp.example/token",
                "jwks_uri": "https://idp.example/jwks",
                "issuer": "https://idp.example/",
            },
        )
    )
    c = OIDCClient(issuer="https://idp.example/", client_id="abc", client_secret="xyz")
    await c.discover()
    url, state = c.authorization_url("https://app/callback")
    assert url.startswith("https://idp.example/authorize?")
    assert "client_id=abc" in url
    assert "redirect_uri=https" in url
    assert f"state={state}" in url
    assert "scope=openid+profile+email" in url


@respx.mock
@pytest.mark.asyncio
async def test_exchange_code_returns_subject_and_username():
    respx.get("https://idp.example/.well-known/openid-configuration").mock(
        return_value=Response(
            200,
            json={
                "authorization_endpoint": "https://idp.example/authorize",
                "token_endpoint": "https://idp.example/token",
                "userinfo_endpoint": "https://idp.example/userinfo",
                "jwks_uri": "https://idp.example/jwks",
                "issuer": "https://idp.example/",
            },
        )
    )
    respx.post("https://idp.example/token").mock(
        return_value=Response(200, json={"access_token": "AT", "token_type": "Bearer"})
    )
    respx.get("https://idp.example/userinfo").mock(
        return_value=Response(
            200,
            json={
                "sub": "user-123",
                "preferred_username": "alice",
                "email": "alice@example.com",
            },
        )
    )
    c = OIDCClient(issuer="https://idp.example/", client_id="abc", client_secret="xyz")
    info = await c.exchange_code(code="CODE", redirect_uri="https://app/callback")
    assert info.subject == "user-123"
    assert info.username == "alice"
