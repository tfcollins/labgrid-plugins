import json


def test_websocket_initial_state(client_with_data):
    with client_with_data.websocket_connect("/api/ws") as ws:
        data = json.loads(ws.receive_text())
        assert data["type"] == "initial_state"
        assert len(data["data"]["places"]) == 2
        assert len(data["data"]["resources"]) == 3


def test_websocket_initial_state_empty(client):
    with client.websocket_connect("/api/ws") as ws:
        data = json.loads(ws.receive_text())
        assert data["type"] == "initial_state"
        assert data["data"]["places"] == []
        assert data["data"]["resources"] == []
