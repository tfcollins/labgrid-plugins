# Hardware Request — Client Core + `Lease` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A consumer calls `with request(part="adrv9002") as board:` and gets a booted board's libIIO URI (`board.uri`), with labgrid-plugins selecting a free matching board, reserving/queuing, booting it to a Linux shell, and releasing it on exit — even on failure or Ctrl-C — with zero strategy/driver/resource config from the consumer.

**Architecture:** A new client-side package `adi_lg_plugins/request/` with five focused modules: `errors` (typed exceptions + CLI exit codes), `match_client` (HTTP to the coordinator's `GET /api/match` built in Plan 1), `reservation` (wrap `labgrid-client reserve/acquire/release` by tag filter), `uri` (resolve `ip:<address>` from the booted target), and `core` (the `request()` context manager + `Lease` that wires them together and guarantees cleanup). Orchestration runs client-side; the modules are seam-injectable so the whole lifecycle — including failure/cleanup paths — is unit-tested with a fake backend (monkeypatched seams), no hardware.

**Tech Stack:** Python 3.10+, standard-library `urllib`/`subprocess` (no new deps), `labgrid.Environment` for boot, pytest with monkeypatch. ruff line length 100, double quotes, `from __future__ import annotations`. This plan lives in the top-level `adi_lg_plugins` package — run `pytest`/`ruff` from the repo root `/home/tcollins/dev/lg-test/labgrid-plugins`.

This is **Plan 2 of 5** of the first-cut increment (`docs/superpowers/specs/2026-06-03-low-config-hardware-request-fresh-design.md`). It depends on **Plan 1** (coordinator `GET /api/match` returning `satisfiable`, `reservation_filter`, `image`, `strategy`, `place`, `reason`), which is merged on PR #49. Plans 3–5 (CLI, pytest fixture, GitHub Actions) consume this core.

---

## Grounding & reuse

A working reference implementation of this exact core exists on the **original** track's branch `feat/hw-request-phase1` (`adi_lg_plugins/request/{core,reservation,uri,match_client,errors}.py`). This plan adapts that proven code to the **fresh** Plan-1 `/api/match` contract. The differences from that reference are deliberate and must be honored:

| Aspect | Original (`feat/hw-request-phase1`) | This plan (fresh) |
| --- | --- | --- |
| `/match` fields parsed | `version`, `matlab_boards`, `candidates` | `image`, `strategy`, `place` |
| `Lease.matlab_board` | present | **dropped** (MATLAB surface is deferred; no catalog field for it yet) |
| `power_down` param | absent | **added** (default `False`; spec's "optional power down") |
| `mode` query param sent to `/match` | yes (`mode=uri`) | **not sent** (fresh `/api/match` has no `mode` param) |

The reservation-CLI parsing (`reservation.py`) and URI resolution (`uri.py`) are contract-stable and reused essentially verbatim.

## OPEN QUESTION to confirm during implementation — `image` → `KuiperRelease.release_version`

`core._boot` pins the boot image by setting `KuiperRelease.release_version = match.image`. The value of `match.image` comes straight from the Plan-1 catalog's `image:` field, which currently holds the **placeholder** `kuiper-2023_R2`. `KuiperRelease.release_version` expects a release-version string of the form the CLI uses (e.g. `2023_R2_P1`). **Before the hardware smoke test (Task 7) can pass, the catalog's `image:` value must be a real `KuiperRelease` release version.** This plan treats `match.image` as the verbatim `release_version`; the data-file value is a Plan-1 follow-up (a one-line change in `coordinator/api/board_catalog.yaml`), not a code change here. All unit tests use an explicit fake image string, so they are unaffected. Flagging so the implementer does not silently assume `kuiper-2023_R2` boots.

## File Structure

- Create: `adi_lg_plugins/request/__init__.py` — public API (`request`, `Lease`, error types).
- Create: `adi_lg_plugins/request/errors.py` — exceptions + exit codes.
- Create: `adi_lg_plugins/request/match_client.py` — `get_match()` → `MatchResult`.
- Create: `adi_lg_plugins/request/reservation.py` — `reserve_and_acquire()`, `release()`.
- Create: `adi_lg_plugins/request/uri.py` — `resolve_uri()`.
- Create: `adi_lg_plugins/request/core.py` — `Lease` + `request()` context manager.
- Test: `tests/test_request_errors.py`, `tests/test_request_uri.py`, `tests/test_request_match_client.py`, `tests/test_request_reservation.py`, `tests/test_request_core.py`, `tests/test_request_hw.py` (hardware-gated).

Each module has one responsibility; `core` is the only one that knows the end-to-end flow. The boot/render reuse `adi_lg_plugins.hw_ci.{coordinator,render_env}` (already tested) rather than reimplementing env-yaml rendering.

## Conventions

- All commands run from repo root `/home/tcollins/dev/lg-test/labgrid-plugins`.
- Test runner: `python3 -m pytest tests/<file> -v`.
- Lint: `ruff check . && ruff format --check .` (use `ruff format .` to fix). Run before each commit.
- The `request/` directory currently exists only as a stale `__pycache__` with no tracked `.py` files — you are creating the package from scratch.

---

### Task 1: `errors.py` — exceptions and exit codes

**Files:**
- Create: `adi_lg_plugins/request/errors.py`
- Test: `tests/test_request_errors.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_request_errors.py`:

```python
from __future__ import annotations

import pytest

from adi_lg_plugins.request import errors


def test_exit_codes_are_distinct_and_above_test_runner_codes():
    codes = {errors.EXIT_NO_MATCH, errors.EXIT_UNAVAILABLE, errors.EXIT_PROVISION}
    assert codes == {10, 11, 12}  # distinct, and clear of typical pytest codes (0-5)


def test_exception_hierarchy():
    for cls in (errors.NoMatchingBoard, errors.BoardUnavailable, errors.ProvisionError):
        assert issubclass(cls, errors.RequestError)


def test_provision_error_carries_console_tail():
    e = errors.ProvisionError("boot failed", console_tail="...panic...")
    assert str(e) == "boot failed"
    assert e.console_tail == "...panic..."


def test_provision_error_console_tail_defaults_empty():
    assert errors.ProvisionError("x").console_tail == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_request_errors.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'adi_lg_plugins.request.errors'`.

- [ ] **Step 3: Write minimal implementation** — create `adi_lg_plugins/request/errors.py`:

```python
"""Exceptions and CLI exit codes for the hardware-request layer."""

# Infra exit codes sit well above typical test-runner codes (0-5) so a GitHub
# Actions leg can tell an infra problem from a real test failure.
EXIT_NO_MATCH = 10  # request can never be satisfied (unknown part / no such board)
EXIT_UNAVAILABLE = 11  # matching board(s) exist but none free within `wait`
EXIT_PROVISION = 12  # boot failed


class RequestError(Exception):
    """Base class for hardware-request failures."""


class NoMatchingBoard(RequestError):
    """No place can satisfy the request (catalog/tags); do not wait."""


class BoardUnavailable(RequestError):
    """Matching boards exist but none became free within the wait window."""


class ProvisionError(RequestError):
    """Booting the acquired board failed."""

    def __init__(self, message: str, console_tail: str = ""):
        super().__init__(message)
        self.console_tail = console_tail
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_request_errors.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Lint and commit**

```bash
cd /home/tcollins/dev/lg-test/labgrid-plugins
ruff check adi_lg_plugins/request/errors.py tests/test_request_errors.py && \
  ruff format adi_lg_plugins/request/errors.py tests/test_request_errors.py
git add adi_lg_plugins/request/errors.py tests/test_request_errors.py
git commit -m "feat(request): exceptions and exit codes for hardware-request layer"
```

---

### Task 2: `uri.py` — resolve the libIIO URI from a booted target

**Files:**
- Create: `adi_lg_plugins/request/uri.py`
- Test: `tests/test_request_uri.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_request_uri.py`:

```python
from __future__ import annotations

import pytest

from adi_lg_plugins.request.errors import ProvisionError
from adi_lg_plugins.request.uri import resolve_uri


class FakeNet:
    def __init__(self, address):
        self.address = address


class FakeTarget:
    def __init__(self, net=None, raise_on_get=False):
        self._net = net
        self._raise = raise_on_get

    def get_resource(self, cls):
        if self._raise:
            raise Exception(f"no resource {cls}")
        return self._net


def test_resolve_uri_returns_ip_form():
    tg = FakeTarget(net=FakeNet("10.0.0.57"))
    assert resolve_uri(tg) == "ip:10.0.0.57"


def test_resolve_uri_missing_resource_raises_provision_error():
    tg = FakeTarget(raise_on_get=True)
    with pytest.raises(ProvisionError):
        resolve_uri(tg)


def test_resolve_uri_no_address_raises_provision_error():
    tg = FakeTarget(net=FakeNet(""))
    with pytest.raises(ProvisionError):
        resolve_uri(tg)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_request_uri.py -v`
Expected: FAIL — `ModuleNotFoundError: ...request.uri`.

- [ ] **Step 3: Write minimal implementation** — create `adi_lg_plugins/request/uri.py`:

```python
"""Resolve a booted target's libIIO URI from its NetworkService resource."""

from __future__ import annotations

from typing import Any

from .errors import ProvisionError


def resolve_uri(target: Any) -> str:
    """Return ``ip:<address>`` from the target's NetworkService resource.

    Mirrors the resolution used by the MCP server (tools/mcp.py).
    """
    try:
        net = target.get_resource("NetworkService")
    except Exception as e:  # noqa: BLE001 - target raises a bare Exception when absent
        raise ProvisionError(f"no NetworkService resource on booted target: {e}") from e
    address = getattr(net, "address", None)
    if not address:
        raise ProvisionError("booted target's NetworkService has no address")
    return f"ip:{address}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_request_uri.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Lint and commit**

```bash
cd /home/tcollins/dev/lg-test/labgrid-plugins
ruff check adi_lg_plugins/request/uri.py tests/test_request_uri.py && \
  ruff format adi_lg_plugins/request/uri.py tests/test_request_uri.py
git add adi_lg_plugins/request/uri.py tests/test_request_uri.py
git commit -m "feat(request): resolve libIIO URI from a booted target"
```

---

### Task 3: `match_client.py` — query the coordinator's `/api/match`

**Files:**
- Create: `adi_lg_plugins/request/match_client.py`
- Test: `tests/test_request_match_client.py`

This parses the **fresh** Plan-1 `/api/match` response: `satisfiable`, `reason`, `reservation_filter`, `image`, `strategy`, `place`.

- [ ] **Step 1: Write the failing test** — create `tests/test_request_match_client.py`:

```python
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
        return {"satisfiable": True, "reservation_filter": {}, "image": "PIN", "strategy": "S",
                "place": "p"}

    monkeypatch.setattr(match_client, "_get_json", fake_get_json)
    match_client.get_match("http://c:8000", part="adrv9002", bootfile="PIN")
    assert "bootfile=PIN" in captured["url"]
    assert "carrier=" not in captured["url"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_request_match_client.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation** — create `adi_lg_plugins/request/match_client.py`:

```python
"""HTTP client for the coordinator's /api/match endpoint (Plan 1 contract).

Uses only the standard library (urllib) to avoid adding a dependency.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import urlencode
from urllib.request import urlopen


@dataclass(frozen=True)
class MatchResult:
    satisfiable: bool
    reason: str = ""
    reservation_filter: dict[str, str] = field(default_factory=dict)
    image: str | None = None
    strategy: str | None = None
    place: str | None = None


def _base_url(coord: str) -> str:
    """Turn a coordinator reference (host:port or full URL) into an http base URL.

    The coordinator REST API listens on the API port; callers pass the
    host:port of that API (e.g. ``10.0.0.41:8000``).
    """
    if coord.startswith(("http://", "https://")):
        return coord.rstrip("/")
    return f"http://{coord.rstrip('/')}"


def _get_json(url: str, timeout: float = 15.0) -> dict:
    with urlopen(url, timeout=timeout) as resp:  # noqa: S310 - trusted lab URL
        return json.loads(resp.read().decode("utf-8"))


def get_match(
    coord: str,
    *,
    part: str,
    carrier: str | None = None,
    bootfile: str | None = None,
    timeout: float = 15.0,
) -> MatchResult:
    params = {"part": part}
    if carrier:
        params["carrier"] = carrier
    if bootfile:
        params["bootfile"] = bootfile
    url = f"{_base_url(coord)}/api/match?{urlencode(params)}"
    data = _get_json(url, timeout=timeout)
    return MatchResult(
        satisfiable=bool(data.get("satisfiable")),
        reason=data.get("reason") or "",
        reservation_filter=data.get("reservation_filter") or {},
        image=data.get("image"),
        strategy=data.get("strategy"),
        place=data.get("place"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_request_match_client.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Lint and commit**

```bash
cd /home/tcollins/dev/lg-test/labgrid-plugins
ruff check adi_lg_plugins/request/match_client.py tests/test_request_match_client.py && \
  ruff format adi_lg_plugins/request/match_client.py tests/test_request_match_client.py
git add adi_lg_plugins/request/match_client.py tests/test_request_match_client.py
git commit -m "feat(request): HTTP client for coordinator /api/match"
```

---

### Task 4: `reservation.py` — reserve by tag filter, acquire, release

**Files:**
- Create: `adi_lg_plugins/request/reservation.py`
- Test: `tests/test_request_reservation.py`

Wraps `labgrid-client`: `reserve --shell --wait <k=v...>` (queues until a matching place frees, bounded by `wait`), discovers the allocated place from `reservations` output, then `acquire`. `release()` releases the place and cancels the reservation and never raises (cleanup must not mask the original error).

- [ ] **Step 1: Write the failing test** — create `tests/test_request_reservation.py`:

```python
from __future__ import annotations

import subprocess

import pytest

from adi_lg_plugins.request import reservation
from adi_lg_plugins.request.errors import BoardUnavailable
from adi_lg_plugins.request.reservation import Reservation


def test_filter_args_formats_tags():
    assert reservation._filter_args({"daughter-board": "adrv9002", "carrier": "zcu102"}) == [
        "daughter-board=adrv9002",
        "carrier=zcu102",
    ]


def test_parse_token_extracts_lg_token():
    assert reservation._parse_token("blah\nLG_TOKEN=abc123\nblah") == "abc123"
    assert reservation._parse_token("no token here") is None


def test_parse_allocated_place_finds_place_in_allocations_block():
    out = (
        "Reservation 'abc123':\n"
        "  owner: ci\n"
        "  state: allocated\n"
        "  allocations:\n"
        "    main: lab1-host/adrv9002-zcu102\n"
    )
    assert reservation._parse_allocated_place(out, "abc123") == "adrv9002-zcu102"


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_reserve_and_acquire_happy_path(monkeypatch):
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        if "reserve" in argv:
            return _completed(stdout="LG_TOKEN=tok9\n")
        if "reservations" in argv:
            return _completed(
                stdout="Reservation 'tok9':\n  allocations:\n    main: h/adrv9002-zcu102\n"
            )
        if "acquire" in argv:
            return _completed()
        return _completed()

    monkeypatch.setattr(reservation.subprocess, "run", fake_run)
    res = reservation.reserve_and_acquire("c:8000", {"daughter-board": "adrv9002"}, wait=60)
    assert res == Reservation(place="adrv9002-zcu102", token="tok9")


def test_reserve_timeout_raises_board_unavailable(monkeypatch):
    def fake_run(argv, **kw):
        if "reserve" in argv:
            raise subprocess.TimeoutExpired(cmd=argv, timeout=kw.get("timeout"))
        return _completed()

    monkeypatch.setattr(reservation.subprocess, "run", fake_run)
    with pytest.raises(BoardUnavailable):
        reservation.reserve_and_acquire("c:8000", {"daughter-board": "adrv9002"}, wait=1)


def test_acquire_failure_cancels_reservation_and_raises(monkeypatch):
    cancelled = []

    def fake_run(argv, **kw):
        if "reserve" in argv:
            return _completed(stdout="LG_TOKEN=tok9\n")
        if "reservations" in argv:
            return _completed(stdout="Reservation 'tok9':\n  allocations:\n    main: h/p1\n")
        if "acquire" in argv:
            return _completed(returncode=1, stderr="busy")
        if "cancel-reservation" in argv:
            cancelled.append(argv)
            return _completed()
        return _completed()

    monkeypatch.setattr(reservation.subprocess, "run", fake_run)
    with pytest.raises(BoardUnavailable):
        reservation.reserve_and_acquire("c:8000", {"daughter-board": "adrv9002"}, wait=60)
    assert cancelled, "acquire failure must cancel the reservation to avoid a leak"


def test_release_never_raises(monkeypatch):
    def boom(argv, **kw):
        raise RuntimeError("network down")

    monkeypatch.setattr(reservation.subprocess, "run", boom)
    # Must not raise despite subprocess errors.
    reservation.release("c:8000", Reservation(place="p1", token="tok9"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_request_reservation.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation** — create `adi_lg_plugins/request/reservation.py`:

```python
"""Wrap labgrid-client reservations: reserve by tag filter, acquire, release.

Reserves by tags (not a known place name) and discovers the allocated place
from the reservation, so consumers never name a place.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass

from .errors import BoardUnavailable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Reservation:
    place: str
    token: str


def _filter_args(filt: dict[str, str]) -> list[str]:
    return [f"{k}={v}" for k, v in filt.items()]


def _parse_token(stdout: str) -> str | None:
    m = re.search(r"LG_TOKEN=(\S+)", stdout)
    return m.group(1) if m else None


def _parse_allocated_place(stdout: str, token: str) -> str | None:
    """Find the allocated place for `token` in `labgrid-client reservations` output.

    Allocations look like ``main: <exporter>/<place>``; return the bare place.
    """
    in_block = False
    in_allocations = False
    for line in stdout.splitlines():
        if line.startswith("Reservation"):
            in_block = token in line
            in_allocations = False
            continue
        if not in_block:
            continue
        if re.search(r"^\s+allocations:\s*$", line):
            in_allocations = True
            continue
        if re.search(r"^\s+\w[\w-]*:\s*$", line):
            in_allocations = False
            continue
        if in_allocations:
            m = re.search(r":\s*([\w./-]+)\s*$", line)
            if m and "/" in m.group(1):
                return m.group(1).rsplit("/", 1)[-1]
    return None


def reserve_and_acquire(
    coord: str,
    filt: dict[str, str],
    *,
    wait: float,
    client: str = "labgrid-client",
) -> Reservation:
    base = [client, "-x", coord]
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, trusted client
            [*base, "reserve", "--shell", "--wait", *_filter_args(filt)],
            capture_output=True,
            text=True,
            timeout=wait,
        )
    except subprocess.TimeoutExpired as e:
        raise BoardUnavailable(f"no free board matching {filt} within {wait:.0f}s") from e
    if proc.returncode != 0:
        raise BoardUnavailable(f"reservation failed for {filt}: {proc.stderr.strip()}")

    token = _parse_token(proc.stdout)
    if not token:
        raise BoardUnavailable(f"could not parse reservation token from: {proc.stdout!r}")

    res_proc = subprocess.run(  # noqa: S603
        [*base, "reservations"], capture_output=True, text=True, timeout=15
    )
    place = _parse_allocated_place(res_proc.stdout, token)
    if not place:
        raise BoardUnavailable(f"reservation {token} has no allocated place yet")

    acq = subprocess.run(  # noqa: S603
        [*base, "-p", f"+{token}", "acquire"], capture_output=True, text=True, timeout=30
    )
    if acq.returncode != 0:
        # Best-effort cancel so we don't leak the reservation.
        subprocess.run([*base, "cancel-reservation", token], capture_output=True, text=True)  # noqa: S603
        raise BoardUnavailable(f"acquire failed for place {place}: {acq.stderr.strip()}")

    return Reservation(place=place, token=token)


def release(coord: str, reservation: Reservation, *, client: str = "labgrid-client") -> None:
    """Release the place and cancel the reservation. Never raises."""
    base = [client, "-x", coord]
    for cmd in (
        [*base, "-p", f"+{reservation.token}", "release"],
        [*base, "cancel-reservation", reservation.token],
    ):
        try:
            subprocess.run(cmd, capture_output=True, text=True, timeout=15)  # noqa: S603
        except Exception as e:  # noqa: BLE001 - cleanup must not mask original error
            logger.warning("reservation cleanup step failed (%s): %s", " ".join(cmd), e)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_request_reservation.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Lint and commit**

```bash
cd /home/tcollins/dev/lg-test/labgrid-plugins
ruff check adi_lg_plugins/request/reservation.py tests/test_request_reservation.py && \
  ruff format adi_lg_plugins/request/reservation.py tests/test_request_reservation.py
git add adi_lg_plugins/request/reservation.py tests/test_request_reservation.py
git commit -m "feat(request): labgrid reservation wrapper (reserve/acquire/release)"
```

---

### Task 5: `core.py` — `Lease` + `request()` orchestration + cleanup

**Files:**
- Create: `adi_lg_plugins/request/core.py`
- Test: `tests/test_request_core.py`

The orchestration. It reuses `hw_ci.coordinator.{resolve_coordinator,list_live_places}` and `hw_ci.render_env.render_env_to` for env rendering, and `labgrid.Environment` for boot. Every external step (`resolve_coordinator`, `match_client.get_match`, `reservation.reserve_and_acquire`/`release`, `_concrete_place`, `_render_env`, `_boot`, `resolve_uri`, `_power_off`) is a module-level name so tests monkeypatch them — this is the "fake backend" that exercises the full lifecycle, including cleanup-on-failure, with no hardware.

- [ ] **Step 1: Write the failing test** — create `tests/test_request_core.py`:

```python
from __future__ import annotations

import pytest

from adi_lg_plugins.request import core
from adi_lg_plugins.request.errors import (
    BoardUnavailable,
    NoMatchingBoard,
    ProvisionError,
)
from adi_lg_plugins.request.match_client import MatchResult
from adi_lg_plugins.request.reservation import Reservation


class FakePlace:
    def __init__(self, name="adrv9002-zcu102"):
        self.name = name
        self.carrier = "zcu102"
        self.daughter_board = "adrv9002"
        self.boot_strategy = "BootFPGASoC"
        self.hdl_config = None
        self.extra_tags = {}


def _match(satisfiable=True):
    return MatchResult(
        satisfiable=satisfiable,
        reason="" if satisfiable else "unknown part",
        reservation_filter={"daughter-board": "adrv9002", "carrier": "zcu102"},
        image="2023_R2_P1",
        strategy="BootFPGASoC",
        place="adrv9002-zcu102",
    )


@pytest.fixture
def patched(monkeypatch):
    state = {"released": None, "booted_image": None, "powered_off": None}

    monkeypatch.setattr(core, "resolve_coordinator", lambda c: "coord:8000")
    monkeypatch.setattr(core.match_client, "get_match", lambda *a, **k: _match())
    monkeypatch.setattr(
        core.reservation,
        "reserve_and_acquire",
        lambda *a, **k: Reservation(place="adrv9002-zcu102", token="tok"),
    )
    monkeypatch.setattr(
        core.reservation, "release", lambda coord, res, **k: state.update(released=res.place)
    )
    monkeypatch.setattr(core, "_concrete_place", lambda coord, name: FakePlace(name=name))
    monkeypatch.setattr(core, "_render_env", lambda place: "/tmp/env.yaml")

    def fake_boot(env_path, strategy, *, image, target_name="main"):
        state["booted_image"] = image
        return object()  # fake labgrid target

    monkeypatch.setattr(core, "_boot", fake_boot)
    monkeypatch.setattr(core, "resolve_uri", lambda tg: "ip:10.0.0.57")
    monkeypatch.setattr(
        core, "_power_off", lambda tg, strat: state.update(powered_off=strat)
    )
    return state


def test_request_yields_lease_and_releases(patched):
    with core.request(part="adrv9002") as board:
        assert board.uri == "ip:10.0.0.57"
        assert board.place == "adrv9002-zcu102"
        assert board.carrier == "zcu102"
        assert board.tags["daughter-board"] == "adrv9002"
        assert board.console is None
    assert patched["released"] == "adrv9002-zcu102"
    assert patched["booted_image"] == "2023_R2_P1"
    assert patched["powered_off"] is None  # power_down defaults off


def test_request_releases_on_exception(patched):
    with pytest.raises(RuntimeError):
        with core.request(part="adrv9002"):
            raise RuntimeError("boom")
    assert patched["released"] == "adrv9002-zcu102"


def test_request_power_down_powers_off_before_release(patched):
    with core.request(part="adrv9002", power_down=True):
        pass
    assert patched["powered_off"] == "BootFPGASoC"
    assert patched["released"] == "adrv9002-zcu102"


def test_request_no_match_raises_without_reserving(monkeypatch):
    monkeypatch.setattr(core, "resolve_coordinator", lambda c: "coord:8000")
    monkeypatch.setattr(core.match_client, "get_match", lambda *a, **k: _match(satisfiable=False))

    def boom(*a, **k):
        raise AssertionError("must not reserve when unsatisfiable")

    monkeypatch.setattr(core.reservation, "reserve_and_acquire", boom)
    with pytest.raises(NoMatchingBoard):
        with core.request(part="adrv9002"):
            pass


def test_request_provision_error_still_releases(patched, monkeypatch):
    def bad_boot(*a, **k):
        raise ProvisionError("boot failed")

    monkeypatch.setattr(core, "_boot", bad_boot)
    with pytest.raises(ProvisionError):
        with core.request(part="adrv9002"):
            pass
    assert patched["released"] == "adrv9002-zcu102"


def test_request_unavailable_propagates(patched, monkeypatch):
    def busy(*a, **k):
        raise BoardUnavailable("all busy")

    monkeypatch.setattr(core.reservation, "reserve_and_acquire", busy)
    with pytest.raises(BoardUnavailable):
        with core.request(part="adrv9002"):
            pass


def test_request_flash_mode_not_supported(patched):
    with pytest.raises(NotImplementedError):
        with core.request(part="adrv9002", mode="flash"):
            pass


def test_request_unknown_filters_rejected(patched):
    with pytest.raises(NotImplementedError):
        with core.request(part="adrv9002", hdl_config="lvds"):
            pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_request_core.py -v`
Expected: FAIL — `...request.core` missing.

- [ ] **Step 3: Write minimal implementation** — create `adi_lg_plugins/request/core.py`:

```python
"""Client-side orchestration for the hardware-request layer (uri mode).

Flow: resolve coordinator -> GET /match -> reserve+acquire (labgrid, queues
if busy) -> find the concrete place -> render env -> boot to shell -> resolve
URI -> yield Lease -> on exit: optional power-down, then release (always).
"""

from __future__ import annotations

import logging
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..hw_ci.coordinator import list_live_places, resolve_coordinator
from ..hw_ci.render_env import render_env_to
from . import match_client, reservation
from .errors import NoMatchingBoard, ProvisionError
from .uri import resolve_uri

logger = logging.getLogger(__name__)


@dataclass
class Lease:
    """A booted board handle yielded by ``request()``.

    ``target`` is the live labgrid Target; it is only valid inside the
    ``with`` block and is released when the block exits. ``uri`` is the
    primary handover for pyadi-iio. ``console`` is reserved for the future
    flash mode and is always None here.
    """

    place: str
    carrier: str
    tags: dict[str, str] = field(default_factory=dict)
    uri: str | None = None
    console: Any = None
    target: Any = None


def _concrete_place(coord: str, name: str):
    """Return the validated hw_ci Place for `name` from the coordinator."""
    places, _skipped = list_live_places(coord)
    for p in places:
        if p.name == name:
            return p
    raise ProvisionError(f"acquired place '{name}' not found among live places")


def _render_env(place) -> str:
    out = Path(tempfile.mkdtemp(prefix="adi-lg-req-")) / "env.yaml"
    render_env_to(place, out)
    return str(out)


def _boot(env_path: str, strategy_name: str, *, image: str | None, target_name: str = "main"):
    """Boot the board to a Linux shell and return the labgrid target."""
    from labgrid import Environment

    env = Environment(env_path)
    tg = env.get_target(target_name)
    if image:
        try:
            res = tg.get_resource("KuiperRelease")
            res.release_version = image
            logger.info("Using image version %s", image)
        except Exception:  # noqa: BLE001 - resource may be absent for some boards
            logger.warning("no KuiperRelease resource to pin image %s", image)
    strategy = tg.get_driver(strategy_name)
    try:
        strategy.transition("shell")
    except Exception as e:  # noqa: BLE001 - normalise any strategy error
        raise ProvisionError(f"boot failed: {e}") from e
    return tg


def _power_off(target: Any, strategy_name: str) -> None:
    """Best-effort power-down via the strategy's powered_off transition.

    Never raises: power-down is a courtesy on exit and must not mask the
    user's result or block the subsequent release.
    """
    try:
        target.get_driver(strategy_name).transition("powered_off")
    except Exception as e:  # noqa: BLE001 - power-down is best-effort
        logger.warning("power_down requested but power-off failed: %s", e)


@contextmanager
def request(
    *,
    part: str,
    carrier: str | None = None,
    mode: str = "uri",
    bootfile: str | None = None,
    wait: float = 1800.0,
    coord: str | None = None,
    power_down: bool = False,
    target_name: str = "main",
    **filters: str,
):
    """Request a board, boot it, yield a Lease, and release on exit.

    Only ``mode='uri'`` is supported in this increment.
    """
    if mode != "uri":
        raise NotImplementedError(f"mode '{mode}' is not available yet (uri only)")
    if filters:
        raise NotImplementedError(
            f"extra filters {sorted(filters)} are not supported yet "
            "(only part + carrier narrow the match)"
        )

    coord = resolve_coordinator(coord)
    match = match_client.get_match(coord, part=part, carrier=carrier, bootfile=bootfile)
    if not match.satisfiable:
        raise NoMatchingBoard(match.reason or f"no board for part '{part}'")

    res = reservation.reserve_and_acquire(coord, match.reservation_filter, wait=wait)
    target = None
    strategy_name = match.strategy or ""
    try:
        place = _concrete_place(coord, res.place)
        strategy_name = place.boot_strategy
        env_path = _render_env(place)
        target = _boot(env_path, strategy_name, image=match.image, target_name=target_name)
        uri = resolve_uri(target)
        yield Lease(
            place=res.place,
            carrier=place.carrier,
            tags={"daughter-board": place.daughter_board, "carrier": place.carrier,
                  "boot-strategy": strategy_name},
            uri=uri,
            target=target,
        )
    finally:
        if power_down and target is not None:
            _power_off(target, strategy_name)
        reservation.release(coord, res)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_request_core.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Lint and commit**

```bash
cd /home/tcollins/dev/lg-test/labgrid-plugins
ruff check adi_lg_plugins/request/core.py tests/test_request_core.py && \
  ruff format adi_lg_plugins/request/core.py tests/test_request_core.py
git add adi_lg_plugins/request/core.py tests/test_request_core.py
git commit -m "feat(request): request() orchestration, Lease, cleanup, power_down"
```

---

### Task 6: `__init__.py` — public API

**Files:**
- Create: `adi_lg_plugins/request/__init__.py`
- Test: `tests/test_request_public_api.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_request_public_api.py`:

```python
from __future__ import annotations


def test_public_api_exports():
    from adi_lg_plugins.request import (
        BoardUnavailable,
        Lease,
        NoMatchingBoard,
        ProvisionError,
        RequestError,
        request,
    )

    assert callable(request)
    assert issubclass(NoMatchingBoard, RequestError)
    assert issubclass(BoardUnavailable, RequestError)
    assert issubclass(ProvisionError, RequestError)
    # Lease is a dataclass with the expected primary handover field.
    lease = Lease(place="p", carrier="zcu102", uri="ip:1.2.3.4")
    assert lease.uri == "ip:1.2.3.4"
    assert lease.console is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_request_public_api.py -v`
Expected: FAIL — `request` not importable from the package (no `__init__.py`).

- [ ] **Step 3: Write minimal implementation** — create `adi_lg_plugins/request/__init__.py`:

```python
"""Low-config hardware request layer (uri mode).

Public API::

    from adi_lg_plugins.request import request

    with request(part="adrv9002") as board:
        sdr = adi.adrv9002(uri=board.uri)

See docs/superpowers/specs/2026-06-03-low-config-hardware-request-fresh-design.md.
"""

from .core import Lease, request
from .errors import (
    BoardUnavailable,
    NoMatchingBoard,
    ProvisionError,
    RequestError,
)

__all__ = [
    "request",
    "Lease",
    "RequestError",
    "NoMatchingBoard",
    "BoardUnavailable",
    "ProvisionError",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_request_public_api.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Run the whole new suite + lint + commit**

```bash
cd /home/tcollins/dev/lg-test/labgrid-plugins
python3 -m pytest tests/test_request_*.py -v   # all request unit tests green (hw test will skip)
ruff check adi_lg_plugins/request/__init__.py tests/test_request_public_api.py && \
  ruff format adi_lg_plugins/request/__init__.py tests/test_request_public_api.py
git add adi_lg_plugins/request/__init__.py tests/test_request_public_api.py
git commit -m "feat(request): public API (request, Lease, errors)"
```

---

### Task 7: Hardware smoke test (gated)

**Files:**
- Test: `tests/test_request_hw.py`

A single real end-to-end run behind the `--run-hardware` gate (see `tests/conftest.py`). It is `@pytest.mark.hardware`, so a normal `pytest` run skips it; it runs only in the lab / HW-CI with `--run-hardware` and a reachable coordinator (`LG_COORDINATOR`/`ADI_LG_COORDINATOR`).

**Prerequisite (see OPEN QUESTION above):** the coordinator's `board_catalog.yaml` `image:` value for `adrv9002` must be a real `KuiperRelease` release version (e.g. `2023_R2_P1`), not the placeholder `kuiper-2023_R2`, or the boot will fail to find the image.

- [ ] **Step 1: Write the test** — create `tests/test_request_hw.py`:

```python
from __future__ import annotations

import os

import pytest

from adi_lg_plugins.request import request


@pytest.mark.hardware
def test_request_adrv9002_uri_end_to_end():
    """Boot adrv9002-zcu102 via the request core and confirm a usable URI.

    Requires --run-hardware and a reachable coordinator. Validates the full
    lifecycle: match -> reserve -> acquire -> boot -> URI -> release.
    """
    if not (os.environ.get("LG_COORDINATOR") or os.environ.get("ADI_LG_COORDINATOR")):
        pytest.skip("no coordinator configured (LG_COORDINATOR / ADI_LG_COORDINATOR)")

    with request(part="adrv9002", carrier="zcu102", wait=1800) as board:
        assert board.uri and board.uri.startswith("ip:")
        assert board.place
        assert board.tags.get("daughter-board") == "adrv9002"
```

- [ ] **Step 2: Verify it is collected but skipped without the gate**

Run: `python3 -m pytest tests/test_request_hw.py -v`
Expected: 1 skipped, with reason "need --run-hardware option to run" (from `conftest.py`'s gate). Do NOT attempt a real `--run-hardware` run here — that is a lab-only step.

- [ ] **Step 3: Lint and commit**

```bash
cd /home/tcollins/dev/lg-test/labgrid-plugins
ruff check tests/test_request_hw.py && ruff format tests/test_request_hw.py
git add tests/test_request_hw.py
git commit -m "test(request): gated hardware end-to-end smoke (uri mode)"
```

---

## Self-Review (completed during plan authoring)

**Spec coverage** — this plan implements the spec's "The Request Contract", "Error Handling & Cleanup", and the Plan-2 build-order item ("Request core + Lease + cleanup — provable against the fake backend, then the hardware smoke"):
- `request(part, carrier, bootfile, wait, power_down, **filters)` context manager ✓ (Task 5). `carrier` optional ✓; `bootfile` single optional pin ✓; `wait` with queue-then-timeout ✓ (Task 4 `BoardUnavailable`); `power_down` default off ✓ (Task 5).
- `Lease.uri` primary handover ✓; `.console` reserved/None ✓; `.place`/`.tags`/`.carrier` metadata ✓. `matlab_board` intentionally dropped (deferred MATLAB surface) ✓.
- Errors: `NoMatchingBoard` (no wait), `BoardUnavailable` (after `wait`), `ProvisionError` (carries console tail) ✓ (Tasks 1, 4, 5).
- Cleanup unconditional in `finally`, release never raises ✓ (Tasks 4, 5); leak-on-acquire-failure cancels the reservation ✓ (Task 4).
- "Fake backend" exercising the full lifecycle incl. failure/cleanup ✓ (Task 5 monkeypatched seams: success, release-on-exception, no-match-no-reserve, provision-error-still-releases, unavailable, power_down).
- Hardware smoke behind `--run-hardware` ✓ (Task 7).

Deliberately deferred (later plans / increments), consistent with the spec: SIGINT/SIGTERM handlers + exit-code mapping (those belong to the **CLI**, Plan 3 — this library raises typed exceptions; the CLI translates them to `EXIT_*`), flash mode, `.ip`/`.jtag` interfaces, MATLAB metadata.

**Placeholder scan** — no TBD/TODO; every code step is complete. The one genuine unknown (image string → `KuiperRelease.release_version`) is called out explicitly as a data-file prerequisite, not left implicit.

**Type consistency** — `MatchResult` fields (`satisfiable`, `reason`, `reservation_filter`, `image`, `strategy`, `place`) are used identically in `match_client.py`, `core.py`, and both test files. `Reservation(place, token)` is consistent across `reservation.py` and `core.py`. `_boot(env_path, strategy_name, *, image, target_name)` and `_power_off(target, strategy_name)` signatures match their call sites and the monkeypatched fakes in `test_request_core.py`. `resolve_uri(target)` is consistent across `uri.py` and `core.py`. The reused `hw_ci` helpers (`resolve_coordinator`, `list_live_places`, `render_env_to`, `Place.{name,carrier,daughter_board,boot_strategy}`) match the signatures verified in `adi_lg_plugins/hw_ci/`.

## Open Questions / cross-layer notes for implementation

- **`image` → `release_version` (the one real prerequisite).** Confirm the catalog `image:` value is a valid `KuiperRelease` release version before the Task-7 smoke run; update `coordinator/api/board_catalog.yaml` if it still holds the `kuiper-2023_R2` placeholder. Unit tests are unaffected.
- **Second coordinator round-trip.** `core` calls `list_live_places` again (via `_concrete_place`) to get the validated `Place` for env rendering, even though `/match` already returned `strategy`/`place`. This mirrors the proven path and keeps env rendering identical to CI. If the extra round-trip ever matters, a later refactor can construct the `Place` from the `/match` result instead — out of scope here.
- **`strategy` source.** `core` uses `place.boot_strategy` (from the live place) as the operative strategy name for both rendering and `get_driver`, since the rendered template defines a driver of that name. `match.strategy` should equal it (both derive from the place's `boot-strategy` tag); a divergence would surface as a `get_driver` failure → `ProvisionError`. Treating them as authoritative-equal is intentional.
