"""Health check execution runner."""

from __future__ import annotations

import asyncio
import getpass
import json
import logging
import os
import signal
import time
from typing import Any

from ..config import settings
from .store import BoardHealthStore

logger = logging.getLogger(__name__)

# After a timeout, how long `adi-lg health-check` gets after SIGINT to run its
# teardown (halt the DUT, power it off, release the place) before SIGKILL.
TEARDOWN_GRACE = 120.0
# A user cancel only waits briefly, so the API request stays quick.
CANCEL_GRACE = 5.0


class HealthCheckRunner:
    def __init__(self, store: BoardHealthStore, coordinator_client: Any):
        self.store = store
        self.coordinator_client = coordinator_client
        self._active_tasks: dict[int, asyncio.Task] = {}
        self._active_processes: dict[int, asyncio.subprocess.Process] = {}
        self.teardown_grace = TEARDOWN_GRACE
        self.cancel_grace = CANCEL_GRACE

    @staticmethod
    async def _stop_process(proc: asyncio.subprocess.Process, grace: float) -> None:
        """SIGINT so the CLI's `finally` tears down and releases; SIGKILL after *grace*.

        SIGTERM would skip Python's `finally` blocks; SIGINT raises
        KeyboardInterrupt, which runs them.
        """
        if proc.returncode is not None:
            return
        try:
            proc.send_signal(signal.SIGINT)
            await asyncio.wait_for(proc.wait(), timeout=grace)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass

    async def _release_place(self, place_name: str, env: dict[str, str]) -> None:
        """Release the place if the health-check identity still holds it.

        Runs as the same identity as the subprocess (same env) and never with
        --kick, so it can only drop a lock the health check itself left.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                "labgrid-client",
                "-x",
                settings.coordinator_address,
                "-p",
                place_name,
                "release",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
            logger.info(
                "Fallback release of %s: rc=%s %s",
                place_name,
                proc.returncode,
                out.decode("utf-8", errors="replace").strip(),
            )
        except Exception as e:
            logger.warning("Fallback release of %s failed: %s", place_name, e)

    def is_running(self, run_id: int) -> bool:
        return run_id in self._active_tasks and not self._active_tasks[run_id].done()

    async def cancel_run(self, run_id: int) -> bool:
        proc = self._active_processes.get(run_id)
        if proc is not None:
            try:
                await self._stop_process(proc, self.cancel_grace)
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
        fetch_drivers: bool = True,
        timeout: float = 900.0,
    ) -> asyncio.Task:
        task = asyncio.create_task(
            self._execute_check(
                run_id=run_id,
                place_name=place_name,
                image=image,
                power_down=power_down,
                fetch_drivers=fetch_drivers,
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
        fetch_drivers: bool = True,
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
        if fetch_drivers:
            cmd.append("--drivers")

        await self.store.append_run_log(run_id, f"Starting health check for '{place_name}'...\n")
        await self.store.append_run_log(run_id, f"Command: {' '.join(cmd)}\n\n")

        env["PYTHONUNBUFFERED"] = "1"
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            self._active_processes[run_id] = proc

            stdout_lines: list[str] = []
            stderr_lines: list[str] = []
            log_queue: asyncio.Queue[str] = asyncio.Queue()
            readers_done = asyncio.Event()

            async def read_stdout():
                assert proc.stdout is not None
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace")
                    stdout_lines.append(decoded)
                    await log_queue.put(decoded)

            async def read_stderr():
                assert proc.stderr is not None
                while True:
                    line = await proc.stderr.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace")
                    stderr_lines.append(decoded)
                    await log_queue.put(decoded)

            async def flush_logs():
                batch: list[str] = []
                last_flush = time.monotonic()
                while True:
                    try:
                        line = await asyncio.wait_for(log_queue.get(), timeout=0.2)
                        batch.append(line)
                        log_queue.task_done()
                    except asyncio.TimeoutError:
                        pass

                    now = time.monotonic()
                    if batch and (now - last_flush >= 0.5 or log_queue.empty()):
                        text = "".join(batch)
                        batch.clear()
                        last_flush = now
                        try:
                            await self.store.append_run_log(run_id, text)
                        except Exception as e:
                            logger.warning("Failed appending log for run %d: %s", run_id, e)

                    if readers_done.is_set() and log_queue.empty():
                        if batch:
                            text = "".join(batch)
                            batch.clear()
                            try:
                                await self.store.append_run_log(run_id, text)
                            except Exception as e:
                                logger.warning(
                                    "Failed appending final log for run %d: %s", run_id, e
                                )
                        break

            stdout_task = asyncio.create_task(read_stdout())
            stderr_task = asyncio.create_task(read_stderr())
            flush_task = asyncio.create_task(flush_logs())

            try:
                await asyncio.wait_for(proc.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                await self.store.append_run_log(
                    run_id,
                    f"\n[ERROR] Health check timed out after {timeout}s; "
                    f"stopping it (up to {self.teardown_grace:.0f}s for teardown)\n",
                )
                await self._stop_process(proc, self.teardown_grace)
                await self._release_place(place_name, env)
                duration = time.monotonic() - start_time
                await self.store.finish_run(
                    run_id,
                    status="failed",
                    duration=duration,
                    error_message=f"Health check timed out after {timeout:.0f} seconds",
                )
                return
            finally:
                await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
                readers_done.set()
                await flush_task
                self._active_processes.pop(run_id, None)

            duration = time.monotonic() - start_time
            stdout_str = "".join(stdout_lines)
            stderr_str = "".join(stderr_lines)

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
                    drivers=parsed.get("drivers"),
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
            await self._release_place(place_name, env)
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
