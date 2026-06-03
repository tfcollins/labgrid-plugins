# Low-Config Hardware Request — Design

**Date:** 2026-06-02
**Status:** Approved (design); Phase 1 ready for planning
**Repo:** `adi-labgrid-plugins`

## Problem

Consumer repos that run hardware tests against ADI boards — `pyadi-iio`, `TransceiverToolbox`, and `no-os` — currently carry significant labgrid configuration burden to reach a board. To run a test today a consumer must know place names, maintain `supported-boards.yml` and a duplicated `board_map.yaml`, hand-pin Kuiper image versions, and wire up the `hw-matrix` workflow's acquire + env-yaml steps. The strategy/driver/resource model leaks into every consumer.

We want consumers to **request hardware by what it is** — e.g. "an AD9361, optionally on a ZCU102, optionally at a given image version" — and have labgrid and the coordinator manage selection, acquisition, boot/flash, and release. Consumers should not need to know about strategies, drivers, or resources.

## Goals

- A consumer requests a board **part-centrically** (`part`, optional `carrier`, optional filters) with an **optional bootfile/firmware version**, and gets back a ready-to-use handle.
- Support **two run models** from the start:
  - **`uri` mode** — boot the board (Linux) and return a libIIO URI. Used by `pyadi-iio` and `TransceiverToolbox`.
  - **`flash` mode** — flash a firmware binary onto the board, capture serial, assert pass/fail. Used by `no-os` (the board *is* the device under test).
- Expose the same core through **three surfaces**: a generic **CLI**, an integrated **pytest plugin**, and reusable **GitHub Action templates**.
- Move selection/provisioning intelligence **coordinator-side** (a board catalog), retiring the duplicated `board_map.yaml` and per-consumer pinning.
- Keep the contract clean enough that orchestration could later move server-side without changing any surface.

## Non-Goals

- Server-side boot orchestration (a fat `POST /request` that boots on the exporter). The interface is designed to allow it later, but this design keeps boot in the requesting process (today's model).
- Replacing the `hw-matrix` matrix fan-out. We keep fan-out and per-board JUnit reporting; we only collapse each leg's acquire/env/board_map steps into one call.
- Comprehensive flash-platform coverage. Phase 3 covers only the platforms `no-os` CI needs first; others are added as catalog entries over time.

## Settled Decisions (from brainstorming)

| Question | Decision |
| --- | --- |
| Surfaces | One shared core; CLI + pytest plugin + GHA templates on top |
| Run models | Both `uri` and `flash` from the start |
| Request model | Part-centric; `carrier` + arbitrary tag filters optional; coordinator picks any free match |
| Bootfile/version | Default "latest stable", pinnable; flash mode defaults to consumer's built artifact |
| Resolution intelligence | Coordinator-side board catalog (latest image, flash method, MATLAB board name) |
| CI integration | Keep matrix fan-out; each leg becomes one `adi-lg request` call |
| Orchestration | Client-orchestrated core + thin coordinator catalog; phased delivery |

## Architecture

One client-side **core** with thin surfaces above and a thin coordinator extension below.

```
Surfaces (thin)
  CLI: adi-lg request …      pytest: adi_board fixture
  GHA template: matrix leg → adi-lg request --run '…'
        │  (all call the same core)
Core: adi_lg_plugins/request/  (NEW)
  HardwareRequest → match → reserve/acquire → boot/flash
                  → yield Lease(handle) → release
  uri mode  → Lease.uri (libIIO URI)
  flash mode→ Lease.console + Lease.flash()
        │  (uses existing labgrid reservations + strategies)
Coordinator (thin additions)
  board_catalog.yaml + GET /match + GET /catalog
  (parts→places, latest image, flash method, matlab board name)
  env_gen extended for flash mode
```

Principles:

- **Orchestration lives only in the core.** Every surface is a wrapper that builds a `HardwareRequest`, enters its context, and runs user work. No surface re-implements logic.
- **Boot runs in the requesting process** (CLI/pytest/CI runner), actuating hardware through the coordinator/exporter — exactly as the `hw-matrix` runner does today. This consolidates existing steps rather than relocating them.
- **The coordinator stays a catalog + reservation broker.** Its new responsibility is answering "what free place satisfies this request, and what metadata describes it." The `HardwareRequest → Lease` contract is shaped so a future server-side `POST /request` could implement it without changing surfaces.

## The Request Contract

Core object — one context manager, mode-parameterized:

```python
from adi_lg_plugins.request import request

# uri mode (default): boot Linux, hand back a libIIO URI
with request(part="ad9361", carrier="zcu102", bootfile="2023_R2_P1") as board:
    sdr = adi.ad9361(uri=board.uri)
    ...
# place released automatically on exit (even on exception)

# flash mode: flash a built binary, capture serial, assert
with request(part="adxl355", mode="flash", artifact="build/app.elf") as board:
    board.flash()
    board.console.expect("PASS", timeout=30)
```

`request(...)` parameters (only `part` required):

- `part` — daughter-board/chip, e.g. `"ad9361"`.
- `carrier` and arbitrary `**filters` (e.g. `hdl_config="lvds"`) — narrow the match against place tags.
- `mode` — `"uri"` (default) or `"flash"`.
- `bootfile` — pin a version; omitted → coordinator's "latest stable" for the matched board (uri mode).
- `artifact` — firmware path; defaults to the consumer's built binary (flash mode).
- `wait` — max time to wait for a free matching board (default 30 min); `0` = fail fast.

`Lease` object (yielded inside the `with`):

- `.uri` — libIIO URI (uri mode).
- `.console` — serial read/expect handle (flash mode; also available in uri mode for debugging).
- `.flash(artifact=None)` — program the board (flash mode).
- `.place`, `.tags`, `.board_name`, `.matlab_board` — metadata from the catalog. `.matlab_board` retires `board_map.yaml`.

### Surfaces (all thin wrappers over `request(...)`)

- **CLI** — `adi-lg request --part ad9361 --carrier zcu102 [--bootfile V] [--mode flash --artifact app.elf] --run '<cmd>'`. Acquires + boots, exports `IIO_URI` / `LG_PLACE` into the child env, runs `<cmd>`, releases. Exit code is the child's, except for the reserved infra exit codes below. This is what `adi-lg-matlab` and no-os shell out to.
- **pytest plugin** — ships in `adi_lg_plugins` as a pytest entry point; consumers add the dependency:
  ```python
  @pytest.mark.adi_hardware(part="ad9361")
  def test_rx(adi_board):
      sdr = adi.ad9361(uri=adi_board.uri)
  ```
- **GHA template** — reusable workflow; each matrix leg runs `adi-lg request --part ${{ matrix.part }} --run '<cmd>'`, replacing today's acquire-place + env-yaml + board_map steps. JUnit/reporting per leg unchanged.

## Coordinator Catalog & Matching

`board_catalog.yaml` — one new file served by the coordinator; the single source of truth that today is scattered across `supported-boards.yml`, `board_map.yaml`, and hand-pinned Kuiper versions. Keyed by part, with per-carrier overrides:

```yaml
boards:
  ad9361:
    image_channel: kuiper-stable          # how "latest" resolves (uri mode)
    carriers:
      zcu102: { matlab_board: zynqmp-zcu102-rev10-ad9361-fmcomms2-3 }
      zc706:  { matlab_board: zynq-zc706-adv7511-ad9361-fmcomms2-3 }
  adxl355:
    flash:                                 # flash mode metadata
      platform: stm32                       # → which flash driver
      tool: openocd
      default_artifact: build/app.elf
```

The catalog **enriches** existing place tags (`carrier` / `daughter-board` / `boot-strategy`) rather than duplicating them: places remain the source of truth for *what exists and is free*; the catalog adds *how to provision/identify it*.

Endpoints:

- `GET /catalog` — the resolved catalog (discovery/tooling).
- `GET /match?part=…&carrier=…&mode=…&bootfile=…` — validates the request is satisfiable and returns: a **reservation filter** (the tag expression), the **resolved bootfile version** (latest→concrete, or the pin echoed back), the strategy, and per-board metadata (`matlab_board`, flash method). It does **not** acquire — selection/queuing is delegated to labgrid's reservation system.

**Contention** is handled by labgrid reservations: the client reserves by the tag filter from `/match`, and labgrid queues until a matching place is free (bounded by `wait`). Parallel CI legs requesting `ad9361` queue across the pool of `ad9361` boards.

## Boot Orchestration & the Two Modes

The core's `request()` runs: `GET /match` → create labgrid reservation (wait) → acquire place → fetch extended env-yaml → mode-specific provisioning → yield `Lease` → on exit release + cancel reservation.

**`uri` mode** reuses today's strategies unchanged (`env_gen` infers `BootFPGASoC`/etc.). `bootfile` flows into `KuiperRelease.release_version` (catalog resolves `latest`→concrete). After boot, the URI is resolved from the place's network resource (or a post-boot console query) and exposed as `Lease.uri`.

**`flash` mode** is the genuinely new boot path (Phase 3). A new `FlashStrategy` + per-platform `FlashDriver` (selected by the catalog's `flash.platform`): power on → program the artifact via the platform tool (e.g. OpenOCD for STM32/Maxim, `xsdb`/JTAG for Xilinx) → expose the serial console. `Lease.flash()` programs; `Lease.console.expect(...)` reads. First cut covers only the platforms no-os CI needs; others are added as catalog entries later.

**Lease lifecycle / cleanup** is a first-class concern: the context manager guarantees release on normal exit and on exception. The CLI additionally installs SIGINT/SIGTERM handlers plus a `finally` so a Ctrl-C or CI job-timeout still releases the place and cancels the reservation. Leaked acquisitions are the primary operational risk and are treated explicitly.

## Error Handling

Failures are classified so surfaces can react and CI gets clear signals. Each maps to a stable CLI exit code so GHA legs distinguish infra flake from real test failure from boot breakage:

- **Unsatisfiable request** (no place has the part/filters at all) — `/match` returns empty; core raises `NoMatchingBoard` immediately (no wait). Dedicated exit code.
- **All matching boards busy** — reservation waits up to `wait`; on timeout raises `BoardUnavailable`. `wait=0` fails fast. Dedicated exit code.
- **Boot/flash failure** — strategy errors raise `ProvisionError` carrying the captured console log; the place is still released. CLI prints the console tail for triage. Dedicated exit code.
- **Bad bootfile/artifact** (version not in channel; artifact path missing) — validated up front (`/match` for versions, local stat for artifacts) so it fails before acquiring a board.
- **Cleanup is unconditional** — release + reservation-cancel run in `finally`; a release failure is logged but never masks the original error.
- **Test-command failure** — in `--run` mode, the child command's own non-zero exit propagates unchanged (distinct from all infra codes above).

## Testing

- **Unit** — matching/catalog resolution, "latest"→concrete version resolution, request-param validation, exit-code mapping. No hardware; runs in `nox -s tests` / the CI unit job.
- **Coordinator** — `/match` and `/catalog` against fixture catalogs + fake place sets, in `coordinator/api/tests/`.
- **Orchestration with a fake backend** — a stub reservation+boot backend exercises the full `request()` lifecycle (match → acquire → boot → lease → release) plus failure/cleanup paths without hardware. This is the key safety net for the leak-on-failure concern.
- **pytest plugin** — tested with pytest's `pytester`.
- **Hardware smoke** — one real `uri`-mode and one real `flash`-mode end-to-end run behind the existing `@pytest.mark.hardware` / `--run-hardware` gate, lab/HW-CI only.

## Phase Plan

1. **Phase 1 — `uri` mode end-to-end** (first implementation plan's scope): `board_catalog.yaml` + `GET /match` + `GET /catalog`, client core (`HardwareRequest` / `Lease`), `adi-lg request` CLI, reservation + lease + cleanup, URI resolution. Validated on `pyadi-iio` against one board.
2. **Phase 2 — surfaces**: pytest plugin (entry point + fixture), reusable GHA template replacing in-leg acquire/env/board_map steps, and `matlab_board` from the catalog wired into `adi-lg-matlab` (retires `board_map.yaml`).
3. **Phase 3 — `flash` mode / no-os**: `FlashStrategy` + first platform `FlashDriver`(s), flash-mode `Lease` (`flash()` / `console`), catalog `flash:` entries, no-os CI template.

Each phase is independently useful and shippable. Phase 1 is the scope of the first implementation plan; Phases 2 and 3 are specified here but sequenced after.

## Open Questions for Implementation Planning

- Exact URI resolution mechanism in `uri` mode (place network-resource tag vs. post-boot console query) — pick during Phase 1 planning based on what the exporter already exposes.
- Concrete CLI exit-code numbers and their documentation surface.
- First flash platform(s) to support in Phase 3, driven by no-os CI priorities (STM32 / Maxim / Xilinx MicroBlaze).
