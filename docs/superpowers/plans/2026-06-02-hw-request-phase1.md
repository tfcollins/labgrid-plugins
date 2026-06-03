# Hardware Request — Phase 1 (uri mode) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a consumer request a board by part (`adi-lg request --part ad9361 --run '<cmd>'`), and have labgrid-plugins select a free matching board, boot it (Linux), export its libIIO URI, run the command, and release the board — with zero strategy/driver/resource config from the consumer.

**Architecture:** A thin coordinator extension (a `board_catalog.yaml` + `GET /api/catalog` and `GET /api/match` endpoints) answers "what free place satisfies this request and what image version / MATLAB name describes it." A new client-side core package `adi_lg_plugins/request/` orchestrates match → reserve+acquire (labgrid reservations) → render env (reusing `hw_ci.render_env`) → boot (reusing existing strategies) → resolve URI → yield a `Lease` → release on exit. A new `adi-lg request` CLI command wraps the core. Boot runs client-side exactly as the existing hw-matrix runner does today.

**Tech Stack:** Python 3.10+, Click, FastAPI/Pydantic v2 (coordinator), labgrid `>=25.0` (`Environment`, reservations via `labgrid-client`), attrs, pytest + Click `CliRunner` + FastAPI `TestClient`, ruff (line-length 100, double quotes), nox.

**Scope boundary (Phase 1 only):** `uri` mode end-to-end on a single board. `flash` mode, the pytest plugin, and GHA templates are **out of scope** (Phases 2–3) — `--mode flash` is accepted by the CLI but errors out cleanly. `Lease.console` is present but `None` in Phase 1.

---

## File Structure

**Coordinator (new/modified):**
- Create `coordinator/api/app/board_catalog.yaml` — the catalog data (channels + boards).
- Create `coordinator/api/app/catalog.py` — load + resolve catalog, pure match logic.
- Create `coordinator/api/app/routers/catalog.py` — `GET /api/catalog`, `GET /api/match`.
- Modify `coordinator/api/app/models.py` — add `CatalogModel`, `MatchResponse`, `MatchCandidate`.
- Modify `coordinator/api/app/config.py` — add `board_catalog_path` setting.
- Modify `coordinator/api/app/main.py` — `include_router(catalog.router, prefix="/api")`.
- Create `coordinator/api/tests/test_catalog.py` — pure resolution/match tests.
- Create `coordinator/api/tests/test_catalog_router.py` — endpoint tests via `TestClient`.

**Client core (new):**
- Create `adi_lg_plugins/request/__init__.py` — public exports (`request`, `Lease`, errors).
- Create `adi_lg_plugins/request/errors.py` — exceptions + exit-code constants.
- Create `adi_lg_plugins/request/match_client.py` — HTTP client for `/match`, `/catalog`.
- Create `adi_lg_plugins/request/reservation.py` — labgrid reserve/acquire/release wrapper.
- Create `adi_lg_plugins/request/uri.py` — URI resolution from a booted target.
- Create `adi_lg_plugins/request/core.py` — `request()` context manager + `Lease` + `_boot`.
- Modify `adi_lg_plugins/tools/cli.py` — add the `request` subcommand.
- Create `tests/test_request_match_client.py`, `tests/test_request_reservation.py`, `tests/test_request_uri.py`, `tests/test_request_core.py`, `tests/test_request_cli.py`.
- Create `tests/test_request_hw.py` — hardware-gated end-to-end smoke (added to `conftest.py` collect-ignore list).

---

## Task 0: Create the working branch

**Files:** none (git only)

- [ ] **Step 1: Branch off the design branch**

The design spec is committed on `design/low-config-hardware-request`. Create the implementation branch from there.

Run:
```bash
cd /home/tcollins/dev/lg-test/labgrid-plugins
git checkout design/low-config-hardware-request
git checkout -b feat/hw-request-phase1
git branch --show-current
```
Expected output: `feat/hw-request-phase1`

---

## Task 1: Board catalog data file

**Files:**
- Create: `coordinator/api/app/board_catalog.yaml`

- [ ] **Step 1: Write the catalog file**

```yaml
# Board catalog for the hardware-request layer.
# `channels` maps an image channel to its current "latest stable" version.
# `boards` maps a part (daughter-board tag value) to its image channel and
# per-carrier metadata. Phase 1 uses: image_channel, carriers.*.matlab_board.
channels:
  kuiper-stable: "2023_R2_P1"

boards:
  ad9361:
    image_channel: kuiper-stable
    carriers:
      zcu102:
        matlab_board: zynqmp-zcu102-rev10-ad9361-fmcomms2-3
      zc706:
        matlab_board: zynq-zc706-adv7511-ad9361-fmcomms2-3
  ad9081:
    image_channel: kuiper-stable
    carriers:
      zcu102:
        matlab_board: zynqmp-zcu102-rev10-ad9081
```

- [ ] **Step 2: Commit**

```bash
git add coordinator/api/app/board_catalog.yaml
git commit -m "feat(catalog): add board_catalog.yaml data file"
```

---

## Task 2: Catalog loader + resolution (pure logic)

**Files:**
- Create: `coordinator/api/app/catalog.py`
- Test: `coordinator/api/tests/test_catalog.py`

- [ ] **Step 1: Write the failing test**

```python
# coordinator/api/tests/test_catalog.py
import textwrap

import pytest

from app.catalog import (
    Catalog,
    ResolvedBoard,
    UnknownPart,
    UnresolvableVersion,
    load_catalog,
    resolve_board,
)

CATALOG_YAML = textwrap.dedent(
    """
    channels:
      kuiper-stable: "2023_R2_P1"
    boards:
      ad9361:
        image_channel: kuiper-stable
        carriers:
          zcu102: {matlab_board: zynqmp-zcu102-rev10-ad9361-fmcomms2-3}
          zc706:  {matlab_board: zynq-zc706-adv7511-ad9361-fmcomms2-3}
      ad9081:
        image_channel: kuiper-stable
        carriers:
          zcu102: {matlab_board: zynqmp-zcu102-rev10-ad9081}
    """
)


@pytest.fixture
def catalog(tmp_path):
    p = tmp_path / "board_catalog.yaml"
    p.write_text(CATALOG_YAML)
    return load_catalog(p)


def test_load_catalog_parses_channels_and_boards(catalog):
    assert isinstance(catalog, Catalog)
    assert catalog.channels["kuiper-stable"] == "2023_R2_P1"
    assert set(catalog.boards) == {"ad9361", "ad9081"}
    assert catalog.boards["ad9361"].carriers["zcu102"].matlab_board.endswith("fmcomms2-3")


def test_resolve_board_defaults_to_channel_latest(catalog):
    r = resolve_board(catalog, part="ad9361")
    assert isinstance(r, ResolvedBoard)
    assert r.part == "ad9361"
    assert r.version == "2023_R2_P1"
    assert r.matlab_boards == {
        "zcu102": "zynqmp-zcu102-rev10-ad9361-fmcomms2-3",
        "zc706": "zynq-zc706-adv7511-ad9361-fmcomms2-3",
    }


def test_resolve_board_honours_pinned_bootfile(catalog):
    r = resolve_board(catalog, part="ad9361", bootfile="2024_R1")
    assert r.version == "2024_R1"


def test_resolve_board_unknown_part_raises(catalog):
    with pytest.raises(UnknownPart):
        resolve_board(catalog, part="nope")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd coordinator/api && python -m pytest tests/test_catalog.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.catalog'`

- [ ] **Step 3: Write the implementation**

```python
# coordinator/api/app/catalog.py
"""Board catalog: load board_catalog.yaml and resolve part -> image/version/metadata.

Pure logic, no FastAPI imports, so it is unit-testable in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class CatalogError(Exception):
    """Base class for catalog resolution failures."""


class UnknownPart(CatalogError):
    """The requested part is not in the catalog."""


class UnresolvableVersion(CatalogError):
    """No bootfile pin given and no channel version could be resolved."""


@dataclass(frozen=True)
class CarrierEntry:
    matlab_board: str | None = None


@dataclass(frozen=True)
class BoardEntry:
    part: str
    image_channel: str | None
    carriers: dict[str, CarrierEntry] = field(default_factory=dict)


@dataclass(frozen=True)
class Catalog:
    channels: dict[str, str] = field(default_factory=dict)
    boards: dict[str, BoardEntry] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolvedBoard:
    part: str
    version: str | None
    matlab_boards: dict[str, str]


def load_catalog(path: str | Path) -> Catalog:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    channels = {str(k): str(v) for k, v in (raw.get("channels") or {}).items()}
    boards: dict[str, BoardEntry] = {}
    for part, entry in (raw.get("boards") or {}).items():
        entry = entry or {}
        carriers = {
            str(cname): CarrierEntry(matlab_board=(cval or {}).get("matlab_board"))
            for cname, cval in (entry.get("carriers") or {}).items()
        }
        boards[str(part)] = BoardEntry(
            part=str(part),
            image_channel=entry.get("image_channel"),
            carriers=carriers,
        )
    return Catalog(channels=channels, boards=boards)


def resolve_board(
    catalog: Catalog,
    *,
    part: str,
    carrier: str | None = None,
    bootfile: str | None = None,
) -> ResolvedBoard:
    """Resolve a request into a concrete image version + per-carrier MATLAB names.

    `carrier` is accepted for symmetry/validation but does not change version
    resolution in Phase 1. A pinned `bootfile` is taken as-is; otherwise the
    board's channel "latest" is used.
    """
    board = catalog.boards.get(part)
    if board is None:
        raise UnknownPart(f"part '{part}' is not in the board catalog")

    if bootfile:
        version: str | None = bootfile
    elif board.image_channel and board.image_channel in catalog.channels:
        version = catalog.channels[board.image_channel]
    else:
        raise UnresolvableVersion(
            f"part '{part}' has no pinned bootfile and no resolvable image channel"
        )

    matlab_boards = {
        cname: c.matlab_board for cname, c in board.carriers.items() if c.matlab_board
    }
    return ResolvedBoard(part=part, version=version, matlab_boards=matlab_boards)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd coordinator/api && python -m pytest tests/test_catalog.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add coordinator/api/app/catalog.py coordinator/api/tests/test_catalog.py
git commit -m "feat(catalog): load board_catalog.yaml and resolve part->version/metadata"
```

---

## Task 3: Pure place-matching logic

**Files:**
- Modify: `coordinator/api/app/catalog.py` (add `match_places` + `MatchData`)
- Test: `coordinator/api/tests/test_catalog.py` (add cases)

- [ ] **Step 1: Write the failing test (append to test_catalog.py)**

```python
# append to coordinator/api/tests/test_catalog.py
from app.catalog import MatchData, match_places


def _place(name, daughter, carrier, *, acquired=None, strategy="BootFPGASoC"):
    return {
        "name": name,
        "acquired": acquired,
        "tags": {
            "daughter-board": daughter,
            "carrier": carrier,
            "boot-strategy": strategy,
        },
    }


def test_match_places_filters_by_part(catalog):
    places = [
        _place("p1", "ad9361", "zcu102"),
        _place("p2", "ad9081", "zcu102"),
    ]
    m = match_places(catalog, places, part="ad9361")
    assert isinstance(m, MatchData)
    assert m.satisfiable is True
    assert m.reservation_filter == {"daughter-board": "ad9361"}
    assert [c.place for c in m.candidates] == ["p1"]
    assert m.version == "2023_R2_P1"


def test_match_places_narrows_by_carrier(catalog):
    places = [
        _place("p1", "ad9361", "zcu102"),
        _place("p3", "ad9361", "zc706"),
    ]
    m = match_places(catalog, places, part="ad9361", carrier="zc706")
    assert m.reservation_filter == {"daughter-board": "ad9361", "carrier": "zc706"}
    assert [c.place for c in m.candidates] == ["p3"]


def test_match_places_no_live_place_is_unsatisfiable(catalog):
    m = match_places(catalog, [], part="ad9361")
    assert m.satisfiable is False
    assert "no matching" in m.reason.lower()


def test_match_places_unknown_part_is_unsatisfiable(catalog):
    m = match_places(catalog, [_place("p1", "ad9361", "zcu102")], part="nope")
    assert m.satisfiable is False
    assert "catalog" in m.reason.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd coordinator/api && python -m pytest tests/test_catalog.py -k match -v`
Expected: FAIL with `ImportError: cannot import name 'match_places'`

- [ ] **Step 3: Add the implementation to catalog.py**

```python
# append to coordinator/api/app/catalog.py


@dataclass(frozen=True)
class MatchCandidate:
    place: str
    carrier: str
    acquired: bool


@dataclass(frozen=True)
class MatchData:
    satisfiable: bool
    reason: str = ""
    reservation_filter: dict[str, str] = field(default_factory=dict)
    version: str | None = None
    matlab_boards: dict[str, str] = field(default_factory=dict)
    candidates: list[MatchCandidate] = field(default_factory=list)


def match_places(
    catalog: Catalog,
    places: list[dict],
    *,
    part: str,
    carrier: str | None = None,
    bootfile: str | None = None,
) -> MatchData:
    """Match a request against live places using catalog + place tags.

    `places` are raw place dicts (name, acquired, tags) as returned by the
    coordinator client. Returns a MatchData describing satisfiability, the
    labgrid reservation filter, resolved version, and candidate places.
    """
    try:
        resolved = resolve_board(catalog, part=part, carrier=carrier, bootfile=bootfile)
    except CatalogError as e:
        return MatchData(satisfiable=False, reason=str(e))

    reservation_filter = {"daughter-board": part}
    if carrier:
        reservation_filter["carrier"] = carrier

    candidates: list[MatchCandidate] = []
    for p in places:
        tags = p.get("tags") or {}
        if tags.get("daughter-board") != part:
            continue
        if carrier and tags.get("carrier") != carrier:
            continue
        candidates.append(
            MatchCandidate(
                place=p.get("name", ""),
                carrier=tags.get("carrier", ""),
                acquired=bool(p.get("acquired")),
            )
        )

    if not candidates:
        return MatchData(
            satisfiable=False,
            reason=f"no matching place for part '{part}'"
            + (f" carrier '{carrier}'" if carrier else ""),
            reservation_filter=reservation_filter,
            version=resolved.version,
            matlab_boards=resolved.matlab_boards,
        )

    return MatchData(
        satisfiable=True,
        reservation_filter=reservation_filter,
        version=resolved.version,
        matlab_boards=resolved.matlab_boards,
        candidates=candidates,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd coordinator/api && python -m pytest tests/test_catalog.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add coordinator/api/app/catalog.py coordinator/api/tests/test_catalog.py
git commit -m "feat(catalog): add pure match_places logic"
```

---

## Task 4: Pydantic models + config setting

**Files:**
- Modify: `coordinator/api/app/models.py`
- Modify: `coordinator/api/app/config.py`

- [ ] **Step 1: Add Pydantic response models to models.py**

Append to `coordinator/api/app/models.py`:

```python
# --- Hardware-request catalog/match models ---


class CarrierModel(BaseModel):
    matlab_board: str | None = None


class BoardModel(BaseModel):
    image_channel: str | None = None
    carriers: dict[str, CarrierModel] = {}


class CatalogModel(BaseModel):
    channels: dict[str, str] = {}
    boards: dict[str, BoardModel] = {}


class MatchCandidateModel(BaseModel):
    place: str
    carrier: str
    acquired: bool


class MatchResponse(BaseModel):
    satisfiable: bool
    reason: str = ""
    reservation_filter: dict[str, str] = {}
    version: str | None = None
    matlab_boards: dict[str, str] = {}
    candidates: list[MatchCandidateModel] = []
```

- [ ] **Step 2: Add the catalog path setting to config.py**

In `coordinator/api/app/config.py`, add a field to the existing `Settings` class (follow the existing field style). The default points at the bundled catalog beside the app package:

```python
    board_catalog_path: str = str(Path(__file__).resolve().parent / "board_catalog.yaml")
```

If `config.py` does not already `from pathlib import Path`, add that import at the top.

- [ ] **Step 3: Verify the package still imports**

Run: `cd coordinator/api && python -c "from app.models import MatchResponse, CatalogModel; from app.config import settings; print(settings.board_catalog_path)"`
Expected: prints a path ending in `app/board_catalog.yaml`

- [ ] **Step 4: Commit**

```bash
git add coordinator/api/app/models.py coordinator/api/app/config.py
git commit -m "feat(catalog): add catalog/match Pydantic models and board_catalog_path setting"
```

---

## Task 5: Catalog + match router

**Files:**
- Create: `coordinator/api/app/routers/catalog.py`
- Modify: `coordinator/api/app/main.py`
- Test: `coordinator/api/tests/test_catalog_router.py`

- [ ] **Step 1: Write the failing test**

```python
# coordinator/api/tests/test_catalog_router.py
import textwrap
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

CATALOG_YAML = textwrap.dedent(
    """
    channels:
      kuiper-stable: "2023_R2_P1"
    boards:
      ad9361:
        image_channel: kuiper-stable
        carriers:
          zcu102: {matlab_board: zynqmp-zcu102-rev10-ad9361-fmcomms2-3}
    """
)


class FakeCoordinator:
    def __init__(self, places):
        self._places = places

    def get_places(self):
        return self._places


def _place(name, daughter, carrier, *, acquired=None):
    return {
        "name": name,
        "acquired": acquired,
        "tags": {"daughter-board": daughter, "carrier": carrier, "boot-strategy": "BootFPGASoC"},
    }


@pytest.fixture
def client(tmp_path):
    from app.config import settings as cfg
    from app.main import app

    catalog_file = tmp_path / "board_catalog.yaml"
    catalog_file.write_text(CATALOG_YAML)
    cfg.board_catalog_path = str(catalog_file)

    fake = FakeCoordinator([_place("p1", "ad9361", "zcu102"), _place("p2", "ad9081", "zcu102")])

    @asynccontextmanager
    async def _lifespan(_app):
        _app.state.coordinator = fake
        yield

    app.router.lifespan_context = _lifespan
    with TestClient(app) as c:
        yield c


def test_get_catalog(client):
    r = client.get("/api/catalog")
    assert r.status_code == 200
    assert r.json()["channels"]["kuiper-stable"] == "2023_R2_P1"


def test_match_satisfiable(client):
    r = client.get("/api/match", params={"part": "ad9361"})
    assert r.status_code == 200
    body = r.json()
    assert body["satisfiable"] is True
    assert body["reservation_filter"] == {"daughter-board": "ad9361"}
    assert body["version"] == "2023_R2_P1"
    assert [c["place"] for c in body["candidates"]] == ["p1"]


def test_match_no_place(client):
    r = client.get("/api/match", params={"part": "ad9361", "carrier": "zc706"})
    assert r.status_code == 200
    assert r.json()["satisfiable"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd coordinator/api && python -m pytest tests/test_catalog_router.py -v`
Expected: FAIL (404 on `/api/catalog` because the router is not registered yet)

- [ ] **Step 3: Write the router**

```python
# coordinator/api/app/routers/catalog.py
from fastapi import APIRouter, Request

from ..catalog import load_catalog, match_places
from ..config import settings
from ..models import CatalogModel, MatchResponse

router = APIRouter(tags=["catalog"])


def _get_client(request: Request):
    return request.app.state.coordinator


def _load() -> object:
    return load_catalog(settings.board_catalog_path)


@router.get("/catalog", response_model=CatalogModel)
async def get_catalog():
    cat = _load()
    return {
        "channels": cat.channels,
        "boards": {
            part: {
                "image_channel": b.image_channel,
                "carriers": {cn: {"matlab_board": c.matlab_board} for cn, c in b.carriers.items()},
            }
            for part, b in cat.boards.items()
        },
    }


@router.get("/match", response_model=MatchResponse)
async def match(
    request: Request,
    part: str,
    carrier: str | None = None,
    mode: str = "uri",
    bootfile: str | None = None,
):
    cat = _load()
    places = _get_client(request).get_places()
    # Normalise PlaceModel objects or dicts to plain dicts.
    norm = [p if isinstance(p, dict) else p.model_dump() for p in places]
    data = match_places(cat, norm, part=part, carrier=carrier, bootfile=bootfile)
    return {
        "satisfiable": data.satisfiable,
        "reason": data.reason,
        "reservation_filter": data.reservation_filter,
        "version": data.version,
        "matlab_boards": data.matlab_boards,
        "candidates": [
            {"place": c.place, "carrier": c.carrier, "acquired": c.acquired}
            for c in data.candidates
        ],
    }
```

- [ ] **Step 4: Register the router in main.py**

In `coordinator/api/app/main.py`, add `catalog` to the routers import (mirror the existing `from .routers import (...)` block) and add this line beside the other `app.include_router(...)` calls:

```python
app.include_router(catalog.router, prefix="/api")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd coordinator/api && python -m pytest tests/test_catalog_router.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Run the whole coordinator suite + lint**

Run: `cd coordinator/api && python -m pytest -q && ruff check app && ruff format --check app`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add coordinator/api/app/routers/catalog.py coordinator/api/app/main.py coordinator/api/tests/test_catalog_router.py
git commit -m "feat(catalog): add GET /api/catalog and GET /api/match endpoints"
```

---

## Task 6: Client errors + exit codes

**Files:**
- Create: `adi_lg_plugins/request/__init__.py` (empty for now, package marker)
- Create: `adi_lg_plugins/request/errors.py`
- Test: `tests/test_request_errors.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_request_errors.py
from adi_lg_plugins.request.errors import (
    EXIT_NO_MATCH,
    EXIT_PROVISION,
    EXIT_UNAVAILABLE,
    BoardUnavailable,
    NoMatchingBoard,
    ProvisionError,
    RequestError,
)


def test_exit_codes_are_distinct():
    assert len({EXIT_NO_MATCH, EXIT_UNAVAILABLE, EXIT_PROVISION}) == 3


def test_exceptions_subclass_request_error():
    for exc in (NoMatchingBoard, BoardUnavailable, ProvisionError):
        assert issubclass(exc, RequestError)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_request_errors.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'adi_lg_plugins.request'`

- [ ] **Step 3: Write the implementation**

```python
# adi_lg_plugins/request/__init__.py
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

```python
# adi_lg_plugins/request/errors.py
"""Exceptions and CLI exit codes for the hardware-request layer."""

# Infra exit codes are kept well above typical test-runner codes so a GHA leg
# can tell an infra problem from a real test failure.
EXIT_NO_MATCH = 10  # request can never be satisfied (unknown part / no such board)
EXIT_UNAVAILABLE = 11  # matching board(s) exist but none free within `wait`
EXIT_PROVISION = 12  # boot/flash failed


class RequestError(Exception):
    """Base class for hardware-request failures."""


class NoMatchingBoard(RequestError):
    """No place can satisfy the request (catalog/tags); do not wait."""


class BoardUnavailable(RequestError):
    """Matching boards exist but none became free within the wait window."""


class ProvisionError(RequestError):
    """Booting/flashing the acquired board failed."""

    def __init__(self, message: str, console_tail: str = ""):
        super().__init__(message)
        self.console_tail = console_tail
```

Note: `__init__.py` imports `core` (built in Task 10). To keep this task's test green before Task 10 exists, create a **temporary** `adi_lg_plugins/request/core.py` stub now:

```python
# adi_lg_plugins/request/core.py  (temporary stub, fully implemented in Task 10)
class Lease:  # noqa: D101 - replaced in Task 10
    pass


def request(*args, **kwargs):  # noqa: D103 - replaced in Task 10
    raise NotImplementedError
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_request_errors.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add adi_lg_plugins/request/__init__.py adi_lg_plugins/request/errors.py adi_lg_plugins/request/core.py tests/test_request_errors.py
git commit -m "feat(request): add errors and exit codes for hardware-request layer"
```

---

## Task 7: Match HTTP client

**Files:**
- Create: `adi_lg_plugins/request/match_client.py`
- Test: `tests/test_request_match_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_request_match_client.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_request_match_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'adi_lg_plugins.request.match_client'`

- [ ] **Step 3: Write the implementation**

```python
# adi_lg_plugins/request/match_client.py
"""HTTP client for the coordinator's /api/match and /api/catalog endpoints.

Uses only the standard library (urllib) to avoid adding a dependency.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import urlencode
from urllib.request import urlopen


@dataclass(frozen=True)
class MatchCandidate:
    place: str
    carrier: str
    acquired: bool


@dataclass(frozen=True)
class MatchResult:
    satisfiable: bool
    reason: str = ""
    reservation_filter: dict[str, str] = field(default_factory=dict)
    version: str | None = None
    matlab_boards: dict[str, str] = field(default_factory=dict)
    candidates: list[MatchCandidate] = field(default_factory=list)


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
    mode: str = "uri",
    bootfile: str | None = None,
    timeout: float = 15.0,
) -> MatchResult:
    params = {"part": part, "mode": mode}
    if carrier:
        params["carrier"] = carrier
    if bootfile:
        params["bootfile"] = bootfile
    url = f"{_base_url(coord)}/api/match?{urlencode(params)}"
    data = _get_json(url, timeout=timeout)
    return MatchResult(
        satisfiable=bool(data.get("satisfiable")),
        reason=data.get("reason", ""),
        reservation_filter=data.get("reservation_filter") or {},
        version=data.get("version"),
        matlab_boards=data.get("matlab_boards") or {},
        candidates=[
            MatchCandidate(place=c["place"], carrier=c.get("carrier", ""), acquired=c.get("acquired", False))
            for c in (data.get("candidates") or [])
        ],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_request_match_client.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add adi_lg_plugins/request/match_client.py tests/test_request_match_client.py
git commit -m "feat(request): add HTTP client for /api/match"
```

---

## Task 8: Reservation wrapper (reserve / acquire / release)

**Files:**
- Create: `adi_lg_plugins/request/reservation.py`
- Test: `tests/test_request_reservation.py`

This wraps `labgrid-client` the way `.github/actions/acquire-place/action.yml` does, but in Python: reserve by tag filter with `--wait`, discover the allocated place, acquire via the reservation token, and release/cancel on teardown.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_request_reservation.py
import subprocess

import pytest

from adi_lg_plugins.request import reservation
from adi_lg_plugins.request.errors import BoardUnavailable


def test_parse_token_from_reserve_shell_output():
    out = "export LG_TOKEN=abc123\n"
    assert reservation._parse_token(out) == "abc123"


def test_parse_allocated_place_from_reservations_block():
    # Sample `labgrid-client reservations` output: token header then fields.
    block = (
        "Reservation 'abc123':\n"
        "  owner: ci/runner\n"
        "  state: allocated\n"
        "  filters:\n"
        "    main: daughter-board=ad9361\n"
        "  allocations:\n"
        "    main: lab1/mini2\n"
    )
    assert reservation._parse_allocated_place(block, "abc123") == "mini2"


def test_reserve_and_acquire_happy_path(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        joined = " ".join(cmd)
        if "reserve" in joined:
            return subprocess.CompletedProcess(cmd, 0, stdout="export LG_TOKEN=tok9\n", stderr="")
        if "reservations" in joined:
            out = "Reservation 'tok9':\n  allocations:\n    main: lab1/mini2\n"
            return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
        if "acquire" in joined:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(reservation.subprocess, "run", fake_run)

    res = reservation.reserve_and_acquire(
        "10.0.0.41:20408", {"daughter-board": "ad9361"}, wait=60
    )
    assert res.place == "mini2"
    assert res.token == "tok9"
    assert any("acquire" in " ".join(c) for c in calls)


def test_reserve_timeout_raises_board_unavailable(monkeypatch):
    def fake_run(cmd, **kw):
        if "reserve" in " ".join(cmd):
            raise subprocess.TimeoutExpired(cmd, timeout=1)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(reservation.subprocess, "run", fake_run)
    with pytest.raises(BoardUnavailable):
        reservation.reserve_and_acquire("c", {"daughter-board": "ad9361"}, wait=1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_request_reservation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'adi_lg_plugins.request.reservation'`

- [ ] **Step 3: Write the implementation**

```python
# adi_lg_plugins/request/reservation.py
"""Wrap labgrid-client reservations: reserve by tag filter, acquire, release.

Mirrors .github/actions/acquire-place/action.yml but reserves by tags (not a
known place name) and discovers the allocated place from the reservation.
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

    Allocations look like ``main: <exporter>/<place>``; we return the bare place.
    """
    in_block = False
    for line in stdout.splitlines():
        if line.startswith("Reservation"):
            in_block = token in line
            continue
        if in_block:
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
        raise BoardUnavailable(
            f"no free board matching {filt} within {wait:.0f}s"
        ) from e
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

Run: `python -m pytest tests/test_request_reservation.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add adi_lg_plugins/request/reservation.py tests/test_request_reservation.py
git commit -m "feat(request): add labgrid reservation wrapper (reserve/acquire/release)"
```

> **Implementation note for the hardware task (Task 12):** the exact `labgrid-client reservations` output format must be confirmed against the installed labgrid `>=25.0`. If the allocation line differs from the sample above, adjust `_parse_allocated_place` and its unit test together.

---

## Task 9: URI resolution from a booted target

**Files:**
- Create: `adi_lg_plugins/request/uri.py`
- Test: `tests/test_request_uri.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_request_uri.py
import pytest

from adi_lg_plugins.request.errors import ProvisionError
from adi_lg_plugins.request.uri import resolve_uri


class FakeResource:
    def __init__(self, address):
        self.address = address


class FakeTarget:
    def __init__(self, resource):
        self._resource = resource

    def get_resource(self, name):
        if self._resource is None:
            raise Exception(f"no resource {name}")
        return self._resource


def test_resolve_uri_builds_ip_uri():
    tg = FakeTarget(FakeResource("10.0.0.57"))
    assert resolve_uri(tg) == "ip:10.0.0.57"


def test_resolve_uri_missing_network_raises():
    with pytest.raises(ProvisionError):
        resolve_uri(FakeTarget(None))


def test_resolve_uri_missing_address_raises():
    with pytest.raises(ProvisionError):
        resolve_uri(FakeTarget(FakeResource(None)))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_request_uri.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'adi_lg_plugins.request.uri'`

- [ ] **Step 3: Write the implementation**

```python
# adi_lg_plugins/request/uri.py
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

Run: `python -m pytest tests/test_request_uri.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add adi_lg_plugins/request/uri.py tests/test_request_uri.py
git commit -m "feat(request): add URI resolution from booted target"
```

---

## Task 10: Core `request()` context manager + `Lease`

**Files:**
- Modify: `adi_lg_plugins/request/core.py` (replace the Task 6 stub)
- Test: `tests/test_request_core.py`

The core wires the pieces together. It calls module-level functions (`match_client.get_match`, `reservation.reserve_and_acquire`, `_concrete_place`, `_boot`, `resolve_uri`) so tests monkeypatch them — the same pattern existing tests use to patch `cli.Environment`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_request_core.py
import pytest

from adi_lg_plugins.request import core
from adi_lg_plugins.request.errors import (
    BoardUnavailable,
    NoMatchingBoard,
    ProvisionError,
)
from adi_lg_plugins.request.match_client import MatchCandidate, MatchResult
from adi_lg_plugins.request.reservation import Reservation


class FakePlace:
    def __init__(self, name="mini2", carrier="zcu102", strategy="BootFPGASoC"):
        self.name = name
        self.carrier = carrier
        self.daughter_board = "ad9361"
        self.boot_strategy = strategy
        self.hdl_config = None
        self.extra_tags = {}


def _match(satisfiable=True):
    return MatchResult(
        satisfiable=satisfiable,
        reservation_filter={"daughter-board": "ad9361"},
        version="2023_R2_P1",
        matlab_boards={"zcu102": "zynqmp-zcu102-rev10-ad9361-fmcomms2-3"},
        candidates=[MatchCandidate("mini2", "zcu102", False)],
    )


@pytest.fixture
def patched(monkeypatch):
    state = {"released": None, "booted_version": None}

    monkeypatch.setattr(core, "resolve_coordinator", lambda c: "coord:8000")
    monkeypatch.setattr(core.match_client, "get_match", lambda *a, **k: _match())
    monkeypatch.setattr(
        core.reservation,
        "reserve_and_acquire",
        lambda *a, **k: Reservation(place="mini2", token="tok"),
    )

    def fake_release(coord, res, **k):
        state["released"] = res.place

    monkeypatch.setattr(core.reservation, "release", fake_release)
    monkeypatch.setattr(core, "_concrete_place", lambda coord, name: FakePlace(name=name))
    monkeypatch.setattr(core, "_render_env", lambda place: "/tmp/env.yaml")

    def fake_boot(env_path, strategy, *, version, target_name="main"):
        state["booted_version"] = version
        return object()  # fake target

    monkeypatch.setattr(core, "_boot", fake_boot)
    monkeypatch.setattr(core, "resolve_uri", lambda tg: "ip:10.0.0.57")
    return state


def test_request_yields_lease_and_releases(patched):
    with core.request(part="ad9361") as board:
        assert board.uri == "ip:10.0.0.57"
        assert board.place == "mini2"
        assert board.matlab_board == "zynqmp-zcu102-rev10-ad9361-fmcomms2-3"
        assert board.console is None
    assert patched["released"] == "mini2"
    assert patched["booted_version"] == "2023_R2_P1"


def test_request_releases_on_exception(patched):
    with pytest.raises(RuntimeError):
        with core.request(part="ad9361"):
            raise RuntimeError("boom")
    assert patched["released"] == "mini2"


def test_request_no_match_raises_without_reserving(monkeypatch):
    monkeypatch.setattr(core, "resolve_coordinator", lambda c: "coord:8000")
    monkeypatch.setattr(core.match_client, "get_match", lambda *a, **k: _match(satisfiable=False))

    def boom(*a, **k):
        raise AssertionError("must not reserve when unsatisfiable")

    monkeypatch.setattr(core.reservation, "reserve_and_acquire", boom)
    with pytest.raises(NoMatchingBoard):
        with core.request(part="ad9361"):
            pass


def test_request_flash_mode_not_supported(patched):
    with pytest.raises(NotImplementedError):
        with core.request(part="ad9361", mode="flash"):
            pass


def test_request_provision_error_still_releases(patched, monkeypatch):
    def bad_boot(*a, **k):
        raise ProvisionError("boot failed")

    monkeypatch.setattr(core, "_boot", bad_boot)
    with pytest.raises(ProvisionError):
        with core.request(part="ad9361"):
            pass
    assert patched["released"] == "mini2"


def test_request_unavailable_propagates(patched, monkeypatch):
    def busy(*a, **k):
        raise BoardUnavailable("all busy")

    monkeypatch.setattr(core.reservation, "reserve_and_acquire", busy)
    with pytest.raises(BoardUnavailable):
        with core.request(part="ad9361"):
            pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_request_core.py -v`
Expected: FAIL (the Task 6 stub `request` raises `NotImplementedError` / has no context-manager behavior)

- [ ] **Step 3: Replace core.py with the full implementation**

```python
# adi_lg_plugins/request/core.py
"""Client-side orchestration for the hardware-request layer (uri mode).

Flow: resolve coordinator -> GET /match -> reserve+acquire (labgrid) ->
fetch concrete place -> render env -> boot -> resolve URI -> yield Lease ->
release on exit (always).
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
    place: str
    carrier: str
    tags: dict[str, str] = field(default_factory=dict)
    uri: str | None = None
    matlab_board: str | None = None
    console: Any = None  # Phase 3 (flash mode); always None in Phase 1
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


def _boot(env_path: str, strategy_name: str, *, version: str | None, target_name: str = "main"):
    """Boot the board to a Linux shell and return the labgrid target."""
    from labgrid import Environment

    env = Environment(env_path)
    tg = env.get_target(target_name)
    if version:
        try:
            res = tg.get_resource("KuiperRelease")
            res.release_version = version
            logger.info("Using image version %s", version)
        except Exception:  # noqa: BLE001 - resource may be absent for some boards
            logger.warning("no KuiperRelease resource to pin version %s", version)
    strategy = tg.get_driver(strategy_name)
    try:
        strategy.transition("shell")
    except Exception as e:  # noqa: BLE001 - normalise any strategy error
        raise ProvisionError(f"boot failed: {e}") from e
    return tg


@contextmanager
def request(
    *,
    part: str,
    carrier: str | None = None,
    mode: str = "uri",
    bootfile: str | None = None,
    wait: float = 1800.0,
    coord: str | None = None,
    target_name: str = "main",
    **filters: str,
):
    """Request a board, boot it, yield a Lease, and release on exit.

    Phase 1 supports ``mode='uri'`` only.
    """
    if mode != "uri":
        raise NotImplementedError(f"mode '{mode}' is not available in Phase 1 (uri only)")

    coord = resolve_coordinator(coord)
    match = match_client.get_match(coord, part=part, carrier=carrier, mode=mode, bootfile=bootfile)
    if not match.satisfiable:
        raise NoMatchingBoard(match.reason or f"no board for part '{part}'")

    res = reservation.reserve_and_acquire(coord, match.reservation_filter, wait=wait)
    try:
        place = _concrete_place(coord, res.place)
        env_path = _render_env(place)
        target = _boot(env_path, place.boot_strategy, version=match.version, target_name=target_name)
        uri = resolve_uri(target)
        lease = Lease(
            place=res.place,
            carrier=place.carrier,
            tags={"daughter-board": place.daughter_board, "carrier": place.carrier},
            uri=uri,
            matlab_board=match.matlab_boards.get(place.carrier),
            target=target,
        )
        yield lease
    finally:
        reservation.release(coord, res)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_request_core.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Run the full request-layer unit suite**

Run: `python -m pytest tests/test_request_*.py -v`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add adi_lg_plugins/request/core.py tests/test_request_core.py
git commit -m "feat(request): implement request() orchestration and Lease (uri mode)"
```

---

## Task 11: `adi-lg request` CLI command

**Files:**
- Modify: `adi_lg_plugins/tools/cli.py`
- Test: `tests/test_request_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_request_cli.py
from contextlib import contextmanager
from unittest.mock import MagicMock

from click.testing import CliRunner

from adi_lg_plugins.request.errors import EXIT_NO_MATCH, NoMatchingBoard
from adi_lg_plugins.tools import cli as cli_mod
from adi_lg_plugins.tools.cli import cli


def _runner():
    return CliRunner()


def test_request_help():
    result = _runner().invoke(cli, ["request", "--help"])
    assert result.exit_code == 0
    assert "--part" in result.output


def test_request_flash_mode_rejected():
    result = _runner().invoke(cli, ["request", "--part", "ad9361", "--mode", "flash"])
    assert result.exit_code != 0
    assert "flash" in result.output.lower()


def test_request_runs_command_with_uri(monkeypatch):
    lease = MagicMock(uri="ip:10.0.0.57", place="mini2")

    @contextmanager
    def fake_request(**kwargs):
        yield lease

    captured = {}

    def fake_call(cmd, shell, env):
        captured["cmd"] = cmd
        captured["uri"] = env.get("IIO_URI")
        captured["place"] = env.get("LG_PLACE")
        return 0

    monkeypatch.setattr(cli_mod, "request", fake_request)
    monkeypatch.setattr(cli_mod.subprocess, "call", fake_call)

    result = _runner().invoke(cli, ["request", "--part", "ad9361", "--run", "echo hi"])
    assert result.exit_code == 0
    assert captured["cmd"] == "echo hi"
    assert captured["uri"] == "ip:10.0.0.57"
    assert captured["place"] == "mini2"


def test_request_no_match_exit_code(monkeypatch):
    @contextmanager
    def fake_request(**kwargs):
        raise NoMatchingBoard("no such board")
        yield  # pragma: no cover

    monkeypatch.setattr(cli_mod, "request", fake_request)
    result = _runner().invoke(cli, ["request", "--part", "nope", "--run", "true"])
    assert result.exit_code == EXIT_NO_MATCH


def test_request_propagates_command_exit_code(monkeypatch):
    lease = MagicMock(uri="ip:10.0.0.57", place="mini2")

    @contextmanager
    def fake_request(**kwargs):
        yield lease

    monkeypatch.setattr(cli_mod, "request", fake_request)
    monkeypatch.setattr(cli_mod.subprocess, "call", lambda cmd, shell, env: 3)
    result = _runner().invoke(cli, ["request", "--part", "ad9361", "--run", "false"])
    assert result.exit_code == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_request_cli.py -v`
Expected: FAIL (no `request` subcommand; `--help` lists no `--part`)

- [ ] **Step 3: Add imports + the command to cli.py**

At the top of `adi_lg_plugins/tools/cli.py`, add (next to the existing imports):

```python
import subprocess
import sys

from adi_lg_plugins.request import (
    BoardUnavailable,
    NoMatchingBoard,
    ProvisionError,
    request,
)
from adi_lg_plugins.request.errors import (
    EXIT_NO_MATCH,
    EXIT_PROVISION,
    EXIT_UNAVAILABLE,
)
```

Then add this command (anywhere after the `cli` group is defined):

```python
@cli.command(name="request")
@click.option("--part", required=True, help="Part / daughter-board, e.g. ad9361")
@click.option("--carrier", default=None, help="Optional carrier filter, e.g. zcu102")
@click.option(
    "--mode",
    type=click.Choice(["uri", "flash"]),
    default="uri",
    help="uri: boot Linux and export IIO_URI (default). flash: Phase 3 (not yet available).",
)
@click.option("--bootfile", default=None, help="Pin an image version (default: latest stable)")
@click.option("--wait", default=1800, type=int, help="Seconds to wait for a free board (0=fail fast)")
@click.option("--coord", default=None, help="Coordinator host:port (default: $LG_COORDINATOR)")
@click.option("--run", "run_cmd", default=None, help="Command to run with IIO_URI/LG_PLACE exported")
def request_cmd(part, carrier, mode, bootfile, wait, coord, run_cmd):
    """Request a board by part, boot it, run a command against it, and release it."""
    if mode == "flash":
        raise click.ClickException("flash mode is not available in Phase 1 (uri mode only)")

    try:
        with request(
            part=part, carrier=carrier, mode=mode, bootfile=bootfile, wait=wait, coord=coord
        ) as board:
            if not run_cmd:
                console.print(board.uri or board.place)
                return
            env = os.environ.copy()
            if board.uri:
                env["IIO_URI"] = board.uri
            env["LG_PLACE"] = board.place
            console.print(f"[green]Booted {board.place} -> {board.uri}[/green]")
            rc = subprocess.call(run_cmd, shell=True, env=env)
            sys.exit(rc)
    except NoMatchingBoard as e:
        console.print(f"[bold red]No matching board: {e}[/bold red]")
        sys.exit(EXIT_NO_MATCH)
    except BoardUnavailable as e:
        console.print(f"[bold red]Board unavailable: {e}[/bold red]")
        sys.exit(EXIT_UNAVAILABLE)
    except ProvisionError as e:
        console.print(f"[bold red]Provisioning failed: {e}[/bold red]")
        if getattr(e, "console_tail", ""):
            console.print(e.console_tail)
        sys.exit(EXIT_PROVISION)
```

Note: `os` and `console` are already imported/defined in `cli.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_request_cli.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Run the whole main-package suite + lint**

Run: `python -m pytest tests/ -q && ruff check adi_lg_plugins tests && ruff format --check adi_lg_plugins tests`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add adi_lg_plugins/tools/cli.py tests/test_request_cli.py
git commit -m "feat(cli): add 'adi-lg request' command (uri mode)"
```

---

## Task 12: Hardware end-to-end smoke test (gated)

**Files:**
- Create: `tests/test_request_hw.py`
- Modify: `tests/conftest.py` (add the new module to `collect_ignore_glob`)

This is the real validation of the design against one board. It is gated behind `--run-hardware` and excluded from default collection (it needs a live coordinator + board).

- [ ] **Step 1: Add the module to the collection-exclusion list in conftest.py**

In `tests/conftest.py`, add `"test_request_hw.py"` to the existing `collect_ignore_glob` list.

- [ ] **Step 2: Write the hardware smoke test**

```python
# tests/test_request_hw.py
"""End-to-end hardware smoke test for the request layer (uri mode).

Requires a live coordinator (LG_COORDINATOR or --coord via env) with at least
one free board whose daughter-board tag matches REQUEST_PART. Run with:

    pytest tests/test_request_hw.py --run-hardware -v

Set ADI_LG_TEST_PART to override the part (default: ad9361).
"""

import os

import pytest

from adi_lg_plugins.request import request

REQUEST_PART = os.environ.get("ADI_LG_TEST_PART", "ad9361")


@pytest.mark.hardware
def test_request_boots_board_and_returns_uri():
    with request(part=REQUEST_PART, wait=1800) as board:
        assert board.uri and board.uri.startswith("ip:")
        assert board.place
        # libiio is an optional runtime dep; only assert a live context if present.
        try:
            import iio
        except ImportError:
            pytest.skip("libiio not installed; URI returned but not exercised")
        ctx = iio.Context(board.uri)
        assert ctx.devices, "no IIO devices found on booted board"
```

- [ ] **Step 3: Verify it is excluded from the default run**

Run: `python -m pytest tests/ -q`
Expected: PASS; `test_request_hw.py` is NOT collected (no errors from missing hardware/coordinator).

- [ ] **Step 4: (Lab only) Run against real hardware and confirm reservation parsing**

Run (on a host with `labgrid-client`, `LG_COORDINATOR` set, and a free board):
```bash
export LG_COORDINATOR=<coord-host:port>
pytest tests/test_request_hw.py --run-hardware -v
```
Expected: PASS — board reserved, booted, URI returned, released afterward.
If reservation discovery fails, confirm the real `labgrid-client reservations` format and fix `reservation._parse_allocated_place` + `tests/test_request_reservation.py` together (see Task 8 note).

- [ ] **Step 5: Commit**

```bash
git add tests/test_request_hw.py tests/conftest.py
git commit -m "test(request): add gated hardware end-to-end smoke test (uri mode)"
```

---

## Task 13: Final verification + docs pointer

**Files:**
- Modify: `adi_lg_plugins/request/__init__.py` (docstring only)
- (Optional) docs note if the repo has a user-guide index for the CLI.

- [ ] **Step 1: Add a module docstring to request/__init__.py**

Prepend to `adi_lg_plugins/request/__init__.py`:

```python
"""Low-config hardware request layer (Phase 1: uri mode).

Public API:
    from adi_lg_plugins.request import request
    with request(part="ad9361") as board:
        sdr = adi.ad9361(uri=board.uri)

See docs/superpowers/specs/2026-06-02-low-config-hardware-request-design.md.
"""
```

- [ ] **Step 2: Run the complete suites + lint for both packages**

Run:
```bash
python -m pytest tests/ -q
ruff check adi_lg_plugins tests && ruff format --check adi_lg_plugins tests
cd coordinator/api && python -m pytest -q && ruff check app && ruff format --check app && cd ../..
```
Expected: all green.

- [ ] **Step 3: Commit**

```bash
git add adi_lg_plugins/request/__init__.py
git commit -m "docs(request): document Phase 1 public API"
```

- [ ] **Step 4: Confirm the branch is ready**

Run: `git log --oneline design/low-config-hardware-request..feat/hw-request-phase1`
Expected: the full list of Phase 1 commits, ready for review / PR.

---

## Phase 1 Done — Definition of Done

- `GET /api/catalog` and `GET /api/match` serve from `board_catalog.yaml`; unit + router tests green.
- `adi-lg request --part <p> --run '<cmd>'` reserves a free matching board, boots it (uri mode), exports `IIO_URI`/`LG_PLACE`, runs the command, propagates its exit code, and always releases the board.
- Infra failures map to distinct exit codes (`10` no-match, `11` unavailable, `12` provision).
- `Lease` carries `uri`, `place`, `carrier`, `tags`, `matlab_board`; `console` is `None` (Phase 3).
- Full request lifecycle (incl. release-on-error) covered by tests without hardware; one gated hardware smoke test validates a real board.
- `--mode flash` is cleanly rejected (Phase 3).

**Deferred to later phases (not in this plan):** pytest plugin + GHA template (Phase 2), `flash` mode / `FlashStrategy` / no-os (Phase 3), wiring `matlab_board` into `adi-lg-matlab` to retire `board_map.yaml` (Phase 2).
