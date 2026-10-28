"""Unit tests for the coordinator REST write helpers (login/create_place/
add_match/set_place_tags) added to adi_lg_plugins.hw_ci.coordinator.

Mocked the same way tests/test_discover_places.py mocks the read path:
monkeypatch `urllib.request.urlopen` with a fake that inspects the
`Request` object and returns a canned response.
"""

from __future__ import annotations

import io
import json
import urllib.error

import pytest

from adi_lg_plugins.hw_ci import coordinator as coord_mod


class _Resp(io.BytesIO):
    def __init__(self, body: bytes, headers: dict[str, str] | None = None):
        super().__init__(body)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_login_returns_session_cookie(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["body"] = json.loads(req.data)
        resp = _Resp(b'{"username": "admin", "role": "admin"}')
        resp.headers = {"Set-Cookie": "lg_session=abc123; Path=/; HttpOnly"}
        return resp

    monkeypatch.setattr(coord_mod.urllib.request, "urlopen", fake_urlopen)
    cookie = coord_mod.login("coord:8000", "admin", "hunter2")

    assert captured["url"] == "http://coord:8000/api/auth/login"
    assert captured["method"] == "POST"
    assert captured["body"] == {"username": "admin", "password": "hunter2"}
    assert cookie == "lg_session=abc123"


def test_login_raises_without_cookie(monkeypatch):
    def fake_urlopen(req, timeout=None):
        resp = _Resp(b"{}")
        resp.headers = {}
        return resp

    monkeypatch.setattr(coord_mod.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="no session cookie"):
        coord_mod.login("coord:8000", "admin", "hunter2")


def test_login_raises_on_bad_credentials(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 401, "Unauthorized", {}, io.BytesIO(b"invalid credentials")
        )

    monkeypatch.setattr(coord_mod.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="401"):
        coord_mod.login("coord:8000", "admin", "wrong")


def test_create_place_posts_name_with_cookie(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["body"] = json.loads(req.data)
        captured["cookie"] = req.headers.get("Cookie")
        return _Resp(b'{"name": "rack1"}')

    monkeypatch.setattr(coord_mod.urllib.request, "urlopen", fake_urlopen)
    coord_mod.create_place("coord:8000", "lg_session=abc123", "rack1")

    assert captured["url"] == "http://coord:8000/api/places"
    assert captured["method"] == "POST"
    assert captured["body"] == {"name": "rack1"}
    assert captured["cookie"] == "lg_session=abc123"


def test_create_place_swallows_already_exists(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 400, "Bad Request", {}, io.BytesIO(b"place 'rack1' already exists")
        )

    monkeypatch.setattr(coord_mod.urllib.request, "urlopen", fake_urlopen)
    coord_mod.create_place("coord:8000", "lg_session=abc123", "rack1")  # must not raise


def test_create_place_reraises_other_errors(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 401, "Unauthorized", {}, io.BytesIO(b"not authenticated")
        )

    monkeypatch.setattr(coord_mod.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError, match="401"):
        coord_mod.create_place("coord:8000", "lg_session=abc123", "rack1")


def test_add_match_posts_pattern(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        return _Resp(b"{}")

    monkeypatch.setattr(coord_mod.urllib.request, "urlopen", fake_urlopen)
    coord_mod.add_match("coord:8000", "lg_session=abc123", "rack1", "host/GROUP/*")

    assert captured["url"] == "http://coord:8000/api/places/rack1/matches"
    assert captured["body"] == {"pattern": "host/GROUP/*", "rename": None}


def test_set_place_tags_puts_tags(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["body"] = json.loads(req.data)
        return _Resp(b"{}")

    monkeypatch.setattr(coord_mod.urllib.request, "urlopen", fake_urlopen)
    coord_mod.set_place_tags("coord:8000", "lg_session=abc123", "rack1", {"carrier": "zcu102"})

    assert captured["url"] == "http://coord:8000/api/places/rack1/tags"
    assert captured["method"] == "PUT"
    assert captured["body"] == {"tags": {"carrier": "zcu102"}}


def test_get_place_returns_the_place(monkeypatch):
    captured = {}

    def fake_urlopen(url, timeout=None):
        captured["url"] = url
        return _Resp(b'{"name": "rack1", "matches": [], "tags": {}}')

    monkeypatch.setattr(coord_mod.urllib.request, "urlopen", fake_urlopen)

    assert coord_mod.get_place("coord:8000", "rack1")["name"] == "rack1"
    assert captured["url"] == "http://coord:8000/api/places/rack1"


def test_get_place_returns_none_for_an_unknown_place(monkeypatch):
    def fake_urlopen(url, timeout=None):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO(b"not found"))

    monkeypatch.setattr(coord_mod.urllib.request, "urlopen", fake_urlopen)

    assert coord_mod.get_place("coord:8000", "rack1") is None


def test_get_place_reports_other_errors(monkeypatch):
    def fake_urlopen(url, timeout=None):
        raise urllib.error.HTTPError(url, 502, "Bad Gateway", {}, io.BytesIO(b"no coordinator"))

    monkeypatch.setattr(coord_mod.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="502 no coordinator"):
        coord_mod.get_place("coord:8000", "rack1")


@pytest.mark.parametrize(
    ("match", "pattern"),
    [
        (
            {"exporter": "rack1", "group": "ZCU102_AD9081", "cls": "*", "name": None},
            "rack1/ZCU102_AD9081/*",
        ),
        (
            {"exporter": "*", "group": "g", "cls": "SerialPort", "name": "uart"},
            "*/g/SerialPort/uart",
        ),
    ],
)
def test_match_pattern_is_the_pattern_the_match_was_added_with(match, pattern):
    assert coord_mod.match_pattern(match) == pattern
