"""Asyncio background scheduler for recurring board health checks."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .runner import HealthCheckRunner
from .store import BoardHealthStore

logger = logging.getLogger(__name__)


class HealthCheckScheduler:
    def __init__(
        self,
        store: BoardHealthStore,
        runner: HealthCheckRunner,
        coordinator_client: Any,
        check_interval: float = 30.0,
    ):
        self.store = store
        self.runner = runner
        self.coordinator_client = coordinator_client
        self.check_interval = check_interval
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Board health check scheduler started.")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Board health check scheduler stopped.")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self._evaluate_due_schedules()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in health check scheduler loop: %s", e, exc_info=True)

            try:
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break

    async def _evaluate_due_schedules(self) -> None:
        now = time.time()
        due_schedules = await self.store.get_due_schedules(now)
        for schedule in due_schedules:
            logger.info("Triggering scheduled health check: %s (id=%d)", schedule.name, schedule.id)
            await self.trigger_schedule(schedule.id)

    async def trigger_schedule(self, schedule_id: int) -> list[int]:
        """Trigger an execution of a schedule now, returning the created run IDs."""
        schedule = await self.store.get_schedule(schedule_id)
        if not schedule:
            return []

        now = time.time()
        await self.store.advance_schedule_time(schedule.id, now)

        # Resolve target places
        places = schedule.places
        if "*" in places or places == ["*"]:
            try:
                all_places = self.coordinator_client.get_places()
                target_names = [p.name for p in all_places]
            except Exception as e:
                logger.warning("Could not list places from coordinator client: %s", e)
                target_names = []
        else:
            target_names = list(places)

        run_ids = []
        for place_name in target_names:
            run = await self.store.create_run(
                place_name=place_name,
                trigger="scheduled",
                triggered_by=schedule.name,
                schedule_id=schedule.id,
                image=schedule.image,
            )
            self.runner.start_check(
                run_id=run.id,
                place_name=place_name,
                image=schedule.image,
                power_down=schedule.power_down,
            )
            run_ids.append(run.id)

        return run_ids
