"""Tests for the history and statistics router endpoints."""

from __future__ import annotations

import asyncio
import time


def _seed_events(recorder, loop):
    """Seed the recorder with test events and wait for them to be consumed."""

    async def _seed():
        # Place acquisition events
        await recorder.record_event(
            "place_acquired", place_name="board-a", user="alice", details="acquired"
        )
        await recorder.record_event(
            "place_released", place_name="board-a", user="alice", details="released"
        )
        await recorder.record_event(
            "place_acquired", place_name="board-b", user="bob", details="acquired"
        )

        # Resource events
        await recorder.record_event("resource_online", resource_key="exporter1/group1/Res1")
        await recorder.record_event("resource_offline", resource_key="exporter1/group1/Res1")
        await recorder.record_event("resource_online", resource_key="exporter2/group2/Res2")

        # Generic event
        await recorder.record_event("custom_event", details="something happened")

        # Allow consumer to process all queued events
        for _ in range(20):
            if recorder._queue.empty():
                break
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.1)

    loop.run_until_complete(_seed())


class TestEventsEndpoint:
    def test_get_events_empty(self, client_with_recorder):
        resp = client_with_recorder.get("/api/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["events"] == []
        assert data["total"] == 0

    def test_get_events_returns_seeded(self, client_with_recorder):
        recorder = client_with_recorder.app.state.recorder
        # The recorder consumer task runs on the loop created in the fixture.
        # We need to insert events directly into the DB to avoid loop issues.
        _insert_events_sync(recorder)

        resp = client_with_recorder.get("/api/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 7
        assert len(data["events"]) == 7
        # Events returned in descending timestamp order
        timestamps = [e["timestamp"] for e in data["events"]]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_filter_by_event_type(self, client_with_recorder):
        _insert_events_sync(client_with_recorder.app.state.recorder)

        resp = client_with_recorder.get("/api/events?event_type=place_acquired")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        for e in data["events"]:
            assert e["event_type"] == "place_acquired"

    def test_filter_by_place_name(self, client_with_recorder):
        _insert_events_sync(client_with_recorder.app.state.recorder)

        resp = client_with_recorder.get("/api/events?place_name=board-a")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        for e in data["events"]:
            assert e["place_name"] == "board-a"

    def test_pagination(self, client_with_recorder):
        _insert_events_sync(client_with_recorder.app.state.recorder)

        resp = client_with_recorder.get("/api/events?limit=3&offset=0")
        data = resp.json()
        assert len(data["events"]) == 3
        assert data["total"] == 7

        resp2 = client_with_recorder.get("/api/events?limit=3&offset=3")
        data2 = resp2.json()
        assert len(data2["events"]) == 3
        assert data2["total"] == 7

        # No overlap
        ids1 = {e["id"] for e in data["events"]}
        ids2 = {e["id"] for e in data2["events"]}
        assert ids1.isdisjoint(ids2)


class TestPlaceStats:
    def test_place_stats(self, client_with_recorder):
        _insert_events_sync(client_with_recorder.app.state.recorder)

        resp = client_with_recorder.get("/api/stats/places")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        place_names = [p["place_name"] for p in data]
        assert "board-a" in place_names
        for p in data:
            assert "total_sessions" in p
            assert "total_acquired_seconds" in p
            assert "utilization_percent" in p

    def test_place_sessions(self, client_with_recorder):
        _insert_events_sync(client_with_recorder.app.state.recorder)

        resp = client_with_recorder.get("/api/stats/places/board-a/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        for s in data:
            assert s["user"] == "alice"
            assert "acquired_at" in s
            assert "duration_seconds" in s


class TestResourceStats:
    def test_resource_stats(self, client_with_recorder):
        _insert_events_sync(client_with_recorder.app.state.recorder)

        resp = client_with_recorder.get("/api/stats/resources")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        for r in data:
            assert "resource_key" in r
            assert "uptime_percent" in r
            assert "total_online_seconds" in r
            assert "total_offline_seconds" in r


class TestExporterStats:
    def test_exporter_stats(self, client_with_recorder):
        _insert_events_sync(client_with_recorder.app.state.recorder)

        resp = client_with_recorder.get("/api/stats/exporters")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        exporter_names = [e["exporter"] for e in data]
        assert "exporter1" in exporter_names
        for e in data:
            assert "resource_count" in e
            assert "avg_uptime_percent" in e


class TestOverview:
    def test_overview(self, client_with_recorder):
        _insert_events_sync(client_with_recorder.app.state.recorder)

        resp = client_with_recorder.get("/api/stats/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_events_24h" in data
        assert data["total_events_24h"] == 7
        assert "avg_acquisition_duration_hours" in data
        assert "busiest_hour" in data
        assert "most_used_place" in data
        assert "avg_uptime_percent" in data


def _insert_events_sync(recorder):
    """Insert test events directly into the SQLite database (bypassing the async queue)."""
    import sqlite3

    now = time.time()
    conn = sqlite3.connect(recorder.db_path)
    cur = conn.cursor()

    events = [
        (now - 6, "place_acquired", "board-a", None, "alice", "acquired"),
        (now - 5, "place_released", "board-a", None, "alice", "released"),
        (now - 4, "place_acquired", "board-b", None, "bob", "acquired"),
        (now - 3, "resource_online", None, "exporter1/group1/Res1", None, None),
        (now - 2, "resource_offline", None, "exporter1/group1/Res1", None, None),
        (now - 1, "resource_online", None, "exporter2/group2/Res2", None, None),
        (now, "custom_event", None, None, None, "something happened"),
    ]

    for ts, etype, place, rkey, user, details in events:
        cur.execute(
            "INSERT INTO events (timestamp, event_type, place_name, resource_key, user, details)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (ts, etype, place, rkey, user, details),
        )

        if etype == "place_acquired" and place and user:
            cur.execute(
                "INSERT INTO place_sessions (place_name, user, acquired_at) VALUES (?, ?, ?)",
                (place, user, ts),
            )
        elif etype == "place_released" and place:
            cur.execute(
                "UPDATE place_sessions SET released_at = ?"
                " WHERE place_name = ? AND released_at IS NULL",
                (ts, place),
            )
        elif etype == "resource_online" and rkey:
            cur.execute(
                "INSERT INTO resource_availability (resource_key, available, changed_at)"
                " VALUES (?, 1, ?)",
                (rkey, ts),
            )
        elif etype == "resource_offline" and rkey:
            cur.execute(
                "INSERT INTO resource_availability (resource_key, available, changed_at)"
                " VALUES (?, 0, ?)",
                (rkey, ts),
            )

    conn.commit()
    conn.close()
