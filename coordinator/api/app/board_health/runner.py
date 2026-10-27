"""Health check execution runner."""

from __future__ import annotations

import asyncio
import getpass
import json
import logging
import os
import time
from typing import Any

from ..config import settings
from .store import BoardHealthStore

logger = logging.getLogger(__name__)


class HealthCheckRunner:
    def __init__(self, store: BoardHealthStore, coordinator_client: Any):
        self.store = store
        self.coordinator_client = coordinator_client
        self._active_tasks: dict[int, asyncio.Task] = {}
        self._active_processes: dict[int, asyncio.subprocess.Process] = {}

    def is_running(self, run_id: int) -> bool:
        return run_id in self._active_tasks and not self._active_tasks[run_id].done()

    async def cancel_run(self, run_id: int) -> bool:
        proc = self._active_processes.get(run_id)
        if proc is not None:
            try:
                proc.terminate()
                await asyncio.sleep(0.5)
                if proc.returncode is None:
                    proc.kill()
            except Exception as e:
                logger.warning("Error killing health check process for run %s: %s", run_id, e)

        task = self._active_tasks.get(run_id)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            return True
        return False

    def start_check(
        self,
        *,
        run_id: int,
        place_name: str,
        image: str | None = None,
        power_down: bool = True,
        timeout: float = 600.0,
    ) -> asyncio.Task:
        task = asyncio.create_task(
            self._execute_check(
                run_id=run_id,
                place_name=place_name,
                image=image,
                power_down=power_down,
                timeout=timeout,
            )
        )
        self._active_tasks[run_id] = task
        task.add_done_callback(lambda _: self._active_tasks.pop(run_id, None))
        return task

    async def _execute_check(
        self,
        *,
        run_id: int,
        place_name: str,
        image: str | None,
        power_down: bool,
        timeout: float,
    ) -> None:
        start_time = time.monotonic()
        await self.store.start_run(run_id, image=image)

        # Authorize the labgrid-client subprocess identity
        subprocess_identity = f"{settings.api_name}/{getpass.getuser()}"
        try:
            await self.coordinator_client.allow_place(place_name, subprocess_identity)
        except Exception as e:
            logger.warning("allow_place(%s, %s) failed: %s", place_name, subprocess_identity, e)

        env = dict(os.environ)
        env["LG_HOSTNAME"] = settings.api_name
        env["LG_CROSSBAR"] = settings.coordinator_address
        env["LG_API"] = "http://127.0.0.1:8000"

        cmd = [
            "adi-lg",
            "health-check",
            "--place",
            place_name,
            "--coord",
            settings.coordinator_address,
            "--json",
            "--timeout",
            str(timeout),
        ]
        if image:
            cmd.extend(["--image", image])
        if not power_down:
            cmd.append("--no-power-down")

        await self.store.append_run_log(run_id, f"Starting health check for '{place_name}'...\n")
        await self.store.append_run_log(run_id, f"Command: {' '.join(cmd)}\n\n")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            self._active_processes[run_id] = proc

            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                duration = time.monotonic() - start_time
                await self.store.append_run_log(
                    run_id, f"\n[ERROR] Health check timed out after {timeout}s\n"
                )
                await self.store.finish_run(
                    run_id,
                    status="failed",
                    duration=duration,
                    error_message=f"Health check timed out after {timeout:.0f} seconds",
                )
                return
            finally:
                self._active_processes.pop(run_id, None)

            duration = time.monotonic() - start_time
            stdout_str = stdout_b.decode("utf-8", errors="replace")
            stderr_str = stderr_b.decode("utf-8", errors="replace")

            full_log = (
                stdout_str + ("\n--- stderr ---\n" + stderr_str if stderr_str else "")
            ).strip()
            await self.store.append_run_log(run_id, full_log + "\n")

            # Try to parse json output
            parsed: dict[str, Any] | None = None
            for line in stdout_str.splitlines():
                line = line.strip()
                if line.startswith("{") and line.endswith("}"):
                    try:
                        parsed = json.loads(line)
                        break
                    except Exception:
                        pass
            if (
                parsed is None
                and stdout_str.strip().startswith("{")
                and stdout_str.strip().endswith("}")
            ):
                try:
                    parsed = json.loads(stdout_str.strip())
                except Exception:
                    pass

            if parsed:
                status = parsed.get("status", "failed")
                if status == "busy":
                    status = "busy"
                elif status == "error":
                    status = "failed"

                await self.store.finish_run(
                    run_id,
                    status=status,
                    duration=parsed.get("duration", duration),
                    ip_address=parsed.get("ip_address"),
                    iiod_reachable=bool(parsed.get("iiod_reachable", False)),
                    error_message=parsed.get("error_message"),
                    boot_strategy=parsed.get("boot_strategy"),
                    image=parsed.get("image", image),
                )
            else:
                status = "passed" if proc.returncode == 0 else "failed"
                await self.store.finish_run(
                    run_id,
                    status=status,
                    duration=duration,
                    error_message=stderr_str
                    or ("Health check failed" if status == "failed" else None),
                )

        except asyncio.CancelledError:
            duration = time.monotonic() - start_time
            await self.store.append_run_log(
                run_id, "\n[CANCELLED] Health check cancelled by user\n"
            )
            await self.store.finish_run(
                run_id,
                status="cancelled",
                duration=duration,
                error_message="Cancelled by user",
            )
            raise
        except Exception as e:
            duration = time.monotonic() - start_time
            logger.exception("Health check failed unexpectedly for %s: %s", place_name, e)
            await self.store.append_run_log(run_id, f"\n[EXCEPTION] {e}\n")
            await self.store.finish_run(
                run_id,
                status="failed",
                duration=duration,
                error_message=str(e),
            )
