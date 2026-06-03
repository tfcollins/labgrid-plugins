# Hardware Request — GitHub Actions Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A reusable `workflow_call` GitHub Actions workflow that, for any consumer repo (starting with pyadi-iio), **discovers** which boards its tests want (from `iio_hardware` markers) ∩ which the coordinator has live, **fans out** one independent job per available board, and runs that board's tests via a single `adi-lg request --part <board> --run 'pytest …'` call — implementing planning.md's three CI rules: *skip if missing*, *queue if busy*, *independent job per board*.

**Architecture:** Two pieces. (1) A part-keyed matrix builder: a pure `build_request_matrix()` + an `adi-lg-hw-ci request-matrix` CLI subcommand that harvests wanted parts (reusing `hw_ci.markers.harvest_markers`, AST-based so it never imports test modules) and probes the coordinator's Plan-1 `GET /api/match` for each, emitting a matrix of available parts and `::warning::` annotations for wanted-but-missing ones. (2) `.github/workflows/hw-request.yml`: a `preflight` job that runs the builder, a matrix `hw-request` job whose every leg is one `adi-lg request` call (the `--wait` handles queue-if-busy; the per-shard `HW_DAUGHTER` env reuses the existing plugin narrowing), and a `report` job that aggregates JUnit.

**Tech Stack:** Python 3.10+ (`hw_ci` CLI), GitHub Actions reusable workflow YAML, the existing `setup-uv-venv` composite action, `adi-lg request` (Plan 3) + `adi-lg-hw-ci` (existing). ruff line length 100, double quotes. Run `pytest`/`ruff` from repo root `/home/tcollins/dev/lg-test/labgrid-plugins`.

This is **Plan 5 of 5** (the last) of the first-cut increment (`docs/superpowers/specs/2026-06-03-low-config-hardware-request-fresh-design.md`). It depends on **Plan 1** (`GET /api/match`), **Plan 2** (`match_client`), and **Plan 3** (`adi-lg request`) — all merged to `main`.

---

## Grounding & reuse (what already exists)

This repo already hosts a sophisticated v1/v2 `hw-matrix.yml` whose legs do acquire-place + render-env + board_map + `pytest --lg-config`. **Plan 5 does NOT extend it.** The fresh design's contribution is exactly to *collapse* each leg into one `adi-lg request` call, so this is a new, much smaller reusable workflow. The v1/v2 workflows stay as-is.

Reused building blocks (do not reimplement):
- `adi_lg_plugins/hw_ci/markers.py` → `harvest_markers(test_root, marker="iio_hardware") -> dict[test_id, MarkerSpec]`; `MarkerSpec.iio_hardware` is a `frozenset[str]` of part names. AST-based (never imports test modules — pyadi-iio's `import adi` dlopens libiio).
- `adi_lg_plugins/hw_ci/coordinator.py` → `resolve_coordinator(explicit) -> str`.
- `adi_lg_plugins/request/match_client.py` → `get_match(coord, *, part, …) -> MatchResult` with `.satisfiable` (Plan 2; talks to Plan-1 `/api/match`).
- `adi_lg_plugins/pytest_plugin` → reads `HW_DAUGHTER`/`HW_CARRIER` env to deselect tests whose `iio_hardware` args don't match (per-shard narrowing). The leg sets `HW_DAUGHTER` so `pytest -m iio_hardware` runs only that board's tests.
- `adi_lg_plugins/hw_ci/cli.py` → the `adi-lg-hw-ci` argparse CLI (subcommands `discover`/`render-env`/`resolve-resources`/`list-strategies`); add `request-matrix` alongside, mirroring `discover`'s `--github-output`/stdout-JSON/stderr-summary convention.
- `.github/actions/setup-uv-venv` → composite action installing the package + deps.

## File Structure

- Create: `adi_lg_plugins/hw_ci/request_matrix.py` — pure `build_request_matrix()`.
- Modify: `adi_lg_plugins/hw_ci/cli.py` — add the `request-matrix` subcommand.
- Create: `.github/workflows/hw-request.yml` — the reusable workflow.
- Create: `docs/source/user-guide/hw-request.rst` — usage docs; add to the toctree.
- Modify: `docs/source/user-guide/index.rst` — toctree entry.
- Test: `tests/hw_ci/test_request_matrix.py`.

## Conventions

- Commands from repo root. Test runner: `python3 -m pytest tests/hw_ci/test_request_matrix.py -v`.
- Lint: `ruff check <files> && ruff format <files>` before each commit.

---

### Task 1: `build_request_matrix` + `request-matrix` CLI subcommand

**Files:**
- Create: `adi_lg_plugins/hw_ci/request_matrix.py`
- Modify: `adi_lg_plugins/hw_ci/cli.py`
- Test: `tests/hw_ci/test_request_matrix.py`

- [ ] **Step 1: Write the failing test** — create `tests/hw_ci/test_request_matrix.py`:

```python
from __future__ import annotations

import json
from types import SimpleNamespace

from adi_lg_plugins.hw_ci import cli as hw_cli
from adi_lg_plugins.hw_ci.request_matrix import RequestMatrix, build_request_matrix


# ---- pure builder ----


def test_build_splits_available_and_missing():
    avail = {"adrv9002", "ad9081"}
    r = build_request_matrix(["ad9081", "adrv9002", "ad9361"], lambda p: p in avail)
    assert isinstance(r, RequestMatrix)
    assert r.parts == ["ad9081", "adrv9002"]  # available, sorted
    assert r.missing == ["ad9361"]  # wanted but no live board


def test_build_dedupes_and_sorts():
    r = build_request_matrix(["b", "a", "a"], lambda p: True)
    assert r.parts == ["a", "b"]
    assert r.missing == []


def test_build_all_missing():
    r = build_request_matrix(["x"], lambda p: False)
    assert r.parts == []
    assert r.missing == ["x"]


# ---- CLI subcommand (monkeypatched: no coordinator, no test files) ----


def test_request_matrix_cli_emits_matrix_and_annotates(monkeypatch, capsys):
    from adi_lg_plugins.hw_ci import coordinator as coord_mod
    from adi_lg_plugins.hw_ci import markers as markers_mod
    from adi_lg_plugins.request import match_client

    monkeypatch.setattr(coord_mod, "resolve_coordinator", lambda c: "coord:8000")
    monkeypatch.setattr(
        markers_mod,
        "harvest_markers",
        lambda root, marker="iio_hardware": {
            "t1": SimpleNamespace(iio_hardware=frozenset({"adrv9002"})),
            "t2": SimpleNamespace(iio_hardware=frozenset({"ad9361"})),
        },
    )
    available = {"adrv9002"}
    monkeypatch.setattr(
        match_client,
        "get_match",
        lambda coord, *, part, **k: SimpleNamespace(satisfiable=part in available),
    )

    rc = hw_cli.main(["request-matrix", "--test-root", "test", "--coord", "coord:8000"])
    assert rc == 0

    out = capsys.readouterr()
    assert json.loads(out.out) == {"include": [{"part": "adrv9002"}]}
    # missing part surfaced as a GitHub workflow annotation on stderr
    assert "::warning::" in out.err
    assert "ad9361" in out.err


def test_request_matrix_cli_probe_failure_treated_as_unavailable(monkeypatch, capsys):
    from adi_lg_plugins.hw_ci import coordinator as coord_mod
    from adi_lg_plugins.hw_ci import markers as markers_mod
    from adi_lg_plugins.request import match_client

    monkeypatch.setattr(coord_mod, "resolve_coordinator", lambda c: "coord:8000")
    monkeypatch.setattr(
        markers_mod,
        "harvest_markers",
        lambda root, marker="iio_hardware": {
            "t1": SimpleNamespace(iio_hardware=frozenset({"adrv9002"}))
        },
    )

    def boom(coord, *, part, **k):
        raise RuntimeError("coordinator unreachable")

    monkeypatch.setattr(match_client, "get_match", boom)
    rc = hw_cli.main(["request-matrix", "--test-root", "test", "--coord", "coord:8000"])
    assert rc == 0
    out = capsys.readouterr()
    assert json.loads(out.out) == {"include": []}  # probe failure -> not in matrix
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/hw_ci/test_request_matrix.py -v`
Expected: FAIL — `...hw_ci.request_matrix` missing and the `request-matrix` subcommand isn't wired.

- [ ] **Step 3: Write the implementation**

(a) Create `adi_lg_plugins/hw_ci/request_matrix.py`:

```python
"""Build the part-keyed CI matrix for the fresh hardware-request workflow.

Pure of IO: given the parts a test suite wants (harvested from
``iio_hardware`` markers) and a ``satisfiable(part)`` probe, return the matrix
of parts that have a live board (one CI leg each) plus the wanted-but-missing
parts to annotate as skipped.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestMatrix:
    parts: list[str]  # available -> one CI leg each
    missing: list[str]  # wanted but no live board -> annotate + skip


def build_request_matrix(
    wanted_parts: Iterable[str],
    satisfiable: Callable[[str], bool],
) -> RequestMatrix:
    parts: list[str] = []
    missing: list[str] = []
    for part in sorted(set(wanted_parts)):
        (parts if satisfiable(part) else missing).append(part)
    return RequestMatrix(parts=parts, missing=missing)
```

(b) Add the `request-matrix` subcommand to `adi_lg_plugins/hw_ci/cli.py`.

First add the command function (place it after `_cmd_discover`):

```python
def _cmd_request_matrix(args: argparse.Namespace) -> int:
    """Emit a part-keyed matrix: wanted parts (from markers) that have a live
    board (per GET /api/match). Missing parts are surfaced as GH annotations."""
    from adi_lg_plugins.request import match_client

    from .request_matrix import build_request_matrix

    coord = coord_mod.resolve_coordinator(args.coord)
    markers = markers_mod.harvest_markers(args.test_root, marker=args.marker)
    wanted = sorted({h for spec in markers.values() for h in spec.iio_hardware})

    def satisfiable(part: str) -> bool:
        try:
            return bool(match_client.get_match(coord, part=part).satisfiable)
        except Exception as e:  # noqa: BLE001 - a probe failure must not crash discovery
            print(f"# /api/match probe failed for {part!r}: {e}", file=sys.stderr)
            return False

    result = build_request_matrix(wanted, satisfiable)
    matrix = {"include": [{"part": p} for p in result.parts]}

    if args.github_output:
        gh_out = os.environ.get("GITHUB_OUTPUT")
        if gh_out:
            with open(gh_out, "a", encoding="utf-8") as f:
                f.write(f"matrix={json.dumps(matrix)}\n")
                f.write(f"count={len(result.parts)}\n")
        else:
            print("warning: --github-output given but $GITHUB_OUTPUT is unset", file=sys.stderr)

    # stdout: the matrix JSON (so the CLI is usable outside GHA).
    print(json.dumps(matrix, indent=2))
    # stderr: human summary + a GitHub annotation per wanted-but-missing part.
    print(
        f"# request-matrix: {len(wanted)} wanted part(s), {len(result.parts)} available",
        file=sys.stderr,
    )
    for p in result.missing:
        print(
            f"::warning::part {p!r} is wanted by tests but no live board is on the "
            f"coordinator — skipping",
            file=sys.stderr,
        )
    return 0
```

Then register the subparser inside `main()` (next to the existing `discover`/`render-env` `add_parser` calls), mirroring the `discover` options:

```python
    pm = sub.add_parser("request-matrix", help="emit a part-keyed matrix for the hw-request workflow")
    pm.add_argument("--test-root", required=True, help="path to the consumer's test directory")
    pm.add_argument("--marker", default="iio_hardware", help="hardware-gating marker name")
    pm.add_argument("--coord", default=None, help="coordinator host:port (default: $LG_COORDINATOR)")
    pm.add_argument(
        "--github-output",
        action="store_true",
        help="also write matrix=/count= to $GITHUB_OUTPUT",
    )
    pm.set_defaults(func=_cmd_request_matrix)
```

(If `_cmd_discover` references `coord_mod`/`markers_mod`/`os`/`sys`/`json` via module-level imports, reuse those same names — they are already imported at the top of `cli.py`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/hw_ci/test_request_matrix.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Lint and commit**

```bash
cd /home/tcollins/dev/lg-test/labgrid-plugins
ruff check adi_lg_plugins/hw_ci/request_matrix.py adi_lg_plugins/hw_ci/cli.py tests/hw_ci/test_request_matrix.py && \
  ruff format adi_lg_plugins/hw_ci/request_matrix.py adi_lg_plugins/hw_ci/cli.py tests/hw_ci/test_request_matrix.py
git add adi_lg_plugins/hw_ci/request_matrix.py adi_lg_plugins/hw_ci/cli.py tests/hw_ci/test_request_matrix.py
git commit -m "feat(hw-ci): request-matrix subcommand (part-keyed discovery for hw-request workflow)"
```

---

### Task 2: The reusable `hw-request.yml` workflow

**Files:**
- Create: `.github/workflows/hw-request.yml`
- Test (validation step): parse + structural check.

- [ ] **Step 1: Create `.github/workflows/hw-request.yml`:**

```yaml
name: HW Request (low-config)

# Reusable workflow: a consumer repo (e.g. pyadi-iio) calls this to run its
# hardware tests by *part*. labgrid selects a free matching board, boots it,
# runs the tests, and releases it — one independent job per board.
#
#   jobs:
#     hw:
#       uses: tfcollins/labgrid-plugins/.github/workflows/hw-request.yml@main
#       with:
#         coordinator: "10.0.0.41:8000"
#         test-root: "test"
on:
  workflow_call:
    inputs:
      coordinator:
        description: "Coordinator host:port for the REST API (GET /api/match) and reservations."
        type: string
        required: true
      test-root:
        description: "Path to the test directory to harvest markers from and run."
        type: string
        default: "test"
      marker:
        description: "Top-level pytest marker gating hardware tests."
        type: string
        default: "iio_hardware"
      wait:
        description: "Seconds each leg queues for a free matching board (0 = fail fast)."
        type: number
        default: 1800
      runner-label:
        description: "Self-hosted runner label for the per-board legs (must reach the coordinator + lab)."
        type: string
        default: "hw-lab"
      preflight-runner-label:
        description: "Runner label for the discovery preflight (must reach the coordinator REST API)."
        type: string
        default: "hw-coordinator"
      pytest-args:
        description: "Extra args appended to the per-leg pytest command."
        type: string
        default: ""

jobs:
  preflight:
    runs-on: [self-hosted, "${{ inputs.preflight-runner-label }}"]
    outputs:
      matrix: ${{ steps.plan.outputs.matrix }}
      count: ${{ steps.plan.outputs.count }}
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/setup-uv-venv
      - id: plan
        env:
          LG_COORDINATOR: ${{ inputs.coordinator }}
        run: |
          adi-lg-hw-ci request-matrix \
            --test-root "${{ inputs.test-root }}" \
            --marker "${{ inputs.marker }}" \
            --coord "${{ inputs.coordinator }}" \
            --github-output

  hw-request:
    needs: preflight
    if: ${{ fromJSON(needs.preflight.outputs.count) > 0 }}
    runs-on: [self-hosted, "${{ inputs.runner-label }}"]
    strategy:
      fail-fast: false
      matrix: ${{ fromJSON(needs.preflight.outputs.matrix) }}
    env:
      LG_COORDINATOR: ${{ inputs.coordinator }}
      # Reuse the pytest plugin's per-shard narrowing: deselect tests whose
      # iio_hardware args don't include this board.
      HW_DAUGHTER: ${{ matrix.part }}
    steps:
      - uses: actions/checkout@v4
      - uses: tfcollins/labgrid-plugins/.github/actions/setup-uv-venv@main
      - name: Request ${{ matrix.part }} and run its tests
        run: |
          adi-lg request --part "${{ matrix.part }}" --wait "${{ inputs.wait }}" \
            --run "pytest ${{ inputs.test-root }} -m ${{ inputs.marker }} --junitxml=results-${{ matrix.part }}.xml ${{ inputs.pytest-args }}"
      - name: Upload JUnit
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: junit-${{ matrix.part }}
          path: results-${{ matrix.part }}.xml
          if-no-files-found: ignore

  report:
    needs: hw-request
    if: always()
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          pattern: junit-*
          merge-multiple: true
      - name: Publish test results
        uses: EnricoMi/publish-unit-test-result-action@v2
        with:
          junit_files: "results-*.xml"
```

Mapping to planning.md's three CI rules:
- **skip if missing** — a wanted part with no live board is not in `matrix` (and gets a `::warning::` annotation from `request-matrix`).
- **queue if busy** — `adi-lg request --wait` reserves through labgrid, which queues until a matching board frees.
- **independent job per board** — the `hw-request` matrix, `fail-fast: false`.

- [ ] **Step 2: Validate the workflow YAML parses and has the expected shape**

Run:
```bash
python3 - <<'PY'
import yaml
d = yaml.safe_load(open(".github/workflows/hw-request.yml"))
# `on:` parses as the boolean True key in YAML 1.1 — accept either.
trig = d.get("on", d.get(True))
assert "workflow_call" in trig, "must be a reusable (workflow_call) workflow"
assert set(d["jobs"]) == {"preflight", "hw-request", "report"}, d["jobs"].keys()
assert d["jobs"]["hw-request"]["needs"] == "preflight"
assert "request-matrix" in yaml.dump(d["jobs"]["preflight"])
assert "adi-lg request" in yaml.dump(d["jobs"]["hw-request"])
print("hw-request.yml OK")
PY
```
Expected: `hw-request.yml OK`. If `actionlint` is installed, also run `actionlint .github/workflows/hw-request.yml` (optional; ignore self-hosted-runner-label warnings).

- [ ] **Step 3: Commit**

```bash
cd /home/tcollins/dev/lg-test/labgrid-plugins
git add .github/workflows/hw-request.yml
git commit -m "feat(ci): reusable hw-request workflow (discover -> per-board adi-lg request -> report)"
```

---

### Task 3: Document the workflow

**Files:**
- Create: `docs/source/user-guide/hw-request.rst`
- Modify: `docs/source/user-guide/index.rst`

- [ ] **Step 1: Create `docs/source/user-guide/hw-request.rst`:**

```rst
Hardware CI by part (hw-request)
================================

``hw-request.yml`` is a reusable workflow that runs a consumer repo's hardware
tests **by part**. A consumer repo marks its tests with
``@pytest.mark.iio_hardware([...])`` and calls the workflow; labgrid selects a
free matching board, boots it, runs the tests, and releases it — one
independent job per board, with **no** place names, env yaml, or board maps in
the consumer repo.

How it differs from ``hw-matrix.yml``
-------------------------------------

``hw-matrix.yml`` (v1/v2) fans out per *place* and each leg does
acquire-place + render-env + board_map + ``pytest --lg-config``.
``hw-request.yml`` fans out per *part* and each leg is a single
``adi-lg request`` call that does all of that internally. Both coexist.

Calling it
----------

.. code-block:: yaml

   # .github/workflows/hw.yml in the consumer repo (e.g. pyadi-iio)
   name: HW
   on: [pull_request]
   jobs:
     hw:
       uses: tfcollins/labgrid-plugins/.github/workflows/hw-request.yml@main
       with:
         coordinator: "10.0.0.41:8000"
         test-root: "test"
         # marker: iio_hardware        # default
         # wait: 1800                   # seconds to queue for a busy board
         # runner-label: hw-lab         # self-hosted label for the per-board legs
         # pytest-args: "-v"

What happens
------------

#. **preflight** harvests the parts the suite wants from its
   ``iio_hardware`` markers (statically, via ``adi-lg-hw-ci request-matrix`` —
   it never imports test modules), probes ``GET /api/match`` for each, and
   emits a matrix of the parts that have a live board. A wanted part with no
   live board is **skipped** with a ``::warning::`` annotation.
#. **hw-request** runs one job per available part:
   ``adi-lg request --part <p> --wait <N> --run 'pytest -m iio_hardware …'``.
   The reservation **queues** if every matching board is busy (bounded by
   ``wait``). ``HW_DAUGHTER=<p>`` narrows the run to that board's tests.
#. **report** aggregates the per-leg JUnit into a single PR check.

Requirements
------------

* Self-hosted runners: one reachable by the coordinator REST API
  (``preflight-runner-label``) and a pool that can reach the coordinator and
  actuate the lab (``runner-label``).
* The coordinator must serve the Plan-1 board catalog (``GET /api/match``).
```

- [ ] **Step 2: Add it to the user-guide toctree** — in `docs/source/user-guide/index.rst`, add `hw-request` to the `.. toctree::` list, immediately after the `hw-ci-bash` entry:

```rst
   hardware-ci
   hw-ci-v2
   hw-ci-bash
   hw-request
   examples
```

- [ ] **Step 3: Sanity-check + commit**

```bash
cd /home/tcollins/dev/lg-test/labgrid-plugins
python3 -c "from docutils.core import publish_doctree; publish_doctree(open('docs/source/user-guide/hw-request.rst').read())" 2>&1 | grep -iE "severe|error" || echo "no RST errors"
git add docs/source/user-guide/hw-request.rst docs/source/user-guide/index.rst
git commit -m "docs(ci): document the reusable hw-request workflow"
```

(If `docutils` is missing, visually confirm the section-underline lengths match their titles.)

---

## Self-Review (completed during plan authoring)

**Spec coverage** — implements the spec's "Surface C — GitHub Actions (discover → fan out → run)":
- Preflight harvests `iio_hardware`/`iio_carrier` markers via `--collect-only`-equivalent static harvest, queries the coordinator, emits the intersection ✓ (Task 1). (Uses the AST harvester, which is the project's deliberate substitute for `--collect-only` so it doesn't `import adi`.)
- Wanted-but-missing → visible skip annotation ✓ (`::warning::`, Task 1).
- Per-board jobs each run `adi-lg request --part <board> --run 'pytest …'` ✓ (Task 2).
- Queue-if-busy via labgrid reservation (`--wait`) ✓; independent job per board via the matrix ✓; per-leg JUnit aggregated ✓ (Task 2).
- planning.md's three rules map cleanly (documented in Task 2 + Task 3).

Deliberately out of scope: extending/replacing `hw-matrix.yml` (v1/v2 stay); flash/no-os CI; carrier-narrowed matrix legs (the matrix is part-keyed; carrier is left to the coordinator's match — a future enhancement).

**Placeholder scan** — no TBD/TODO; every code/step is complete.

**Type/name consistency** — `build_request_matrix(wanted_parts, satisfiable) -> RequestMatrix(parts, missing)` matches its call site and tests. The CLI uses `markers_mod.harvest_markers`, `coord_mod.resolve_coordinator`, and `match_client.get_match(coord, part=…).satisfiable` — signatures verified against the merged code. The workflow's `matrix: ${{ fromJSON(needs.preflight.outputs.matrix) }}` consumes the `{"include":[{"part":…}]}` shape the CLI emits, and `matrix.part` is the leg key. `HW_DAUGHTER` is the env var the existing `pytest_plugin` reads.

## Open Questions / notes for implementation

- **Runner labels** (`hw-lab`, `hw-coordinator`) are placeholders for the lab's actual self-hosted labels — surface as inputs (done) and confirm the real labels with the lab admin before a consumer adopts the workflow.
- **Part-keyed vs carrier-narrowed:** the matrix is one leg per part; the coordinator picks any free carrier. If a consumer needs to pin a carrier per leg, extend `request-matrix` to emit `{part, carrier}` from `iio_carrier` markers and pass `--carrier` to the leg — deferred.
- **Catalog prerequisite:** the same Plan-1 follow-up applies — the catalog's `image:` must be a real `KuiperRelease` version before a leg actually boots hardware.
- **`adi-lg request` quoting:** the leg passes the whole `pytest …` command as one string to `--run`; keep `pytest-args` simple (no nested quotes) or the consumer can wrap a script.
