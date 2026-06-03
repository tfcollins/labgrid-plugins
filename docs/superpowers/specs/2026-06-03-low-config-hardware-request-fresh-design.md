# Low-Config Hardware Request (Fresh Design) — Design

**Date:** 2026-06-03
**Status:** Approved (design); ready for implementation planning
**Repo:** `adi-labgrid-plugins`
**Source idea:** `planning.md` ("Support other repos/projects with labgrid plugins")

> This is a **fresh** brainstorm of the goals in `planning.md`, conducted at the
> user's request without anchoring on the prior `2026-06-02-low-config-hardware-request-design.md`.
> It converges on a similar shape (a good design is a good design) but the
> decisions below were re-derived from scratch and re-scoped to the first cut
> the user actually wants now.

## Problem

Consumer repos that run hardware tests against ADI boards — `pyadi-iio`,
`TransceiverToolbox`, and `no-os` — carry significant labgrid configuration
burden to reach a board. Today a consumer must know place names, maintain its
own board maps, hand-pin image versions, and wire up acquire + env-yaml steps.
The strategy/driver/resource model leaks into every consumer.

We want consumers to **request hardware by what it is** — "an ADRV9002,
optionally on a ZCU102, optionally at a given image version" — and have labgrid
and the coordinator manage selection, acquisition, boot, interface handover,
and release. Consumers must never define strategies, drivers, or resources.

## Goals

- A consumer requests a board **part-centrically** (`part`, optional `carrier`,
  optional `**filters`) with an **optional bootfile/image version**, and gets
  back a ready-to-use handle exposing the board's interfaces (primarily a
  libIIO URI).
- Ship three surfaces over one shared core: a generic **CLI**, a **pytest**
  integration, and a reusable **GitHub Actions** workflow.
- Move part→provisioning intelligence **coordinator-side** (a board catalog),
  so projects need no board maps or image pinning.
- Guarantee cleanup: a board is always released (and optionally powered down)
  even on failure, Ctrl-C, or CI timeout.
- Keep the `request → handle` contract clean enough that orchestration could
  move server-side later **without changing any surface**.

## Non-Goals (this design / first cut)

- **MATLAB / TransceiverToolbox** surface — designed-for (the catalog and the
  `adi-lg request` CLI are shaped to host it later) but not built now.
- **`flash` mode / no-os** (the board is the device under test) — deferred; the
  catalog and contract are extensible to add it.
- **Server-side boot orchestration** (a fat `POST /request` that boots on the
  exporter). The contract allows it later; this design keeps boot in the
  requesting process.
- **Rich `--bootfile` handling** (release channels, multi-file boot sets,
  artifact paths). First cut is a single optional version pin; explicitly an
  area to expand later.

## Settled Decisions (from this brainstorm)

| Question | Decision |
| --- | --- |
| Where orchestration runs | **Client-side now, server-ready contract.** Boot runs in the consumer's process (CLI/pytest/CI runner) via the coordinator; the `request → Lease` contract is drawn so it could move server-side later without changing surfaces. |
| Where part→provisioning resolution lives | **Coordinator-side catalog (API).** A `board_catalog.yaml` served via `GET /match` / `GET /catalog`; single source of truth, retires per-project board maps and image pinning. Place tags say what's free; catalog says how to provision it. |
| First shippable increment | **Core + generic CLI + pytest + GitHub Actions**, `uri`-mode only, validated on `pyadi-iio` against **one board: adrv9002-zcu102 (Kuiper 2023-R2 default)**. MATLAB, flash/no-os, and richer bootfile handling are deferred. |
| How CI chooses boards | **From test markers via `--collect-only`.** Reuse `pyadi-iio`'s existing `iio_hardware` / `iio_carrier` markers as the "wanted" set; intersect with live coordinator discovery. Missing → visible skip; busy → queued via labgrid reservation; one job per board. |
| `--carrier` | Optional on every surface; omitted → coordinator picks any free place carrying the part. |
| Power-down | Optional (`--power-down`); default off — release the place but leave it powered for the next user. |

## Architecture

One client-side **core** with thin surfaces above and a thin coordinator
catalog below.

```
Surfaces (thin wrappers, no orchestration logic of their own)
  CLI:     adi-lg request --part … [--carrier …] --run '<cmd>'
  pytest:  adi_board fixture  (reuses iio_hardware / iio_carrier markers)
  GitHub Actions:  preflight (collect-only ∩ discovery) → per-board jobs
        │  all build the same request and enter its context
Core:  adi_lg_plugins/request/   (the ONLY place orchestration lives)
  request(part, carrier=…, bootfile=…, wait=…, power_down=…) →
    GET /match → reserve (queues if busy) → acquire → boot strategy
    → resolve interfaces → yield Lease → release (+ optional power-down)
        │  uses existing labgrid reservations + strategies
Coordinator (thin additions)
  board_catalog.yaml + GET /match + GET /catalog
  (part + carrier → strategy, default image, interfaces, metadata)
```

Principles:

- **Orchestration lives only in the core.** Every surface builds a request,
  enters its context, and runs user work. No surface re-implements logic.
- **Boot runs in the requesting process**, actuating hardware through the
  coordinator/exporter — consolidating today's acquire + env-yaml steps into
  one call rather than relocating them.
- **The coordinator stays a catalog + reservation broker.** Its new job is
  answering "what free place satisfies this request, and what describes it."

## The Request Contract

One context manager, the same in every surface:

```python
from adi_lg_plugins.request import request

# carrier optional; bootfile defaults to the catalog's image (Kuiper 2023-R2)
with request(part="adrv9002", carrier="zcu102") as board:
    sdr = adi.adrv9002(uri=board.uri)
    ...
# place released automatically on exit, even on exception
```

`request(...)` parameters (only `part` required):

- `part` — daughter-board / chip, e.g. `"adrv9002"`.
- `carrier` and arbitrary `**filters` — narrow the match against place tags.
  Both optional; omitted carrier → any free place carrying the part.
- `bootfile` — pin an image version; omitted → the catalog's default image for
  the matched board. *(First cut: a single optional version string. Expansion
  to channels / multi-file boot sets / artifact paths is deferred.)*
- `wait` — max time to queue for a busy matching board (default 30 min);
  `0` = fail fast.
- `power_down` — default `False`; release the place but leave it powered for the
  next user. `True` powers the board down after release.

`Lease` (yielded inside the `with`):

- `.uri` — the libIIO URI; the **primary handover** for `pyadi-iio`.
- `.console` / `.ip` / `.jtag` — the other interfaces from `planning.md`,
  populated **when the matched place exposes them**.
- `.place`, `.tags`, `.board_name` — metadata from the matched place + catalog.

**Key principle:** consumers never name a strategy, driver, or resource. They
name a *part*; the coordinator catalog resolves everything else.

## Surfaces (all thin wrappers over `request(...)`)

### Surface A — generic CLI (`adi-lg request`)

```bash
adi-lg request --part adrv9002 [--carrier zcu102] [--bootfile 2023_R2] \
               [--wait 30m] [--power-down] --run 'pytest test/ -k adrv9002'
```

Builds the request, queues + acquires + boots, exports the resolved interfaces
into the child env (`IIO_URI`, plus `LG_PLACE` / `LG_SERIAL` / etc. when
present), runs `<cmd>`, then releases (and optionally powers down) in a
`finally`. Installs SIGINT/SIGTERM handlers so a Ctrl-C or CI job-timeout still
releases the place and cancels the reservation. This CLI is the single entry
point everything else (including the future MATLAB launcher) shells out to.

**Stratified exit codes** so callers and CI distinguish infra problems from real
test failures:

- The child command's own exit code passes through unchanged in `--run` mode.
- Dedicated codes reserved for *no matching board*, *board busy past `wait`*,
  and *boot failed* (the last prints the captured console tail for triage).

### Surface B — pytest integration (`adi_board` fixture)

Ships in the existing `adi_lg_plugins` pytest plugin (a `pytest11` entry point),
so any project that `pip install`s the package gets it — no per-repo conftest
plumbing. It **reuses `pyadi-iio`'s existing `iio_hardware` / `iio_carrier`
markers** (which decide *which* tests run); the fixture decides *what board*
they run against.

```python
@pytest.mark.iio_hardware(["adrv9002"])
def test_rx(adi_board):
    sdr = adi.adrv9002(uri=adi_board.uri)
```

**Dual-mode, automatic** — the same suite runs locally and in CI:

- **CI / already-booted:** if `IIO_URI` (or `--adi-uri`) is set, reuse that
  board; release nothing.
- **Local dev:** otherwise self-request a board via the core (`--adi-part` /
  `ADI_PART`; carrier from `--adi-carrier` / `ADI_CARRIER`) and release it at
  session teardown.
- **Neither configured:** the test **skips** cleanly (matches the repo's
  hardware-gating ethos — no hardware shouldn't hard-fail a local run).

Session-scoped: one board provisioned per `pytest` invocation, shared by all
tests. An `adi_uri` convenience fixture yields `adi_board.uri`.

### Surface C — GitHub Actions (discover → fan out → run)

A reusable `workflow_call` workflow, two stages:

1. **Preflight (one job):** run `pytest --collect-only` to harvest the
   `iio_hardware` / `iio_carrier` markers (the project's "wanted" set), query
   the coordinator for live places (`GET /match` / discovery), and emit the
   **intersection** as a job matrix. A wanted board **not present** on any
   coordinator is **not** in the matrix and is surfaced as a **visible skip
   annotation** (not a silent drop).
2. **Per-board jobs (matrix fan-out):** each leg runs
   `adi-lg request --part <board> --run 'pytest -m "iio_hardware and <board>" …'`.
   Because the core reserves through labgrid, a board **in use queues** until
   free (bounded by `wait`); independent boards run in parallel. Per-leg JUnit
   is uploaded and aggregated.

`planning.md`'s three CI rules map cleanly: *skip if missing* = preflight
intersection + annotation; *queue if busy* = labgrid reservation inside each
leg; *independent job per board* = the matrix.

## Coordinator Catalog & Matching

One new `board_catalog.yaml` served by the coordinator — the single source of
truth that retires per-project board maps and hand-pinned images. It
**enriches** place tags rather than duplicating them: places remain the source
of truth for *what exists and is free*; the catalog adds *how to provision and
identify it*.

First-cut schema (only what `uri`-mode needs):

```yaml
boards:
  adrv9002:
    image: kuiper-2023_R2        # default image when --bootfile omitted
    carriers:
      zcu102: {}                  # the carrier is a valid match; no extra metadata yet
```

The catalog entry is **extensible**: per-surface metadata (a MATLAB board name
to retire `TransceiverToolbox/board_map.yaml`, a flash method for no-os) is
added to a board's entry **when that surface is built**, not before. This keeps
"single source of truth" as a stated direction without designing unused fields.

Endpoints:

- `GET /catalog` — the resolved catalog (discovery / tooling).
- `GET /match?part=…&carrier=…&bootfile=…` — validates the request is
  satisfiable and returns: a **reservation filter** (the tag expression to
  reserve by), the **resolved image version** (default echoed concrete, or the
  pin echoed back), the **strategy**, and per-board metadata. It does **not**
  acquire — selection / queuing is delegated to labgrid's reservation system,
  so contention is handled uniformly across CLI, pytest, and CI.

## Error Handling & Cleanup

Failures are classified so every surface reacts correctly and CI distinguishes
infra flake from a real test failure:

- **No matching board** (part/filters exist nowhere) → `/match` empty → raise
  immediately, no wait. Dedicated CLI exit code; pytest **fails** (you asked for
  a board that doesn't exist).
- **All matching boards busy** → reservation waits up to `wait`; on timeout
  raise. `wait=0` fails fast. Dedicated exit code.
- **Boot failure** → strategy error carries the captured console tail; the place
  is still released; CLI prints the tail. Dedicated exit code.
- **Cleanup is unconditional** — release (+ optional power-down) and
  reservation-cancel run in `finally`, behind SIGINT/SIGTERM handlers. A release
  failure is logged but never masks the original error. Leaked acquisitions are
  the primary operational risk and are treated as first-class.
- **Test-command failure** — in `--run` mode the child's non-zero exit
  propagates unchanged (distinct from all infra codes above).

## Testing

- **Unit (no hardware):** catalog / match resolution, default-image resolution,
  request-param validation, exit-code mapping. Runs in `nox -s tests`.
- **Coordinator:** `/match` and `/catalog` against fixture catalogs + fake place
  sets, in `coordinator/api/tests/`.
- **Orchestration with a fake backend:** a stub reservation + boot backend
  exercises the full `request()` lifecycle (match → reserve → acquire → boot →
  lease → release) plus the failure / cleanup paths without hardware — the key
  safety net for the leak-on-failure concern.
- **pytest plugin:** tested via pytest's `pytester` — reuse path, self-request
  path, skip path, and session-scoping.
- **Hardware smoke:** one real end-to-end `uri`-mode run on adrv9002-zcu102,
  behind the existing `@pytest.mark.hardware` / `--run-hardware` gate, lab /
  HW-CI only.

## Build Order (within this first cut)

The first increment is coherent but built and validated in this order so each
step is independently demonstrable:

1. **Catalog + `/match` + `/catalog`** (coordinator) — resolvable against fake
   places.
2. **Request core + `Lease` + cleanup** — provable against the fake backend,
   then the hardware smoke.
3. **`adi-lg request` CLI** — the generic local runner.
4. **pytest `adi_board` fixture** — dual-mode, on `pyadi-iio`.
5. **GitHub Actions workflow** — preflight discovery + per-board fan-out.

MATLAB, `flash` / no-os mode, and richer `--bootfile` handling are designed-for
in the contract but explicitly deferred.

## Open Questions for Implementation Planning

- Exact URI-resolution mechanism in `uri` mode (place network-resource tag vs.
  post-boot console query) — pick during planning based on what the exporter
  already exposes.
- Concrete CLI exit-code numbers and where they're documented.
- Exactly which interfaces beyond `.uri` the first-cut `Lease` populates
  (`.console` is cheap; `.ip` / `.jtag` only if a consumer needs them now).
- Whether the GitHub Actions workflow targets a single coordinator or fans the
  discovery query across several.
