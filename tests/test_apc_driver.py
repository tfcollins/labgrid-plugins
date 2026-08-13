"""Unit tests for the APC PDU driver status helpers."""

from unittest.mock import MagicMock

import pytest
from labgrid.binding import BindingState

from adi_lg_plugins.drivers.apcpowerdriver import APCDriver, APCPdu, APCPduException


@pytest.fixture
def pdu():
    return APCPdu("10.0.0.42")


def test_get_outlet_status_reads_status_for_v7(monkeypatch, pdu):
    transport = object()

    async def fake_transport_create(_host):
        return transport

    async def fake_get_cmd(_dispatcher, _community, _target, _varbind):
        value = MagicMock()
        value.prettyPrint.return_value = "1"
        varbind = (MagicMock(), value)
        return (None, None, None, (varbind,))

    monkeypatch.setattr(
        "adi_lg_plugins.drivers.apcpowerdriver.UdpTransportTarget.create",
        fake_transport_create,
    )
    monkeypatch.setattr(
        "adi_lg_plugins.drivers.apcpowerdriver.get_cmd",
        fake_get_cmd,
    )

    assert pdu.get_outlet_status(3) == 1


def test_get_outlet_status_raises_on_snmp_error(monkeypatch, pdu):
    async def fake_transport_create(_host):
        return object()

    async def fake_get_cmd(_dispatcher, _community, _target, _varbind):
        return ("boom", None, None, ())

    monkeypatch.setattr(
        "adi_lg_plugins.drivers.apcpowerdriver.UdpTransportTarget.create",
        fake_transport_create,
    )
    monkeypatch.setattr(
        "adi_lg_plugins.drivers.apcpowerdriver.get_cmd",
        fake_get_cmd,
    )

    with pytest.raises(APCPduException, match="boom"):
        pdu.get_outlet_status(5)


def test_get_outlet_status_raises_on_missing_varbinds(monkeypatch, pdu):
    async def fake_transport_create(_host):
        return object()

    async def fake_get_cmd(_dispatcher, _community, _target, _varbind):
        return (None, None, None, ())

    monkeypatch.setattr(
        "adi_lg_plugins.drivers.apcpowerdriver.UdpTransportTarget.create",
        fake_transport_create,
    )
    monkeypatch.setattr(
        "adi_lg_plugins.drivers.apcpowerdriver.get_cmd",
        fake_get_cmd,
    )

    with pytest.raises(APCPduException, match="No SNMP response"):
        pdu.get_outlet_status(8)


def test_apc_pdu_defaults_to_private_write_community(monkeypatch):
    async def fake_transport_create(_host):
        return object()

    async def fake_set_cmd(_dispatcher, _community, _target, _varbind):
        assert _community.communityName == "private"
        return (None, None, None, ())

    monkeypatch.setattr(
        "adi_lg_plugins.drivers.apcpowerdriver.UdpTransportTarget.create",
        fake_transport_create,
    )
    monkeypatch.setattr(
        "adi_lg_plugins.drivers.apcpowerdriver.set_cmd",
        fake_set_cmd,
    )

    APCPdu("10.0.0.42").set_outlet_on(3, True)


def test_apc_pdu_uses_configured_read_and_write_communities(monkeypatch):
    pdu = APCPdu("10.0.0.42", read_community="lab-read", write_community="lab-write")

    async def fake_transport_create(_host):
        return object()

    async def fake_get_cmd(_dispatcher, _community, _target, _varbind):
        assert _community.communityName == "lab-read"
        value = MagicMock()
        value.prettyPrint.return_value = "1"
        varbind = (MagicMock(), value)
        return (None, None, None, (varbind,))

    async def fake_set_cmd(_dispatcher, _community, _target, _varbind):
        assert _community.communityName == "lab-write"
        return (None, None, None, ())

    monkeypatch.setattr(
        "adi_lg_plugins.drivers.apcpowerdriver.UdpTransportTarget.create",
        fake_transport_create,
    )
    monkeypatch.setattr(
        "adi_lg_plugins.drivers.apcpowerdriver.get_cmd",
        fake_get_cmd,
    )
    monkeypatch.setattr(
        "adi_lg_plugins.drivers.apcpowerdriver.set_cmd",
        fake_set_cmd,
    )

    assert pdu.get_outlet_status(3) == 1
    pdu.set_outlet_on(3, False)


def _active_driver_with_status(status_code: int):
    driver = APCDriver.__new__(APCDriver)
    driver.logger = MagicMock()
    driver.state = BindingState.active
    driver.outlet = 2
    driver.pdu_dev = MagicMock()
    driver.pdu_dev.get_outlet_status.return_value = status_code
    return driver


def test_apc_driver_get_reports_on_for_on_status():
    driver = _active_driver_with_status(1)
    assert driver.get() is True


def test_apc_driver_get_reports_off_for_off_status():
    driver = _active_driver_with_status(2)
    assert driver.get() is False
