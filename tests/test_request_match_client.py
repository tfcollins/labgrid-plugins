from adi_lg_plugins.request import match_client


def test_get_match_parses_response(monkeypatch):
    captured = {}

    def fake_get_json(url, timeout=15.0):
        captured["url"] = url
        return {
            "satisfiable": True,
            "reason": "",
            "reservation_filter": {"daughter-board": "ad9361"},
            "version": "2023_R2_P1",
            "matlab_boards": {"zcu102": "zynqmp-zcu102-rev10-ad9361-fmcomms2-3"},
            "candidates": [{"place": "p1", "carrier": "zcu102", "acquired": False}],
        }

    monkeypatch.setattr(match_client, "_get_json", fake_get_json)

    res = match_client.get_match("10.0.0.41:8000", part="ad9361", carrier="zcu102")

    assert res.satisfiable is True
    assert res.reservation_filter == {"daughter-board": "ad9361"}
    assert res.version == "2023_R2_P1"
    assert res.candidates[0].place == "p1"
    assert "part=ad9361" in captured["url"]
    assert "carrier=zcu102" in captured["url"]


def test_get_match_builds_base_url_from_host_port(monkeypatch):
    captured = {}

    def fake_get_json(url, timeout=15.0):
        captured["url"] = url
        return {"satisfiable": False, "reason": "x", "reservation_filter": {}, "candidates": []}

    monkeypatch.setattr(match_client, "_get_json", fake_get_json)
    match_client.get_match("10.0.0.41:8000", part="ad9361")
    assert captured["url"].startswith("http://10.0.0.41:8000/api/match?")
