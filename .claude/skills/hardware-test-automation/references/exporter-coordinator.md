# Exporter / coordinator infrastructure

The "bring hardware online" side — distinct from running tests. You're here when the user needs
a board to *exist* in the system before any CI or script can acquire it: deploying an exporter,
registering self-hosted runners, adding a board to the catalog, or defining place tags. Most of
this is owned by a lab admin; an empty CI matrix usually traces back to a gap here.

The work lives in two sibling subprojects with their own conventions (see the repo's
`CLAUDE.md`): **`exporter_configs/`** and **`coordinator/`**. Read those before generating —
they evolve independently of the plugin package.

## How the pieces connect

```
 exporter host (RPi / VCU118 / ZCU102 …)         coordinator host
 ┌─────────────────────────────┐                 ┌──────────────────────────┐
 │ labgrid-exporter             │  gRPC :20408    │ labgrid coordinator       │
 │  + exporter_configs YAML     │ ───────────────▶│  (places, reservations)   │
 │  (declares resources/places) │                 │ FastAPI bridge :8000      │
 └─────────────────────────────┘                 │ board_catalog.yaml        │
 self-hosted GH runner on the host                │ env-gen                   │
   (registered via register-hw-runners.sh)        └──────────────────────────┘
```

A place is acquirable only when **all** of these exist: an exporter exporting it, a catalog
entry for its board, the right **tags**, and (for CI) a runner that can reach it.

## Exporter configs — `exporter_configs/`

YAML templates for deploying labgrid exporters, plus validation:

- `exporter_configs/templates/*.yaml` — per-host-class templates (RPi / VCU118 / ZCU102 …).
  Start from the closest template; don't author an exporter config from scratch.
- `exporter_configs/validate.py` + `exporter_configs/schemas/*.json` — **validate every config
  you produce** against the schema before deploying. A malformed exporter config fails to export
  the place, which shows up downstream as a silently-missing place.

Every committed env YAML and render template carries `imports: [adi_lg_plugins]` so ADI
drivers/resources/strategies resolve by name — keep that key when you edit or generate one.

## Place tags — the matching contract

Places are matched by tags (schema in `adi_lg_plugins/hw_ci/schema.py`, `Place`). A board is
discoverable by CI / `request()` only when tagged:

| Tag             | Required | Meaning                                                            |
|-----------------|----------|--------------------------------------------------------------------|
| `daughter-board`| yes      | The part (matched against markers / catalog), e.g. `ad9361`        |
| `carrier`       | yes      | The FPGA carrier, e.g. `zcu102`                                    |
| `boot-strategy` | yes      | Strategy class name, e.g. `BootFPGASoC` (must be a real strategy)  |
| `runner`        | optional | Self-hosted runner label that can drive this place                 |
| `ethaddr`       | optional | Fixed MAC for TFTP boot; `stock` opts out of MAC pinning           |
| `disabled`      | optional | `disabled=<reason>` quarantines the place (dynamic discovery skips it) |

A missing required tag or an unknown `boot-strategy` drops the place from matching **silently** —
no error, the matrix just comes up empty. This is the single most common "why isn't my board
showing up" cause.

## Board catalog — `coordinator/api/board_catalog.yaml`

Defines each board the coordinator knows about (schema: `coordinator/api/app/catalog.py`,
`BoardEntry` / `FlashConfig`). uri-mode boards need an `image:`; flash-mode boards need a
`flash:` block. The template shape is `adi_lg_plugins/hw_ci/onboarding_templates/board-catalog-entry.yaml`.

**Editing the catalog requires redeploying the coordinator host** — it does not hot-reload.

## Registering self-hosted runners — `.github/scripts/register-hw-runners.sh`

Registers GitHub Actions runners on lab hosts, including **one lab host across multiple GitHub
scopes** (orgs/repos) via `--scopes`. Re-read the script's header for current flags.

```bash
.github/scripts/register-hw-runners.sh \
  --hosts-file ./hosts.tsv \
  --scopes org:analogdevicesinc,repo:tfcollins/labgrid-plugins,repo:tfcollins/vrt49 \
  [bq mini2]   # optional alias filter
```

Hosts file is TSV: `alias  ssh_target  runner_label  runner_name_base  [lg_direct_env_path]`.
Per host × scope it mints a registration token, SCPs a bootstrap script, and installs a runner
service in `~/actions-runner-<scope_slug>/` named `<base>-<scope_slug>` with labels
`self-hosted,<runner_label>`. The optional 5th column writes `LG_DIRECT_ENV=<path>` into the
runner's `.env` for direct-mode legs. Requires `gh` auth with admin on each scope.

The runner-setup human guide is `docs/source/user-guide/hardware-ci.rst` (the runner-setup
section) and `docs/source/user-guide/hardware-ci-runner-setup.rst`.

## Coordinator stack — `coordinator/`

Docker-compose stack: the labgrid coordinator, a FastAPI REST/WebSocket bridge
(`coordinator/api/`), and a React/Vite dashboard (`coordinator/web/`). Brought up with
`docker compose up -d` from `coordinator/`. Ports: coordinator `:20408` (gRPC — what clients
reserve against), API `:8000` (REST/WebSocket bridge), web `:3000`.

Env-gen (`coordinator/api/app/env_gen.py`) renders labgrid env YAML for a place on demand
(this is what dynamic CI fetches from `/api/places/<name>/env-yaml`); it emits
`imports: [adi_lg_plugins]`. When you change how envs are generated, work inside `coordinator/` —
its dependency set and ruff config are independent of the top-level package, and its tests run
from `coordinator/api/`, not the top-level `nox -s tests`.

## A "board isn't acquirable" checklist

When CI or a script can't find a board, walk the chain in this order:

1. Is an **exporter** running on the host and exporting the place? (validate its config)
2. Is there a **catalog entry** for the part, with `image:`/`flash:` as the mode needs? (and was
   the coordinator **redeployed** after the edit?)
3. Are the **place tags** complete and correct (`daughter-board`/`carrier`/`boot-strategy`)?
4. Is a **runner** with the expected label online on the right GitHub scope?
5. Does the **marker/manifest part string** match the catalog and the tag *exactly*?

The discovery preflight (`adi-lg-hw-ci request-matrix …`, see `references/consumer-ci.md`)
collapses 2–5 into one no-hardware command — run it first.
