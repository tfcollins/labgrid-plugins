"""Recording retention sweeper."""

from __future__ import annotations

import asyncio
import logging
import os
import time

from .store import RecordingStore

logger = logging.getLogger(__name__)


async def sweep_retention(
    store: RecordingStore,
    *,
    retention_days: int,
    max_bytes_per_place: int,
) -> int:
    """One-shot sweep. Returns count of deleted recordings."""
    deleted = 0
    threshold = time.time() - retention_days * 86400
    for rec in await store.list_older_than(threshold=threshold):
        try:
            if rec.file_path and os.path.exists(rec.file_path):
                os.remove(rec.file_path)
        except OSError:
            pass
        await store.delete(rec.id)
        deleted += 1

    by_place: dict[str, list] = {}
    for rec in await store.list(limit=10_000):
        by_place.setdefault(rec.place_name, []).append(rec)
    for _place, recs in by_place.items():
        recs.sort(key=lambda r: r.started_at)
        total = sum(r.byte_count for r in recs)
        for r in recs:
            if total <= max_bytes_per_place:
                break
            try:
                if r.file_path and os.path.exists(r.file_path):
                    os.remove(r.file_path)
            except OSError:
                pass
            await store.delete(r.id)
            total -= r.byte_count
            deleted += 1
    return deleted


async def run_retention_loop(
    store: RecordingStore,
    *,
    retention_days: int,
    max_bytes_per_place: int,
    interval_seconds: float = 86400.0,
) -> None:
    """Background task: sweep on startup, then every `interval_seconds`."""
    while True:
        try:
            n = await sweep_retention(
                store,
                retention_days=retention_days,
                max_bytes_per_place=max_bytes_per_place,
            )
            if n:
                logger.info("retention: deleted %d recordings", n)
        except Exception as e:
            logger.warning("retention sweep failed: %s", e)
        await asyncio.sleep(interval_seconds)
