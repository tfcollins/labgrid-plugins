from __future__ import annotations

from adi_lg_plugins.request import match_client


def test_get_match_parses_fresh_response(monkeypatch):
    captured = {}

    def fake_get_json(url, timeout=15.0):
        captured["url"] = url
        return {
            "satisfiable": True,
            "reason": None,
            "reservation_filter": {"daughter-board": "adrv9002", "carrier": "zcu102"},
            "image": "2023_R2_P1",
            "strategy": "BootFPGASoC",
            "place": "adrv9002-zcu102",
        }

    monkeypatch.setattr(match_client, "_get_json", fake_get_json)

    res = match_client.get_match("10.0.0.41:8000", part="adrv9002", carrier="zcu102")

    assert res.satisfiable is True
    assert res.reservation_filter == {"daughter-board": "adrv9002", "carrier": "zcu102"}
    assert res.image == "2023_R2_P1"
    assert res.strategy == "BootFPGASoC"
    assert res.place == "adrv9002-zcu102"
    assert "part=adrv9002" in captured["url"]
    assert "carrier=zcu102" in captured["url"]


def test_get_match_builds_base_url_from_host_port(monkeypatch):
    captured = {}

    def fake_get_json(url, timeout=15.0):
        captured["url"] = url
        return {"satisfiable": False, "reason": "unknown part", "reservation_filter": {}}

    monkeypatch.setattr(match_client, "_get_json", fake_get_json)
    res = match_client.get_match("10.0.0.41:8000", part="nope")
    assert res.satisfiable is False
    assert res.reason == "unknown part"
    assert captured["url"].startswith("http://10.0.0.41:8000/api/match?")


def test_get_match_passes_bootfile_and_omits_unset_carrier(monkeypatch):
    captured = {}

    def fake_get_json(url, timeout=15.0):
        captured["url"] = url
        return {
            "satisfiable": True,
            "reservation_filter": {},
            "image": "PIN",
            "strategy": "S",
            "place": "p",
        }

    monkeypatch.setattr(match_client, "_get_json", fake_get_json)
    match_client.get_match("http://c:8000", part="adrv9002", bootfile="PIN")
    assert "bootfile=PIN" in captured["url"]
    assert "carrier=" not in captured["url"]
