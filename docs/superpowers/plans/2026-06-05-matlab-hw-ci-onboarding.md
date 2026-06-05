# MATLAB Hardware-CI Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Onboard TransceiverToolbox (MATLAB) onto the consolidated hardware-CI flow — a board-map discovery CLI + a reusable `matlab-hw-request.yml` whose per-leg uses the existing `adi-lg request` core to boot a board and run `runHWTests` against its libIIO URI — and fix the broken TransceiverToolbox consumer workflow.

**Architecture:** Mirror the no-os flash structure. A generic board-map module (`hw_ci/board_map.py`, restored from the deleted `matlab_ci/board_map.py`) maps a coordinator place's `(daughter-board, carrier, hdl-config)` tags to a MATLAB board name. A new `adi-lg-hw-ci matlab-matrix` preflight lists live places, looks each up in the board map, and emits a `{part, carrier, runner, matlab_board}` matrix. The reusable workflow's per-leg runs `adi-lg request --part … --run 'matlab -batch runHWTests(<matlab_board>)'` — no bespoke launcher. `runHWTests.m` already reads `IIO_URI` and emits JUnit, so it is untouched.

**Tech Stack:** Python 3.10+ (attrs/dataclasses, PyYAML, pytest, ruff, nox), GitHub Actions reusable workflows, MATLAB `-batch`.

---

## File Structure

**Hub (labgrid-plugins) — new:**
- `adi_lg_plugins/hw_ci/board_map.py` — board-map model + loader (generic) **and** `MatlabLeg` + `build_matlab_matrix` (the place→leg builder).
- `.github/workflows/matlab-hw-request.yml` — the reusable MATLAB workflow.
- `docs/source/onboarding-templates/matlab-hw-request.yml` — drop-in consumer template.
- Tests: `tests/hw_ci/test_board_map.py`, `tests/hw_ci/test_matlab_matrix.py`.

**Hub — modified:**
- `adi_lg_plugins/hw_ci/cli.py` — add the `matlab-matrix` subcommand (`_cmd_matlab_matrix` + subparser).
- `.github/workflows/tests.yml` — register the two new test files.
- `docs/source/user-guide/onboarding-a-consumer-repo.rst` — add a "matlab mode" section.
- `AGENTS.md` — add matlab to the decision tree + verify step.

**Consumer (TransceiverToolbox, separate subrepo) — modified:**
- `.github/workflows/hw-matlab.yml` — replace the dead `adi-lg-matlab` jobs with a thin call to the reusable workflow.

---

## Task 1: Restore the board-map module

**Files:**
- Create: `adi_lg_plugins/hw_ci/board_map.py`
- Test: `tests/hw_ci/test_board_map.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/hw_ci/test_board_map.py`:

```python
import pytest

from adi_lg_plugins.hw_ci.board_map import (
    BoardMap,
    BoardMapEntry,
    BoardMapError,
    load_board_map,
)
from adi_lg_plugins.hw_ci.schema import Place


def _place(name, daughter, carrier, hdl=None, runner="hw-x", acquired=None):
    return Place(
        name=name,
        carrier=carrier,
        daughter_board=daughter,
        boot_strategy="BootFPGASoC",
        hdl_config=hdl,
        acquired=acquired,
        extra_tags={"runner": runner},
    )


def test_lookup_returns_matlab_board_for_matching_place():
    bm = BoardMap(
        entries=(
            BoardMapEntry(matlab_board="zynqmp-zcu102-rev10-adrv9002-vcmos",
                          daughter_board="adrv9002", carrier="zcu102"),
        )
    )
    assert bm.lookup(_place("mini2", "adrv9002", "zcu102")) == "zynqmp-zcu102-rev10-adrv9002-vcmos"


def test_lookup_no_match_returns_none():
    bm = BoardMap(entries=(BoardMapEntry(matlab_board="x", daughter_board="adrv9009"),))
    assert bm.lookup(_place("mini2", "adrv9002", "zcu102")) is None


def test_lookup_most_specific_entry_wins():
    # A carrier+hdl-config entry must beat a bare daughter-board entry.
    bm = BoardMap(
        entries=(
            BoardMapEntry(matlab_board="generic", daughter_board="adrv9002"),
            BoardMapEntry(matlab_board="lvds", daughter_board="adrv9002",
                          carrier="zcu102", hdl_config="lvds"),
        )
    )
    assert bm.lookup(_place("m", "adrv9002", "zcu102", hdl="lvds")) == "lvds"
    assert bm.lookup(_place("m", "adrv9002", "zed")) == "generic"


def test_load_board_map_parses_boards_list(tmp_path):
    p = tmp_path / "board_map.yaml"
    p.write_text(
        "boards:\n"
        "  - {carrier: zcu102, daughter-board: adrv9002, matlab_board: zynqmp-zcu102-rev10-adrv9002-vcmos}\n"
        "  - {daughter-board: pluto, matlab_board: pluto}\n"
    )
    bm = load_board_map(str(p))
    assert len(bm.entries) == 2
    assert bm.entries[0].carrier == "zcu102"
    assert bm.entries[1].carrier is None  # carrier-agnostic


def test_load_board_map_rejects_entry_missing_required_keys(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("boards:\n  - {carrier: zcu102, matlab_board: foo}\n")  # no daughter-board
    with pytest.raises(BoardMapError):
        load_board_map(str(p))


def test_load_board_map_rejects_missing_boards_key(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("not_boards: []\n")
    with pytest.raises(BoardMapError):
        load_board_map(str(p))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `nox -s tests -- tests/hw_ci/test_board_map.py`
Expected: FAIL — `ModuleNotFoundError: adi_lg_plugins.hw_ci.board_map`.

- [ ] **Step 3: Create the module**

Create `adi_lg_plugins/hw_ci/board_map.py` (restored verbatim from the deleted
`adi_lg_plugins/matlab_ci/board_map.py` at git ref `a65f602^`; it already imports from
`adi_lg_plugins.hw_ci.schema`, so only its location changes):

```python
"""Map a coordinator place's tags to a MATLAB board reference name.

labgrid place tags describe hardware as ``(carrier, daughter-board,
hdl-config)`` — e.g. ``zcu102`` + ``adrv9002``. MATLAB toolboxes such as
TransceiverToolbox instead key their HW test entry points on long HDL
reference names (e.g. ``zynqmp-zcu102-rev10-adrv9002-vcmos``, the values
in ``runHWTests.m``'s ``switch``). This module bridges that gap with a
consumer-supplied YAML board map.

Board-map file format::

    boards:
      - {carrier: zcu102, daughter-board: adrv9002, matlab_board: zynqmp-zcu102-rev10-adrv9002-vcmos}
      - {daughter-board: ad9361, matlab_board: zynq-zed-adv7511-ad9361-fmcomms2-3}

Each entry must carry ``daughter-board`` and ``matlab_board``. ``carrier``
and ``hdl-config`` are optional narrowing keys: an entry with them set
only matches a place whose tags agree, and the *most specific* matching
entry wins. The loader/schema is generic; the file content is
toolbox-specific.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from adi_lg_plugins.hw_ci.schema import Place


class BoardMapError(ValueError):
    """The board-map file is missing, malformed, or has invalid entries."""


@dataclass(frozen=True)
class BoardMapEntry:
    """One ``(tags) -> matlab board name`` row of the board map."""

    matlab_board: str
    daughter_board: str
    carrier: str | None = None
    hdl_config: str | None = None

    @property
    def specificity(self) -> int:
        """How many optional narrowing keys this entry constrains."""
        return int(self.carrier is not None) + int(self.hdl_config is not None)

    def matches(self, place: Place) -> bool:
        if self.daughter_board != place.daughter_board:
            return False
        if self.carrier is not None and self.carrier != place.carrier:
            return False
        if self.hdl_config is not None and self.hdl_config != place.hdl_config:
            return False
        return True


@dataclass(frozen=True)
class BoardMap:
    """An ordered set of :class:`BoardMapEntry` rows."""

    entries: tuple[BoardMapEntry, ...]

    def lookup(self, place: Place) -> str | None:
        """Return the MATLAB board name for ``place``, or ``None``.

        Among all matching entries, the most specific (most narrowing
        keys) wins. Ties resolve to the first entry in file order.
        """
        matches = [e for e in self.entries if e.matches(place)]
        if not matches:
            return None
        best = max(matches, key=lambda e: e.specificity)
        return best.matlab_board


def load_board_map(path: str | Path) -> BoardMap:
    """Parse a board-map YAML file into a :class:`BoardMap`.

    Raises :class:`BoardMapError` on a missing file, non-mapping top
    level, missing ``boards:`` list, or an entry without the required
    ``daughter-board`` / ``matlab_board`` keys.
    """
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise BoardMapError(f"board-map file not found: {path}") from e
    except yaml.YAMLError as e:
        raise BoardMapError(f"board-map file {path} is not valid YAML: {e}") from e

    if not isinstance(raw, dict) or "boards" not in raw:
        raise BoardMapError(f"board-map file {path} must have a top-level 'boards:' list")
    boards = raw["boards"]
    if not isinstance(boards, list):
        raise BoardMapError(f"board-map file {path}: 'boards' must be a list")

    entries: list[BoardMapEntry] = []
    for i, row in enumerate(boards):
        if not isinstance(row, dict):
            raise BoardMapError(f"board-map file {path}: entry #{i} is not a mapping")
        daughter = row.get("daughter-board")
        matlab_board = row.get("matlab_board")
        if not daughter or not matlab_board:
            raise BoardMapError(
                f"board-map file {path}: entry #{i} must set both "
                f"'daughter-board' and 'matlab_board'; got {sorted(row)}"
            )
        entries.append(
            BoardMapEntry(
                matlab_board=str(matlab_board),
                daughter_board=str(daughter),
                carrier=str(row["carrier"]) if row.get("carrier") else None,
                hdl_config=str(row["hdl-config"]) if row.get("hdl-config") else None,
            )
        )
    return BoardMap(entries=tuple(entries))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `nox -s tests -- tests/hw_ci/test_board_map.py`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add adi_lg_plugins/hw_ci/board_map.py tests/hw_ci/test_board_map.py
git commit -m "feat(hw_ci): board_map module — map place tags to a MATLAB board name"
```

---

## Task 2: The place→leg matrix builder

**Files:**
- Modify: `adi_lg_plugins/hw_ci/board_map.py` (append `MatlabLeg` + `build_matlab_matrix`)
- Test: `tests/hw_ci/test_matlab_matrix.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/hw_ci/test_matlab_matrix.py`:

```python
from adi_lg_plugins.hw_ci.board_map import (
    BoardMap,
    BoardMapEntry,
    MatlabLeg,
    build_matlab_matrix,
)
from adi_lg_plugins.hw_ci.schema import Place


def _place(name, daughter, carrier, hdl=None, runner="hw-x", acquired=None):
    return Place(
        name=name,
        carrier=carrier,
        daughter_board=daughter,
        boot_strategy="BootFPGASoC",
        hdl_config=hdl,
        acquired=acquired,
        extra_tags={"runner": runner},
    )


_BM = BoardMap(
    entries=(
        BoardMapEntry(matlab_board="zynqmp-zcu102-rev10-adrv9002-vcmos",
                      daughter_board="adrv9002", carrier="zcu102"),
    )
)


def test_build_emits_one_leg_per_mapped_live_place():
    places = [_place("mini2", "adrv9002", "zcu102", runner="hw-mini2")]
    legs, skipped = build_matlab_matrix(places, _BM)
    assert skipped == []
    assert legs == [
        MatlabLeg(
            part="adrv9002",
            carrier="zcu102",
            runner="hw-mini2",
            matlab_board="zynqmp-zcu102-rev10-adrv9002-vcmos",
        )
    ]


def test_build_skips_unmapped_live_place():
    places = [_place("nuc", "daq3", "vcu118", runner="hw-nuc")]  # not in the board map
    legs, skipped = build_matlab_matrix(places, _BM)
    assert legs == []
    assert skipped == ["nuc"]


def test_build_skips_acquired_place():
    places = [_place("mini2", "adrv9002", "zcu102", acquired="someone")]
    legs, skipped = build_matlab_matrix(places, _BM)
    assert legs == []
    assert skipped == []  # acquired != unmapped; not annotated


def test_build_runner_defaults_to_none_when_no_runner_tag():
    p = Place(name="x", carrier="zcu102", daughter_board="adrv9002",
              boot_strategy="BootFPGASoC", extra_tags={})
    legs, _ = build_matlab_matrix([p], _BM)
    assert legs[0].runner is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `nox -s tests -- tests/hw_ci/test_matlab_matrix.py`
Expected: FAIL — `ImportError: cannot import name 'MatlabLeg'`.

- [ ] **Step 3: Append `MatlabLeg` + `build_matlab_matrix` to `board_map.py`**

First add `Iterable` to the imports at the top of `adi_lg_plugins/hw_ci/board_map.py`
(so the import block reads `from collections.abc import Iterable` then
`from dataclasses import dataclass`). Then add at the end of the file:

```python
@dataclass(frozen=True)
class MatlabLeg:
    """One MATLAB CI leg: which part/carrier to request + the MATLAB board name."""

    part: str  # = the place's daughter-board (what `adi-lg request --part` reserves)
    carrier: str
    runner: str | None  # the place's `runner` tag (CI runner label); None -> workflow fallback
    matlab_board: str  # the runHWTests(<board>) argument


def build_matlab_matrix(
    places: Iterable[Place],
    board_map: BoardMap,
) -> tuple[list[MatlabLeg], list[str]]:
    """Split live places into MATLAB legs + the names of unmapped (skipped) places.

    One leg per FREE place whose tags resolve to a MATLAB board name via
    ``board_map``. Acquired places are skipped silently (contention, not a config
    gap). A live, free place with no board-map entry is returned in ``skipped`` so
    the caller can annotate it (the toolbox has no test entry point for it)."""
    legs: list[MatlabLeg] = []
    skipped: list[str] = []
    for place in places:
        if place.is_acquired:
            continue
        matlab_board = board_map.lookup(place)
        if matlab_board is None:
            skipped.append(place.name)
            continue
        legs.append(
            MatlabLeg(
                part=place.daughter_board,
                carrier=place.carrier,
                runner=place.extra_tags.get("runner"),
                matlab_board=matlab_board,
            )
        )
    return legs, skipped
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `nox -s tests -- tests/hw_ci/test_matlab_matrix.py tests/hw_ci/test_board_map.py`
Expected: PASS (10 tests total).

- [ ] **Step 5: Commit**

```bash
git add adi_lg_plugins/hw_ci/board_map.py tests/hw_ci/test_matlab_matrix.py
git commit -m "feat(hw_ci): build_matlab_matrix — live places + board map -> CI legs"
```

---

## Task 3: The `matlab-matrix` CLI subcommand

**Files:**
- Modify: `adi_lg_plugins/hw_ci/cli.py` (add `_cmd_matlab_matrix` + subparser)
- Test: `tests/hw_ci/test_matlab_matrix_cli.py`

> Context: `cli.py` already has `_emit_matrix(matrix, *, count, missing, kind, github_output)`,
> `coord_mod.resolve_coordinator`, and `coord_mod.list_live_places(coord) -> (places, skipped)`.
> The argparse tree is built inside `def main(argv=None) -> int:`; `main` ends with
> `return ns.func(ns)`. Mirror `_cmd_noos_matrix`.

- [ ] **Step 1: Write the failing test**

Create `tests/hw_ci/test_matlab_matrix_cli.py`:

```python
import json
from types import SimpleNamespace

from adi_lg_plugins.hw_ci import cli as cli_mod
from adi_lg_plugins.hw_ci.schema import Place


def _place(name, daughter, carrier, runner):
    return Place(
        name=name, carrier=carrier, daughter_board=daughter,
        boot_strategy="BootFPGASoC", extra_tags={"runner": runner},
    )


def test_matlab_matrix_emits_legs_for_mapped_places(tmp_path, monkeypatch, capsys):
    board_map = tmp_path / "board_map.yaml"
    board_map.write_text(
        "boards:\n"
        "  - {carrier: zcu102, daughter-board: adrv9002, matlab_board: zynqmp-zcu102-rev10-adrv9002-vcmos}\n"
    )
    monkeypatch.setenv("LG_COORDINATOR", "10.0.0.41:20408")

    def fake_list_live_places(coord, **kw):
        return (
            [
                _place("mini2", "adrv9002", "zcu102", "hw-mini2"),
                _place("nuc", "daq3", "vcu118", "hw-nuc"),  # unmapped -> skipped
            ],
            [],
        )

    monkeypatch.setattr(cli_mod.coord_mod, "list_live_places", fake_list_live_places)

    args = SimpleNamespace(board_map=str(board_map), coord=None, github_output=False)
    rc = cli_mod._cmd_matlab_matrix(args)
    assert rc == 0

    out = capsys.readouterr()
    leg = json.loads(out.out)["include"][0]
    assert leg == {
        "part": "adrv9002",
        "carrier": "zcu102",
        "runner": "hw-mini2",
        "matlab_board": "zynqmp-zcu102-rev10-adrv9002-vcmos",
    }
    # the unmapped live place is annotated as a skip
    assert "::warning::" in out.err
    assert "nuc" in out.err


def test_matlab_matrix_parser_wires_via_main(monkeypatch, tmp_path):
    board_map = tmp_path / "bm.yaml"
    board_map.write_text("boards: []\n")
    monkeypatch.setenv("LG_COORDINATOR", "c:20408")
    monkeypatch.setattr(cli_mod.coord_mod, "list_live_places", lambda *a, **k: ([], []))
    rc = cli_mod.main(["matlab-matrix", "--board-map", str(board_map)])
    assert rc == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `nox -s tests -- tests/hw_ci/test_matlab_matrix_cli.py`
Expected: FAIL — `AttributeError: module ... has no attribute '_cmd_matlab_matrix'`.

- [ ] **Step 3: Add the command function**

In `adi_lg_plugins/hw_ci/cli.py`, add a module-level import near the other `from .` imports:

```python
from .board_map import build_matlab_matrix, load_board_map
```

Add the command function next to `_cmd_noos_matrix`:

```python
def _cmd_matlab_matrix(args: argparse.Namespace) -> int:
    """Emit a MATLAB CI matrix: live places that resolve to a MATLAB board (via the
    consumer's board map). Each leg carries the part/carrier to request + the
    matlab_board to pass to runHWTests. Live places with no board-map entry are
    annotated as skipped (the toolbox has no test entry point for them)."""
    coord = coord_mod.resolve_coordinator(args.coord)
    board_map = load_board_map(args.board_map)
    places, _bad = coord_mod.list_live_places(coord)

    legs, skipped = build_matlab_matrix(places, board_map)
    matrix = {
        "include": [
            {
                "part": leg.part,
                "carrier": leg.carrier,
                "runner": leg.runner or "",
                "matlab_board": leg.matlab_board,
            }
            for leg in legs
        ]
    }
    _emit_matrix(
        matrix,
        count=len(legs),
        missing=skipped,
        kind="matlab-matrix",
        github_output=args.github_output,
    )
    print(
        f"# matlab-matrix: {len(places)} live place(s), {len(legs)} testable, "
        f"{len(skipped)} skipped (no board_map entry)",
        file=sys.stderr,
    )
    return 0
```

> Note: `_emit_matrix`'s per-item warning reads `"<kind>: '<item>' is wanted but no live
> board matches…"`. For matlab the `missing` items are live-but-unmapped place names, so
> the wording is slightly generic but conveys "skipped". That is acceptable and keeps the
> shared helper; do NOT fork `_emit_matrix`.

- [ ] **Step 4: Register the subparser inside `main()`**

In `adi_lg_plugins/hw_ci/cli.py`, alongside the other `sub.add_parser(...)` registrations:

```python
    pmm = sub.add_parser(
        "matlab-matrix",
        help="emit a MATLAB CI matrix from a board map + live coordinator places",
    )
    pmm.add_argument("--board-map", required=True, help="path to the consumer's board_map.yaml")
    pmm.add_argument("--coord", default=None)
    pmm.add_argument(
        "--github-output", action="store_true", help="also write matrix=/count= to $GITHUB_OUTPUT"
    )
    pmm.set_defaults(func=_cmd_matlab_matrix)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `nox -s tests -- tests/hw_ci/test_matlab_matrix_cli.py && nox -s lint`
Expected: PASS; lint clean.

- [ ] **Step 6: Commit**

```bash
git add adi_lg_plugins/hw_ci/cli.py tests/hw_ci/test_matlab_matrix_cli.py
git commit -m "feat(hw_ci): add 'adi-lg-hw-ci matlab-matrix' subcommand"
```

---

## Task 4: The reusable `matlab-hw-request.yml` workflow

**Files:**
- Create: `.github/workflows/matlab-hw-request.yml`

> No unit test (it's a workflow). Validate by YAML-parsing + careful review; the live run is
> deferred. Mirror `.github/workflows/noos-hw-request.yml`'s shape.

- [ ] **Step 1: Create the workflow**

Create `.github/workflows/matlab-hw-request.yml`:

```yaml
name: MATLAB HW Request

# Reusable workflow: boot a matching board via labgrid, run the MATLAB toolbox's
# runHWTests(<board>) against the booted board's libIIO URI, collect JUnit, release.
# Discovery: the preflight runs `adi-lg-hw-ci matlab-matrix`, intersecting the consumer's
# board_map.yaml with the coordinator's live places. Each leg uses the same `adi-lg request`
# core as the uri/flash flows (reserve -> boot -> export IIO_URI -> run -> release).
#
# The leg runner must have MATLAB installed (+ a reachable license) and the libIIO libs.

on:
  workflow_call:
    inputs:
      coordinator:
        description: "gRPC coordinator host:port (e.g. host:20408)."
        required: true
        type: string
      board-map:
        description: "Path (in the consumer checkout) to the MATLAB board_map.yaml."
        type: string
        default: "test/hw_ci/board_map.yaml"
      runner-label:
        description: "Fallback self-hosted runner label for the per-board legs."
        type: string
        default: "hw-lab"
      preflight-runner-label:
        description: "Runner label for the discovery preflight (reaches the coordinator)."
        type: string
        default: "hw-coordinator"
      matlab-bin:
        description: "Path to the MATLAB binary on the leg runner."
        type: string
        default: "/opt/MATLAB/R2025b/bin/matlab"
      wait:
        description: "Seconds each leg queues for a free matching board (0 = fail fast)."
        type: number
        default: 1800
      venv-dir:
        description: "Absolute path for the persistent uv venv on the runner."
        type: string
        default: "$HOME/.cache/matlab-hw-request/venv"
      install-cmd:
        description: "Command (with $VENV_DIR exported) to install adi-labgrid-plugins."
        type: string
        default: >-
          uv pip install --quiet --python "$VENV_DIR/bin/python"
          "adi-labgrid-plugins @ git+https://github.com/tfcollins/labgrid-plugins@main"

jobs:
  preflight:
    runs-on: [self-hosted, "${{ inputs.preflight-runner-label }}"]
    outputs:
      matrix: ${{ steps.plan.outputs.matrix }}
      count: ${{ steps.plan.outputs.count }}
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive
      - uses: tfcollins/labgrid-plugins/.github/actions/setup-uv-venv@main
        with:
          venv_dir: ${{ inputs.venv-dir }}
          install_cmd: ${{ inputs.install-cmd }}
      - id: plan
        env:
          LG_COORDINATOR: ${{ inputs.coordinator }}
        run: |
          adi-lg-hw-ci matlab-matrix \
            --board-map "${{ inputs.board-map }}" \
            --coord "${{ inputs.coordinator }}" \
            --github-output

  matlab-hw-request:
    needs: preflight
    if: ${{ fromJSON(needs.preflight.outputs.count) > 0 }}
    runs-on: [self-hosted, "${{ matrix.runner || inputs.runner-label }}"]
    strategy:
      fail-fast: false
      matrix: ${{ fromJSON(needs.preflight.outputs.matrix) }}
    env:
      LG_COORDINATOR: ${{ inputs.coordinator }}
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: recursive
      - uses: tfcollins/labgrid-plugins/.github/actions/setup-uv-venv@main
        with:
          venv_dir: ${{ inputs.venv-dir }}
          install_cmd: ${{ inputs.install-cmd }}
      - name: Request ${{ matrix.part }} and run runHWTests(${{ matrix.matlab_board }})
        env:
          MATLAB_BIN: ${{ inputs.matlab-bin }}
          MATLAB_BOARD: ${{ matrix.matlab_board }}
        run: |
          set -euo pipefail
          # The MATLAB invocation runs *inside* the booted-board reservation: adi-lg
          # request exports IIO_URI (+ LG_PLACE/LG_CARRIER) and passes the parent env
          # (MATLAB_BIN/MATLAB_BOARD/GITHUB_WORKSPACE) to the child. runHWTests reads
          # IIO_URI itself. The quoted heredoc keeps the MATLAB string literal intact
          # (avoids nested-quote interpolation). Exit 3 (Incomplete/CheckDevice-skip)
          # is normalized to success, matching the prior MATLAB CI behavior.
          cat > run-matlab.sh <<'EOF'
          set +e
          "$MATLAB_BIN" -batch "cd('$GITHUB_WORKSPACE'); runHWTests('$MATLAB_BOARD')"
          rc=$?
          [ "$rc" -eq 3 ] && rc=0
          exit $rc
          EOF
          adi-lg request --part "${{ matrix.part }}" --carrier "${{ matrix.carrier }}" \
            --wait "${{ inputs.wait }}" --run "bash run-matlab.sh"
      - name: Upload JUnit
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: matlab-junit-${{ matrix.matlab_board }}
          path: "*_HWTestResults.xml"
          if-no-files-found: ignore
```

- [ ] **Step 2: Validate YAML**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/matlab-hw-request.yml')); print('YAML OK')"`
Expected: `YAML OK`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/matlab-hw-request.yml
git commit -m "feat(ci): reusable matlab-hw-request.yml (boot board + run runHWTests vs IIO_URI)"
```

---

## Task 5: Register the new tests in CI

**Files:**
- Modify: `.github/workflows/tests.yml`

- [ ] **Step 1: Add the two new test files**

In `.github/workflows/tests.yml`, in the `nox -s tests -- \` file list, add (keep the
existing entries + the backslash-continuation; do not duplicate; the final list entry must
not have a trailing `\`):

```
          tests/hw_ci/test_board_map.py \
          tests/hw_ci/test_matlab_matrix.py \
          tests/hw_ci/test_matlab_matrix_cli.py \
```

- [ ] **Step 2: Run the listed suite locally**

Run: `nox -s tests -- tests/hw_ci/test_board_map.py tests/hw_ci/test_matlab_matrix.py tests/hw_ci/test_matlab_matrix_cli.py`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/tests.yml
git commit -m "ci: exercise the MATLAB board_map + matlab-matrix tests"
```

---

## Task 6: Docs — onboarding guide, AGENTS.md, template

**Files:**
- Create: `docs/source/onboarding-templates/matlab-hw-request.yml`
- Modify: `docs/source/user-guide/onboarding-a-consumer-repo.rst`
- Modify: `AGENTS.md`

- [ ] **Step 1: Create the consumer template**

Create `docs/source/onboarding-templates/matlab-hw-request.yml`:

```yaml
# Template — copy into <consumer-repo>/.github/workflows/hw-matlab.yml; replace <PLACEHOLDERS>.
#
# matlab-mode hardware CI: labgrid boots a matching board; the leg runs the toolbox's
# runHWTests(<matlab_board>) against the booted board's libIIO URI; JUnit is collected;
# the board is released. Discovery intersects test/hw_ci/board_map.yaml with live boards.
# The leg runner must have MATLAB installed (+ a reachable license).
#
# Repo vars: ADI_LG_COORDINATOR (gRPC host:20408), HW_REQUEST_RUNNER, HW_PREFLIGHT_RUNNER,
#            MATLAB_BIN (path to the matlab binary on the runner).

name: HW MATLAB

on:
  workflow_dispatch:
  pull_request:
    types: [labeled]

jobs:
  hw-matlab:
    if: >-
      github.event_name == 'workflow_dispatch' ||
      contains(github.event.pull_request.labels.*.name, 'hw-test')
    uses: tfcollins/labgrid-plugins/.github/workflows/matlab-hw-request.yml@main
    with:
      coordinator: ${{ vars.ADI_LG_COORDINATOR }}    # MUST be the gRPC coordinator host:20408
      board-map: "test/hw_ci/board_map.yaml"
      runner-label: ${{ vars.HW_REQUEST_RUNNER }}
      preflight-runner-label: ${{ vars.HW_PREFLIGHT_RUNNER }}
      matlab-bin: ${{ vars.MATLAB_BIN }}
```

- [ ] **Step 2: Add a "matlab mode" section to the onboarding guide**

In `docs/source/user-guide/onboarding-a-consumer-repo.rst`, after the "flash mode" section,
add:

```rst
matlab mode (MATLAB ``runHWTests``)
-----------------------------------

**Workflow** — copy into ``.github/workflows/hw-matlab.yml``:

.. literalinclude:: ../onboarding-templates/matlab-hw-request.yml
   :language: yaml

**Board map** — ``test/hw_ci/board_map.yaml`` maps each board's
``(daughter-board, carrier, hdl-config)`` to the MATLAB board name passed to
``runHWTests`` (most-specific entry wins):

.. code-block:: yaml

   boards:
     - {carrier: zcu102, daughter-board: adrv9002, matlab_board: zynqmp-zcu102-rev10-adrv9002-vcmos}
     - {daughter-board: pluto, matlab_board: pluto}

``runHWTests.m`` reads the URI from ``$IIO_URI`` (exported by ``adi-lg request``) and emits
``<matlab_board>_HWTestResults.xml`` — no test-side changes are needed. The leg runner must
have MATLAB installed. Verify discovery with:

.. code-block:: bash

   export LG_COORDINATOR=<host>:20408
   adi-lg-hw-ci matlab-matrix --board-map test/hw_ci/board_map.yaml --coord "$LG_COORDINATOR"
```

Also update the **Step 1 decision-tree table** row for matlab so the "Reusable workflow"
column reads ``matlab-hw-request.yml`` and "Discovery" reads ``board_map.yaml``.

- [ ] **Step 3: Update `AGENTS.md`**

In `AGENTS.md`, in the Step-1 decision-tree table, change the matlab row's workflow to
``matlab-hw-request.yml`` and discovery to ``a board_map.yaml`` (it currently says
"(bespoke) hw-matlab.yml"). In the "Step 5 — verify" section, add the matlab verify line:

```
# matlab mode
adi-lg-hw-ci matlab-matrix --board-map test/hw_ci/board_map.yaml --coord "$LG_COORDINATOR"
```

And in Step 2's "matlab" note, change "not a drop-in template" to point at
``onboarding-templates/matlab-hw-request.yml`` (it now IS a drop-in).

- [ ] **Step 4: Build the docs**

Run: `nox -s docs`
Expected: builds; only the pre-existing warnings (xilinxjtagdriver docstring + coordinator
WebSocket JSON block); no new warnings from the new section / template.

- [ ] **Step 5: Commit**

```bash
git add docs/source/onboarding-templates/matlab-hw-request.yml \
        docs/source/user-guide/onboarding-a-consumer-repo.rst AGENTS.md
git commit -m "docs: matlab mode in the onboarding guide + AGENTS.md + drop-in template"
```

---

## Task 7: Fix the broken TransceiverToolbox consumer (separate subrepo)

**Files (in `/home/tcollins/dev/lg-test/TransceiverToolbox`, NOT labgrid-plugins):**
- Modify: `.github/workflows/hw-matlab.yml`

> Work inside the TransceiverToolbox subrepo per the workspace CLAUDE.md. Branch first
> (don't commit on its default branch). This is the only consumer-side change.
> ``runHWTests.m`` and ``test/hw_ci/board_map.yaml`` are NOT touched.

- [ ] **Step 1: Replace the dead `adi-lg-matlab` jobs with a thin reusable call**

In `TransceiverToolbox/.github/workflows/hw-matlab.yml`, keep the `name:` and the `on:`
triggers (`workflow_dispatch`, the scheduled `cron`, and the PR-label trigger), and replace
the `discover`/`hw`/`publish` jobs with:

```yaml
jobs:
  hw-matlab:
    if: >-
      github.event_name != 'pull_request' ||
      contains(github.event.pull_request.labels.*.name, 'hw-test')
    uses: tfcollins/labgrid-plugins/.github/workflows/matlab-hw-request.yml@main
    with:
      coordinator: ${{ vars.ADI_LG_COORDINATOR }}
      board-map: "test/hw_ci/board_map.yaml"
      runner-label: ${{ vars.HW_REQUEST_RUNNER }}
      preflight-runner-label: ${{ vars.HW_PREFLIGHT_RUNNER }}
      matlab-bin: ${{ vars.MATLAB_BIN }}
```

Update the header comment to note it now consumes the reusable `matlab-hw-request.yml`
(the bespoke `adi-lg-matlab` launcher is gone). Confirm `vars.ADI_LG_COORDINATOR` is the
**gRPC** coordinator (`host:20408`); if the repo var currently holds the REST `:8000`, note
that it must be updated for the leg's `adi-lg request` to reserve.

- [ ] **Step 2: Validate YAML**

Run: `cd /home/tcollins/dev/lg-test/TransceiverToolbox && python3 -c "import yaml; yaml.safe_load(open('.github/workflows/hw-matlab.yml')); print('YAML OK')"`
Expected: `YAML OK`.

- [ ] **Step 3: Commit (on a branch in the TransceiverToolbox repo)**

```bash
cd /home/tcollins/dev/lg-test/TransceiverToolbox
git checkout -b ci/matlab-hw-request
git add .github/workflows/hw-matlab.yml
git commit -m "ci(hw-matlab): consume the labgrid-plugins matlab-hw-request reusable workflow

The bespoke adi-lg-matlab launcher was removed from labgrid-plugins; migrate to
the consolidated reusable workflow (board_map discovery -> adi-lg request -> runHWTests)."
```

---

## Final Verification

After all tasks:

- [ ] **Unit + lint + docs:** `nox -s lint`; the full new-suite run from Task 5 Step 2;
  `nox -s docs` (clean).
- [ ] **Live discovery half (no MATLAB run — deferred per the spec):** against the live
  coordinator,
  `adi-lg-hw-ci matlab-matrix --board-map /home/tcollins/dev/lg-test/TransceiverToolbox/test/hw_ci/board_map.yaml --coord 10.0.0.41:20408`
  emits legs for the mapped live boards (e.g. `adrv9002/zcu102 →
  zynqmp-zcu102-rev10-adrv9002-vcmos` on `hw-mini2`; adrv9009/adrv9371 if their places are
  live) and annotates unmapped live places (e.g. daq3) as skipped. The `count` is > 0.
- [ ] **Deferred (documented, not executed):** the end-to-end leg
  (`adi-lg request … --run 'matlab … runHWTests'`) on a MATLAB-equipped runner against the
  booted adrv9002 board. Prerequisites: a self-hosted runner with MATLAB + a reachable
  license + the booted board; the TransceiverToolbox repo vars set (`ADI_LG_COORDINATOR`
  gRPC, `HW_REQUEST_RUNNER`, `HW_PREFLIGHT_RUNNER`, `MATLAB_BIN`); lab runners registered on
  the TransceiverToolbox repo scope.
```
