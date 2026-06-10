<!-- Template — copy into <consumer-repo>/AGENTS.md; replace <PLACEHOLDERS>. -->
# AGENTS.md — <consumer-repo> hardware CI

This repo runs hardware tests via the shared **labgrid-plugins** hardware-CI flow.
The canonical, mode-by-mode onboarding recipe lives in the hub — read it first:
<https://github.com/tfcollins/labgrid-plugins/blob/main/AGENTS.md>
(human guide: the *Onboarding a consumer repo* page in the labgrid-plugins docs).

## How this repo is wired (mode: `<uri | flash | matlab>`)

- **Workflow:** `.github/workflows/hw-request.yml` → reusable
  `tfcollins/labgrid-plugins/.github/workflows/<hw-request | noos-hw-request>.yml@main`
- **Discovery:** `<@pytest.mark.iio_hardware([...]) under <test-root> | manifest tools/hw_ci/projects.yaml>`
- **Repo variables** (Settings → Secrets and variables → Actions → Variables):
  `LG_COORDINATOR` (gRPC `:20408`), `HW_REQUEST_RUNNER`, `HW_PREFLIGHT_RUNNER`
  - Optional Prism reporting also needs `PRISM_UPLOAD_ENABLED` + `PRISM_URL` variables
    and the `PRISM_API_TOKEN`/`PRISM_EMAIL`/`PRISM_PASSWORD` secrets passed explicitly
    in the caller's `secrets:` block (cross-org `secrets: inherit` does NOT work); see
    "Uploading results to Prism" in the hub docs.
- **Boards covered:** `<list the parts>`

## To add a board or extend coverage

Follow the hub `AGENTS.md`. In short:

1. Add a `<@pytest.mark.iio_hardware(["<part>"]) marker | manifest entry>`.
2. Confirm the coordinator catalog has the `<part>` and a live `place` is tagged for it
   (a lab admin owns this).
3. Verify before opening a PR:
   ```bash
   export LG_COORDINATOR=<gRPC host:port>
   adi-lg-hw-ci <request-matrix --test-root <dir> | noos-matrix --manifest tools/hw_ci/projects.yaml> \
       --coord "$LG_COORDINATOR"
   # expect a matrix leg for your new board; a missing board is annotated as skipped.
   ```
