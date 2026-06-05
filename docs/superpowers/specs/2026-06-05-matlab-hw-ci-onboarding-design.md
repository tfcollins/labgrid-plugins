# MATLAB Hardware-CI Onboarding — Design

**Date:** 2026-06-05
**Status:** Approved (architecture + components + data flow); spec under review.

## Context

The low-config hardware-test flow now drives two of the three ADI test surfaces:
`pyadi-iio` (uri mode — Python/pytest against a booted board's libIIO URI) and `no-os`
(flash mode — build firmware, JTAG-flash, validate on serial). The third surface,
**TransceiverToolbox (MATLAB)**, runs `runHWTests(board)` against a booted board's URI —
but its CI (`TransceiverToolbox/.github/workflows/hw-matlab.yml`) is currently **broken**:
it calls an `adi-lg-matlab discover/run` launcher that was **removed** from labgrid-plugins
on 2026-05-23 (commit `a65f602`, whose message states *"the pyadi-iio pattern is the right
shape for MATLAB toolboxes too"*). The migration was started (the bespoke launcher deleted)
but never finished, leaving the consumer workflow calling a command that no longer exists.

This design finishes the migration: it onboards MATLAB onto the **consolidated
reusable-workflow pattern**, mirroring the no-os flash flow. MATLAB reuses the existing
`adi-lg request` core (reserve → boot → export `IIO_URI` → run a child command → release)
with `runHWTests` as the child command — no bespoke launcher, no duplicated boot/URI/release
code.

Two facts make this clean (verified by exploration):
- `runHWTests.m` already reads `IIO_URI` from the environment (each test class' `uri`
  property is overwritten from `getenv('IIO_URI')` in `TestClassSetup`), and already emits
  JUnit (`<matlab_board>_HWTestResults.xml`) with exit codes `0`=pass / `2`=fail /
  `3`=incomplete-skip / `1`=error. **No MATLAB-side changes are needed.**
- `TransceiverToolbox/test/hw_ci/board_map.yaml` already exists and maps
  `(daughter-board, carrier, hdl-config) → matlab_board`. **No change needed.**

The only MATLAB-specific need vs. the uri flow is **discovery** (a board_map instead of
`@pytest.mark.iio_hardware` markers) and carrying the resolved **`matlab_board`** name into
the per-board leg.

## Goals / Non-goals

**Goals**
- A generic board-map module in the hub (`adi_lg_plugins/hw_ci/board_map.py`).
- A discovery subcommand `adi-lg-hw-ci matlab-matrix` (board_map ∩ live places → matrix).
- A reusable workflow `.github/workflows/matlab-hw-request.yml` whose per-leg uses
  `adi-lg request --run '<matlab cmd>'`.
- Fix `TransceiverToolbox/.github/workflows/hw-matlab.yml` to a thin consumer of the
  reusable workflow.
- Unit tests for the new module + CLI; verify the **discovery half** against the live
  coordinator.
- Docs: extend the onboarding guide + `AGENTS.md` so MATLAB is a first-class mode (a real
  reusable workflow, not "bespoke").

**Non-goals (explicitly deferred)**
- The actual `matlab -batch runHWTests(...)` run on hardware (adrv9002/mini2). It needs a
  self-hosted runner with MATLAB + a reachable license + the booted board. Documented as
  the final step; **not executed** in this work.
- Any change to `runHWTests.m` or `board_map.yaml` (already compatible).
- Restoring the deleted `adi-lg-matlab` launcher (the chosen direction is the consolidated
  pattern, not the bespoke tool).
- Merging the reusable workflows into one (uri/flash/matlab legs differ; keep them
  separate, as with no-os).

## Architecture

```
TransceiverToolbox (consumer):            labgrid-plugins (hub):
  test/hw_ci/board_map.yaml  ──┐
  .github/workflows/             │   .github/workflows/matlab-hw-request.yml
    hw-matlab.yml (4 inputs) ────┼──▶   preflight:  adi-lg-hw-ci matlab-matrix
                                 │        → matrix[{part, carrier, runner, matlab_board}]
  test/runHWTests.m            │       per leg (runs-on: matrix.runner == hw-<place>):
    (reads $IIO_URI) ◀──────────┘         adi-lg request --part <part> --carrier <carrier>
                                            --run 'matlab -batch "runHWTests(<matlab_board>)"'
                                          → reserve → boot (place boot-strategy) → export
                                            IIO_URI → run MATLAB → collect JUnit → release
```

**Discovery is place-centric** (unlike pyadi's marker harvest). `matlab-matrix` lists the
live coordinator places (full tag set) and looks each up in the consumer's `board_map.yaml`
— matching on `daughter-board` (required) plus optional `carrier`/`hdl-config`, **most
specific entry wins**. Each live place that maps to a `matlab_board` becomes one CI leg.
The leg then drives the **existing** `adi-lg request` core; MATLAB adds no new
reservation/boot logic.

## Components

### 1. `adi_lg_plugins/hw_ci/board_map.py` (new)

Restore + adapt the logic from the deleted `adi_lg_plugins/matlab_ci/board_map.py` into a
generic `hw_ci` module (it is not MATLAB-specific — any board-name-mapped harness can use
it):

```python
@dataclass(frozen=True)
class BoardMapEntry:
    matlab_board: str
    daughter_board: str
    carrier: str | None = None
    hdl_config: str | None = None
    @property
    def specificity(self) -> int: ...        # carrier? + hdl_config?
    def matches(self, place: Place) -> bool: ...  # daughter-board req; carrier/hdl-config narrow

@dataclass(frozen=True)
class BoardMap:
    entries: tuple[BoardMapEntry, ...]
    def lookup(self, place: Place) -> str | None:   # best (most-specific) match's matlab_board

def load_board_map(path: str) -> BoardMap:          # parse + validate the YAML
```

It consumes the existing `Place` schema (`adi_lg_plugins/hw_ci/schema.py`), whose tags
include `daughter-board`, `carrier`, and the optional `hdl-config`. The `board_map.yaml`
top-level key is `boards:` (a list of `{carrier?, daughter-board, hdl-config?, matlab_board}`),
matching the existing TransceiverToolbox file.

### 2. `adi-lg-hw-ci matlab-matrix` (new subcommand in `hw_ci/cli.py`)

`adi-lg-hw-ci matlab-matrix --board-map <yaml> [--coord <host:port>] [--github-output]`:
- `coord = resolve_coordinator(args.coord)`; `places, skipped = list_live_places(coord)`
  (reuse `hw_ci/coordinator.py` — the **same place discovery the `discover` and `render-env`
  preflights already use**: it reads the coordinator's REST `/api/places` and falls back to
  the `labgrid-client` CLI). Unlike `request-matrix`/`noos-matrix`, matlab-matrix is
  place-centric, so it lists places rather than probing `/api/match` per part.
- For each live place: `matlab_board = board_map.lookup(place)`. If found, emit a leg
  `{part: place.daughter_board, carrier: place.carrier, runner: place.runner or "",
  matlab_board}`. Skip (annotate) live places with no board-map entry.
- Emit via the shared `_emit_matrix(matrix, count, missing, kind="matlab-matrix",
  github_output=...)` helper (same as request-matrix / noos-matrix).
- A small pure helper `build_matlab_matrix(places, board_map) -> (legs, skipped)` holds the
  logic for unit testing (mirrors `build_request_matrix` / `build_noos_matrix`).

### 3. `.github/workflows/matlab-hw-request.yml` (new reusable workflow)

Mirrors `noos-hw-request.yml`'s shape:
- **inputs**: `coordinator` (required), `board-map` (default `test/hw_ci/board_map.yaml`),
  `runner-label` (default `hw-lab`), `preflight-runner-label` (default `hw-coordinator`),
  `matlab-bin` (default `/opt/MATLAB/R2025b/bin/matlab`), `wait` (default 1800),
  `reached-state` (default `shell`), `venv-dir`, `install-cmd` (default installs
  `adi-labgrid-plugins@main`), `run-cmd` (default the MATLAB invocation below).
- **preflight** (on `preflight-runner-label`): `adi-lg-hw-ci matlab-matrix --board-map …
  --coord … --github-output` → outputs `matrix`, `count`.
- **matlab-hw-request leg** (`runs-on: [self-hosted, "${{ matrix.runner || inputs.runner-label }}"]`,
  one per matrix entry; `submodules: recursive` checkout for the toolbox):
  - `adi-lg request --part "${{ matrix.part }}" --carrier "${{ matrix.carrier }}"
    --wait "${{ inputs.wait }}" --run "<run-cmd>"`.
  - default `run-cmd`: `"${MATLAB_BIN}" -batch "cd('$GITHUB_WORKSPACE'); runHWTests('${MATLAB_BOARD}')"`
    with `MATLAB_BIN` / `MATLAB_BOARD` exported from `inputs.matlab-bin` /
    `matrix.matlab_board`.
  - JUnit `*_HWTestResults.xml` uploaded as an artifact per leg.

### 4. `TransceiverToolbox/.github/workflows/hw-matlab.yml` (fix the broken consumer)

Replace the dead `adi-lg-matlab discover/run` jobs with a thin call:

```yaml
jobs:
  hw-matlab:
    uses: tfcollins/labgrid-plugins/.github/workflows/matlab-hw-request.yml@main
    with:
      coordinator: ${{ vars.ADI_LG_COORDINATOR }}    # MUST be the gRPC coordinator host:20408
      board-map: "test/hw_ci/board_map.yaml"
      runner-label: ${{ vars.HW_REQUEST_RUNNER }}
      preflight-runner-label: ${{ vars.HW_PREFLIGHT_RUNNER }}
      matlab-bin: ${{ vars.MATLAB_BIN }}
```

Keep its existing triggers (`workflow_dispatch`, the scheduled cron, PR label). **No change
to `runHWTests.m` or `board_map.yaml`.** This fix lands in the TransceiverToolbox repo (a
separate subrepo) and is the only consumer-side change.

## Data flow (one leg)

1. preflight `matlab-matrix` → `{part: adrv9002, carrier: zcu102, runner: hw-mini2,
   matlab_board: zynqmp-zcu102-rev10-adrv9002-vcmos}`.
2. leg lands on `hw-mini2`; `adi-lg request --part adrv9002 --carrier zcu102 --run '<matlab>'`.
3. `request()` reserves the place, boots it via the place's `boot-strategy` tag, resolves
   the URI, exports `IIO_URI` (+ `LG_PLACE`, `LG_CARRIER`) into the child env.
4. child runs `matlab -batch "runHWTests('zynqmp-zcu102-rev10-adrv9002-vcmos')"`;
   `runHWTests` reads `IIO_URI`, runs the matched test classes, writes
   `<matlab_board>_HWTestResults.xml`, exits 0/2/3/1.
5. workflow normalizes exit 3 → 0, uploads the JUnit, and `request()` releases the place
   (always).

## Run command & exit codes

`runHWTests` exit semantics: `0` pass, `2` fail, `3` incomplete (a test `assumeFail`ed via
`CheckDevice` — treated as skip), `1` exception. The old bespoke flow treated **`3` as
success**. The reusable workflow preserves that: the leg wraps the `--run` command so an
exit of `3` maps to `0`, while `0`/`2`/`1` propagate unchanged (`adi-lg request` already
forwards the child's exit code). The wrapper is a one-line shell guard in the workflow's
`run-cmd` default, not MATLAB or Python code.

## Error handling

- **Unmapped live place**: `matlab-matrix` annotates it as a skip (`::warning::`) and omits
  it from the matrix — never fails discovery.
- **No live board for any board-map entry**: `count=0`; the leg job is gated on
  `count > 0` (as in noos-hw-request) so the workflow is green-with-annotations, not failed.
- **Malformed board_map.yaml**: `load_board_map` raises a clear error (missing
  `daughter-board`/`matlab_board`).
- **MATLAB/license/runner failures** (deferred hardware path): surface as the leg's exit
  code; documented in the onboarding guide's troubleshooting.

## Testing / Verification

- **Unit (no hardware, added to `.github/workflows/tests.yml`)**:
  - `board_map.py`: load + validate (good / missing-key); `lookup` match, specificity
    (carrier+hdl-config beats carrier-only beats bare), and no-match → None.
  - `matlab-matrix`: `build_matlab_matrix` emits a leg per mapped live place with the right
    `matlab_board`/`runner`, skips unmapped places; the CLI emits the 4-key include and uses
    `_emit_matrix`.
- **Live (no MATLAB run — per the deferral)**: deploy nothing new coordinator-side;
  `adi-lg-hw-ci matlab-matrix --board-map TransceiverToolbox/test/hw_ci/board_map.yaml
  --coord <live>` against the real coordinator yields the expected legs (e.g. adrv9002/zcu102
  → `zynqmp-zcu102-rev10-adrv9002-vcmos`, with the place's runner). This is the same
  "discovery-half" proof used for the pyadi and no-os first cuts.
- **Deferred (documented, not run)**: the end-to-end `matlab -batch runHWTests` leg on a
  MATLAB-equipped runner against the booted adrv9002 board.
- **Docs**: add a "matlab mode" path to `onboarding-a-consumer-repo.rst` and the `AGENTS.md`
  decision tree (matlab now has a reusable workflow + a `matlab-matrix` verify step), and a
  consumer-workflow template `docs/source/onboarding-templates/matlab-hw-request.yml`.

## Risks

- **MATLAB on the runner** (deferred): the leg runner needs MATLAB + a reachable license +
  the toolbox build (submodule init). Out of scope now, but the gating prerequisite for the
  hardware run.
- **board_map ↔ runHWTests.m drift**: the two duplicate board-name knowledge (the YAML
  header already warns). Not changed here; noted as existing tech debt.
- **hdl-config narrowing vs. `adi-lg request --part`**: discovery resolves `matlab_board`
  using the place's `hdl-config`, but `adi-lg request --part/--carrier` reserves by
  daughter-board+carrier only. If one carrier hosts two hdl-config variants (adrv9002 cmos
  vs lvds) on *different* places, request could reserve the other variant. First cut accepts
  this (the common case is one variant per carrier); a future `--hdl-config` request filter
  is the fix.
