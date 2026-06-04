# Hardware-CI Consolidation — Design

**Date:** 2026-06-04
**Status:** Approved (architecture + data flow); spec under review.

## Context

The low-config hardware-test flow now drives three repos: `labgrid-plugins`
(the shared coordinator + reusable workflows + the `adi_lg_plugins` package),
`pyadi-iio` (uri mode — pytest against a booted board), and `no-os` (flash mode
— build firmware, JTAG-flash, validate on serial). It works end-to-end and is
green in CI on real hardware (ad9371/bq, adrv9009/nemo).

Getting there left the **DUT repos carrying lab/toolchain knowledge that isn't
theirs**. no-os's `hw-request.yml` has a ~15-line inline `build-cmd` shell block
(source Vivado, a `libtinfo` `LD_LIBRARY_PATH` shim, `NOOS_VITIS_HSI_FLOW=1`,
resolve the `.xsa` from a hand-staged `NOOS_XSA_DIR` with a **buggy** fallback
that silently builds the wrong board, then `unzip` the bitstream + ps7_init),
and the lab runner must be provisioned with `NOOS_XSA_DIR`, `VITIS_SETTINGS`,
and the shim. Any future flash-DUT would copy all of it. Inside
`labgrid-plugins`, `_resolve_api` and the two matrix CLI commands are duplicated,
the boot banner default lives in three places, and `kuiperdldriver.py` carries
dead stubs and a typo. Docs predate flash mode.

This change pushes the lab/toolchain logic **back into `labgrid-plugins` as
unit-tested Python CLI subcommands**, sources the board's `.xsa` automatically
**from the Kuiper image** (eliminating `NOOS_XSA_DIR`), declares per-project
metadata in the manifest, removes the duplication and cruft, and documents the
single remaining host requirement (Vivado). Outcome: a DUT repo opts into
hardware CI with a manifest and four workflow inputs; the lab knowledge has one
home.

## Goals / Non-goals

**Goals**
- DUT `build-cmd` collapses to a single command; no per-DUT shell, no
  `NOOS_XSA_DIR`, no manual shim, no `.xsa` staging.
- The board's `.xsa` is fetched from the Kuiper image, keyed by the place's
  board + carrier, cached per release.
- Per-project metadata (validation banner, extra build vars) is declared once in
  the manifest, not hardcoded in the workflow.
- Remove duplication (`_resolve_api`, the matrix CLI tails, the banner default)
  and cruft (the `.xsa` fallback bug, `kuiperdldriver` stubs/typo, stale docs).
- A hardware-CI runner-setup + flash-mode doc.

**Non-goals**
- Merging the two reusable workflows into one (uri vs flash legs differ enough;
  keep them separate, share only the preflight).
- Changing the uri/pyadi flow behaviour (only the shared `_resolve_api` move and
  the shared preflight action touch it).
- HDL builds (the `.xsa` comes from Kuiper, not a Vivado HDL build).

## Architecture

```
DUT repo (no-os):                     labgrid-plugins (shared):
  tools/hw_ci/projects.yaml  ──┐
  .github/workflows/             │   .github/workflows/noos-hw-request.yml
    hw-request.yml (4 inputs) ───┼──▶   preflight:  adi-lg-hw-ci noos-matrix
                                 │        → matrix[{part, noos_project, carrier,
                                 │                   runner, board, release,
                                 │                   validate_banner, build_vars}]
                                 │      per leg:
                                 │        build:  adi-lg-hw-ci build-noos …
                                 │        flash:  adi-lg request --mode flash …
                                 │
  runner: Vivado installed ◀─────┘   adi_lg_plugins/hw_ci/
                                       kuiper_xsa.py   (fetch .xsa from Kuiper)
                                       build_noos.py   (env + orchestrate make)
                                       cli.py          (fetch-xsa, build-noos,
                                                        noos-matrix, request-matrix)
```

The boundary: **Python owns the lab/toolchain logic** (env construction, the
Kuiper `.xsa` fetch, manifest parsing, matrix building — all unit-tested); the
**workflow stays thin** (checkout → setup-venv → `build-noos` → `request`); the
**DUT declares intent** (the manifest + four inputs).

## Components

### 1. `hw_ci/kuiper_xsa.py` + `adi-lg-hw-ci fetch-xsa`  *(the key new feature)*

The Kuiper download + boot-FAT-partition reader currently lives inside
`KuiperDLDriver` (a labgrid driver bound to a `KuiperRelease` resource + a
target). Refactor the reusable parts into a standalone module so both the driver
and the CI CLI use them:

- Extract the image download/cache + `IMGFileExtractor` FAT-partition reading
  into helpers callable without a labgrid target. `KuiperDLDriver` keeps its
  resource-bound methods but delegates to the shared helpers (DRY).
- `fetch_board_xsa(release, board, carrier, cache_dir, *, xsa_dir=None) -> Path`:
  1. Locate/download the Kuiper image for `release` (reuse the existing
     download + cache; default cache `~/.labgrid/kuiper_releases/`).
  2. Resolve the board's boot-partition folder: use `xsa_dir` if given
     (catalog `flash.kuiper_xsa_dir`), else **search** the FAT partition for a
     directory matching `*<carrier>*<board>*` (case-insensitive) that contains
     `bootgen_sysfiles.tgz`. Raise a clear error listing candidates if 0 or >1
     match.
  3. Extract `<folder>/bootgen_sysfiles.tgz` from the FAT partition, then
     `system_top.xsa` from the tgz, into `cache_dir/<release>/<board>_<carrier>/`.
     Cache the result (skip re-extraction if present).
  4. Return the `.xsa` path.

- `adi-lg-hw-ci fetch-xsa --release R --board B --carrier C [--out PATH]
  [--xsa-dir DIR]` — thin CLI wrapper; prints the resolved `.xsa` path.

`board` is the **canonical daughter-board** (e.g. `adrv9371`, not the alias
`ad9371`) — that's what the Kuiper folder is named after. The matrix supplies it
(see §3). Kuiper folder examples: `zynq-zc706-adv7511-adrv9009`,
`zynqmp-zcu102-rev10-adrv9002` — the `*<carrier>*<board>*` search handles the
`adv7511`/`rev10` infixes.

### 2. `hw_ci/build_noos.py` + `adi-lg-hw-ci build-noos`

The DUT's single build entry point. `build-noos --project P --carrier C --board
B --release R [--validate BANNER] [--build-var K=V ...]`:

1. **Vivado**: source from `$VITIS_SETTINGS`, else auto-detect the newest
   `/opt/Xilinx/Vivado/*/settings64.sh` or `/tools/Xilinx/*/Vivado/settings64.sh`.
   Capture its env via `bash -c "set +u; source … ; env -0"` (handles the
   2025.1 unbound-`PYTHONPATH`-under-`set -u` quirk).
2. **libtinfo shim**: ensure `~/.local/xlnxshim/{libtinfo,libncurses,libncursesw}.so.5`
   exist as symlinks to the system `.so.6` (idempotent; create if missing) and
   prepend to `LD_LIBRARY_PATH`. Removes the host pre-provisioning step.
3. Set `NOOS_VITIS_HSI_FLOW=1` (pure-hsi project flow; no Eclipse backend).
4. `xsa = fetch_board_xsa(release, board, carrier, …)`; copy to
   `projects/P/system_top.xsa`; extract `ps7_init.tcl` + `system_top.bit` into
   `projects/P/build_hw/`.
5. `make -C projects/P <build_vars>` with the composed env.
6. Print the artifact paths (`.elf`, `build_hw/system_top.bit`,
   `build_hw/ps7_init.tcl`) so the flash step can consume them.

The env construction, shim management, Vivado auto-detect, and the `fetch_board_xsa`
call are unit-tested; the `make`/Vivado invocation is the integration boundary
(mocked in unit tests).

### 3. Discovery: manifest + matrix plumbing

**Manifest** (`no-os/tools/hw_ci/projects.yaml`) — Pydantic-validated (replaces
raw-dict access in `noos_manifest.py`), with optional per-project metadata:
```yaml
projects:
  - noos_project: adrv9009
    part: adrv9009
    carriers: [zc706]
    validate_banner: "Successfully initialized"   # default if omitted
    build_vars: {}                                 # extra make vars
```
`NoOSProject`/`NoOSLeg` gain `validate_banner` (default `"Successfully
initialized"`) and `build_vars`.

**`noos-matrix`** emits per leg: `{part, noos_project, carrier, runner, board,
release, validate_banner, build_vars}`. `board` + `release` come from the
`/api/match?mode=flash` result (the canonical daughter-board from
`reservation_filter`, the Kuiper release from `image`). The reusable workflow's
build step calls `build-noos --board ${{matrix.board}} --release
${{matrix.release}} --validate "${{matrix.validate_banner}}" …`; the flash step
validates on `matrix.validate_banner`.

**Matching** (`coordinator/api/app/matching.py`): flash mode now returns `image`
(the board's Kuiper release — today it returns `None`) so the matrix can carry
the `.xsa` source release. Alias resolution already yields the canonical
`reservation_filter` daughter-board; the matrix uses it as `board`.

### 4. Catalog `FlashConfig` extensions

```python
class FlashConfig(BaseModel):
    strategy: str
    noos_project: str
    a9_target_name: str | None = None    # per-board override; else env_gen default
    kuiper_xsa_dir: str | None = None    # explicit Kuiper boot folder; else search
```
`env_gen` emits `a9_target_name` from the catalog when set (otherwise the
existing `*Cortex-A9 MPCore #0` default), removing the hardcoded board
assumption.

## DRY + cruft + docs

- **`_resolve_api`** moves from `request/core.py` to `hw_ci/coordinator.py`
  (beside `resolve_coordinator`); `core.py` and both `cli.py` callsites import it
  from there. The gRPC→REST derivation has one home.
- **Matrix CLI tail** — extract the `$GITHUB_OUTPUT` write + `::warning::`
  annotation loop into `_emit_matrix(matrix, count, missing, kind)`; both
  `request-matrix` and `noos-matrix` call it.
- **Banner default** — one value `"Successfully initialized"` in `env_gen`
  `STRATEGY_CONFIGS[BootNoOSJTAG]` and the `BootNoOSJTAG` strategy attr, as the
  fallback when `--validate` is not passed.
- **Shared preflight (lower priority)** — extract the identical preflight job
  (setup-venv → `*-matrix` → outputs) into a `.github/actions/hw-preflight`
  composite action used by both `hw-request.yml` and `noos-hw-request.yml`.
- **Cruft**: delete the no-os `.xsa` `adrv9371` fallback (subsumed by
  `build-noos`); in `kuiperdldriver.py` remove the no-op `__del__`, fix the
  `"FAILEDZz"` typo, and resolve the `NotImplementedError` boot-files stub
  (implement-or-remove); refresh the stale `hardware-ci.rst` "flash deferred"
  note.
- **Docs**: new `docs/source/user-guide/hardware-ci-runner-setup.rst` (register a
  runner; the one host requirement = Vivado; the manifest format; flash mode;
  troubleshooting noting Channel-closed + libtinfo are now auto-handled);
  extend `hw-request.rst` with the flash/`build-noos` flow.

## Resulting DUT (no-os) workflow

```yaml
jobs:
  noos-hw-request:
    uses: tfcollins/labgrid-plugins/.github/workflows/noos-hw-request.yml@main
    with:
      coordinator: ${{ vars.LG_COORDINATOR }}
      manifest: "tools/hw_ci/projects.yaml"
      runner-label: ${{ vars.HW_REQUEST_RUNNER }}
      preflight-runner-label: ${{ vars.HW_PREFLIGHT_RUNNER }}
```
`build-cmd`/`bitstream-path`/`ps7-init-path`/`validate-banner` drop to defaults
(`build-cmd` defaults to `adi-lg-hw-ci build-noos …`; the artifact paths are its
known outputs; the banner comes from the manifest). Runner setup: install Vivado,
register the runner.

## Error handling

- `fetch_board_xsa`: 0/multiple folder matches → error listing candidates; tgz
  missing `system_top.xsa` → clear error; download/MD5 failure → propagate with
  the release name.
- `build-noos`: no Vivado found → actionable error (set `VITIS_SETTINGS`); `make`
  non-zero → propagate the tail; shim target `.so.6` absent → error naming the
  package.
- Matching: flash mode on a board without a `flash` block stays unsatisfiable
  (unchanged); missing `image` for a flash board → matrix annotates it as a skip.

## Testing

- `kuiper_xsa`: board→folder search (match / no-match / ambiguous), tgz→`.xsa`
  extraction, cache reuse — against a fixture FAT listing / mocked `IMGFileExtractor`.
- `build_noos`: Vivado auto-detect, env composition (incl. the `set +u` source),
  shim creation idempotency, the orchestration order — mocking `fetch_board_xsa`
  and the `make` subprocess.
- `noos_manifest`: Pydantic validation (good/missing-keys/defaults); `noos-matrix`
  emits `board`/`release`/`validate_banner` per leg; API derivation via the moved
  `_resolve_api`.
- `matching`: flash mode returns `image`; flash + alias → canonical
  `reservation_filter`.
- `xilinxjtagdriver`: the `load_and_run_elf` path-absolutize (keep/extend).
- `_resolve_api` tests follow it to `hw_ci/coordinator`.
- All new test files added to `.github/workflows/tests.yml`.

## Verification

- Unit: `pytest coordinator/api/tests/` + the plugin tests (`nox -s tests -- …`);
  `ruff`.
- Live (no hardware): redeploy the coordinator; `GET /api/match?part=adrv9009&
  mode=flash` returns `image`; `adi-lg-hw-ci fetch-xsa --release 2023_R2_P1
  --board adrv9009 --carrier zc706` extracts the `.xsa` from the cached Kuiper
  image; `adi-lg-hw-ci noos-matrix` emits the enriched legs.
- End-to-end: re-run the no-os workflow with the trimmed `with:` block — both
  legs (ad9371/bq, adrv9009/nemo) stay green, now with no `NOOS_XSA_DIR` and the
  DUT `build-cmd` gone.

## Risks

- The Kuiper image is ~3.5 GB; `fetch_board_xsa` must cache aggressively
  (download once per release per runner) and the runner needs disk headroom.
- The folder search convention (`*<carrier>*<board>*`) may need the
  `kuiper_xsa_dir` override for irregular board names — the override exists for
  exactly that.
- Sourcing Vivado from Python and capturing env must preserve the working
  behaviour proven on bq (2023.2) and nemo (2025.1).
