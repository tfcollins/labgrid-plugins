# AGENTS.md — onboarding a repo onto ADI hardware CI

This file is for AI coding agents (and humans) wiring a **new consumer repo** onto the
labgrid-plugins hardware-CI flow. It is an executable recipe: follow the steps, run the
verify commands, then open the PR. The human reference with full prose is
`docs/source/user-guide/onboarding-a-consumer-repo.rst`; deep per-topic docs are linked
from there. Copy-paste starting files live in `docs/source/onboarding-templates/`.

> Repo-level guidance for working *inside this package* is in `CLAUDE.md`. This file is
> specifically about onboarding **other** repos as hardware-CI consumers.

## What this flow does

A consumer repo's CI calls a **reusable workflow** here. A *preflight* job discovers which
of the consumer's wanted boards are live on the lab **coordinator**, then fans out one CI
leg per board to a **self-hosted runner** co-located with that board. The board is
reserved, provisioned, exercised, and released automatically — the consumer never defines
labgrid drivers/strategies or touches a board directly. Boards are boot-verified (iiod
reachable) before tests run, and boot failures are reported distinctly (exit 12 plus an
`::error title=boot-failure::` annotation) so they never masquerade as test failures.

## Step 1 — pick the mode (decision tree)

| If the consumer… | Mode | Reusable workflow | Discovery |
|---|---|---|---|
| runs **Python/pytest** against a booted Linux board over libIIO (a URI) | **uri** | `hw-request.yml` | `@pytest.mark.iio_hardware(["<part>"])` markers |
| builds **bare-metal firmware**, JTAG-flashes it, validates over serial | **flash** | `noos-hw-request.yml` | a `tools/hw_ci/projects.yaml` manifest |
| runs **MATLAB** `runHWTests` against a URI | **matlab** | `matlab-hw-request.yml` | a `board_map.yaml` |
| **drives boot itself** via labgrid (pytest plugin + `LG_ENV`, e.g. per-test DTBs) | **uri workflow, `request-mode: reserve`** | `hw-request.yml` with `request-mode: "reserve"` | `@pytest.mark.iio_hardware(["<part>"])` markers |

> **Deprecation notice:** `hw-matrix.yml` and `hw-matrix-v2.yml` are deprecated. New
> consumers must use the hw-request family (`hw-request.yml`, `noos-hw-request.yml`,
> `matlab-hw-request.yml`) pinned at `@v3.1` (current release). Removal of the deprecated
> workflows is tracked by the HW-CI convergence effort.

Reference consumers: pyadi-iio (uri), no-os (flash), TransceiverToolbox (matlab). Matlab
now has a drop-in template at `onboarding-templates/matlab-hw-request.yml` and the
reusable `matlab-hw-request.yml` workflow — see Step 2 below. The rest of this file covers
all three modes.

## Step 2 — add the files to the consumer repo

Copy the matching template(s) from `docs/source/onboarding-templates/` and replace the
`<PLACEHOLDERS>`:

**uri mode**
- `.github/workflows/hw-request.yml` ← `hw-request-uri.yml` (set `test-root`, `install-cmd`).
- `test/hw/conftest.py` ← `conftest-iio-uri.py` (the `iio_uri` fixture).
- Mark the hardware tests: `@pytest.mark.iio_hardware(["<part>"])` — **string literals only**
  (the preflight AST-parses them; variables/f-strings are silently invisible).
- Optional carrier narrowing: `@pytest.mark.iio_carrier(["<carrier>"])`.

**flash mode**
- `.github/workflows/hw-request.yml` ← `noos-hw-request-flash.yml`.
- `tools/hw_ci/projects.yaml` ← `projects.yaml` (one entry per buildable project).
- Each `projects/<noos_project>/` must `make` an `.elf` (+ the workflow extracts the
  bitstream + ps7_init from the Kuiper `.xsa`).

**matlab mode**
- `.github/workflows/hw-matlab.yml` ← `matlab-hw-request.yml` (set `coordinator`, `runner-label`,
  `preflight-runner-label`, `matlab-bin`).
- `test/hw_ci/board_map.yaml` — maps `(daughter-board, carrier, hdl-config)` to the MATLAB board
  name passed to `runHWTests`. Most-specific entry wins. Example:
  ```yaml
  boards:
    - {carrier: zcu102, daughter-board: adrv9002, matlab_board: zynqmp-zcu102-rev10-adrv9002-vcmos}
    - {daughter-board: pluto, matlab_board: pluto}
  ```
- `runHWTests.m` reads `$IIO_URI` (exported by `adi-lg request`) and emits
  `<matlab_board>_HWTestResults.xml` — no test-side changes needed. The leg runner must
  have MATLAB installed (+ a reachable license).
- **One extra repo var beyond the Step-3 three**: `MATLAB_BIN` (path to the `matlab`
  binary on the runner, e.g. `/opt/MATLAB/R2025b/bin/matlab`).

Drop `docs/source/onboarding-templates/AGENTS-consumer-stub.md` into the consumer repo as
its own `AGENTS.md` and fill in the wiring.

## Step 3 — set the three repo variables (REQUIRED, easy to miss)

In the consumer repo: **Settings → Secrets and variables → Actions → Variables**:

| Variable | Value | Notes |
|---|---|---|
| `LG_COORDINATOR` | `<host>:20408` | the **gRPC** coordinator port — NOT the REST `:8000`. The workflow derives the REST API from it. |
| `HW_REQUEST_RUNNER` | e.g. `hw-lab` | fallback runner label for the per-board legs |
| `HW_PREFLIGHT_RUNNER` | e.g. `hw-coordinator` | runner label that can reach the coordinator |

If unset, matrix jobs receive empty values and fail.

**Optional — Prism result reporting** (`hw-request.yml` / `matlab-hw-request.yml`): two
more repo variables — `PRISM_UPLOAD_ENABLED` (`true` enables the `prism-upload` input)
and `PRISM_URL` (Prism base URL) — plus three Actions **secrets** passed explicitly in
the caller's `secrets:` block: `PRISM_API_TOKEN`, `PRISM_EMAIL`, `PRISM_PASSWORD`
(cross-org `secrets: inherit` does NOT work). See "Uploading results to Prism" in
`docs/source/user-guide/hw-request.rst`.

## Step 4 — confirm the prerequisites you do NOT own (ask a lab admin)

These live **coordinator-side** and **lab-side**; an agent cannot create them but MUST
verify they exist (Step 5 will fail clearly if they don't):

- **Catalog entry** for each `part` in `coordinator/api/board_catalog.yaml`
  (schema: `coordinator/api/app/catalog.py` → `BoardEntry`/`FlashConfig`; template:
  `onboarding-templates/board-catalog-entry.yaml`). uri needs `image`; flash needs a
  `flash:` block. After any catalog edit the coordinator host must be **redeployed**
  (it does not auto-update).
- **A live place** tagged `daughter-board=<part> carrier=<carrier> boot-strategy=<Strategy>`
  (+ optional `runner=<label>`).
- **Runner scope**: the lab runners must be registered on the consumer repo's (or its
  org's) GitHub scope, or legs queue forever. See
  `.github/scripts/register-hw-runners.sh --scopes`.
- **flash only**: the leg runner needs **Vivado/Vitis** installed (the workflow installs
  the `[kuiper]`/pytsk3 dep and sources the `.xsa` from the Kuiper image itself) and
  ~10 GB free disk for the Kuiper image.

## Step 5 — verify BEFORE opening the PR (uses existing CLI; no hardware)

Install the package (`pip install -e ".[dev]"` here, or `pip install adi-labgrid-plugins`)
and run the discovery preflight against the live coordinator — this proves the markers/
manifest + catalog + places line up:

```bash
export LG_COORDINATOR=<host>:20408

# uri mode: harvest markers under test-root, intersect with live boards
adi-lg-hw-ci request-matrix --test-root <test/hw> --coord "$LG_COORDINATOR"

# flash mode: intersect the manifest with live flash-capable boards
adi-lg-hw-ci noos-matrix --manifest tools/hw_ci/projects.yaml --coord "$LG_COORDINATOR"

# matlab mode
adi-lg-hw-ci matlab-matrix --board-map test/hw_ci/board_map.yaml --coord "$LG_COORDINATOR"
```

**Success** = the printed `matrix.include` has one leg per board you expect, each with a
non-empty `runner`. A wanted board with no live place is emitted as a `::warning::` skip
(that means the catalog/place is missing — Step 4). Other quick checks:

```bash
adi-lg-hw-ci list-strategies                    # the board's boot-strategy must appear here
# flash only — prove the .xsa is extractable for a board:
adi-lg-hw-ci fetch-xsa --release <2023_R2_P1> --board <canonical-board> --carrier <carrier>
```

Then trigger the workflow (`workflow_dispatch`, or add the `hw-request` PR label) and
confirm both the preflight and the per-board legs go green.

## Friction checklist (the things that actually go wrong)

- `LG_COORDINATOR` must be the **gRPC `:20408`**, not REST `:8000`.
- `@pytest.mark.iio_hardware(...)` args must be **string literals** (AST-parsed; computed
  lists are invisible to discovery).
- The **three repo vars** must exist before the first run.
- **Runner scope**: a runner registered only for `repo:a/b` cannot serve `repo:a/c` — each
  consumer repo (or the org) needs its own registration.
- **Place tags**: missing `daughter-board`/`carrier`/`boot-strategy`, or an unknown
  `boot-strategy`, silently drops the place from matching.
- **flash `kuiper_xsa_dir`**: some boards' Kuiper boot folders are named for a *family*
  (e.g. adrv9371 lives in `…-adrv937x`), so the `*<carrier>*<board>*` search misses —
  the catalog `flash.kuiper_xsa_dir` override pins the folder.
- **flash runner**: needs Vivado + the `[kuiper]`/pytsk3 install + ~10 GB disk for the
  Kuiper image.
- After editing the coordinator catalog, **redeploy the coordinator host** — it does not
  auto-update.

## Source of truth (cite, don't guess)

- Manifest schema: `adi_lg_plugins/hw_ci/noos_manifest.py` (`NoOSProject`).
- Place-tag schema: `adi_lg_plugins/hw_ci/schema.py` (`Place`, required/optional tags).
- Catalog schema: `coordinator/api/app/catalog.py` (`BoardEntry`, `FlashConfig`).
- Reusable workflow inputs: `docs/source/user-guide/github-actions.rst`.
- CLI: `docs/source/user-guide/cli.rst` (`adi-lg-hw-ci`, `adi-lg request`).
- **Pinning**: consumer `uses:` lines must reference `@v3.1` (current release), e.g.
  `uses: tfcollins/labgrid-plugins/.github/workflows/hw-request.yml@v3.1`. Bump the pin
  when a new release tags. Never pin to `@main` in production workflows.
