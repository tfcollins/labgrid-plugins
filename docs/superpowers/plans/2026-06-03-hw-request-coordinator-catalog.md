# Hardware Request — Coordinator Catalog + `/match` + `/catalog` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a coordinator-side board catalog and two read-only endpoints (`GET /api/catalog`, `GET /api/match`) so a client can resolve "part + optional carrier + optional bootfile" into a reservation filter, a resolved image version, and a boot strategy — without the client knowing any board map.

**Architecture:** A YAML data file (`board_catalog.yaml`) is loaded at startup into `app.state.catalog`. A pure function `match_places(catalog, places, part, carrier, bootfile)` computes a `MatchResult` from the catalog plus the coordinator's live places. A thin FastAPI router exposes the catalog and the match result. No acquisition happens here — selection/queuing stays with labgrid's reservation system; this layer only answers "is this satisfiable, and how is it provisioned."

**Tech Stack:** Python 3.10+, FastAPI, Pydantic v2, PyYAML (already a transitive dep via labgrid), pytest + Starlette `TestClient`. Tooling: ruff (line length 100, double quotes). This plan lives entirely in `coordinator/api/` — run all commands from there.

This is **Plan 1 of the first-cut increment** described in `docs/superpowers/specs/2026-06-03-low-config-hardware-request-fresh-design.md`. Plans 2–5 (request core, CLI, pytest fixture, GitHub Actions) follow once this lands and are written separately.

---

## Conventions

- **Working directory:** all `pytest`/`ruff` commands run from `coordinator/api/`.
- **Test runner:** `python3 -m pytest <path> -v`.
- **Lint:** `ruff check . && ruff format --check .` (run before each commit; `ruff format .` to fix).
- **Place-tag contract** (already used by `env_gen.resolve_strategy` and the hw-ci v2 schema): a place that can serve a board carries tags `daughter-board=<part>`, `carrier=<carrier>`, and optionally `boot-strategy=<StrategyClassName>`. This plan reads those tags; it does not change how they are set.

## File Structure

- Create: `coordinator/api/board_catalog.yaml` — the catalog data file (one board: `adrv9002`).
- Create: `coordinator/api/app/catalog.py` — catalog Pydantic models + `load_catalog()` + `resolve_image()`.
- Create: `coordinator/api/app/matching.py` — pure `match_places()` + `MatchResult` model.
- Create: `coordinator/api/app/routers/catalog.py` — `GET /catalog`, `GET /match`.
- Modify: `coordinator/api/app/config.py` — add `board_catalog_path` setting.
- Modify: `coordinator/api/app/main.py` — load catalog at startup, include the router.
- Create: `coordinator/api/tests/test_catalog.py` — loader/resolve unit tests.
- Create: `coordinator/api/tests/test_matching.py` — pure match-logic unit tests.
- Create: `coordinator/api/tests/test_catalog_router.py` — endpoint tests.

Each file has one responsibility: `catalog.py` = data shape + loading; `matching.py` = the decision logic (pure, no FastAPI/IO); `routers/catalog.py` = HTTP wiring only.

---

### Task 1: Catalog models, loader, and data file

**Files:**
- Create: `coordinator/api/app/catalog.py`
- Create: `coordinator/api/board_catalog.yaml`
- Modify: `coordinator/api/app/config.py`
- Test: `coordinator/api/tests/test_catalog.py`

- [ ] **Step 1: Write the failing test**

Create `coordinator/api/tests/test_catalog.py`:

```python
from pathlib import Path

import pytest

from app.catalog import BoardCatalog, load_catalog, resolve_image

FIXTURE = """\
boards:
  adrv9002:
    image: kuiper-2023_R2
    carriers:
      zcu102: {}
"""


def _write(tmp_path: Path, text: str) -> str:
    p = tmp_path / "board_catalog.yaml"
    p.write_text(text)
    return str(p)


def test_load_catalog_parses_board(tmp_path):
    cat = load_catalog(_write(tmp_path, FIXTURE))
    assert isinstance(cat, BoardCatalog)
    assert "adrv9002" in cat.boards
    entry = cat.boards["adrv9002"]
    assert entry.image == "kuiper-2023_R2"
    assert "zcu102" in entry.carriers


def test_load_catalog_missing_file_returns_empty(tmp_path):
    cat = load_catalog(str(tmp_path / "does_not_exist.yaml"))
    assert cat.boards == {}


def test_load_catalog_ignores_unknown_carrier_fields(tmp_path):
    # Extensibility: future per-carrier metadata must not break parsing.
    text = FIXTURE + "        matlab_board: some-future-name\n"
    cat = load_catalog(_write(tmp_path, text))
    assert "zcu102" in cat.boards["adrv9002"].carriers


def test_resolve_image_defaults_to_catalog(tmp_path):
    cat = load_catalog(_write(tmp_path, FIXTURE))
    entry = cat.boards["adrv9002"]
    assert resolve_image(entry, None) == "kuiper-2023_R2"


def test_resolve_image_honors_pin(tmp_path):
    cat = load_catalog(_write(tmp_path, FIXTURE))
    entry = cat.boards["adrv9002"]
    assert resolve_image(entry, "2023_R2_P1") == "2023_R2_P1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_catalog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.catalog'`.

- [ ] **Step 3: Write minimal implementation**

Create `coordinator/api/app/catalog.py`:

```python
"""Board catalog: part -> default image + valid carriers.

The catalog enriches place tags; it never duplicates them. Places remain
the source of truth for what hardware exists and is free. The catalog adds
how to provision/identify a board (default image now; per-surface metadata
like a MATLAB board name or flash method later).
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class BoardCarrier(BaseModel):
    """Per-carrier catalog entry. Empty today; extensible.

    `extra="allow"` lets future per-surface fields (e.g. a MATLAB board
    name, a flash method) be added to the data file without breaking
    older parsers.
    """

    model_config = {"extra": "allow"}


class BoardEntry(BaseModel):
    image: str
    carriers: dict[str, BoardCarrier] = {}


class BoardCatalog(BaseModel):
    boards: dict[str, BoardEntry] = {}


def load_catalog(path: str) -> BoardCatalog:
    """Load and validate the catalog. A missing file yields an empty
    catalog (and a warning) rather than crashing startup."""
    p = Path(path)
    if not p.exists():
        logger.warning("board catalog not found at %s; serving empty catalog", path)
        return BoardCatalog()
    data = yaml.safe_load(p.read_text()) or {}
    return BoardCatalog.model_validate(data)


def resolve_image(entry: BoardEntry, bootfile: str | None) -> str:
    """A pinned bootfile wins; otherwise the board's default image."""
    return bootfile or entry.image
```

Create `coordinator/api/board_catalog.yaml`:

```yaml
# Board catalog served by GET /api/catalog and consumed by GET /api/match.
# Keyed by part (daughter-board / chip). `image` is the default boot image
# when a request omits --bootfile. `carriers` lists the FPGA carriers a part
# is valid on; per-carrier maps are intentionally empty for now and are
# extended with per-surface metadata when those surfaces are built.
boards:
  adrv9002:
    image: kuiper-2023_R2
    carriers:
      zcu102: {}
```

Modify `coordinator/api/app/config.py` — add the setting inside the `Settings` class, after the `database_path` line:

```python
    database_path: str = "/data/coordinator_history.db"
    board_catalog_path: str = "/data/board_catalog.yaml"
```

(The container mounts `board_catalog.yaml` to `/data/`; tests pass an explicit path. The `LG_` env prefix already in `Settings.model_config` means `LG_BOARD_CATALOG_PATH` overrides it.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_catalog.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Lint and commit**

```bash
cd coordinator/api
ruff check app/catalog.py app/config.py tests/test_catalog.py && ruff format app/catalog.py app/config.py tests/test_catalog.py
git add app/catalog.py app/config.py board_catalog.yaml tests/test_catalog.py
git commit -m "feat(catalog): board catalog model, loader, and adrv9002 data file"
```

---

### Task 2: Pure `match_places` logic

**Files:**
- Create: `coordinator/api/app/matching.py`
- Test: `coordinator/api/tests/test_matching.py`

This is the decision core: given the catalog and the coordinator's live places, decide whether a request is satisfiable and what to provision with. It is a pure function over its arguments (no FastAPI, no IO) so it is unit-tested without a process boundary.

- [ ] **Step 1: Write the failing test**

Create `coordinator/api/tests/test_matching.py`:

```python
from app.catalog import BoardCatalog
from app.matching import MatchResult, match_places
from app.models import PlaceModel

CATALOG = BoardCatalog.model_validate(
    {
        "boards": {
            "adrv9002": {
                "image": "kuiper-2023_R2",
                "carriers": {"zcu102": {}},
            }
        }
    }
)


def _place(name, *, part=None, carrier=None, strategy=None, acquired=None):
    tags = {}
    if part:
        tags["daughter-board"] = part
    if carrier:
        tags["carrier"] = carrier
    if strategy:
        tags["boot-strategy"] = strategy
    return PlaceModel(name=name, tags=tags, acquired=acquired)


def test_unknown_part_is_unsatisfiable():
    res = match_places(CATALOG, [], part="nosuchpart")
    assert isinstance(res, MatchResult)
    assert res.satisfiable is False
    assert "unknown part" in res.reason


def test_unknown_carrier_is_unsatisfiable():
    res = match_places(CATALOG, [], part="adrv9002", carrier="vcu118")
    assert res.satisfiable is False
    assert "carrier" in res.reason


def test_no_live_place_is_unsatisfiable():
    # Catalog knows the board, but no place is tagged for it.
    res = match_places(CATALOG, [_place("other", part="ad9081")], part="adrv9002")
    assert res.satisfiable is False
    assert "no live place" in res.reason


def test_match_returns_filter_image_and_strategy():
    places = [_place("p1", part="adrv9002", carrier="zcu102", strategy="BootFPGASoC")]
    res = match_places(CATALOG, places, part="adrv9002", carrier="zcu102")
    assert res.satisfiable is True
    assert res.reservation_filter == {"daughter-board": "adrv9002", "carrier": "zcu102"}
    assert res.image == "kuiper-2023_R2"
    assert res.strategy == "BootFPGASoC"
    assert res.place == "p1"


def test_match_without_carrier_omits_carrier_from_filter():
    places = [_place("p1", part="adrv9002", carrier="zcu102", strategy="BootFPGASoC")]
    res = match_places(CATALOG, places, part="adrv9002")
    assert res.satisfiable is True
    assert res.reservation_filter == {"daughter-board": "adrv9002"}


def test_match_prefers_a_free_place_for_place_field():
    places = [
        _place("busy", part="adrv9002", carrier="zcu102", strategy="BootFPGASoC", acquired="bob"),
        _place("free", part="adrv9002", carrier="zcu102", strategy="BootFPGASoC"),
    ]
    res = match_places(CATALOG, places, part="adrv9002", carrier="zcu102")
    assert res.satisfiable is True
    # All-busy is still satisfiable (reservation queues); when a free one
    # exists we surface it as the informational candidate.
    assert res.place == "free"


def test_bootfile_pin_flows_into_image():
    places = [_place("p1", part="adrv9002", carrier="zcu102", strategy="BootFPGASoC")]
    res = match_places(CATALOG, places, part="adrv9002", carrier="zcu102", bootfile="2023_R2_P1")
    assert res.image == "2023_R2_P1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_matching.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.matching'`.

- [ ] **Step 3: Write minimal implementation**

Create `coordinator/api/app/matching.py`:

```python
"""Pure request-matching logic for GET /api/match.

`match_places` is a pure function of (catalog, live places, request) so it
is unit-tested without FastAPI or a coordinator connection. It never
acquires or reserves — it only decides satisfiability and returns how to
provision: the reservation tag-filter, the resolved image, and the boot
strategy. Contention (all matching boards busy) is NOT unsatisfiable here;
that is left to labgrid's reservation queue on the client side.
"""

from __future__ import annotations

from pydantic import BaseModel

from .catalog import BoardCatalog, resolve_image
from .env_gen import resolve_strategy
from .models import PlaceModel


class MatchResult(BaseModel):
    satisfiable: bool
    reservation_filter: dict[str, str] = {}
    image: str | None = None
    strategy: str | None = None
    place: str | None = None  # informational candidate (a free one if any)
    reason: str | None = None


def _candidates(places: list[PlaceModel], part: str, carrier: str | None) -> list[PlaceModel]:
    out = []
    for p in places:
        if p.tags.get("daughter-board") != part:
            continue
        if carrier is not None and p.tags.get("carrier") != carrier:
            continue
        out.append(p)
    return out


def match_places(
    catalog: BoardCatalog,
    places: list[PlaceModel],
    part: str,
    carrier: str | None = None,
    bootfile: str | None = None,
) -> MatchResult:
    entry = catalog.boards.get(part)
    if entry is None:
        return MatchResult(satisfiable=False, reason=f"unknown part: {part!r}")

    if carrier is not None and carrier not in entry.carriers:
        return MatchResult(
            satisfiable=False,
            reason=f"carrier {carrier!r} not valid for part {part!r}",
        )

    candidates = _candidates(places, part, carrier)
    if not candidates:
        where = f"{part!r}" + (f" on {carrier!r}" if carrier else "")
        return MatchResult(satisfiable=False, reason=f"no live place for {where}")

    reservation_filter = {"daughter-board": part}
    if carrier is not None:
        reservation_filter["carrier"] = carrier

    # Prefer a free candidate as the informational place; fall back to the
    # first candidate when all are busy (the request is still satisfiable —
    # the client's reservation will queue).
    chosen = next((p for p in candidates if p.acquired is None), candidates[0])
    # Strategy comes from the place's boot-strategy tag (reusing env_gen's
    # validated resolver; inference needs resource classes we don't have here,
    # so pass an empty set and rely on the tag).
    strategy = resolve_strategy(chosen.tags, set())

    return MatchResult(
        satisfiable=True,
        reservation_filter=reservation_filter,
        image=resolve_image(entry, bootfile),
        strategy=strategy,
        place=chosen.name,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_matching.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Lint and commit**

```bash
cd coordinator/api
ruff check app/matching.py tests/test_matching.py && ruff format app/matching.py tests/test_matching.py
git add app/matching.py tests/test_matching.py
git commit -m "feat(catalog): pure match_places logic"
```

---

### Task 3: `/catalog` + `/match` router and startup wiring

**Files:**
- Create: `coordinator/api/app/routers/catalog.py`
- Modify: `coordinator/api/app/main.py`
- Test: `coordinator/api/tests/test_catalog_router.py`

- [ ] **Step 1: Write the failing test**

Create `coordinator/api/tests/test_catalog_router.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.catalog import BoardCatalog
from app.main import app
from app.models import PlaceModel

from .conftest import MockCoordinatorClient

CATALOG = BoardCatalog.model_validate(
    {
        "boards": {
            "adrv9002": {
                "image": "kuiper-2023_R2",
                "carriers": {"zcu102": {}},
            }
        }
    }
)


@pytest.fixture
def catalog_client():
    """TestClient with a mock coordinator and a loaded catalog on app.state."""
    coord = MockCoordinatorClient()
    coord._places["adrv9002-zcu102"] = PlaceModel(
        name="adrv9002-zcu102",
        tags={
            "daughter-board": "adrv9002",
            "carrier": "zcu102",
            "boot-strategy": "BootFPGASoC",
        },
    )
    app.state.coordinator = coord
    app.state.catalog = CATALOG
    return TestClient(app)


def test_get_catalog_returns_boards(catalog_client):
    resp = catalog_client.get("/api/catalog")
    assert resp.status_code == 200
    data = resp.json()
    assert data["boards"]["adrv9002"]["image"] == "kuiper-2023_R2"
    assert "zcu102" in data["boards"]["adrv9002"]["carriers"]


def test_match_satisfiable(catalog_client):
    resp = catalog_client.get("/api/match", params={"part": "adrv9002", "carrier": "zcu102"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["satisfiable"] is True
    assert data["reservation_filter"] == {"daughter-board": "adrv9002", "carrier": "zcu102"}
    assert data["image"] == "kuiper-2023_R2"
    assert data["strategy"] == "BootFPGASoC"
    assert data["place"] == "adrv9002-zcu102"


def test_match_unknown_part_is_satisfiable_false(catalog_client):
    resp = catalog_client.get("/api/match", params={"part": "nosuchpart"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["satisfiable"] is False
    assert "unknown part" in data["reason"]


def test_match_requires_part(catalog_client):
    resp = catalog_client.get("/api/match")
    assert resp.status_code == 422  # FastAPI: missing required query param
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_catalog_router.py -v`
Expected: FAIL — `404` on `/api/catalog` (router not registered) / `ImportError` for `app.routers.catalog`.

- [ ] **Step 3: Write minimal implementation**

Create `coordinator/api/app/routers/catalog.py`:

```python
from fastapi import APIRouter, Query, Request

from ..catalog import BoardCatalog
from ..matching import MatchResult, match_places

router = APIRouter(tags=["catalog"])


def _catalog(request: Request) -> BoardCatalog:
    # Set at startup in main.lifespan; default-empty if loading failed.
    return getattr(request.app.state, "catalog", BoardCatalog())


def _client(request: Request):
    return request.app.state.coordinator


@router.get("/catalog", response_model=BoardCatalog)
async def get_catalog(request: Request) -> BoardCatalog:
    return _catalog(request)


@router.get("/match", response_model=MatchResult)
async def get_match(
    request: Request,
    part: str = Query(..., description="Part / daughter-board, e.g. adrv9002"),
    carrier: str | None = Query(None, description="Optional FPGA carrier, e.g. zcu102"),
    bootfile: str | None = Query(None, description="Optional image/version pin"),
) -> MatchResult:
    places = _client(request).get_places()
    return match_places(_catalog(request), places, part=part, carrier=carrier, bootfile=bootfile)
```

Modify `coordinator/api/app/main.py`:

(a) Add `catalog` to the routers import block. The existing block (around line 12) is `from .routers import (` — add `catalog,` to that tuple, keeping alphabetical/existing order:

```python
from .routers import (
    auth,
    catalog,
    console,
    health,
    history,
    places,
    power,
    recordings,
    reservations,
    resources,
    sdmux,
    users,
)
```

(b) Load the catalog in `lifespan`. Inside the `async def lifespan(app: FastAPI):` body, alongside the other `app.state.*` setup, add:

```python
    from .catalog import load_catalog

    app.state.catalog = load_catalog(settings.board_catalog_path)
```

(c) Register the router next to the other `include_router` calls (after the `health` line is fine):

```python
app.include_router(catalog.router, prefix="/api")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_catalog_router.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Run the full suite to check for regressions**

Run: `python3 -m pytest -q`
Expected: all previously-passing tests still pass, plus the new files.

- [ ] **Step 6: Lint and commit**

```bash
cd coordinator/api
ruff check app/routers/catalog.py app/main.py tests/test_catalog_router.py && \
  ruff format app/routers/catalog.py app/main.py tests/test_catalog_router.py
git add app/routers/catalog.py app/main.py tests/test_catalog_router.py
git commit -m "feat(catalog): add GET /api/catalog and GET /api/match endpoints"
```

---

## Self-Review (completed during plan authoring)

**Spec coverage** — this plan covers exactly the "Coordinator Catalog & Matching" section of the spec:
- `board_catalog.yaml` served by the coordinator ✓ (Task 1 + Task 3 `/catalog`).
- First-cut schema `boards: { adrv9002: { image, carriers: { zcu102: {} } } }` ✓ (Task 1 data file matches the spec verbatim).
- Catalog is extensible (per-surface metadata later) ✓ (`BoardCarrier` `extra="allow"`, tested).
- `GET /match` returns reservation filter + resolved image + strategy + metadata, and does NOT acquire ✓ (Task 2 logic, Task 3 endpoint).
- Contention is not handled here (left to reservations) ✓ (all-busy is still `satisfiable=True`, tested in `test_match_prefers_a_free_place_for_place_field`).
- "No matching board" surfaced for the client to raise `NoMatchingBoard` ✓ (`satisfiable=False` + `reason`).

Deliberately **out of scope** for this plan (later plans): the client `request()` core, the CLI, the pytest fixture, the GitHub Actions workflow. Those consume these endpoints.

**Placeholder scan** — no TBD/TODO/"handle edge cases"; every step has full code and exact commands.

**Type consistency** — `MatchResult` fields (`satisfiable`, `reservation_filter`, `image`, `strategy`, `place`, `reason`) are identical across `matching.py`, `test_matching.py`, the router, and `test_catalog_router.py`. `load_catalog`/`resolve_image`/`match_places` signatures match every call site. `resolve_strategy(place.tags, set())` matches the existing `env_gen.resolve_strategy(place_tags, resource_classes)` signature confirmed in the codebase.

## Open Questions (deferred to later plans, per spec)

- Concrete CLI exit-code numbers — belong to the CLI plan (Plan 3), not here.
- Exact URI-resolution mechanism — belongs to the request-core plan (Plan 2).
- Whether `/match` should ever return `409`/`404` instead of `200 + satisfiable:false` — current choice (always `200`, body carries `satisfiable`) keeps the client's parsing uniform; revisit only if a consumer needs HTTP-status-based branching.
