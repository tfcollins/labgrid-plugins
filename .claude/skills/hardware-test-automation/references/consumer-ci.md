# Consumer CI: wiring a repo onto the hardware-CI flow

This is the most-used path: a consumer repo (pyadi-iio, no-OS, TransceiverToolbox, …) calls a
**reusable workflow** hosted in `tfcollins/labgrid-plugins` to run its own tests on lab boards.

**The canonical recipe is `AGENTS.md` at the repo root.** It is written to be executed
step-by-step by an agent. Read it and follow it; this reference orients you and fills in the
"why", but `AGENTS.md` + the live templates are the source of truth. The human prose version is
`docs/source/user-guide/onboarding-a-consumer-repo.rst`.

## The three modes

Pick by what the consumer's tests actually are:

| Mode   | What it does                                                      | Discovery input                                   | Reusable workflow            | Reference consumer   |
|--------|------------------------------------------------------------------|---------------------------------------------------|------------------------------|----------------------|
| **uri**   | pytest over libIIO against a booted Linux board                | `@pytest.mark.iio_hardware(["<part>"])` markers   | `hw-request.yml`             | pyadi-iio            |
| **flash** | build no-OS firmware, JTAG-flash, validate serial banner       | `tools/hw_ci/projects.yaml` manifest              | `noos-hw-request.yml`        | no-OS                |
| **matlab**| MATLAB `runHWTests` against a booted board's URI               | `test/hw_ci/board_map.yaml`                       | `matlab-hw-request.yml`      | TransceiverToolbox   |

Advanced variant: **uri with `request-mode: reserve`** — the consumer drives boot itself via
the labgrid pytest plugin and an `LG_ENV` (e.g. per-test device-tree overlays). Only reach for
this when normal uri mode's "boot to shell, hand you a URI" isn't enough.

## The onboarding recipe (what AGENTS.md prescribes)

Five steps. Re-read AGENTS.md for the exact current wording — summarized here so you know the
shape:

1. **Pick the mode** (uri / flash / matlab, above).
2. **Copy templates into the consumer repo** from `adi_lg_plugins/hw_ci/onboarding_templates/` and
   replace the `<PLACEHOLDERS>` (see the template table below).
3. **Set three repo variables** in the consumer's GitHub Actions settings (below).
4. **Confirm lab prerequisites** (a catalog entry per board + a live tagged place + registered
   runners — *the lab admin owns these*, but you must confirm they exist or the matrix is empty).
5. **Verify before opening a PR** by running the discovery preflight locally (below).

## Onboarding templates

In `adi_lg_plugins/hw_ci/onboarding_templates/` — read the actual file before copying; placeholder names
and structure are authoritative there, not here.

| Template file                  | Copy to (in consumer repo)        | For mode | Purpose                                              |
|--------------------------------|-----------------------------------|----------|------------------------------------------------------|
| `hw-request-uri.yml`           | `.github/workflows/hw-request.yml`| uri      | The workflow that calls `hw-request.yml@v<tag>`      |
| `conftest-iio-uri.py`          | `test/hw/conftest.py`             | uri      | Provides the `iio_uri` pytest fixture                |
| `noos-hw-request-flash.yml`    | `.github/workflows/hw-request.yml`| flash    | The workflow that calls `noos-hw-request.yml@v<tag>` |
| `projects.yaml`                | `tools/hw_ci/projects.yaml`       | flash    | Manifest: one entry per buildable no-OS project      |
| `matlab-hw-request.yml`        | `.github/workflows/hw-matlab.yml` | matlab   | The workflow that calls `matlab-hw-request.yml@v<tag>` |
| `board-catalog-entry.yaml`     | *(reference only — lab admin)*    | all      | Shape of a `board_catalog.yaml` entry                |
| `AGENTS-consumer-stub.md`      | `AGENTS.md` (in consumer repo)    | all      | Consumer's own agent recipe; fill in mode + boards   |

## Minimal consumer workflow (uri mode)

This is the shape — **always start from the live template**, since input names and the pinned
tag evolve. Find the current tag first (`git tag --sort=-creatordate | head -1`).

```yaml
name: HW Request
permissions:
  contents: read
  checks: write
  pull-requests: write
on:
  workflow_dispatch:
  pull_request:
    types: [labeled]
jobs:
  hw-request:
    if: >-
      github.event_name == 'workflow_dispatch' ||
      contains(github.event.pull_request.labels.*.name, 'hw-request')
    uses: tfcollins/labgrid-plugins/.github/workflows/hw-request.yml@v3.5   # verify tag
    with:
      coordinator: ${{ vars.LG_COORDINATOR }}          # gRPC host:20408
      test-root: "test/hw"
      runner-label: ${{ vars.HW_REQUEST_RUNNER }}
      preflight-runner-label: ${{ vars.HW_PREFLIGHT_RUNNER }}
      install-cmd: |
        set -euo pipefail
        uv pip install --quiet --python "$VENV_DIR/bin/python" <YOUR_INSTALL_ARGS>
        uv pip install --quiet --python "$VENV_DIR/bin/python" \
          "labgrid-plugins @ git+https://github.com/tfcollins/labgrid-plugins.git@v3.5"
      # prism-upload: ${{ vars.PRISM_UPLOAD_ENABLED == 'true' }}
      # prism-project: <PRISM_PROJECT_SLUG>
    # secrets:                       # cross-org `secrets: inherit` does NOT work — pass explicitly
    #   PRISM_API_TOKEN: ${{ secrets.PRISM_API_TOKEN }}
    #   PRISM_EMAIL: ${{ secrets.PRISM_EMAIL }}
    #   PRISM_PASSWORD: ${{ secrets.PRISM_PASSWORD }}
```

flash mode calls `noos-hw-request.yml` with `manifest: "tools/hw_ci/projects.yaml"` instead of
`test-root`/`install-cmd`. matlab mode calls `matlab-hw-request.yml` with
`board-map: "test/hw_ci/board_map.yaml"` and `matlab-bin: ${{ vars.MATLAB_BIN }}`. Read each
template for the exact input set.

## The three repo variables (must exist before first run)

Set in the consumer repo → Settings → Secrets and variables → Actions → **Variables**. If
missing, jobs queue forever with empty inputs rather than erroring usefully.

| Variable             | Example            | Notes                                                    |
|----------------------|--------------------|----------------------------------------------------------|
| `LG_COORDINATOR`     | `lab-host:20408`   | **gRPC** port `:20408`, *not* REST `:8000`               |
| `HW_REQUEST_RUNNER`  | `hw-lab`           | Self-hosted runner label for per-board legs              |
| `HW_PREFLIGHT_RUNNER`| `hw-coordinator`   | Runner label that can reach the coordinator              |

matlab mode adds `MATLAB_BIN` (path to the matlab binary on the runner). Prism adds
`PRISM_UPLOAD_ENABLED` and `PRISM_URL` (plus the three secrets).

## Discovery preflight — verify without hardware

This is how you prove the wiring is correct *before* burning a board slot. It checks that
markers/manifest + catalog + live places line up. Run it (or hand the command to the user):

```bash
export LG_COORDINATOR=<host>:20408

# uri mode
adi-lg-hw-ci request-matrix --test-root test/hw --coord "$LG_COORDINATOR"
# flash mode
adi-lg-hw-ci noos-matrix --manifest tools/hw_ci/projects.yaml --coord "$LG_COORDINATOR"
# matlab mode
adi-lg-hw-ci matlab-matrix --board-map test/hw_ci/board_map.yaml --coord "$LG_COORDINATOR"
```

**Success** = `matrix.include` has one leg per board you expect, each with a non-empty `runner`.
An empty matrix means a tag mismatch (marker part ≠ catalog ≠ place tag) — the most common
onboarding failure.

## Gotchas specific to consumer CI

- **`secrets: inherit` does not work cross-org.** Pass `PRISM_API_TOKEN`/`PRISM_EMAIL`/
  `PRISM_PASSWORD` explicitly in the `secrets:` block.
- **flash mode runner needs Vivado/Vitis + ~10 GB free disk** for the Kuiper image.
- **Some Kuiper boot folders are named for a family** (e.g. adrv9371 lives under `…-adrv937x`);
  the default `*<carrier>*<board>*` search misses these — override `flash.kuiper_xsa_dir` in the
  catalog entry.
- **Stock Kuiper images randomize the DUT MAC each boot** → a fresh DHCP lease every boot. For a
  stable MAC use the `BootFPGASoCTFTP` strategy with a place tag `ethaddr=<mac>`, or
  `ethaddr=stock` to opt out.
- **Catalog edits require a coordinator redeploy** — the coordinator does not hot-reload
  `board_catalog.yaml`.

## Legacy: hw-matrix.yml

`hw-matrix.yml` (and `hw-matrix-v2.yml`) is the **older** reusable workflow — a static
`hw-nodes.json` manifest with `hw-direct` / `hw-coord` / `hw-dynamic` legs, JUnit aggregation
via `EnricoMi/publish-unit-test-result-action`, and a preflight that probes the coordinator with
`labgrid-client -x <coord> places`. New consumers should use the `hw-request` family above. Only
touch `hw-matrix.yml` when maintaining a repo already on it, or when explicitly asked. Its docs
are in `docs/source/user-guide/hardware-ci.rst`.
