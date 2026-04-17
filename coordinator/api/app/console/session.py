"""Bidirectional pipe between an exporter ser2net TCP socket and a browser WebSocket."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class ConsoleSession:
    def __init__(self, *, host: str, port: int, recorder=None):
        self.host = host
        self.port = port
        self.recorder = recorder
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._closed = asyncio.Event()

    @property
    def is_closed(self) -> bool:
        return self._closed.is_set()

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)

    async def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass

    async def run(self, ws) -> None:
        if self._reader is None or self._writer is None:
            raise RuntimeError("connect() first")
        tcp_to_ws = asyncio.create_task(self._tcp_to_ws(ws))
        ws_to_tcp = asyncio.create_task(self._ws_to_tcp(ws))
        closed_wait = asyncio.create_task(self._closed.wait())
        try:
            done, pending = await asyncio.wait(
                {tcp_to_ws, ws_to_tcp, closed_wait},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
            for t in pending:
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
        finally:
            await self.close()

    async def _tcp_to_ws(self, ws) -> None:
        try:
            while not self._closed.is_set():
                data = await self._reader.read(4096)
                if not data:
                    break
                await ws.send_bytes(data)
                if self.recorder is not None:
                    try:
                        await self.recorder.write_output(data)
                    except Exception as e:
                        logger.warning("recorder.write_output failed: %s", e)
        except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
            pass
        except Exception as e:
            logger.warning("tcp->ws pump failed: %s", e)

    async def _ws_to_tcp(self, ws) -> None:
        try:
            while not self._closed.is_set():
                try:
                    data = await ws.receive_bytes()
                except Exception:
                    break
                if not data:
                    break
                self._writer.write(data)
                await self._writer.drain()
                if self.recorder is not None:
                    try:
                        await self.recorder.write_input(data)
                    except Exception as e:
                        logger.warning("recorder.write_input failed: %s", e)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("ws->tcp pump failed: %s", e)
