import httpx
import pytest
import respx

from app.netbox import NetBoxClient, PlaceNetBoxResponse, auth_header


@pytest.mark.asyncio
async def test_netbox_client_unconfigured():
    client = NetBoxClient(url=None, token=None)
    assert not client.is_configured
    resp = await client.get_place_info("tron")
    assert resp.configured is False
    assert resp.matched is False
    assert resp.device is None


@pytest.mark.asyncio
@respx.mock
async def test_netbox_client_device_matched():
    client = NetBoxClient(
        url="http://netbox.mock",
        token="testtoken123",
        public_url="https://netbox.public.mock",
        ttl_seconds=10,
    )
    assert client.is_configured

    device_payload = {
        "count": 1,
        "results": [
            {
                "id": 42,
                "name": "tron",
                "display": "tron",
                "status": {"value": "active", "label": "Active"},
                "site": {"id": 1, "name": "US-Home", "slug": "us-home"},
                "location": {"id": 1, "name": "Lab Bench", "slug": "lab-bench"},
                "rack": {"id": 10, "name": "Bench-Rack-1"},
                "position": 12.0,
                "face": {"value": "front", "label": "Front"},
                "device_type": {
                    "id": 5,
                    "model": "ADRV9009-ZU11EG",
                    "manufacturer": {"name": "Analog Devices"},
                },
                "role": {"name": "DUT"},
                "primary_ip": {"address": "10.0.1.243/24"},
                "comments": "Connected to ADRV2CRR-FMC",
            }
        ],
    }

    power_payload = {
        "count": 1,
        "results": [
            {
                "name": "Power 1",
                "link_peers": [
                    {
                        "device": {"name": "pdu-homeassistant"},
                        "name": "Outlet 1",
                    }
                ],
            }
        ],
    }

    console_payload = {
        "count": 1,
        "results": [
            {
                "name": "Console",
                "link_peers": [
                    {
                        "device": {"name": "tron-exporter"},
                        "name": "ttyUSB0",
                    }
                ],
            }
        ],
    }

    respx.get("http://netbox.mock/api/dcim/devices/?name=tron").respond(
        status_code=200, json=device_payload
    )
    respx.get("http://netbox.mock/api/dcim/power-ports/?device_id=42").respond(
        status_code=200, json=power_payload
    )
    respx.get("http://netbox.mock/api/dcim/console-ports/?device_id=42").respond(
        status_code=200, json=console_payload
    )

    res = await client.get_place_info("tron")
    assert res.configured is True
    assert res.matched is True
    assert res.device is not None
    assert res.device.id == 42
    assert res.device.name == "tron"
    assert res.device.url == "https://netbox.public.mock/dcim/devices/42/"
    assert res.device.rack == "Bench-Rack-1"
    assert res.device.rack_url == "https://netbox.public.mock/dcim/racks/10/"
    assert res.device.position == 12.0
    assert res.device.site == "US-Home"
    assert res.device.location == "Lab Bench"
    assert res.device.device_type == "ADRV9009-ZU11EG"
    assert res.device.manufacturer == "Analog Devices"
    assert res.device.primary_ip == "10.0.1.243/24"
    assert len(res.device.power_connections) == 1
    assert res.device.power_connections[0].connected_device == "pdu-homeassistant"
    assert res.device.power_connections[0].connected_outlet == "Outlet 1"
    assert len(res.device.console_connections) == 1
    assert res.device.console_connections[0].connected_device == "tron-exporter"
    assert res.device.console_connections[0].connected_port == "ttyUSB0"

    # Cached call: check that a second request returns cached response
    res2 = await client.get_place_info("tron")
    assert res2.device.id == 42
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_netbox_client_not_found():
    client = NetBoxClient(url="http://netbox.mock", token="testtoken123")
    respx.get("http://netbox.mock/api/dcim/devices/?name=unknown").respond(
        status_code=200, json={"count": 0, "results": []}
    )

    res = await client.get_place_info("unknown")
    assert res.configured is True
    assert res.matched is False
    assert res.device is None
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_netbox_client_network_error_graceful():
    client = NetBoxClient(url="http://netbox.mock", token="testtoken123")
    respx.get("http://netbox.mock/api/dcim/devices/?name=err").mock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    res = await client.get_place_info("err")
    assert res.configured is True
    assert res.matched is False
    assert res.error.startswith("cannot reach NetBox")
    assert res.device is None
    await client.close()


def test_get_place_netbox_endpoint_not_found(client):
    resp = client.get("/api/places/nonexistent/netbox")
    assert resp.status_code == 404


def test_get_place_netbox_endpoint_unconfigured(client_with_data):
    resp = client_with_data.get("/api/places/vcu118-lab1/netbox")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is False
    assert data["matched"] is False
    assert data["device"] is None


def test_get_place_netbox_endpoint_returns_the_lookup(client_with_data):
    from app.main import app

    seen = []

    class StubNetBox:
        async def get_place_info(self, name):
            seen.append(name)
            return PlaceNetBoxResponse(configured=True, matched=False)

    app.state.netbox = StubNetBox()
    try:
        resp = client_with_data.get("/api/places/vcu118-lab1/netbox")
    finally:
        del app.state.netbox
    assert resp.status_code == 200
    assert resp.json() == {"configured": True, "matched": False, "device": None, "error": None}
    assert seen == ["vcu118-lab1"]


@pytest.mark.parametrize(
    ("raw", "header"),
    [
        ("0123456789abcdef", "Token 0123456789abcdef"),
        ("nbt_abc.secret", "Bearer nbt_abc.secret"),
        ("  Bearer nbt_abc.secret ", "Bearer nbt_abc.secret"),
        ('"Token 0123"', "Token 0123"),
    ],
)
def test_the_token_is_sent_the_way_netbox_expects(raw, header):
    assert auth_header(raw) == header


@pytest.mark.asyncio
@respx.mock
async def test_the_token_goes_in_the_authorization_header():
    client = NetBoxClient(url="http://netbox.mock", token="nbt_abc.secret")
    route = respx.get("http://netbox.mock/api/dcim/devices/?name=tron").respond(
        status_code=200, json={"count": 0, "results": []}
    )

    await client.get_place_info("tron")

    assert route.calls.last.request.headers["Authorization"] == "Bearer nbt_abc.secret"
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_a_name_shared_by_several_devices_is_not_matched():
    # Device names are unique per site, so two sites can both have a "tron".
    client = NetBoxClient(url="http://netbox.mock", token="t")
    respx.get("http://netbox.mock/api/dcim/devices/?name=tron").respond(
        status_code=200,
        json={"count": 2, "results": [{"id": 1, "name": "tron"}, {"id": 2, "name": "tron"}]},
    )

    res = await client.get_place_info("tron")

    assert res.configured is True
    assert res.matched is False
    assert res.error is None  # NetBox answered; there's just no single match
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_a_rejected_token_is_not_matched_and_not_cached():
    client = NetBoxClient(url="http://netbox.mock", token="bad")
    route = respx.get("http://netbox.mock/api/dcim/devices/?name=tron").respond(
        status_code=403, json={"detail": "Invalid token"}
    )

    res = await client.get_place_info("tron")
    await client.get_place_info("tron")

    assert res.configured is True
    assert res.matched is False
    assert res.error == "NetBox rejected the API token (HTTP 403)"
    assert route.call_count == 2  # retried, not served from cache
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_the_last_answer_is_kept_while_netbox_is_down():
    client = NetBoxClient(url="http://netbox.mock", token="t", ttl_seconds=0)
    devices = respx.get("http://netbox.mock/api/dcim/devices/?name=tron")
    devices.respond(status_code=200, json={"count": 1, "results": [{"id": 7, "name": "tron"}]})
    respx.get("http://netbox.mock/api/dcim/power-ports/?device_id=7").respond(
        status_code=200, json={"results": []}
    )
    respx.get("http://netbox.mock/api/dcim/console-ports/?device_id=7").respond(
        status_code=200, json={"results": []}
    )
    assert (await client.get_place_info("tron")).matched is True

    devices.mock(side_effect=httpx.ConnectError("Connection refused"))
    res = await client.get_place_info("tron")

    assert res.matched is True
    assert res.device.id == 7
    assert res.error is None
    await client.close()


@pytest.mark.asyncio
@respx.mock
async def test_the_device_is_shown_when_its_cabling_cannot_be_read():
    client = NetBoxClient(url="http://netbox.mock", token="t")
    respx.get("http://netbox.mock/api/dcim/devices/?name=tron").respond(
        status_code=200, json={"count": 1, "results": [{"id": 7, "name": "tron"}]}
    )
    respx.get("http://netbox.mock/api/dcim/power-ports/?device_id=7").respond(status_code=500)
    respx.get("http://netbox.mock/api/dcim/console-ports/?device_id=7").mock(
        side_effect=httpx.ReadTimeout("slow")
    )

    res = await client.get_place_info("tron")

    assert res.matched is True
    assert res.device.url == "http://netbox.mock/dcim/devices/7/"
    assert res.device.power_connections == []
    assert res.device.console_connections == []
    await client.close()


@pytest.mark.asyncio
async def test_an_unreadable_ca_bundle_is_reported_not_raised(tmp_path):
    client = NetBoxClient(
        url="http://netbox.mock", token="t", ca_bundle=str(tmp_path / "missing.pem")
    )

    res = await client.get_place_info("tron")

    assert res.configured is True
    assert res.matched is False
    assert "cannot load NetBox CA bundle" in res.error
