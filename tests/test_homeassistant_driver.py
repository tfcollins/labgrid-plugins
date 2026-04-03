import os
import time
from unittest.mock import MagicMock, patch

import pytest

from adi_lg_plugins.drivers.homeassistantdriver import (
    HomeAssistantClient,
    HomeAssistantException,
)

HA_URL = os.environ.get("HA_URL", "http://ha.local:8123")
HA_TOKEN = os.environ.get("HA_TOKEN", "test-token")
HA_ENTITY_ID = os.environ.get("HA_ENTITY_ID", "light.office")


@pytest.fixture
def mock_api_check():
    """Patch _check_api so client can be created without a real HA instance."""
    with patch.object(HomeAssistantClient, "_check_api"):
        yield


@pytest.fixture
def client(mock_api_check):
    return HomeAssistantClient(HA_URL, HA_TOKEN)


class TestHomeAssistantClient:
    def test_check_api_success(self):
        with patch("adi_lg_plugins.drivers.homeassistantdriver.requests") as mock_requests:
            mock_requests.RequestException = Exception
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_requests.get.return_value = mock_resp
            client = HomeAssistantClient(HA_URL, HA_TOKEN)
            mock_requests.get.assert_called_once_with(
                f"{HA_URL}/api/",
                headers=client.headers,
                timeout=10,
            )

    def test_check_api_failure(self):
        with patch("adi_lg_plugins.drivers.homeassistantdriver.requests") as mock_requests:
            mock_requests.RequestException = Exception
            mock_requests.get.side_effect = Exception("Connection refused")
            with pytest.raises(HomeAssistantException, match="Failed to connect"):
                HomeAssistantClient(HA_URL, HA_TOKEN)

    def test_url_trailing_slash_stripped(self, mock_api_check):
        client = HomeAssistantClient(HA_URL + "/", HA_TOKEN)
        assert client.url == HA_URL

    def test_turn_on(self, client):
        with patch("adi_lg_plugins.drivers.homeassistantdriver.requests") as mock_requests:
            mock_resp = MagicMock()
            mock_resp.ok = True
            mock_requests.post.return_value = mock_resp
            client.turn_on("switch.outlet_1")
            mock_requests.post.assert_called_once_with(
                f"{HA_URL}/api/services/switch/turn_on",  # domain from entity_id
                headers=client.headers,
                json={"entity_id": "switch.outlet_1"},
                timeout=10,
            )

    def test_turn_off(self, client):
        with patch("adi_lg_plugins.drivers.homeassistantdriver.requests") as mock_requests:
            mock_resp = MagicMock()
            mock_resp.ok = True
            mock_requests.post.return_value = mock_resp
            client.turn_off("switch.outlet_1")
            mock_requests.post.assert_called_once_with(
                f"{HA_URL}/api/services/switch/turn_off",  # domain from entity_id
                headers=client.headers,
                json={"entity_id": "switch.outlet_1"},
                timeout=10,
            )

    def test_turn_on_error(self, client):
        with patch("adi_lg_plugins.drivers.homeassistantdriver.requests") as mock_requests:
            mock_resp = MagicMock()
            mock_resp.ok = False
            mock_resp.status_code = 401
            mock_resp.text = "Unauthorized"
            mock_requests.post.return_value = mock_resp
            with pytest.raises(HomeAssistantException, match="Failed to turn on"):
                client.turn_on("switch.outlet_1")

    def test_turn_off_error(self, client):
        with patch("adi_lg_plugins.drivers.homeassistantdriver.requests") as mock_requests:
            mock_resp = MagicMock()
            mock_resp.ok = False
            mock_resp.status_code = 404
            mock_resp.text = "Not Found"
            mock_requests.post.return_value = mock_resp
            with pytest.raises(HomeAssistantException, match="Failed to turn off"):
                client.turn_off("switch.outlet_1")

    def test_get_state_on(self, client):
        with patch("adi_lg_plugins.drivers.homeassistantdriver.requests") as mock_requests:
            mock_resp = MagicMock()
            mock_resp.ok = True
            mock_resp.json.return_value = {"state": "on"}
            mock_requests.get.return_value = mock_resp
            assert client.get_state("switch.outlet_1") is True

    def test_get_state_off(self, client):
        with patch("adi_lg_plugins.drivers.homeassistantdriver.requests") as mock_requests:
            mock_resp = MagicMock()
            mock_resp.ok = True
            mock_resp.json.return_value = {"state": "off"}
            mock_requests.get.return_value = mock_resp
            assert client.get_state("switch.outlet_1") is False

    def test_get_state_error(self, client):
        with patch("adi_lg_plugins.drivers.homeassistantdriver.requests") as mock_requests:
            mock_resp = MagicMock()
            mock_resp.ok = False
            mock_resp.status_code = 404
            mock_resp.text = "Not Found"
            mock_requests.get.return_value = mock_resp
            with pytest.raises(HomeAssistantException, match="Failed to get state"):
                client.get_state("switch.outlet_1")

    def test_auth_header(self, client):
        assert client.headers["Authorization"] == f"Bearer {HA_TOKEN}"
        assert client.headers["Content-Type"] == "application/json"

    def test_domain_extraction(self):
        assert HomeAssistantClient._domain("switch.outlet_1") == "switch"
        assert HomeAssistantClient._domain("light.office") == "light"
        assert HomeAssistantClient._domain("input_boolean.flag") == "input_boolean"


@pytest.mark.hardware
class TestHomeAssistantHardware:
    """Hardware tests that talk to a real Home Assistant instance.

    Run with:
        HA_URL=http://192.168.1.100:8123 HA_TOKEN=your-token HA_ENTITY_ID=light.office \
            pytest tests/test_homeassistant_driver.py -k hardware --run-hardware
    """

    @pytest.fixture(autouse=True)
    def _require_env(self):
        if HA_TOKEN == "test-token":
            pytest.skip("HA_TOKEN not set")

    @pytest.fixture
    def client(self):
        return HomeAssistantClient(HA_URL, HA_TOKEN)

    def test_api_reachable(self, client):
        """Verify the Home Assistant API is reachable."""
        assert client.url == HA_URL.rstrip("/")

    def test_turn_on(self, client):
        client.turn_on(HA_ENTITY_ID)
        time.sleep(5)
        assert client.get_state(HA_ENTITY_ID) is True

    def test_turn_off(self, client):
        client.turn_off(HA_ENTITY_ID)
        time.sleep(5)
        assert client.get_state(HA_ENTITY_ID) is False

    def test_cycle(self, client):
        client.turn_off(HA_ENTITY_ID)
        time.sleep(5)
        assert client.get_state(HA_ENTITY_ID) is False
        client.turn_on(HA_ENTITY_ID)
        time.sleep(5)
        assert client.get_state(HA_ENTITY_ID) is True
