"""Mocked unit tests for the Kasa (TP-Link) power driver/resource (no network).

All ``python-kasa`` I/O is mocked: ``Discover.discover_single`` is patched to
return a fake async device, so the sync driver methods (which internally call
``asyncio.run``) exercise child resolution and on/off/get without a network.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from labgrid.binding import BindingState

pytest.importorskip("kasa")

from adi_lg_plugins.drivers import kasadriver as kd
from adi_lg_plugins.drivers.kasadriver import KasaPowerDriver
from adi_lg_plugins.resources.kasa import KasaOutlet

# --- fakes ------------------------------------------------------------------


class FakeChild:
    """Minimal stand-in for a python-kasa child socket / single device."""

    def __init__(self, alias, is_on=False):
        self.alias = alias
        self.is_on = is_on

    async def turn_on(self):
        self.is_on = True

    async def turn_off(self):
        self.is_on = False


class FakeDevice:
    """Minimal stand-in for a python-kasa Device (strip or single plug)."""

    def __init__(self, alias="plug", children=None, is_on=False):
        self.alias = alias
        self.children = children or []
        self.is_on = is_on
        self.disconnected = False

    async def turn_on(self):
        self.is_on = True

    async def turn_off(self):
        self.is_on = False

    async def update(self):
        pass

    async def disconnect(self):
        self.disconnected = True


def _patch_device(monkeypatch, device):
    """Patch Discover.discover_single to return ``device`` and record kwargs."""
    calls = {}

    async def fake_discover_single(host, **kwargs):
        calls["host"] = host
        calls["kwargs"] = kwargs
        return device

    monkeypatch.setattr(kd.Discover, "discover_single", fake_discover_single)
    return calls


def _driver(outlets=None, username=None, password=None, delay=5.0):
    """Build a KasaPowerDriver bypassing labgrid bind/activate machinery."""
    res = MagicMock(spec=KasaOutlet)
    res.host = "10.0.0.5"
    res.outlets = outlets
    res.username = username
    res.password = password
    res.delay = delay
    drv = KasaPowerDriver.__new__(KasaPowerDriver)
    drv.kasa_outlet = res
    drv.logger = MagicMock()
    # labgrid sets this at bind/activate time; @Driver.check_active needs it.
    drv.state = BindingState.active
    return drv, res


# --- resource ---------------------------------------------------------------


def test_resource_requires_host():
    from labgrid import Target

    with pytest.raises(TypeError):
        KasaOutlet(Target("t-no-host"), name=None)


def test_resource_defaults_and_optionals():
    from labgrid import Target

    res = KasaOutlet(Target("t-kasa"), name=None, host="10.0.0.5")
    assert res.host == "10.0.0.5"
    assert res.outlets is None
    assert res.username is None
    assert res.password is None
    assert res.delay == 5.0


def test_resource_credentials_from_env(monkeypatch):
    from labgrid import Target

    monkeypatch.setenv("KASA_USERNAME", "user@example.com")
    monkeypatch.setenv("KASA_PASSWORD", "secret")
    res = KasaOutlet(Target("t-kasa-env"), name=None, host="10.0.0.5")
    assert res.username == "user@example.com"
    assert res.password == "secret"


# --- single plug (no children) ----------------------------------------------


def test_single_plug_on_off_get(monkeypatch):
    dev = FakeDevice(alias="bench-plug")
    _patch_device(monkeypatch, dev)
    drv, _ = _driver()

    drv.on()
    assert dev.is_on is True
    assert dev.disconnected is True  # connection closed after the op

    assert drv.get() is True

    drv.off()
    assert dev.is_on is False
    assert drv.get() is False


# --- power strip: default selects all children ------------------------------


def test_strip_default_controls_all_children(monkeypatch):
    children = [FakeChild("plug0"), FakeChild("plug1"), FakeChild("plug2")]
    dev = FakeDevice(alias="strip", children=children)
    _patch_device(monkeypatch, dev)
    drv, _ = _driver(outlets=None)

    drv.on()
    assert all(c.is_on for c in children)

    drv.off()
    assert not any(c.is_on for c in children)


# --- power strip: select children by index ----------------------------------


def test_strip_selects_children_by_index(monkeypatch):
    children = [FakeChild("plug0"), FakeChild("plug1"), FakeChild("plug2")]
    dev = FakeDevice(alias="strip", children=children)
    _patch_device(monkeypatch, dev)
    drv, _ = _driver(outlets="0, 2")

    drv.on()
    assert children[0].is_on is True
    assert children[1].is_on is False  # not selected
    assert children[2].is_on is True

    # get() reflects only the selected children
    assert drv.get() is True
    children[2].is_on = False
    assert drv.get() is False


# --- power strip: select children by alias ----------------------------------


def test_strip_selects_children_by_alias(monkeypatch):
    children = [FakeChild("left"), FakeChild("middle"), FakeChild("right")]
    dev = FakeDevice(alias="strip", children=children)
    _patch_device(monkeypatch, dev)
    drv, _ = _driver(outlets="left,right")

    drv.on()
    assert children[0].is_on is True
    assert children[1].is_on is False
    assert children[2].is_on is True


def test_unmatched_selector_raises(monkeypatch):
    children = [FakeChild("left"), FakeChild("right")]
    dev = FakeDevice(alias="strip", children=children)
    _patch_device(monkeypatch, dev)
    drv, _ = _driver(outlets="nope")

    with pytest.raises(Exception, match="nope"):
        drv.on()


# --- credentials forwarded to discovery -------------------------------------


def test_credentials_forwarded_to_discover(monkeypatch):
    dev = FakeDevice()
    calls = _patch_device(monkeypatch, dev)
    drv, _ = _driver(username="user@example.com", password="secret")

    drv.on()
    assert calls["host"] == "10.0.0.5"
    assert calls["kwargs"].get("username") == "user@example.com"
    assert calls["kwargs"].get("password") == "secret"


def test_no_credentials_not_forwarded(monkeypatch):
    dev = FakeDevice()
    calls = _patch_device(monkeypatch, dev)
    drv, _ = _driver()

    drv.on()
    assert calls["kwargs"].get("username") is None
    assert calls["kwargs"].get("password") is None


# --- reset cycles off -> delay -> on ----------------------------------------


def test_reset_off_delay_on(monkeypatch):
    children = [FakeChild("plug0", is_on=True)]
    dev = FakeDevice(alias="strip", children=children)
    _patch_device(monkeypatch, dev)
    drv, _ = _driver(outlets=None, delay=1.5)

    sleeps = []
    monkeypatch.setattr(kd.time, "sleep", lambda s: sleeps.append(s))

    drv.reset()
    assert sleeps == [1.5]
    assert children[0].is_on is True  # ended powered on
