# Hardware Request — pytest `adi_board` Fixture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a session-scoped `adi_board` pytest fixture (plus an `adi_uri` convenience fixture) so any project that installs `adi-labgrid-plugins` can write `def test_rx(adi_board): adi.adrv9002(uri=adi_board.uri)`. The fixture is **dual-mode**: in CI it reuses an already-booted board's URI (handed in via `IIO_URI`/`--adi-uri`); locally it self-requests a board by part via the Plan-2 core and releases it at session end; with neither configured it skips cleanly.

**Architecture:** The dual-mode decision lives in a pytest-independent resolver `provision_or_reuse()` in `adi_lg_plugins/request/provision.py` (reuse → yield a `Lease` carrying the URI, release nothing; self-request → enter the Plan-2 `request()` context, release on exit; neither → raise `NoBoardSource`). The existing `adi_lg_plugins.pytest_plugin` (which already owns the `iio_hardware`/`iio_carrier` markers) is extended with three options and the two fixtures; a pure `_board_sources()` helper resolves option→env precedence. Keeping the logic in plain functions makes the whole surface unit-testable **without `pytester`**.

**Tech Stack:** Python 3.10+, pytest plugin API, the Plan-2 `adi_lg_plugins.request` package. ruff line length 100, double quotes, `from __future__ import annotations`. Run `pytest`/`ruff` from repo root `/home/tcollins/dev/lg-test/labgrid-plugins`.

This is **Plan 4 of 5** of the first-cut increment (`docs/superpowers/specs/2026-06-03-low-config-hardware-request-fresh-design.md`). It depends on **Plan 2** (`request`, `Lease`, `RequestError`/`NoMatchingBoard`/`BoardUnavailable`/`ProvisionError`), on PR #50.

---

## Grounding & reuse

The original track designed this exact surface (`docs/superpowers/specs/2026-06-02-hw-request-phase2a-pytest-fixture-design.md`) but never implemented it. This plan implements that design against the **fresh** Plan-2 `Lease` (which has no `matlab_board` field). Key fresh adaptations:
- Reuse-path `Lease` is `Lease(place="", carrier=carrier or "", tags={}, uri=uri)` — `place=""` marks "externally provided" (the fresh `Lease.place` is typed `str`; the original design used `None`).
- Resolver lives in `request/provision.py`; the fixtures are thin wrappers in the existing `pytest_plugin`.

**The existing markers stay untouched.** `iio_hardware`/`iio_carrier` (and `pytest_collection_modifyitems`) decide *which* tests run; `adi_board` decides *what board* they run against. This plan only adds options + fixtures + the resolver.

## Test strategy (no `pytester`)

The repo's existing `pytester`-based plugin tests (`tests/hw_ci/test_markers_plugin.py`) **fail in a source checkout** because they spawn a subprocess pytest that relies on the `pytest11` *entry point*, which is only active after `pip install -e`. To avoid that fragility, Plan 4 tests **drive the fixtures directly** via each fixture's underlying function (`fixture.__pytest_wrapped__.obj`) with a fake config, and unit-test the pure `provision_or_reuse`/`_board_sources` functions. No subprocess, no entry-point dependency, runs green from a plain source checkout.

## File Structure

- Modify: `adi_lg_plugins/request/errors.py` — add `NoBoardSource(RequestError)`.
- Create: `adi_lg_plugins/request/provision.py` — `provision_or_reuse()`.
- Modify: `adi_lg_plugins/request/__init__.py` — export `provision_or_reuse`, `NoBoardSource`.
- Modify: `adi_lg_plugins/pytest_plugin/__init__.py` — add `--adi-part`/`--adi-carrier`/`--adi-uri`, `_board_sources()`, `adi_board`, `adi_uri`.
- Test: `tests/test_provision.py`, `tests/test_pytest_fixtures.py`.

## Conventions

- Commands from repo root. Test runner: `python3 -m pytest tests/<file> -v`.
- Lint: `ruff check <files> && ruff format <files>` before each commit.
- The fixtures **lazy-import** the request stack (inside the fixture body) so loading the always-on `pytest11` plugin stays light for projects that never use `adi_board`.

---

### Task 1: `NoBoardSource` + `provision_or_reuse` resolver

**Files:**
- Modify: `adi_lg_plugins/request/errors.py`
- Create: `adi_lg_plugins/request/provision.py`
- Modify: `adi_lg_plugins/request/__init__.py`
- Test: `tests/test_provision.py`

- [ ] **Step 1: Write the failing test** — create `tests/test_provision.py`:

```python
from __future__ import annotations

from contextlib import contextmanager

import pytest

from adi_lg_plugins.request import provision as provision_mod
from adi_lg_plugins.request.errors import NoBoardSource
from adi_lg_plugins.request.provision import provision_or_reuse


def test_reuse_path_yields_uri_without_self_requesting(monkeypatch):
    def boom(**kwargs):
        raise AssertionError("must not self-request when a URI is provided")

    monkeypatch.setattr(provision_mod, "request", boom)
    with provision_or_reuse("adrv9002", "zcu102", uri="ip:10.0.0.9") as lease:
        assert lease.uri == "ip:10.0.0.9"
        assert lease.place == ""  # externally provided
        assert lease.carrier == "zcu102"


def test_uri_wins_when_both_uri_and_part_given(monkeypatch):
    def boom(**kwargs):
        raise AssertionError("uri must win; no self-request")

    monkeypatch.setattr(provision_mod, "request", boom)
    with provision_or_reuse("adrv9002", uri="ip:1.2.3.4") as lease:
        assert lease.uri == "ip:1.2.3.4"


def test_request_path_enters_request_and_releases(monkeypatch):
    released = {"v": False}
    sentinel = object()

    @contextmanager
    def fake_request(**kwargs):
        fake_request.kwargs = kwargs
        try:
            yield sentinel
        finally:
            released["v"] = True

    monkeypatch.setattr(provision_mod, "request", fake_request)
    with provision_or_reuse(
        "adrv9002", "zcu102", coord="c:8000", bootfile="2023_R2_P1"
    ) as lease:
        assert lease is sentinel
        assert released["v"] is False  # not released until exit
    assert released["v"] is True
    assert fake_request.kwargs == {
        "part": "adrv9002",
        "carrier": "zcu102",
        "bootfile": "2023_R2_P1",
        "coord": "c:8000",
    }


def test_neither_source_raises_no_board_source():
    with pytest.raises(NoBoardSource):
        with provision_or_reuse(None, None):
            pass  # pragma: no cover
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_provision.py -v`
Expected: FAIL — `...request.provision` / `NoBoardSource` don't exist.

- [ ] **Step 3: Write the implementation**

(a) Append `NoBoardSource` to `adi_lg_plugins/request/errors.py` (after the `ProvisionError` class):

```python
class NoBoardSource(RequestError):
    """Neither a reusable URI nor a part was given — no board to provision.

    A library-level signal (no dedicated CLI exit code); the pytest fixture
    maps it to a clean skip.
    """
```

(b) Create `adi_lg_plugins/request/provision.py`:

```python
"""Dual-mode board provisioning shared by the pytest fixture and other surfaces.

``provision_or_reuse`` either *reuses* an externally-provided URI (CI: a board
is already booted) or *self-requests* one via the request core (local dev),
releasing it on exit. It is pytest-independent so the reuse-vs-request
branching is unit-tested without pytest.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from .core import Lease, request
from .errors import NoBoardSource


@contextmanager
def provision_or_reuse(
    part: str | None,
    carrier: str | None = None,
    *,
    uri: str | None = None,
    coord: str | None = None,
    bootfile: str | None = None,
) -> Iterator[Lease]:
    """Yield a booted board handle.

    - ``uri`` set  -> reuse it (no coordinator contact, release nothing).
    - else ``part`` -> self-request via ``request()`` and release on exit.
    - neither       -> raise :class:`NoBoardSource`.
    """
    if uri:
        # place="" marks an externally-provided board; nothing to release.
        yield Lease(place="", carrier=carrier or "", tags={}, uri=uri)
        return
    if part:
        with request(part=part, carrier=carrier, bootfile=bootfile, coord=coord) as lease:
            yield lease
        return
    raise NoBoardSource("no board configured — set IIO_URI/--adi-uri or --adi-part/ADI_PART")
```

(c) Update `adi_lg_plugins/request/__init__.py` — add the new exports. The imports become:

```python
from .core import Lease, request
from .errors import (
    BoardUnavailable,
    NoBoardSource,
    NoMatchingBoard,
    ProvisionError,
    RequestError,
)
from .provision import provision_or_reuse

__all__ = [
    "request",
    "Lease",
    "provision_or_reuse",
    "RequestError",
    "NoMatchingBoard",
    "BoardUnavailable",
    "ProvisionError",
    "NoBoardSource",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_provision.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Lint and commit**

```bash
cd /home/tcollins/dev/lg-test/labgrid-plugins
ruff check adi_lg_plugins/request/errors.py adi_lg_plugins/request/provision.py \
  adi_lg_plugins/request/__init__.py tests/test_provision.py && \
  ruff format adi_lg_plugins/request/errors.py adi_lg_plugins/request/provision.py \
  adi_lg_plugins/request/__init__.py tests/test_provision.py
git add adi_lg_plugins/request/errors.py adi_lg_plugins/request/provision.py \
  adi_lg_plugins/request/__init__.py tests/test_provision.py
git commit -m "feat(request): provision_or_reuse resolver + NoBoardSource"
```

---

### Task 2: pytest options + `adi_board`/`adi_uri` fixtures

**Files:**
- Modify: `adi_lg_plugins/pytest_plugin/__init__.py`
- Test: `tests/test_pytest_fixtures.py`

The existing `pytest_plugin/__init__.py` already defines `pytest_addoption` (with `--hw-ci-export-markers`), `pytest_configure` (markers), `_marker_args`, `pytest_collection_modifyitems`, and `pytest_collection_finish`. This task adds three options to `pytest_addoption`, a pure `_board_sources` helper, and the two fixtures — without touching the existing marker logic.

- [ ] **Step 1: Write the failing test** — create `tests/test_pytest_fixtures.py`:

```python
from __future__ import annotations

from types import SimpleNamespace

import pytest

from adi_lg_plugins.pytest_plugin import _board_sources, adi_board, adi_uri


def _raw(fixture):
    """The underlying function of a @pytest.fixture-decorated object."""
    return fixture.__pytest_wrapped__.obj


def _cfg(**opts):
    """Fake pytest config: getoption(name) returns opts.get(name)."""
    return SimpleNamespace(getoption=lambda name: opts.get(name))


# ---- _board_sources precedence (pure) ----


def test_board_sources_options_win_over_env():
    uri, part, carrier, coord = _board_sources(
        _cfg(adi_uri="ip:opt", adi_part="p_opt", adi_carrier="c_opt").getoption,
        {
            "IIO_URI": "ip:env",
            "ADI_PART": "p_env",
            "ADI_CARRIER": "c_env",
            "LG_COORDINATOR": "coord:8000",
        },
    )
    assert (uri, part, carrier, coord) == ("ip:opt", "p_opt", "c_opt", "coord:8000")


def test_board_sources_falls_back_to_env():
    uri, part, carrier, coord = _board_sources(
        _cfg().getoption,
        {"IIO_URI": "ip:env", "ADI_PART": "p_env", "ADI_CARRIER": "c_env"},
    )
    assert (uri, part, carrier) == ("ip:env", "p_env", "c_env")
    assert coord is None


def test_board_sources_coord_alt_env_name():
    _, _, _, coord = _board_sources(_cfg().getoption, {"ADI_LG_COORDINATOR": "alt:8000"})
    assert coord == "alt:8000"


# ---- adi_board / adi_uri fixture glue (driven directly, no pytester) ----


def test_adi_board_reuse_yields_lease(monkeypatch):
    monkeypatch.setenv("IIO_URI", "ip:1.2.3.4")
    monkeypatch.delenv("ADI_PART", raising=False)
    gen = _raw(adi_board)(_cfg())
    lease = next(gen)
    assert lease.uri == "ip:1.2.3.4"
    assert lease.place == ""
    with pytest.raises(StopIteration):  # teardown; reuse path releases nothing
        next(gen)


def test_adi_board_skips_when_no_source(monkeypatch):
    monkeypatch.delenv("IIO_URI", raising=False)
    monkeypatch.delenv("ADI_PART", raising=False)
    monkeypatch.delenv("ADI_CARRIER", raising=False)
    gen = _raw(adi_board)(_cfg())
    with pytest.raises(pytest.skip.Exception):
        next(gen)


def test_adi_uri_returns_board_uri():
    fake_board = SimpleNamespace(uri="ip:9.9.9.9")
    assert _raw(adi_uri)(fake_board) == "ip:9.9.9.9"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_pytest_fixtures.py -v`
Expected: FAIL — `_board_sources`/`adi_board`/`adi_uri` don't exist yet.

- [ ] **Step 3: Write the implementation** — edit `adi_lg_plugins/pytest_plugin/__init__.py`:

(a) Ensure `os` and `pytest` are imported at the top (they already are). Add the three options inside the existing `pytest_addoption(parser)` function, after the existing `--hw-ci-export-markers` block:

```python
    adi = parser.getgroup("adi-hardware")
    adi.addoption(
        "--adi-part",
        dest="adi_part",
        default=None,
        help="Part to self-request when no URI is provided (e.g. adrv9002).",
    )
    adi.addoption(
        "--adi-carrier",
        dest="adi_carrier",
        default=None,
        help="Optional carrier narrowing for a self-requested board.",
    )
    adi.addoption(
        "--adi-uri",
        dest="adi_uri",
        default=None,
        help="Use a pre-booted board at this libIIO URI (skip self-request).",
    )
```

(b) Append the helper and fixtures at the END of the file (after `pytest_collection_finish`):

```python
def _board_sources(get_option, environ):
    """Resolve ``(uri, part, carrier, coord)`` from pytest options then env.

    Pure function of its inputs (a ``get_option(name)`` callable and an
    ``os.environ``-like mapping) so the precedence is unit-tested without a
    live pytest config. Options take precedence over environment variables.
    """
    uri = get_option("adi_uri") or environ.get("IIO_URI")
    part = get_option("adi_part") or environ.get("ADI_PART")
    carrier = get_option("adi_carrier") or environ.get("ADI_CARRIER")
    coord = environ.get("LG_COORDINATOR") or environ.get("ADI_LG_COORDINATOR")
    return uri, part, carrier, coord


@pytest.fixture(scope="session")
def adi_board(pytestconfig):
    """A booted board handle (a request ``Lease``) for hardware tests.

    Dual-mode: reuse a pre-booted board if ``--adi-uri`` / ``$IIO_URI`` is set
    (release nothing), else self-request one by ``--adi-part`` / ``$ADI_PART``
    (released at session end). With neither configured the test is skipped.
    """
    from adi_lg_plugins.request.errors import NoBoardSource
    from adi_lg_plugins.request.provision import provision_or_reuse

    uri, part, carrier, coord = _board_sources(pytestconfig.getoption, os.environ)
    try:
        with provision_or_reuse(part, carrier, uri=uri, coord=coord) as lease:
            yield lease
    except NoBoardSource as e:
        pytest.skip(str(e))


@pytest.fixture(scope="session")
def adi_uri(adi_board):
    """Just the libIIO URI string — sugar for ``adi.adrv9002(uri=adi_uri)``."""
    return adi_board.uri
```

(Note: `provision_or_reuse` raises `NoBoardSource` on `__enter__` when neither source is set, so the `with` raises before yielding and the `except` converts it to a skip. The request-path errors — `NoMatchingBoard`/`BoardUnavailable`/`ProvisionError` — propagate as an errored fixture with their message, which is the intended "fail loudly" behavior.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_pytest_fixtures.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Confirm the existing marker tests/behavior are untouched**

Run: `python3 -m pytest tests/test_provision.py tests/test_pytest_fixtures.py -v`
Expected: all PASS (4 + 6). (The pre-existing `tests/hw_ci/test_markers_plugin.py` failures are unrelated — they depend on the entry-point install and fail the same way before this change; do not attempt to fix them here.)

- [ ] **Step 6: Lint and commit**

```bash
cd /home/tcollins/dev/lg-test/labgrid-plugins
ruff check adi_lg_plugins/pytest_plugin/__init__.py tests/test_pytest_fixtures.py && \
  ruff format adi_lg_plugins/pytest_plugin/__init__.py tests/test_pytest_fixtures.py
git add adi_lg_plugins/pytest_plugin/__init__.py tests/test_pytest_fixtures.py
git commit -m "feat(pytest): adi_board / adi_uri fixtures with dual-mode provisioning"
```

---

## Self-Review (completed during plan authoring)

**Spec coverage** — implements the spec's "Surface B — pytest integration (`adi_board` fixture)" and the Phase-2a design:
- Session-scoped `adi_board` yielding a booted handle; `adi_uri` sugar ✓ (Task 2).
- Dual-mode automatic: reuse provided URI (no release) vs self-request + release; skip when neither ✓ (Tasks 1 & 2).
- Ships in the existing `pytest_plugin`; existing `iio_hardware`/`iio_carrier` markers untouched ✓.
- Dual-mode logic factored into a pytest-independent, unit-tested resolver (`provision_or_reuse`) ✓ (Task 1).
- Resolution precedence (option → env) with `--adi-part`/`--adi-carrier`/`--adi-uri` and `IIO_URI`/`ADI_PART`/`ADI_CARRIER`/`LG_COORDINATOR` ✓ (`_board_sources`, Task 2).

Deliberately out of scope (later / not needed): `matlab_board` (dropped from the fresh `Lease`); a new `adi_hardware` marker (we reuse the existing markers); flash mode; changing any consumer repo's own conftest.

**Placeholder scan** — no TBD/TODO; every code/step is complete.

**Type/name consistency** — `provision_or_reuse(part, carrier=None, *, uri=None, coord=None, bootfile=None)` matches its call site in `adi_board` and the unit tests; it yields a `Lease` (Plan-2) and forwards exactly `part`/`carrier`/`bootfile`/`coord` to `request()` (verified against Plan-2's `request()` signature). `_board_sources(get_option, environ)` returns `(uri, part, carrier, coord)` consistently across the fixture and its tests. `NoBoardSource` is a `RequestError` subclass (Task 1) imported by the fixture (Task 2). Option dests (`adi_part`/`adi_carrier`/`adi_uri`) match the `_board_sources` lookups.

## Open Questions / notes for implementation

- **Both URI and part set:** the resolver checks `uri` first, so reuse wins (a pre-booted board is never double-provisioned). A debug log when both are set could be added later; not required.
- **`__pytest_wrapped__.obj`** is pytest's stable accessor for a fixture's underlying function (used to drive the fixtures in tests without `pytester`). If a future pytest renames it, fall back to `adi_board.__wrapped__`.
- **CI reuse path:** in a Plan-5 GHA leg that runs `adi-lg request --run 'pytest …'`, `IIO_URI` is already exported, so `adi_board` lands on the reuse path automatically — no double-boot.
- **Consumer adoption (pyadi-iio):** wiring `adi_board` into pyadi-iio's own `--uri`/conftest is that repo's concern, not this plan.
