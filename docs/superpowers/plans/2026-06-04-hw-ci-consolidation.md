# Hardware-CI Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Push the lab/toolchain knowledge that leaked into DUT repos (no-os's inline `build-cmd`, `NOOS_XSA_DIR`, the libtinfo shim, the buggy `.xsa` fallback) back into `labgrid-plugins` as unit-tested Python CLI subcommands, sourcing the board's `.xsa` from the Kuiper image, while removing duplication and cruft.

**Architecture:** New `adi_lg_plugins/hw_ci/kuiper_xsa.py` (fetch a board's `system_top.xsa` from the Kuiper boot FAT partition) and `adi_lg_plugins/hw_ci/build_noos.py` (compose the Vivado/shim env and orchestrate `make`) expose two new `adi-lg-hw-ci` subcommands (`fetch-xsa`, `build-noos`). The no-os manifest gains Pydantic validation plus per-project `validate_banner`/`build_vars`; the matrix carries the board + Kuiper release so the build can fetch the right `.xsa`. Duplicated helpers (`_resolve_api`, the matrix CLI tail, the banner default) get one home; `kuiperdldriver.py` cruft is removed.

**Tech Stack:** Python 3.10+, attrs/labgrid, Pydantic (catalog + manifest), pytest, ruff, nox (uv backend); the coordinator FastAPI package under `coordinator/api/` has its own pytest suite.

---

## File Structure

**New files (top-level package):**
- `adi_lg_plugins/hw_ci/kuiper_xsa.py` — Kuiper image cache + FAT-partition `.xsa` fetch (no labgrid target).
- `adi_lg_plugins/hw_ci/build_noos.py` — Vivado/shim env composition + `make` orchestration.
- `tests/hw_ci/test_kuiper_xsa.py`, `tests/hw_ci/test_build_noos.py`, `tests/hw_ci/test_noos_manifest.py`, `tests/hw_ci/test_coordinator_resolve_api.py`, `tests/hw_ci/test_emit_matrix.py`, `tests/hw_ci/test_fetch_xsa_cli.py`, `tests/hw_ci/test_build_noos_cli.py`.

**Modified files (top-level package):**
- `adi_lg_plugins/hw_ci/coordinator.py` — gains `_resolve_api` (moved from `request/core.py`).
- `adi_lg_plugins/request/core.py` — imports `_resolve_api` from `hw_ci/coordinator.py`; flash branch forwards `a9_target_name`.
- `adi_lg_plugins/hw_ci/cli.py` — `_emit_matrix` helper; `noos-matrix` enriched legs; new `fetch-xsa` + `build-noos` subcommands; `_resolve_api` import.
- `adi_lg_plugins/hw_ci/noos_manifest.py` — Pydantic models + `validate_banner`/`build_vars`; enriched `NoOSLeg`.
- `adi_lg_plugins/drivers/kuiperdldriver.py` — delegate download to a shared free function; remove cruft (`__del__`, `"FAILEDZz"`, `NotImplementedError`, dead `sw_downloads_template`).
- `adi_lg_plugins/strategies/bootnoosjtag.py` — `boot_marker` default → `"Successfully initialized"`.

**Modified files (coordinator package):**
- `coordinator/api/app/catalog.py` — `FlashConfig` gains `a9_target_name`, `kuiper_xsa_dir`.
- `coordinator/api/app/matching.py` — flash mode returns `image` (the board's Kuiper release).
- `coordinator/api/app/env_gen.py` — `BootNoOSJTAG` `boot_marker` default → `"Successfully initialized"`.

**Modified workflow + docs:**
- `.github/workflows/noos-hw-request.yml` — `build-cmd` default → `adi-lg-hw-ci build-noos …`; artifact path defaults.
- `.github/workflows/tests.yml` — add the new test files.
- `docs/source/user-guide/hardware-ci-runner-setup.rst` (new), `docs/source/user-guide/hw-request.rst` (extend), `docs/source/user-guide/hardware-ci.rst` (refresh stale note).
- `no-os/.github/workflows/hw-request.yml` — trim to the four-input form (separate subrepo).

---

## Task 1: Move `_resolve_api` to `hw_ci/coordinator.py`

**Files:**
- Modify: `adi_lg_plugins/hw_ci/coordinator.py`
- Modify: `adi_lg_plugins/request/core.py:48-60`
- Modify: `adi_lg_plugins/hw_ci/cli.py:106-107,158-159` (the two `from adi_lg_plugins.request.core import _resolve_api` imports)
- Test: `tests/hw_ci/test_coordinator_resolve_api.py`

- [ ] **Step 1: Write the failing test**

Create `tests/hw_ci/test_coordinator_resolve_api.py`:

```python
import pytest

from adi_lg_plugins.hw_ci.coordinator import _resolve_api


def test_derives_api_port_8000_from_grpc_coordinator(monkeypatch):
    monkeypatch.delenv("ADI_LG_API", raising=False)
    monkeypatch.delenv("LG_API", raising=False)
    assert _resolve_api("10.0.0.41:20408") == "10.0.0.41:8000"


def test_strips_scheme_then_derives_port(monkeypatch):
    monkeypatch.delenv("ADI_LG_API", raising=False)
    monkeypatch.delenv("LG_API", raising=False)
    assert _resolve_api("http://coord.lab:20408") == "coord.lab:8000"


def test_explicit_override_wins(monkeypatch):
    monkeypatch.setenv("ADI_LG_API", "api.lab:9001")
    assert _resolve_api("10.0.0.41:20408") == "api.lab:9001"


def test_request_core_reexports_same_callable():
    from adi_lg_plugins.request.core import _resolve_api as core_resolve

    assert core_resolve is _resolve_api
```

- [ ] **Step 2: Run test to verify it fails**

Run: `nox -s tests -- tests/hw_ci/test_coordinator_resolve_api.py`
Expected: FAIL — `ImportError: cannot import name '_resolve_api' from 'adi_lg_plugins.hw_ci.coordinator'`.

- [ ] **Step 3: Add `_resolve_api` to `hw_ci/coordinator.py`**

In `adi_lg_plugins/hw_ci/coordinator.py`, append this function after `resolve_coordinator` (the module already imports `os`):

```python
def _resolve_api(coord: str) -> str:
    """REST API base (host:port) for /api/match + /api/places.

    The REST API and the gRPC coordinator are separate services on different
    ports (8000 vs 20408). Honor an explicit ADI_LG_API / LG_API override;
    otherwise default to the coordinator host on port 8000.
    """
    explicit = os.environ.get("ADI_LG_API") or os.environ.get("LG_API")
    if explicit:
        return explicit
    base = coord.split("://", 1)[-1]
    host = base.rsplit(":", 1)[0] if ":" in base else base
    return f"{host}:8000"
```

- [ ] **Step 4: Re-export from `request/core.py`**

In `adi_lg_plugins/request/core.py`, delete the local `_resolve_api` definition (lines 48-60, the `def _resolve_api(coord: str) -> str:` block) and add it to the existing `from ..hw_ci.coordinator import …` import. Change:

```python
from ..hw_ci.coordinator import list_live_places, resolve_coordinator
```

to:

```python
from ..hw_ci.coordinator import _resolve_api, list_live_places, resolve_coordinator
```

(The unused `import os` in `core.py` may now be flagged by ruff — leave it only if other code uses it; otherwise remove the import. Run `nox -s lint` in Step 6 to confirm.)

- [ ] **Step 5: Update the two `cli.py` callsites**

In `adi_lg_plugins/hw_ci/cli.py`, inside `_cmd_request_matrix` and `_cmd_noos_matrix`, replace each:

```python
    from adi_lg_plugins.request.core import _resolve_api
```

with:

```python
    from .coordinator import _resolve_api
```

- [ ] **Step 6: Run tests + lint to verify they pass**

Run: `nox -s tests -- tests/hw_ci/test_coordinator_resolve_api.py tests/test_request_core.py tests/hw_ci/test_request_matrix.py tests/hw_ci/test_noos_matrix.py && nox -s lint`
Expected: PASS; lint clean.

- [ ] **Step 7: Commit**

```bash
git add adi_lg_plugins/hw_ci/coordinator.py adi_lg_plugins/request/core.py adi_lg_plugins/hw_ci/cli.py tests/hw_ci/test_coordinator_resolve_api.py
git commit -m "refactor(hw_ci): move _resolve_api to coordinator module (DRY)"
```

---

## Task 2: Extract the `_emit_matrix` CLI helper

**Files:**
- Modify: `adi_lg_plugins/hw_ci/cli.py` (`_cmd_request_matrix` ~103-150, `_cmd_noos_matrix` ~153-207)
- Test: `tests/hw_ci/test_emit_matrix.py`

- [ ] **Step 1: Write the failing test**

Create `tests/hw_ci/test_emit_matrix.py`:

```python
import json

from adi_lg_plugins.hw_ci.cli import _emit_matrix


def test_writes_github_output_and_returns_nothing(tmp_path, monkeypatch, capsys):
    gh_out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_out))
    matrix = {"include": [{"part": "ad9361"}]}

    _emit_matrix(matrix, count=1, missing=["daq3"], kind="request-matrix", github_output=True)

    written = gh_out.read_text()
    assert f"matrix={json.dumps(matrix)}" in written
    assert "count=1" in written
    err = capsys.readouterr().err
    assert "::warning::" in err
    assert "daq3" in err


def test_no_github_output_when_flag_false(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "gh_output"))
    _emit_matrix({"include": []}, count=0, missing=[], kind="noos-matrix", github_output=False)
    assert not (tmp_path / "gh_output").exists()
    out = capsys.readouterr().out
    assert '"include"' in out  # the matrix is still printed to stdout


def test_warns_when_github_output_requested_but_env_unset(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    _emit_matrix({"include": []}, count=0, missing=[], kind="request-matrix", github_output=True)
    assert "$GITHUB_OUTPUT is unset" in capsys.readouterr().err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `nox -s tests -- tests/hw_ci/test_emit_matrix.py`
Expected: FAIL — `ImportError: cannot import name '_emit_matrix'`.

- [ ] **Step 3: Add the `_emit_matrix` helper**

In `adi_lg_plugins/hw_ci/cli.py`, add this function above `_cmd_request_matrix` (module already imports `json`, `os`, `sys`):

```python
def _emit_matrix(
    matrix: dict,
    *,
    count: int,
    missing: list[str],
    kind: str,
    github_output: bool,
) -> None:
    """Write the matrix to $GITHUB_OUTPUT (when asked), print it to stdout, and
    emit a ``::warning::`` annotation per missing item. Shared by request-matrix
    and noos-matrix so the GH-output + annotation tail lives in one place."""
    if github_output:
        gh_out = os.environ.get("GITHUB_OUTPUT")
        if gh_out:
            with open(gh_out, "a", encoding="utf-8") as f:
                f.write(f"matrix={json.dumps(matrix)}\n")
                f.write(f"count={count}\n")
        else:
            print("warning: --github-output given but $GITHUB_OUTPUT is unset", file=sys.stderr)

    print(json.dumps(matrix, indent=2))
    for item in missing:
        print(
            f"::warning::{kind}: {item!r} is wanted but no live board matches on the "
            f"coordinator — skipping",
            file=sys.stderr,
        )
```

- [ ] **Step 4: Use it in `_cmd_request_matrix`**

In `_cmd_request_matrix`, replace everything from `if args.github_output:` to the end of the function (the `return 0`) with:

```python
    _emit_matrix(
        matrix,
        count=len(result.parts),
        missing=result.missing,
        kind="request-matrix",
        github_output=args.github_output,
    )
    print(
        f"# request-matrix: {len(wanted)} wanted part(s), {len(result.parts)} available",
        file=sys.stderr,
    )
    return 0
```

- [ ] **Step 5: Use it in `_cmd_noos_matrix`**

In `_cmd_noos_matrix`, replace everything from `if args.github_output:` to the end of the function with:

```python
    _emit_matrix(
        matrix,
        count=len(legs),
        missing=missing,
        kind="noos-matrix",
        github_output=args.github_output,
    )
    print(
        f"# noos-matrix: {len(projects)} project(s), {len(legs)} buildable on a live board",
        file=sys.stderr,
    )
    return 0
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `nox -s tests -- tests/hw_ci/test_emit_matrix.py tests/hw_ci/test_request_matrix.py tests/hw_ci/test_noos_matrix.py && nox -s lint`
Expected: PASS; lint clean.

- [ ] **Step 7: Commit**

```bash
git add adi_lg_plugins/hw_ci/cli.py tests/hw_ci/test_emit_matrix.py
git commit -m "refactor(hw_ci): extract _emit_matrix helper shared by both matrix commands"
```

---

## Task 3: Extend `FlashConfig` with `a9_target_name` + `kuiper_xsa_dir`

**Files:**
- Modify: `coordinator/api/app/catalog.py:31-37`
- Test: `coordinator/api/tests/test_catalog.py`

> Run coordinator tests from `coordinator/api/` (its own pytest suite, not the top-level nox).

- [ ] **Step 1: Write the failing test**

Append to `coordinator/api/tests/test_catalog.py`:

```python
def test_flashconfig_optional_overrides_default_none():
    from app.catalog import FlashConfig

    fc = FlashConfig(strategy="BootNoOSJTAG", noos_project="ad9371")
    assert fc.a9_target_name is None
    assert fc.kuiper_xsa_dir is None


def test_flashconfig_accepts_overrides():
    from app.catalog import FlashConfig

    fc = FlashConfig(
        strategy="BootNoOSJTAG",
        noos_project="ad9371",
        a9_target_name="*Cortex-A9 MPCore #1",
        kuiper_xsa_dir="zynq-zc706-adv7511-adrv9371",
    )
    assert fc.a9_target_name == "*Cortex-A9 MPCore #1"
    assert fc.kuiper_xsa_dir == "zynq-zc706-adv7511-adrv9371"
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `coordinator/api/`): `python -m pytest tests/test_catalog.py -k flashconfig -v`
Expected: FAIL — `TypeError`/validation error on the unknown `a9_target_name` field.

- [ ] **Step 3: Add the fields**

In `coordinator/api/app/catalog.py`, change the `FlashConfig` body to:

```python
class FlashConfig(BaseModel):
    """no-os "flash" mode support for a board: which strategy loads the
    firmware and which ``projects/<noos_project>`` builds it. Present only on
    boards that can run no-os bare-metal firmware (vs. the Kuiper SD boot)."""

    strategy: str
    noos_project: str
    # Per-board JTAG target override; when None the env_gen / strategy default
    # ("*Cortex-A9 MPCore #0") applies.
    a9_target_name: str | None = None
    # Explicit Kuiper boot-partition folder holding bootgen_sysfiles.tgz; when
    # None, build-noos searches the FAT partition for *<carrier>*<board>*.
    kuiper_xsa_dir: str | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `coordinator/api/`): `python -m pytest tests/test_catalog.py -k flashconfig -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add coordinator/api/app/catalog.py coordinator/api/tests/test_catalog.py
git commit -m "feat(catalog): add optional a9_target_name + kuiper_xsa_dir to FlashConfig"
```

---

## Task 4: Flash-mode matching returns the board's Kuiper `image`

**Files:**
- Modify: `coordinator/api/app/matching.py:81-104`
- Test: `coordinator/api/tests/test_matching.py`

- [ ] **Step 1: Write the failing test**

Append to `coordinator/api/tests/test_matching.py` (reuse the file's existing helpers for building a `BoardCatalog` + `PlaceModel`; if none exist, construct inline as below):

```python
def test_flash_mode_returns_board_image_release():
    from app.catalog import BoardCatalog, BoardEntry, FlashConfig
    from app.matching import match_places
    from app.models import PlaceModel

    catalog = BoardCatalog(
        boards={
            "adrv9371": BoardEntry(
                image="2023_R2_P1",
                aliases=["ad9371"],
                flash=FlashConfig(strategy="BootNoOSJTAG", noos_project="ad9371"),
                carriers={"zc706": {}},
            )
        }
    )
    places = [
        PlaceModel(
            name="bq",
            tags={"daughter-board": "adrv9371", "carrier": "zc706", "runner": "hw-bq"},
            acquired=None,
        )
    ]

    res = match_places(catalog, places, part="ad9371", carrier="zc706", mode="flash")

    assert res.satisfiable
    assert res.strategy == "BootNoOSJTAG"
    assert res.image == "2023_R2_P1"  # <-- previously None
    assert res.reservation_filter["daughter-board"] == "adrv9371"  # alias → canonical
    assert res.flash is not None and res.flash.noos_project == "ad9371"
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `coordinator/api/`): `python -m pytest tests/test_matching.py -k flash_mode_returns_board_image -v`
Expected: FAIL — `assert res.image == "2023_R2_P1"` fails because flash mode sets `image = None`.

- [ ] **Step 3: Make flash mode carry the release**

In `coordinator/api/app/matching.py`, in the `if mode == "flash":` branch (~line 81), change `image = None` to `image = entry.image`:

```python
    if mode == "flash":
        # The flash strategy comes from the catalog and OVERRIDES the place's
        # boot-strategy tag (the same board serves Kuiper or no-os). The Kuiper
        # `image` is still returned — build-noos sources the board's .xsa from
        # that Kuiper release; the firmware itself is built + passed by the client.
        strategy = entry.flash.strategy
        image = entry.image
        flash = entry.flash
```

- [ ] **Step 4: Run test to verify it passes**

Run (from `coordinator/api/`): `python -m pytest tests/test_matching.py -v`
Expected: PASS (the whole file, to confirm no regression in uri-mode tests).

- [ ] **Step 5: Commit**

```bash
git add coordinator/api/app/matching.py coordinator/api/tests/test_matching.py
git commit -m "feat(matching): flash mode returns the board's Kuiper image release"
```

---

## Task 5: Unify the boot-banner default to `"Successfully initialized"`

**Files:**
- Modify: `coordinator/api/app/env_gen.py:120-124`
- Modify: `adi_lg_plugins/strategies/bootnoosjtag.py` (`boot_marker` attr default)
- Test: `coordinator/api/tests/test_env_gen.py`, `tests/test_bootnoosjtag_strat.py`

- [ ] **Step 1: Write the failing tests**

Append to `coordinator/api/tests/test_env_gen.py`:

```python
def test_bootnoosjtag_default_banner_is_successfully_initialized():
    from app.env_gen import STRATEGY_CONFIGS

    assert STRATEGY_CONFIGS["BootNoOSJTAG"]["boot_marker"] == "Successfully initialized"
```

Append to `tests/test_bootnoosjtag_strat.py`:

```python
def test_default_boot_marker_is_successfully_initialized():
    from adi_lg_plugins.strategies.bootnoosjtag import BootNoOSJTAG

    field = next(f for f in BootNoOSJTAG.__attrs_attrs__ if f.name == "boot_marker")
    assert field.default == "Successfully initialized"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd coordinator/api && python -m pytest tests/test_env_gen.py -k successfully_initialized -v; cd -`
Run: `nox -s tests -- tests/test_bootnoosjtag_strat.py -k successfully_initialized`
Expected: both FAIL (defaults are currently `"Running IIOD server"`).

- [ ] **Step 3: Change the env_gen default**

In `coordinator/api/app/env_gen.py`, in `STRATEGY_CONFIGS["BootNoOSJTAG"]`, change `"boot_marker": "Running IIOD server"` to `"boot_marker": "Successfully initialized"`.

- [ ] **Step 4: Change the strategy default**

In `adi_lg_plugins/strategies/bootnoosjtag.py`, change:

```python
    boot_marker = attr.ib(default="Running IIOD server")
```

to:

```python
    boot_marker = attr.ib(default="Successfully initialized")
```

Also update the SHELL_DEFAULTS comment block reference if it names `"Running IIOD server"` — grep for any other `Running IIOD server` literal in `coordinator/api/app/env_gen.py` and `adi_lg_plugins/strategies/bootnoosjtag.py` and update prose only (do not change `SHELL_DEFAULTS` keys that are unrelated).

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd coordinator/api && python -m pytest tests/test_env_gen.py -v; cd -`
Run: `nox -s tests -- tests/test_bootnoosjtag_strat.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add coordinator/api/app/env_gen.py adi_lg_plugins/strategies/bootnoosjtag.py coordinator/api/tests/test_env_gen.py tests/test_bootnoosjtag_strat.py
git commit -m "refactor: unify BootNoOSJTAG banner default to 'Successfully initialized'"
```

---

## Task 6: Pydantic manifest + `validate_banner`/`build_vars` enrichment

**Files:**
- Modify: `adi_lg_plugins/hw_ci/noos_manifest.py`
- Test: `tests/hw_ci/test_noos_manifest.py`

- [ ] **Step 1: Write the failing test**

Create `tests/hw_ci/test_noos_manifest.py`:

```python
from dataclasses import dataclass

import pytest

from adi_lg_plugins.hw_ci.noos_manifest import (
    NoOSLeg,
    NoOSProject,
    build_noos_matrix,
    load_noos_manifest,
)


@dataclass
class _Match:
    satisfiable: bool
    runner: str | None = None
    image: str | None = None
    reservation_filter: dict | None = None


def _write(tmp_path, text):
    p = tmp_path / "projects.yaml"
    p.write_text(text)
    return str(p)


def test_load_defaults_banner_and_build_vars(tmp_path):
    path = _write(
        tmp_path,
        """
projects:
  - noos_project: adrv9009
    part: adrv9009
    carriers: [zc706]
""",
    )
    projects = load_noos_manifest(path)
    assert projects == [
        NoOSProject(
            noos_project="adrv9009",
            part="adrv9009",
            carriers=["zc706"],
            validate_banner="Successfully initialized",
            build_vars={},
        )
    ]


def test_load_explicit_banner_and_build_vars(tmp_path):
    path = _write(
        tmp_path,
        """
projects:
  - noos_project: ad9371
    part: ad9371
    carriers: [zc706]
    validate_banner: "Done"
    build_vars: {EXAMPLE: iio_example}
""",
    )
    proj = load_noos_manifest(path)[0]
    assert proj.validate_banner == "Done"
    assert proj.build_vars == {"EXAMPLE": "iio_example"}


def test_load_rejects_missing_required_key(tmp_path):
    path = _write(tmp_path, "projects:\n  - part: ad9371\n    carriers: [zc706]\n")
    with pytest.raises(ValueError):
        load_noos_manifest(path)


def test_matrix_leg_carries_board_release_banner_build_vars():
    projects = [
        NoOSProject(
            noos_project="ad9371",
            part="ad9371",
            carriers=["zc706"],
            validate_banner="Done",
            build_vars={"EXAMPLE": "iio_example"},
        )
    ]

    def probe(part, carrier):
        return _Match(
            satisfiable=True,
            runner="hw-bq",
            image="2023_R2_P1",
            reservation_filter={"daughter-board": "adrv9371", "carrier": "zc706"},
        )

    legs, missing = build_noos_matrix(projects, probe)
    assert missing == []
    assert legs == [
        NoOSLeg(
            part="ad9371",
            noos_project="ad9371",
            carrier="zc706",
            runner="hw-bq",
            board="adrv9371",
            release="2023_R2_P1",
            validate_banner="Done",
            build_vars={"EXAMPLE": "iio_example"},
        )
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `nox -s tests -- tests/hw_ci/test_noos_manifest.py`
Expected: FAIL — `NoOSProject` has no `validate_banner`/`build_vars`; `NoOSLeg` has no `board`/`release`.

- [ ] **Step 3: Rewrite `noos_manifest.py`**

Replace the whole body of `adi_lg_plugins/hw_ci/noos_manifest.py` (keep the module docstring) with Pydantic models and enriched leg fields:

```python
"""no-os hardware-CI discovery: map no-os projects to live flash-capable boards.

Unlike pyadi-iio (which gates on ``@pytest.mark.iio_hardware`` markers harvested
from test files), no-os has no pytest markers. Instead a small **manifest**
(committed in no-os, e.g. ``tools/hw_ci/projects.yaml``) declares which
``projects/<noos_project>`` builds which ``part`` on which ``carriers``, with
optional per-project ``validate_banner`` + ``build_vars``. The preflight
intersects that with the coordinator's live flash-capable boards
(``GET /api/match?...&mode=flash``) to produce one CI leg per buildable+live
project; the rest are annotated as skipped.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import yaml
from pydantic import BaseModel

DEFAULT_VALIDATE_BANNER = "Successfully initialized"


class NoOSProject(BaseModel):
    noos_project: str  # projects/<noos_project>
    part: str  # coordinator part to request (may be a catalog alias, e.g. ad9371)
    carriers: list[str] = []  # FPGA carriers this project supports, preference order
    validate_banner: str = DEFAULT_VALIDATE_BANNER  # on-target serial success marker
    build_vars: dict[str, str] = {}  # extra `make` variables (K=V)

    model_config = {"frozen": True}

    def __eq__(self, other: object) -> bool:  # dataclass-style equality for tests
        if not isinstance(other, NoOSProject):
            return NotImplemented
        return self.model_dump() == other.model_dump()

    def __hash__(self) -> int:
        return hash((self.noos_project, self.part, tuple(self.carriers)))


@dataclass
class NoOSLeg:
    part: str
    noos_project: str
    carrier: str
    runner: str | None = None  # self-hosted runner co-located with the board
    board: str | None = None  # canonical daughter-board (.xsa key), e.g. adrv9371
    release: str | None = None  # Kuiper release the board boots (the .xsa source)
    validate_banner: str = DEFAULT_VALIDATE_BANNER
    build_vars: dict[str, str] = field(default_factory=dict)


def load_noos_manifest(path: str) -> list[NoOSProject]:
    """Parse + validate a no-os hw-CI manifest YAML into ``NoOSProject`` entries.

    Raises ``pydantic.ValidationError`` (a ``ValueError``) on a malformed entry
    (e.g. a missing ``noos_project``/``part``)."""
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f.read()) or {}
    return [NoOSProject.model_validate(entry) for entry in data.get("projects", [])]


def build_noos_matrix(
    projects: list[NoOSProject],
    probe: Callable[[str, str], object | None],
) -> tuple[list[NoOSLeg], list[str]]:
    """Split projects into runnable legs and missing (no live board) projects.

    ``probe(part, carrier)`` returns a match result (truthy ``.satisfiable`` plus
    ``.runner``, ``.image``, ``.reservation_filter``) for a live flash-capable
    board, or a falsy/None result otherwise. The first satisfiable carrier (in
    manifest order) wins. The leg carries the canonical daughter-board (from
    ``reservation_filter``) + the Kuiper ``image`` release so the build can fetch
    the board's ``.xsa``."""
    legs: list[NoOSLeg] = []
    missing: list[str] = []
    for proj in projects:
        chosen: tuple[str, object] | None = None
        for carrier in proj.carriers:
            res = probe(proj.part, carrier)
            if res is not None and getattr(res, "satisfiable", False):
                chosen = (carrier, res)
                break
        if chosen is None:
            missing.append(proj.noos_project)
            continue
        carrier, res = chosen
        reservation_filter = getattr(res, "reservation_filter", None) or {}
        legs.append(
            NoOSLeg(
                part=proj.part,
                noos_project=proj.noos_project,
                carrier=carrier,
                runner=getattr(res, "runner", None),
                board=reservation_filter.get("daughter-board"),
                release=getattr(res, "image", None),
                validate_banner=proj.validate_banner,
                build_vars=dict(proj.build_vars),
            )
        )
    return legs, missing
```

- [ ] **Step 4: Run test to verify it passes**

Run: `nox -s tests -- tests/hw_ci/test_noos_manifest.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add adi_lg_plugins/hw_ci/noos_manifest.py tests/hw_ci/test_noos_manifest.py
git commit -m "feat(hw_ci): Pydantic manifest with validate_banner/build_vars; enrich NoOSLeg with board/release"
```

---

## Task 7: `noos-matrix` CLI emits the enriched legs

**Files:**
- Modify: `adi_lg_plugins/hw_ci/cli.py` (`_cmd_noos_matrix`, the `matrix = {…}` block ~178-189)
- Test: `tests/hw_ci/test_noos_matrix.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/hw_ci/test_noos_matrix.py` (the file already exists; reuse its style for invoking the CLI). Add a test that drives `_cmd_noos_matrix` with a patched `match_client.get_match` and a temp manifest, asserting the emitted matrix include carries the new keys:

```python
import json
from types import SimpleNamespace

from adi_lg_plugins.hw_ci import cli as cli_mod


def test_noos_matrix_emits_enriched_legs(tmp_path, monkeypatch, capsys):
    manifest = tmp_path / "projects.yaml"
    manifest.write_text(
        """
projects:
  - noos_project: ad9371
    part: ad9371
    carriers: [zc706]
    validate_banner: "Done"
    build_vars: {EXAMPLE: iio_example}
"""
    )

    monkeypatch.setenv("LG_COORDINATOR", "10.0.0.41:20408")

    def fake_get_match(api, *, part, carrier=None, mode="uri"):
        return SimpleNamespace(
            satisfiable=True,
            runner="hw-bq",
            image="2023_R2_P1",
            reservation_filter={"daughter-board": "adrv9371", "carrier": "zc706"},
        )

    # _cmd_noos_matrix imports match_client locally → patch the source module.
    import adi_lg_plugins.request.match_client as mc

    monkeypatch.setattr(mc, "get_match", fake_get_match)

    args = SimpleNamespace(
        manifest=str(manifest), coord=None, github_output=False
    )
    rc = cli_mod._cmd_noos_matrix(args)
    assert rc == 0

    out = capsys.readouterr().out
    leg = json.loads(out)["include"][0]
    assert leg == {
        "part": "ad9371",
        "noos_project": "ad9371",
        "carrier": "zc706",
        "runner": "hw-bq",
        "board": "adrv9371",
        "release": "2023_R2_P1",
        "validate_banner": "Done",
        "build_vars": {"EXAMPLE": "iio_example"},
    }
```

> `_cmd_noos_matrix` imports `match_client` locally (`from adi_lg_plugins.request import match_client`), so the test patches the source module `adi_lg_plugins.request.match_client.get_match` (which the local import binds to at call time).

- [ ] **Step 2: Run test to verify it fails**

Run: `nox -s tests -- tests/hw_ci/test_noos_matrix.py -k enriched`
Expected: FAIL — emitted leg only has `part/noos_project/carrier/runner`.

- [ ] **Step 3: Emit the enriched keys**

In `adi_lg_plugins/hw_ci/cli.py`, in `_cmd_noos_matrix`, replace the `matrix = {…}` list comprehension with:

```python
    matrix = {
        "include": [
            {
                "part": leg.part,
                "noos_project": leg.noos_project,
                "carrier": leg.carrier,
                "runner": leg.runner or "",
                "board": leg.board or "",
                "release": leg.release or "",
                "validate_banner": leg.validate_banner,
                "build_vars": leg.build_vars,
            }
            for leg in legs
        ]
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `nox -s tests -- tests/hw_ci/test_noos_matrix.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add adi_lg_plugins/hw_ci/cli.py tests/hw_ci/test_noos_matrix.py
git commit -m "feat(hw_ci): noos-matrix emits board/release/validate_banner/build_vars per leg"
```

---

## Task 8: `kuiper_xsa.py` — fetch a board's `.xsa` from the Kuiper image

**Files:**
- Create: `adi_lg_plugins/hw_ci/kuiper_xsa.py`
- Test: `tests/hw_ci/test_kuiper_xsa.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/hw_ci/test_kuiper_xsa.py`:

```python
import io
import tarfile
from pathlib import Path

import pytest

from adi_lg_plugins.hw_ci import kuiper_xsa


def test_resolve_board_folder_unique_match():
    entries = [
        {"path": "/zynq-zc706-adv7511-adrv9009", "type": "dir", "size": 0},
        {"path": "/zynq-zc706-adv7511-adrv9009/bootgen_sysfiles.tgz", "type": "file", "size": 9},
        {"path": "/zynq-zc706-adv7511-adrv9371", "type": "dir", "size": 0},
        {"path": "/zynq-zc706-adv7511-adrv9371/bootgen_sysfiles.tgz", "type": "file", "size": 9},
    ]
    assert (
        kuiper_xsa._resolve_board_folder(entries, board="adrv9009", carrier="zc706")
        == "zynq-zc706-adv7511-adrv9009"
    )


def test_resolve_board_folder_no_match_lists_candidates():
    entries = [
        {"path": "/zynq-zc706-adv7511-adrv9371/bootgen_sysfiles.tgz", "type": "file", "size": 9},
    ]
    with pytest.raises(FileNotFoundError) as e:
        kuiper_xsa._resolve_board_folder(entries, board="ad9081", carrier="zcu102")
    assert "zynq-zc706-adv7511-adrv9371" in str(e.value)


def test_resolve_board_folder_ambiguous():
    entries = [
        {"path": "/a-zc706-adrv9009/bootgen_sysfiles.tgz", "type": "file", "size": 9},
        {"path": "/b-zc706-adrv9009/bootgen_sysfiles.tgz", "type": "file", "size": 9},
    ]
    with pytest.raises(ValueError) as e:
        kuiper_xsa._resolve_board_folder(entries, board="adrv9009", carrier="zc706")
    assert "ambiguous" in str(e.value).lower()


def test_fetch_board_xsa_cache_hit_skips_extraction(tmp_path, monkeypatch):
    cache_dir = tmp_path / "xsa"
    out = cache_dir / "2023_R2_P1" / "adrv9009_zc706" / "system_top.xsa"
    out.parent.mkdir(parents=True)
    out.write_bytes(b"cached")

    def _boom(*a, **k):
        raise AssertionError("must not download/extract on cache hit")

    monkeypatch.setattr(kuiper_xsa, "ensure_kuiper_image", _boom)

    got = kuiper_xsa.fetch_board_xsa(
        "2023_R2_P1", "adrv9009", "zc706", cache_dir=str(cache_dir)
    )
    assert got == out


def test_fetch_board_xsa_extracts_from_tgz(tmp_path, monkeypatch):
    cache_dir = tmp_path / "xsa"

    # A fake bootgen_sysfiles.tgz containing system_top.xsa.
    def fake_extract_file(fs, file_path, output_path):
        assert file_path.endswith("/bootgen_sysfiles.tgz")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(output_path, "w:gz") as tf:
            data = b"XSA-BYTES"
            info = tarfile.TarInfo("system_top.xsa")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        return True

    class FakeExtractor:
        def __init__(self, img_path, logger=None):
            pass

        def get_partitions(self):
            return [{"description": "FAT (0x0c)", "start": 12582912}]

        def open_filesystem(self, offset):
            return object()

        def list_files(self, fs, path="/"):
            return [
                {"path": "/zynq-zc706-adv7511-adrv9009", "type": "dir", "size": 0},
                {
                    "path": "/zynq-zc706-adv7511-adrv9009/bootgen_sysfiles.tgz",
                    "type": "file",
                    "size": 9,
                },
            ]

        extract_file = staticmethod(fake_extract_file)

        def close(self):
            pass

    monkeypatch.setattr(kuiper_xsa, "ensure_kuiper_image", lambda *a, **k: tmp_path / "k.img")
    monkeypatch.setattr(kuiper_xsa, "IMGFileExtractor", FakeExtractor)

    out = kuiper_xsa.fetch_board_xsa(
        "2023_R2_P1", "adrv9009", "zc706", cache_dir=str(cache_dir)
    )
    assert out.read_bytes() == b"XSA-BYTES"
    assert out.name == "system_top.xsa"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `nox -s tests -- tests/hw_ci/test_kuiper_xsa.py`
Expected: FAIL — `ModuleNotFoundError: adi_lg_plugins.hw_ci.kuiper_xsa`.

- [ ] **Step 3: Write `kuiper_xsa.py`**

Create `adi_lg_plugins/hw_ci/kuiper_xsa.py`:

```python
"""Fetch a board's HDL hardware export (``system_top.xsa``) from a Kuiper image.

The Kuiper SD image's boot FAT partition holds, per board+carrier, a folder
(e.g. ``zynq-zc706-adv7511-adrv9009/``) whose ``bootgen_sysfiles.tgz`` contains
the ``system_top.xsa`` Vivado hardware export a no-os build needs. This module
locates/downloads the Kuiper image for a release, finds the board's boot folder
in the FAT partition, extracts the ``.xsa``, and caches it — all without a
labgrid target, so the CI ``build-noos`` step can call it directly.

It reuses the download/cache logic in ``kuiperdldriver`` (the shared
``download_release_image`` free function) and the ``IMGFileExtractor``
FAT-partition reader.
"""

from __future__ import annotations

import fnmatch
import logging
import tarfile
from pathlib import Path

from ..drivers.imageextractor import IMGFileExtractor
from ..drivers.kuiperdldriver import download_release_image

logger = logging.getLogger(__name__)

# Where the raw Kuiper .img is cached (shared with the KuiperRelease default).
DEFAULT_IMAGE_CACHE = Path.home() / ".labgrid" / "kuiper_releases"
# Where extracted .xsa files are cached (<release>/<board>_<carrier>/system_top.xsa).
DEFAULT_XSA_CACHE = Path.home() / ".labgrid" / "kuiper_xsa"

BOOTGEN = "bootgen_sysfiles.tgz"
XSA_NAME = "system_top.xsa"


def ensure_kuiper_image(release: str, image_cache: str | None = None) -> Path:
    """Return the cached Kuiper ``.img`` for ``release``, downloading if absent."""
    cache_path = Path(image_cache or DEFAULT_IMAGE_CACHE)
    cache_path.mkdir(parents=True, exist_ok=True)
    return Path(download_release_image(release, str(cache_path), logger=logger))


def _find_fat_partition(ext: IMGFileExtractor) -> dict:
    for part in ext.get_partitions():
        if "FAT" in part.get("description", ""):
            return part
    raise RuntimeError("no FAT partition found in Kuiper image")


def _resolve_board_folder(entries: list[dict], *, board: str, carrier: str) -> str:
    """Return the boot folder name (no leading slash) matching
    ``*<carrier>*<board>*`` (case-insensitive) that contains
    ``bootgen_sysfiles.tgz``. Raise on 0 (FileNotFoundError) or >1 (ValueError)."""
    pat = f"*{carrier.lower()}*{board.lower()}*"
    tgz_parents = sorted(
        {
            str(Path(e["path"]).parent).lstrip("/")
            for e in entries
            if e.get("type") == "file" and Path(e["path"]).name == BOOTGEN
        }
    )
    matches = [p for p in tgz_parents if fnmatch.fnmatch(Path(p).name.lower(), pat)]
    if not matches:
        raise FileNotFoundError(
            f"no Kuiper boot folder matching '*{carrier}*{board}*' containing {BOOTGEN}; "
            f"candidates: {[Path(p).name for p in tgz_parents]}"
        )
    if len(matches) > 1:
        raise ValueError(
            f"ambiguous Kuiper boot folder for {board}/{carrier}: "
            f"{[Path(m).name for m in matches]} — set flash.kuiper_xsa_dir / --xsa-dir"
        )
    return matches[0]


def fetch_board_xsa(
    release: str,
    board: str,
    carrier: str,
    cache_dir: str | None = None,
    *,
    xsa_dir: str | None = None,
    image_cache: str | None = None,
) -> Path:
    """Resolve + cache the board's ``system_top.xsa`` from the Kuiper image.

    ``board`` is the canonical daughter-board (e.g. ``adrv9371``), ``carrier``
    the FPGA carrier (e.g. ``zc706``). ``xsa_dir`` pins the boot folder name and
    skips the FAT search. Returns the cached ``.xsa`` path."""
    out_dir = Path(cache_dir or DEFAULT_XSA_CACHE) / release / f"{board}_{carrier}"
    out_xsa = out_dir / XSA_NAME
    if out_xsa.exists():
        logger.info("cached .xsa for %s/%s at %s", board, carrier, out_xsa)
        return out_xsa

    img = ensure_kuiper_image(release, image_cache=image_cache)
    ext = IMGFileExtractor(str(img), logger=logger)
    try:
        fat = _find_fat_partition(ext)
        fs = ext.open_filesystem(fat["start"])
        entries = ext.list_files(fs, "/")
        folder = xsa_dir.strip("/") if xsa_dir else _resolve_board_folder(
            entries, board=board, carrier=carrier
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        tgz_path = out_dir / BOOTGEN
        if not ext.extract_file(fs, f"/{folder}/{BOOTGEN}", str(tgz_path)):
            raise FileNotFoundError(f"failed to extract /{folder}/{BOOTGEN} from Kuiper image")
    finally:
        ext.close()

    with tarfile.open(tgz_path) as tf:
        member = next((m for m in tf.getmembers() if Path(m.name).name == XSA_NAME), None)
        if member is None:
            raise FileNotFoundError(f"{BOOTGEN} for {board}/{carrier} has no {XSA_NAME}")
        member.name = XSA_NAME  # flatten any internal path
        tf.extract(member, out_dir)

    logger.info("extracted .xsa for %s/%s to %s", board, carrier, out_xsa)
    return out_xsa
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `nox -s tests -- tests/hw_ci/test_kuiper_xsa.py`
Expected: PASS. (`download_release_image` is added in Task 9; for now the import will fail. If running Task 8 before Task 9, the import error is expected — implement Task 9 next, then re-run. To keep TDD green-per-task, **do Task 9's Step 3 first** if your runner imports eagerly.)

> Ordering note: `kuiper_xsa.py` imports `download_release_image` from `kuiperdldriver`. Implement Task 9 Step 3 (add the free function) **before** running Task 8 Step 4. The two tasks are committed separately but the function must exist for the import to resolve.

- [ ] **Step 5: Commit**

```bash
git add adi_lg_plugins/hw_ci/kuiper_xsa.py tests/hw_ci/test_kuiper_xsa.py
git commit -m "feat(hw_ci): kuiper_xsa.fetch_board_xsa — source system_top.xsa from the Kuiper image"
```

---

## Task 9: Refactor `kuiperdldriver.py` — shared download helper + cruft removal

**Files:**
- Modify: `adi_lg_plugins/drivers/kuiperdldriver.py`
- Test: `tests/test_kuiperdl_download_image.py` (new), plus existing `tests/test_cloudsmith_dl.py` style if present

> Do this task's **Step 3** before Task 8 Step 4 (the import dependency above).

- [ ] **Step 1: Write the failing test**

Create `tests/test_kuiperdl_download_image.py`:

```python
import json
from pathlib import Path

from adi_lg_plugins.drivers import kuiperdldriver


def test_download_release_image_returns_cached_when_present(tmp_path):
    cache = tmp_path
    img = cache / "image_2025-03-18-ADI-Kuiper-full.img"
    img.write_bytes(b"img")
    (cache / "cache_info.json").write_text(
        json.dumps({"2023_R2_P1": {"image_path": str(img)}})
    )

    got = kuiperdldriver.download_release_image("2023_R2_P1", str(cache))
    assert Path(got) == img


def test_check_failure_message_has_no_typo():
    import inspect

    src = inspect.getsource(kuiperdldriver.Downloader.check)
    assert "FAILEDZz" not in src
    assert "MD5 Check: FAILED" in src


def test_no_dead_del_or_notimplemented():
    import inspect

    src = inspect.getsource(kuiperdldriver)
    assert "def __del__" not in src
    assert "NotImplementedError" not in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `nox -s tests -- tests/test_kuiperdl_download_image.py`
Expected: FAIL — `download_release_image` doesn't exist; `FAILEDZz`/`__del__`/`NotImplementedError` still present.

- [ ] **Step 3: Add `download_release_image` + delegate the driver**

In `adi_lg_plugins/drivers/kuiperdldriver.py`, add a module-level free function (place it after the `Downloader` class, before `@target_factory.reg_driver`). It contains the existing cache-check + download flow, parameterized by `cache_path` + `logger`:

```python
def _cache_lookup(cache_path: str, release_version: str) -> str | None:
    """Return the cached .img path for a release if recorded + on disk, else None."""
    cache_file = os.path.join(cache_path, "cache_info.json")
    if not os.path.exists(cache_file):
        return None
    with open(cache_file) as f:
        cache_data = json.load(f)
    entry = cache_data.get(release_version)
    if entry and os.path.exists(entry["image_path"]):
        return entry["image_path"]
    return None


def download_release_image(release_version: str, cache_path: str, *, logger=None) -> str:
    """Download + verify + extract the Kuiper full image for ``release_version``
    into ``cache_path`` (idempotent: returns the cached .img if already present).

    Shared by ``KuiperDLDriver.download_release`` (resource-bound) and the CI
    ``kuiper_xsa`` helper (no target). Returns the cached ``.img`` path."""
    log = logger or logging.getLogger(__name__)
    cached = _cache_lookup(cache_path, release_version)
    if cached is not None:
        log.info("Kuiper release %s already cached at %s", release_version, cached)
        return cached

    os.makedirs(cache_path, exist_ok=True)
    downloader = Downloader()
    rel_info = downloader.releases(release_version)
    log.info("Downloading Kuiper release %s from %s", release_version, rel_info["link"])

    name_archive = rel_info["xzname"] if "xzname" in rel_info else rel_info["zipname"]
    md5_archive = rel_info["xzmd5"] if "xzmd5" in rel_info else rel_info["zipmd5"]
    tarball_path = os.path.join(cache_path, name_archive)
    downloader.download(rel_info["link"], name_archive)
    downloader.check(name_archive, md5_archive)
    downloader.extract(name_archive, rel_info["imgname"])
    img_file = downloader.check(rel_info["imgname"], rel_info["imgmd5"], find_img=True)

    img_filename = os.path.basename(img_file)
    target_path = os.path.join(cache_path, img_filename)
    shutil.move(img_file, target_path)

    if os.path.exists(tarball_path):
        os.remove(tarball_path)
    if os.path.isfile(name_archive):
        os.remove(name_archive)
    if os.path.isdir(rel_info["imgname"]):
        os.rmdir(rel_info["imgname"])

    cache_file = os.path.join(cache_path, "cache_info.json")
    cache_data = {}
    if os.path.exists(cache_file):
        with open(cache_file) as f:
            cache_data = json.load(f)
    cache_data[release_version] = {
        "image_path": target_path,
        "download_time": time.ctime(),
        "download_date": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
    }
    with open(cache_file, "w") as f:
        json.dump(cache_data, f, indent=4)
    log.info("Kuiper release %s cached at %s", release_version, target_path)
    return target_path
```

Add `import logging` to the top of the module (with the other stdlib imports).

- [ ] **Step 4: Delegate `KuiperDLDriver.download_release` + drop the boot-files stub**

Replace the `download_release` method body with a delegation (removing the `get_boot_files` branch that raises `NotImplementedError`):

```python
    def download_release(self, release_version=None):
        """Download the specified Kuiper release version if not already cached."""
        if release_version is None:
            release_version = self.kuiper_resource.release_version
        download_release_image(
            release_version, self.kuiper_resource.cache_path, logger=self.logger
        )
```

Update `download_release` callers in this file: `get_full_image_path` calls `self.download_release(release_version)` (already matches); `get_boot_files_from_release` calls `self.download_release(get_boot_files=False)` — change it to `self.download_release()`.

- [ ] **Step 5: Remove remaining cruft**

In `kuiperdldriver.py`:
- Delete the `__del__` method (lines ~321-326).
- In `Downloader.check`, change `print("MD5 Check: FAILEDZz")` to `print("MD5 Check: FAILED")`.
- Delete the dead `sw_downloads_template = "https://swdownloads.analog.com/cse/boot_partition_files/…"` class attribute (the 404 URL, no longer referenced after the boot-files branch is gone).

- [ ] **Step 6: Run tests to verify they pass**

Run: `nox -s tests -- tests/test_kuiperdl_download_image.py tests/hw_ci/test_kuiper_xsa.py && nox -s lint`
Expected: PASS; lint clean.

- [ ] **Step 7: Commit**

```bash
git add adi_lg_plugins/drivers/kuiperdldriver.py tests/test_kuiperdl_download_image.py
git commit -m "refactor(kuiper): extract download_release_image free fn; remove __del__/typo/NotImplemented cruft"
```

---

## Task 10: `fetch-xsa` CLI subcommand

**Files:**
- Modify: `adi_lg_plugins/hw_ci/cli.py` (add `_cmd_fetch_xsa` + subparser)
- Test: `tests/hw_ci/test_fetch_xsa_cli.py`

- [ ] **Step 1: Write the failing test**

Create `tests/hw_ci/test_fetch_xsa_cli.py`:

```python
from types import SimpleNamespace

from adi_lg_plugins.hw_ci import cli as cli_mod


def test_fetch_xsa_prints_resolved_path(tmp_path, monkeypatch, capsys):
    fake = tmp_path / "system_top.xsa"
    fake.write_bytes(b"x")

    captured = {}

    def fake_fetch(release, board, carrier, cache_dir=None, *, xsa_dir=None):
        captured.update(
            release=release, board=board, carrier=carrier, cache_dir=cache_dir, xsa_dir=xsa_dir
        )
        return fake

    monkeypatch.setattr(cli_mod, "fetch_board_xsa", fake_fetch, raising=False)

    args = SimpleNamespace(
        release="2023_R2_P1", board="adrv9009", carrier="zc706", out=None, xsa_dir=None
    )
    rc = cli_mod._cmd_fetch_xsa(args)
    assert rc == 0
    assert str(fake) in capsys.readouterr().out
    assert captured["board"] == "adrv9009"


def test_fetch_xsa_dispatches_through_main(monkeypatch, tmp_path):
    # The argparse tree is built inside main(); exercise it end-to-end.
    fake = tmp_path / "system_top.xsa"
    fake.write_bytes(b"x")
    seen = {}

    def fake_fetch(release, board, carrier, cache_dir=None, *, xsa_dir=None):
        seen.update(release=release, board=board, carrier=carrier, xsa_dir=xsa_dir)
        return fake

    monkeypatch.setattr(cli_mod, "fetch_board_xsa", fake_fetch, raising=False)
    rc = cli_mod.main(
        ["fetch-xsa", "--release", "2023_R2_P1", "--board", "adrv9009", "--carrier", "zc706"]
    )
    assert rc == 0
    assert seen == {
        "release": "2023_R2_P1",
        "board": "adrv9009",
        "carrier": "zc706",
        "xsa_dir": None,
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `nox -s tests -- tests/hw_ci/test_fetch_xsa_cli.py`
Expected: FAIL — `_cmd_fetch_xsa` / `fetch_board_xsa` not defined.

- [ ] **Step 3: Add the command + subparser**

In `adi_lg_plugins/hw_ci/cli.py`:

Add a module-level import near the top (after the existing imports):

```python
from .kuiper_xsa import fetch_board_xsa
```

Add the command function (next to the other `_cmd_*` functions):

```python
def _cmd_fetch_xsa(args: argparse.Namespace) -> int:
    """Fetch a board's system_top.xsa from the Kuiper image; print its path."""
    xsa = fetch_board_xsa(
        args.release,
        args.board,
        args.carrier,
        cache_dir=args.out,
        xsa_dir=args.xsa_dir,
    )
    print(xsa)
    return 0
```

Register the subparser inside `main()`, alongside the existing `sub.add_parser("request-matrix"/"noos-matrix", …)` registrations (the `sub = p.add_subparsers(...)` object):

```python
    px = sub.add_parser("fetch-xsa", help="extract a board's system_top.xsa from the Kuiper image")
    px.add_argument("--release", required=True, help="Kuiper release (e.g. 2023_R2_P1)")
    px.add_argument("--board", required=True, help="canonical daughter-board (e.g. adrv9009)")
    px.add_argument("--carrier", required=True, help="FPGA carrier (e.g. zc706)")
    px.add_argument("--out", default=None, help="xsa cache dir (default ~/.labgrid/kuiper_xsa)")
    px.add_argument("--xsa-dir", default=None, help="pin the Kuiper boot folder, skip FAT search")
    px.set_defaults(func=_cmd_fetch_xsa)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `nox -s tests -- tests/hw_ci/test_fetch_xsa_cli.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add adi_lg_plugins/hw_ci/cli.py tests/hw_ci/test_fetch_xsa_cli.py
git commit -m "feat(hw_ci): add 'adi-lg-hw-ci fetch-xsa' subcommand"
```

---

## Task 11: `build_noos.py` — env composition + `make` orchestration

**Files:**
- Create: `adi_lg_plugins/hw_ci/build_noos.py`
- Test: `tests/hw_ci/test_build_noos.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/hw_ci/test_build_noos.py`:

```python
import zipfile
from pathlib import Path

import pytest

from adi_lg_plugins.hw_ci import build_noos


def test_detect_vivado_prefers_explicit_env(monkeypatch):
    monkeypatch.setenv("VITIS_SETTINGS", "/custom/settings64.sh")
    assert build_noos.detect_vivado_settings() == Path("/custom/settings64.sh")


def test_detect_vivado_globs_newest(monkeypatch):
    monkeypatch.delenv("VITIS_SETTINGS", raising=False)
    found = [
        "/opt/Xilinx/Vivado/2023.2/settings64.sh",
        "/opt/Xilinx/Vivado/2025.1/settings64.sh",
    ]
    monkeypatch.setattr(build_noos.glob, "glob", lambda p: found if "opt" in p else [])
    assert build_noos.detect_vivado_settings() == Path(found[-1])


def test_detect_vivado_errors_when_absent(monkeypatch):
    monkeypatch.delenv("VITIS_SETTINGS", raising=False)
    monkeypatch.setattr(build_noos.glob, "glob", lambda p: [])
    with pytest.raises(FileNotFoundError):
        build_noos.detect_vivado_settings()


def test_ensure_libtinfo_shim_idempotent(tmp_path, monkeypatch):
    so6 = tmp_path / "libtinfo.so.6"
    so6.write_bytes(b"")
    monkeypatch.setattr(build_noos, "_find_so6", lambda stem: so6 if stem == "libtinfo" else so6)
    shim = tmp_path / "xlnxshim"

    d1 = build_noos.ensure_libtinfo_shim(str(shim))
    d2 = build_noos.ensure_libtinfo_shim(str(shim))  # second call must not raise
    assert (Path(d1) / "libtinfo.so.5").is_symlink()
    assert d1 == d2


def test_build_noos_orchestration_order(tmp_path, monkeypatch):
    noos_root = tmp_path
    proj_dir = noos_root / "projects" / "ad9371"
    proj_dir.mkdir(parents=True)

    # a fake .xsa (a zip carrying ps7_init.tcl + system_top.bit)
    xsa = tmp_path / "system_top.xsa"
    with zipfile.ZipFile(xsa, "w") as z:
        z.writestr("ps7_init.tcl", "init")
        z.writestr("system_top.bit", "bits")

    monkeypatch.setattr(build_noos, "fetch_board_xsa", lambda *a, **k: xsa)
    monkeypatch.setattr(build_noos, "detect_vivado_settings", lambda: Path("/x/settings64.sh"))
    monkeypatch.setattr(build_noos, "source_env", lambda s: {"XILINX_VIVADO": "/x"})
    monkeypatch.setattr(build_noos, "ensure_libtinfo_shim", lambda: tmp_path / "shim")

    calls = {}

    def fake_run(cmd, **kw):
        calls["cmd"] = cmd
        calls["env"] = kw.get("env")
        calls["cwd"] = kw.get("cwd")
        # simulate the .elf the build produces
        (proj_dir / "build").mkdir(exist_ok=True)
        (proj_dir / "build" / "ad9371.elf").write_bytes(b"elf")

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(build_noos.subprocess, "run", fake_run)

    arts = build_noos.build_noos(
        project="ad9371",
        carrier="zc706",
        board="adrv9371",
        release="2023_R2_P1",
        build_vars={"EXAMPLE": "iio_example"},
        noos_root=str(noos_root),
    )

    # .xsa copied into the project; bit + ps7_init extracted to build_hw/
    assert (proj_dir / "system_top.xsa").exists()
    assert (proj_dir / "build_hw" / "ps7_init.tcl").exists()
    assert (proj_dir / "build_hw" / "system_top.bit").exists()
    # make invoked in the project dir with the build var + composed env
    assert calls["cmd"][:3] == ["make", "-C", str(proj_dir)]
    assert "EXAMPLE=iio_example" in calls["cmd"]
    assert calls["env"]["NOOS_VITIS_HSI_FLOW"] == "1"
    assert calls["env"]["XILINX_VIVADO"] == "/x"
    assert str(tmp_path / "shim") in calls["env"]["LD_LIBRARY_PATH"]
    assert Path(arts["elf"]).name == "ad9371.elf"
    assert Path(arts["bitstream"]).name == "system_top.bit"
    assert Path(arts["ps7_init"]).name == "ps7_init.tcl"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `nox -s tests -- tests/hw_ci/test_build_noos.py`
Expected: FAIL — `ModuleNotFoundError: adi_lg_plugins.hw_ci.build_noos`.

- [ ] **Step 3: Write `build_noos.py`**

Create `adi_lg_plugins/hw_ci/build_noos.py`:

```python
"""Build a no-os reference project for hardware CI: compose the Vivado/Vitis
environment (proven on the lab runners), fetch the board's ``.xsa`` from Kuiper,
and orchestrate ``make`` — collapsing the DUT's inline build shell into one
unit-tested entry point.

The lab/toolchain knowledge that used to live in no-os's ``build-cmd`` lives
here: Vivado auto-detect + sourcing under ``set +u`` (2025.1 unbound-PYTHONPATH
quirk), the libtinfo ``.so.5``→``.so.6`` shim (Vitis on Ubuntu 24.04), the
``NOOS_VITIS_HSI_FLOW`` flag (pure-hsi flow, no Eclipse backend), and the
``.xsa`` → ``system_top.bit`` / ``ps7_init.tcl`` extraction the JTAG flash needs.
"""

from __future__ import annotations

import glob
import logging
import os
import subprocess
import zipfile
from pathlib import Path

from .kuiper_xsa import fetch_board_xsa

logger = logging.getLogger(__name__)

_VIVADO_GLOBS = (
    "/opt/Xilinx/Vivado/*/settings64.sh",
    "/tools/Xilinx/*/Vivado/settings64.sh",
)
_SHIM_STEMS = ("libtinfo", "libncurses", "libncursesw")
_SO6_SEARCH = (
    "/usr/lib/x86_64-linux-gnu",
    "/usr/lib",
    "/lib/x86_64-linux-gnu",
    "/usr/lib64",
)


def detect_vivado_settings() -> Path:
    """Return the Vivado ``settings64.sh`` to source: ``$VITIS_SETTINGS`` if set,
    else the newest match under the known install roots."""
    explicit = os.environ.get("VITIS_SETTINGS")
    if explicit:
        return Path(explicit)
    found: list[str] = []
    for pat in _VIVADO_GLOBS:
        found.extend(glob.glob(pat))
    if not found:
        raise FileNotFoundError(
            "no Vivado settings64.sh found under "
            f"{_VIVADO_GLOBS}; set VITIS_SETTINGS to the path"
        )
    return Path(sorted(found)[-1])


def source_env(settings: Path) -> dict[str, str]:
    """Source ``settings`` in a subshell (tolerating unbound vars under set -u)
    and capture the resulting environment as a dict."""
    out = subprocess.check_output(
        ["bash", "-c", f'set +u; source "{settings}" >/dev/null 2>&1; env -0'],
        text=True,
    )
    env: dict[str, str] = {}
    for chunk in out.split("\0"):
        if not chunk:
            continue
        key, _, value = chunk.partition("=")
        env[key] = value
    return env


def _find_so6(stem: str) -> Path | None:
    for d in _SO6_SEARCH:
        cand = Path(d) / f"{stem}.so.6"
        if cand.exists():
            return cand
    return None


def ensure_libtinfo_shim(shim_dir: str | None = None) -> Path:
    """Ensure ``<shim_dir>/{libtinfo,libncurses,libncursesw}.so.5`` exist as
    symlinks to the system ``.so.6`` (idempotent). Returns the shim dir."""
    shim = Path(shim_dir or Path.home() / ".local" / "xlnxshim")
    shim.mkdir(parents=True, exist_ok=True)
    for stem in _SHIM_STEMS:
        link = shim / f"{stem}.so.5"
        if link.exists() or link.is_symlink():
            continue
        target = _find_so6(stem)
        if target is None:
            raise FileNotFoundError(
                f"cannot find {stem}.so.6 on host (install lib{stem}6) to build the shim"
            )
        link.symlink_to(target)
    return shim


def compose_build_env(settings: Path) -> dict[str, str]:
    """Full environment for the no-os make: base env + Vivado env + the libtinfo
    shim on LD_LIBRARY_PATH + the pure-hsi flow flag."""
    env = dict(os.environ)
    env.update(source_env(settings))
    shim = ensure_libtinfo_shim()
    env["LD_LIBRARY_PATH"] = os.pathsep.join(
        [str(shim), env.get("LD_LIBRARY_PATH", "")]
    ).rstrip(os.pathsep)
    env["NOOS_VITIS_HSI_FLOW"] = "1"
    return env


def build_noos(
    *,
    project: str,
    carrier: str,
    board: str,
    release: str,
    build_vars: dict[str, str] | None = None,
    noos_root: str = ".",
    xsa_dir: str | None = None,
) -> dict[str, str]:
    """Build ``projects/<project>`` and return artifact paths.

    Fetches the board's ``.xsa`` from the Kuiper ``release``, copies it into the
    project, extracts ``system_top.bit`` + ``ps7_init.tcl`` into ``build_hw/``
    (the JTAG flash inputs), and runs ``make`` with the composed env + build
    vars. Returns ``{"elf", "bitstream", "ps7_init"}`` host paths."""
    root = Path(noos_root)
    proj_dir = root / "projects" / project
    if not proj_dir.is_dir():
        raise FileNotFoundError(f"no-os project dir not found: {proj_dir}")

    settings = detect_vivado_settings()
    env = compose_build_env(settings)

    xsa = fetch_board_xsa(release, board, carrier, xsa_dir=xsa_dir)
    proj_xsa = proj_dir / "system_top.xsa"
    proj_xsa.write_bytes(Path(xsa).read_bytes())

    build_hw = proj_dir / "build_hw"
    build_hw.mkdir(exist_ok=True)
    with zipfile.ZipFile(xsa) as z:
        for name in ("ps7_init.tcl", "system_top.bit"):
            member = next((n for n in z.namelist() if Path(n).name == name), None)
            if member is None:
                raise FileNotFoundError(f"{name} not found inside {xsa}")
            (build_hw / name).write_bytes(z.read(member))

    cmd = ["make", "-C", str(proj_dir)]
    for key, value in (build_vars or {}).items():
        cmd.append(f"{key}={value}")
    logger.info("building no-os project %s: %s", project, " ".join(cmd))
    result = subprocess.run(cmd, env=env, cwd=str(root))
    if result.returncode != 0:
        raise RuntimeError(f"make failed for projects/{project} (exit {result.returncode})")

    arts = {
        "elf": str(proj_dir / "build" / f"{project}.elf"),
        "bitstream": str(build_hw / "system_top.bit"),
        "ps7_init": str(build_hw / "ps7_init.tcl"),
    }
    for label, path in arts.items():
        print(f"{label}={path}")
    return arts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `nox -s tests -- tests/hw_ci/test_build_noos.py && nox -s lint`
Expected: PASS; lint clean.

- [ ] **Step 5: Commit**

```bash
git add adi_lg_plugins/hw_ci/build_noos.py tests/hw_ci/test_build_noos.py
git commit -m "feat(hw_ci): build_noos — compose Vivado/shim env + orchestrate make + extract flash inputs"
```

---

## Task 12: `build-noos` CLI subcommand

**Files:**
- Modify: `adi_lg_plugins/hw_ci/cli.py` (add `_cmd_build_noos` + subparser)
- Test: `tests/hw_ci/test_build_noos_cli.py`

- [ ] **Step 1: Write the failing test**

Create `tests/hw_ci/test_build_noos_cli.py`:

```python
from types import SimpleNamespace

from adi_lg_plugins.hw_ci import cli as cli_mod


def test_build_noos_cmd_parses_build_vars(monkeypatch):
    captured = {}

    def fake_build_noos(**kw):
        captured.update(kw)
        return {"elf": "/x/ad9371.elf", "bitstream": "/x/b.bit", "ps7_init": "/x/p.tcl"}

    monkeypatch.setattr(cli_mod, "build_noos", fake_build_noos, raising=False)

    args = SimpleNamespace(
        project="ad9371",
        carrier="zc706",
        board="adrv9371",
        release="2023_R2_P1",
        validate="Done",
        build_var=["EXAMPLE=iio_example", "TINYIIOD=y"],
        noos_root=".",
        xsa_dir=None,
    )
    rc = cli_mod._cmd_build_noos(args)
    assert rc == 0
    assert captured["project"] == "ad9371"
    assert captured["build_vars"] == {"EXAMPLE": "iio_example", "TINYIIOD": "y"}


def test_build_noos_dispatches_through_main(monkeypatch):
    seen = {}

    def fake_build_noos(**kw):
        seen.update(kw)
        return {"elf": "/x/ad9371.elf", "bitstream": "/x/b.bit", "ps7_init": "/x/p.tcl"}

    monkeypatch.setattr(cli_mod, "build_noos", fake_build_noos, raising=False)
    rc = cli_mod.main(
        [
            "build-noos",
            "--project", "ad9371",
            "--carrier", "zc706",
            "--board", "adrv9371",
            "--release", "2023_R2_P1",
            "--build-var", "EXAMPLE=iio_example",
        ]
    )
    assert rc == 0
    assert seen["project"] == "ad9371"
    assert seen["build_vars"] == {"EXAMPLE": "iio_example"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `nox -s tests -- tests/hw_ci/test_build_noos_cli.py`
Expected: FAIL — `_cmd_build_noos` / `build_noos` not wired.

- [ ] **Step 3: Add the command + subparser**

In `adi_lg_plugins/hw_ci/cli.py`:

Add the module-level import (next to the `fetch_board_xsa` import):

```python
from .build_noos import build_noos
```

Add the command function:

```python
def _parse_build_vars(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"--build-var must be K=V, got {pair!r}")
        key, _, value = pair.partition("=")
        out[key] = value
    return out


def _cmd_build_noos(args: argparse.Namespace) -> int:
    """Build a no-os project for HW CI (Vivado env + Kuiper .xsa + make)."""
    build_noos(
        project=args.project,
        carrier=args.carrier,
        board=args.board,
        release=args.release,
        build_vars=_parse_build_vars(args.build_var),
        noos_root=args.noos_root,
        xsa_dir=args.xsa_dir,
    )
    return 0
```

Register the subparser inside `main()`, alongside the other `sub.add_parser(...)` registrations:

```python
    pb = sub.add_parser("build-noos", help="build a no-os project for HW CI (env + Kuiper .xsa)")
    pb.add_argument("--project", required=True, help="projects/<project> to build")
    pb.add_argument("--carrier", required=True, help="FPGA carrier (e.g. zc706)")
    pb.add_argument("--board", required=True, help="canonical daughter-board (e.g. adrv9371)")
    pb.add_argument("--release", required=True, help="Kuiper release for the .xsa (e.g. 2023_R2_P1)")
    pb.add_argument("--validate", default=None, help="on-target banner (informational here)")
    pb.add_argument(
        "--build-var", action="append", default=[], help="extra make var K=V (repeatable)"
    )
    pb.add_argument("--noos-root", default=".", help="no-os checkout root (default cwd)")
    pb.add_argument("--xsa-dir", default=None, help="pin the Kuiper boot folder, skip FAT search")
    pb.set_defaults(func=_cmd_build_noos)
```

> `--validate` is accepted for symmetry with the flash step (the workflow passes the manifest banner through to both `build-noos` and `request`); it does not change the build itself.

- [ ] **Step 4: Run tests to verify they pass**

Run: `nox -s tests -- tests/hw_ci/test_build_noos_cli.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add adi_lg_plugins/hw_ci/cli.py tests/hw_ci/test_build_noos_cli.py
git commit -m "feat(hw_ci): add 'adi-lg-hw-ci build-noos' subcommand"
```

---

## Task 13: Forward `a9_target_name` through the flash request

**Files:**
- Modify: `adi_lg_plugins/request/core.py` (flash branch ~189-204)
- Test: `tests/test_request_core.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_request_core.py` a test that the flash branch injects `a9_target_name` into the env subs when the catalog flash block supplies one. Follow the file's existing mocking pattern for `match_client.get_match`, `reservation.reserve_and_acquire`, `_render_env`, and `_boot`. Concretely, capture the `extra_subs` passed to `_render_env`:

```python
def test_flash_request_forwards_a9_target_name(monkeypatch, tmp_path):
    from adi_lg_plugins.request import core

    captured = {}

    monkeypatch.setattr(
        core.match_client,
        "get_match",
        lambda *a, **k: core.match_client.MatchResult(
            satisfiable=True,
            reservation_filter={"daughter-board": "adrv9371"},
            strategy="BootNoOSJTAG",
            place="bq",
            flash={"strategy": "BootNoOSJTAG", "noos_project": "ad9371",
                   "a9_target_name": "*Cortex-A9 MPCore #1"},
        ),
    )
    monkeypatch.setattr(
        core.reservation,
        "reserve_and_acquire",
        lambda *a, **k: type("R", (), {"place": "bq"})(),
    )
    monkeypatch.setattr(core, "_concrete_place", lambda api, name: type("P", (), {"boot_strategy": "BootNoOSJTAG"})())

    def fake_render_env(place, strategy=None, extra_subs=None):
        captured["subs"] = extra_subs
        return str(tmp_path / "env.yaml")

    monkeypatch.setattr(core, "_render_env", fake_render_env)
    monkeypatch.setattr(core, "_boot", lambda *a, **k: object())
    monkeypatch.setattr(core, "_get_console", lambda t: object())

    with core.request(part="ad9371", mode="flash", firmware="/x/ad9371.elf") as lease:
        assert lease.uri is None
    assert captured["subs"]["a9_target_name"] == "*Cortex-A9 MPCore #1"
```

> Adapt the mock target names (`_concrete_place`, `_get_console`, `_render_env`, `_boot`) to the actual symbols in `core.py` — grep the file to confirm exact names; the flash branch references `_render_env`, `_boot`, `_get_console` per the read above. If the real `request()` signature differs, align the call.

- [ ] **Step 2: Run test to verify it fails**

Run: `nox -s tests -- tests/test_request_core.py -k a9_target_name`
Expected: FAIL — `a9_target_name` not in the subs.

- [ ] **Step 3: Forward the override**

In `adi_lg_plugins/request/core.py`, in the `if mode == "flash":` branch, after the existing `subs` are built (and before `_render_env`), add:

```python
            if match.flash and match.flash.get("a9_target_name"):
                subs["a9_target_name"] = match.flash["a9_target_name"]
```

(`match.flash` is the dict from `match_client.MatchResult.flash`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `nox -s tests -- tests/test_request_core.py`
Expected: PASS (whole file, to confirm no flash/uri regression).

- [ ] **Step 5: Commit**

```bash
git add adi_lg_plugins/request/core.py tests/test_request_core.py
git commit -m "feat(request): forward catalog flash.a9_target_name into the BootNoOSJTAG env"
```

---

## Task 14: Trim the reusable `noos-hw-request.yml` to call `build-noos`

**Files:**
- Modify: `.github/workflows/noos-hw-request.yml`

> No unit test — this is a workflow. Validate by re-reading the diff for correctness; the end-to-end run is the Verification section.

- [ ] **Step 1: Change the `build-cmd` default**

In `.github/workflows/noos-hw-request.yml`, change the `build-cmd` input default from `make -C "projects/$NOOS_PROJECT"` to the `build-noos` invocation that consumes the matrix's `board`/`release`/`validate_banner`/`build_vars`. Replace the `build-cmd:` block's `default:` with:

```yaml
        default: |
          adi-lg-hw-ci build-noos \
            --project "$NOOS_PROJECT" \
            --carrier "$CARRIER" \
            --board "$BOARD" \
            --release "$RELEASE" \
            --validate "$VALIDATE_BANNER"
```

- [ ] **Step 2: Default the artifact paths to `build-noos`'s known outputs**

Change the input defaults:
- `firmware-path` default → `projects/$NOOS_PROJECT/build/$NOOS_PROJECT.elf` (already correct — keep).
- `bitstream-path` default → `projects/$NOOS_PROJECT/build_hw/system_top.bit`.
- `ps7-init-path` default → `projects/$NOOS_PROJECT/build_hw/ps7_init.tcl`.
- `validate-banner` default → `Successfully initialized`.

- [ ] **Step 3: Export the new matrix fields into the leg env**

In the `noos-hw-request` job's `env:` block, add the matrix-carried values so `build-cmd` and the flash step can read them:

```yaml
    env:
      LG_COORDINATOR: ${{ inputs.coordinator }}
      NOOS_PROJECT: ${{ matrix.noos_project }}
      CARRIER: ${{ matrix.carrier }}
      BOARD: ${{ matrix.board }}
      RELEASE: ${{ matrix.release }}
      VALIDATE_BANNER: ${{ matrix.validate_banner }}
```

And in the "Flash + validate" step, change the `--validate` argument to use the per-leg banner:

```yaml
                --validate "${{ matrix.validate_banner }}")
```

(Leave the `bitstream`/`ps7-init` conditional forwarding as-is — they now default to non-empty paths, so both branches fire.)

- [ ] **Step 4: Update the workflow header comment**

Replace the header note about provisioning the `.xsa` / `NOOS_XSA_DIR` with: "Per leg: `build-noos` sources the board's `.xsa` from the Kuiper image (no `NOOS_XSA_DIR`), composes the Vivado + libtinfo-shim env, and runs `make`; the runner only needs Vivado installed."

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/noos-hw-request.yml
git commit -m "feat(ci): noos-hw-request build-cmd defaults to 'adi-lg-hw-ci build-noos'"
```

---

## Task 15: Register the new test files in `tests.yml`

**Files:**
- Modify: `.github/workflows/tests.yml` (the explicit pytest file list, ~44-70)

- [ ] **Step 1: Add the new test files to the list**

In `.github/workflows/tests.yml`, in the `nox -s tests --` file list, add (keeping the existing entries):

```yaml
          tests/hw_ci/test_kuiper_xsa.py \
          tests/hw_ci/test_build_noos.py \
          tests/hw_ci/test_noos_manifest.py \
          tests/hw_ci/test_coordinator_resolve_api.py \
          tests/hw_ci/test_emit_matrix.py \
          tests/hw_ci/test_fetch_xsa_cli.py \
          tests/hw_ci/test_build_noos_cli.py \
          tests/test_kuiperdl_download_image.py \
```

- [ ] **Step 2: Verify the full new suite passes locally**

Run:

```bash
nox -s tests -- \
  tests/hw_ci/test_kuiper_xsa.py \
  tests/hw_ci/test_build_noos.py \
  tests/hw_ci/test_noos_manifest.py \
  tests/hw_ci/test_coordinator_resolve_api.py \
  tests/hw_ci/test_emit_matrix.py \
  tests/hw_ci/test_fetch_xsa_cli.py \
  tests/hw_ci/test_build_noos_cli.py \
  tests/hw_ci/test_noos_matrix.py \
  tests/test_kuiperdl_download_image.py \
  tests/test_bootnoosjtag_strat.py \
  tests/test_request_core.py
```

Expected: all PASS.

- [ ] **Step 3: Run coordinator tests**

Run: `cd coordinator/api && python -m pytest tests/test_catalog.py tests/test_matching.py tests/test_env_gen.py -q; cd -`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/tests.yml
git commit -m "ci: exercise the new hw_ci consolidation tests in CI"
```

---

## Task 16: Documentation

**Files:**
- Create: `docs/source/user-guide/hardware-ci-runner-setup.rst`
- Modify: `docs/source/user-guide/hw-request.rst`
- Modify: `docs/source/user-guide/hardware-ci.rst` (refresh the stale "flash deferred" note)
- Modify: `docs/source/user-guide/index.rst` (or the relevant toctree) to include the new page

- [ ] **Step 1: Confirm the docs toctree location**

Run: `grep -rn "hw-request" docs/source/user-guide/*.rst | head` and `sed -n '1,40p' docs/source/user-guide/index.rst`
Expected: identify the toctree that lists `hw-request` so the new page slots beside it.

- [ ] **Step 2: Write `hardware-ci-runner-setup.rst`**

Create `docs/source/user-guide/hardware-ci-runner-setup.rst`:

```rst
Hardware-CI Runner Setup (no-os flash mode)
===========================================

A no-os DUT repo opts into on-hardware CI with a project manifest and four
workflow inputs. The lab/toolchain logic (Vivado sourcing, the libtinfo shim,
the ``.xsa`` fetch) lives in ``adi-labgrid-plugins`` — the runner's only
requirement is a Vivado/Vitis install.

Runner requirements
-------------------

* A self-hosted GitHub Actions runner co-located with the board's JTAG cable.
* Vivado/Vitis installed. ``build-noos`` auto-detects
  ``/opt/Xilinx/Vivado/*/settings64.sh`` (or ``/tools/Xilinx/*/Vivado``); set
  ``VITIS_SETTINGS`` to override.
* Disk headroom for the Kuiper image (~3.5 GB, downloaded once per release and
  cached under ``~/.labgrid/kuiper_releases``; extracted ``.xsa`` files cache
  under ``~/.labgrid/kuiper_xsa``).

Register the runner with ``.github/scripts/register-hw-runners.sh`` (use
``--scopes`` to register one lab host against multiple GitHub scopes).

The manifest
------------

``tools/hw_ci/projects.yaml`` in the DUT repo:

.. code-block:: yaml

   projects:
     - noos_project: adrv9009     # projects/<noos_project>
       part: adrv9009             # coordinator part (may be a catalog alias)
       carriers: [zc706]          # FPGA carriers, preference order
       validate_banner: "Successfully initialized"   # optional; default shown
       build_vars: {}             # optional extra `make` vars

The consumer workflow
---------------------

.. code-block:: yaml

   jobs:
     noos-hw-request:
       uses: tfcollins/labgrid-plugins/.github/workflows/noos-hw-request.yml@main
       with:
         coordinator: ${{ vars.LG_COORDINATOR }}
         manifest: "tools/hw_ci/projects.yaml"
         runner-label: ${{ vars.HW_REQUEST_RUNNER }}
         preflight-runner-label: ${{ vars.HW_PREFLIGHT_RUNNER }}

What happens per leg
--------------------

#. **Discovery** (preflight): ``adi-lg-hw-ci noos-matrix`` intersects the
   manifest with the coordinator's live flash-capable boards and emits one leg
   per buildable project, carrying ``board``, ``release``, ``validate_banner``,
   and ``build_vars``.
#. **Build**: ``adi-lg-hw-ci build-noos`` sources Vivado, ensures the libtinfo
   shim, fetches the board's ``system_top.xsa`` from the Kuiper image, extracts
   ``system_top.bit`` + ``ps7_init.tcl``, and runs ``make``.
#. **Flash + validate**: ``adi-lg request --mode flash`` selects the board's
   ``BootNoOSJTAG`` strategy, JTAG-loads the firmware, and asserts the banner.

Troubleshooting
---------------

* *"Channel closed" during build* — handled automatically:
  ``NOOS_VITIS_HSI_FLOW=1`` uses the pure-``hsi`` flow (no Eclipse backend).
* *``libtinfo.so.5`` / ``libncurses.so.5`` not found* — handled automatically:
  ``build-noos`` creates a ``~/.local/xlnxshim`` symlink shim to the system
  ``.so.6``. Install ``libtinfo6``/``libncurses6`` if the shim target is absent.
* *Ambiguous Kuiper boot folder* — set ``flash.kuiper_xsa_dir`` on the board in
  the coordinator catalog (or pass ``--xsa-dir``) to pin the folder.
```

- [ ] **Step 3: Extend `hw-request.rst`**

In `docs/source/user-guide/hw-request.rst`, add a "Flash mode (no-os)" section documenting: `adi-lg request --mode flash --firmware <elf> [--bitstream <bit>] [--ps7-init <tcl>] --validate <banner>`, and that `adi-lg-hw-ci build-noos` produces those artifacts. Cross-link the new runner-setup page with ``:doc:`hardware-ci-runner-setup```.

- [ ] **Step 4: Refresh `hardware-ci.rst`**

In `docs/source/user-guide/hardware-ci.rst`, find the stale note that says flash mode is deferred/experimental (grep `flash` in that file) and update it to: flash mode is implemented end-to-end (build → JTAG-flash → on-target serial validation) via the `noos-hw-request.yml` reusable workflow; link the runner-setup page.

- [ ] **Step 5: Add the page to the toctree**

In the toctree identified in Step 1, add `hardware-ci-runner-setup` beside `hw-request`.

- [ ] **Step 6: Build the docs**

Run: `nox -s docs`
Expected: builds without warnings about the new file / missing toctree entry.

- [ ] **Step 7: Commit**

```bash
git add docs/source/user-guide/
git commit -m "docs: hardware-CI runner setup + flash-mode build-noos flow"
```

---

## Task 17 (optional, lower priority): Shared `hw-preflight` composite action

**Files:**
- Create: `.github/actions/hw-preflight/action.yml`
- Modify: `.github/workflows/hw-request.yml`, `.github/workflows/noos-hw-request.yml`

> The spec marks this lower priority. Implement only if Tasks 1-16 are green and time allows. The two preflight jobs (`setup-uv-venv` → `*-matrix --github-output` → outputs) are nearly identical; the only difference is the matrix subcommand (`request-matrix --test-root` vs `noos-matrix --manifest`).

- [ ] **Step 1: Write the composite action**

Create `.github/actions/hw-preflight/action.yml` with inputs `coordinator`, `venv-dir`, `install-cmd`, `matrix-cmd` (the full `adi-lg-hw-ci …-matrix … --github-output` line), and outputs `matrix`, `count`. Body: `setup-uv-venv` then run `${{ inputs.matrix-cmd }}` with `LG_COORDINATOR` set and `id: plan`, surfacing `steps.plan.outputs.{matrix,count}`.

- [ ] **Step 2: Use it in both workflows**

Replace each `preflight` job's steps with a single `uses: ./.github/actions/hw-preflight` (or `tfcollins/labgrid-plugins/.github/actions/hw-preflight@main` for cross-repo callers), passing the repo-specific `matrix-cmd`. Keep the job-level `outputs:` mapping to the action's outputs.

- [ ] **Step 3: Commit**

```bash
git add .github/actions/hw-preflight/action.yml .github/workflows/hw-request.yml .github/workflows/noos-hw-request.yml
git commit -m "refactor(ci): extract shared hw-preflight composite action"
```

---

## Final Verification

After all tasks:

- [ ] **Unit:** `nox -s lint` and the full new-suite run from Task 15 Step 2; `cd coordinator/api && python -m pytest tests/ -q`.
- [ ] **Live (no hardware):** redeploy the coordinator; `GET /api/match?part=adrv9009&mode=flash` returns `image` (the Kuiper release); `adi-lg-hw-ci fetch-xsa --release 2023_R2_P1 --board adrv9009 --carrier zc706` extracts the `.xsa` from the cached Kuiper image; `adi-lg-hw-ci noos-matrix --manifest …` emits the enriched legs (`board`/`release`/`validate_banner`/`build_vars`).
- [ ] **End-to-end:** in the no-os subrepo, trim `no-os/.github/workflows/hw-request.yml` to the four-input form (drop `build-cmd`/`bitstream-path`/`ps7-init-path`/`validate-banner`; they now default correctly), then re-run; both legs (ad9371/bq, adrv9009/nemo) stay green with no `NOOS_XSA_DIR` and no DUT `build-cmd`.

> The no-os workflow trim is a separate-subrepo change — commit it inside `no-os/` per the workspace CLAUDE.md, not in `labgrid-plugins`.
