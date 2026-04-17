"""asciinema v2 cast file writer."""

from __future__ import annotations

import asyncio
import json
import time


class CastWriter:
    """Append-only writer that emits an asciinema v2 cast.

    Format: line 1 is a JSON header, subsequent lines are
    [t_seconds, "o"|"i", string] event arrays.

    Uses latin-1 to round-trip arbitrary bytes 0-255 to a Python str;
    json.dumps then escapes non-printable code points safely. Result is
    always valid JSON.
    """

    def __init__(
        self,
        path: str,
        *,
        title: str,
        width: int = 80,
        height: int = 24,
    ):
        self.path = path
        self.title = title
        self.width = width
        self.height = height
        self.byte_count = 0
        self._fp = None
        self._t0: float | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        self._fp = open(self.path, "w", buffering=1, encoding="utf-8")
        self._t0 = time.time()
        header = {
            "version": 2,
            "width": self.width,
            "height": self.height,
            "timestamp": int(self._t0),
            "title": self.title,
        }
        self._fp.write(json.dumps(header) + "\n")

    @staticmethod
    def _encode(b: bytes) -> str:
        return b.decode("latin-1")

    async def _emit(self, kind: str, data: bytes) -> None:
        if self._fp is None or self._t0 is None:
            return
        async with self._lock:
            t = time.time() - self._t0
            line = json.dumps([round(t, 6), kind, self._encode(data)])
            self._fp.write(line + "\n")
            self.byte_count += len(data)

    async def write_output(self, data: bytes) -> None:
        await self._emit("o", data)

    async def write_input(self, data: bytes) -> None:
        await self._emit("i", data)

    async def close(self) -> None:
        if self._fp is None:
            return
        async with self._lock:
            try:
                self._fp.flush()
                self._fp.close()
            finally:
                self._fp = None
