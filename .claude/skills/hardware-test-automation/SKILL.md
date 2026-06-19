---
name: hardware-test-automation
description: >-
  Design and generate automation that uses adi-labgrid-plugins to run tests against real
  hardware. Covers three things: (1) GitHub Actions CI for consumer repos that run their tests
  on lab boards via the reusable hw-request workflows, (2) standalone Python/bash scripts that
  acquire, boot, flash, and drive boards through the adi-lg CLI and labgrid, and (3) exporter
  and coordinator setup to bring hardware online and register self-hosted runners. Use this
  whenever the user wants to run tests on hardware, wire a repo into the hardware-CI flow,
  onboard a consumer repo, acquire/boot/flash/provision a board, write a script that drives
  labgrid or adi-lg, set up a self-hosted runner or exporter, or otherwise leverage this
  project to manage hardware for testing — even if they don't name labgrid, hw-request, or a
  specific workflow file.
---

# Hardware-test automation with adi-labgrid-plugins

This skill helps you design automation — GitHub Actions, scripts, or lab infrastructure — that
uses **this repo** (`adi-labgrid-plugins`) to acquire, boot, flash, and test physical boards.

The defining risk here is **broken automation that looks plausible**: a workflow that pins a
stale tag, a script that imports a function that was renamed, a place filter that silently
matches nothing. Hardware CI fails slowly and expensively (jobs queue for 30 minutes, then
time out), so correctness against the *current* repo matters more than speed.

## Core principle: the repo is the source of truth

Everything this skill describes — workflow inputs, the `request()` API, CLI flags, template
filenames, the current release tag — **lives in the repo and changes over time.** This skill
points you at the canonical building blocks; it does not replace reading them.

Before you generate anything, **adapt a real, current building block rather than inventing
from memory or from this skill's prose.** Concretely:

1. **Find the canonical artifact** for the task (a template, a reusable workflow, the
   `request()` source, a CLI command). The reference files below tell you where each lives.
2. **Read its current version** with the file tools. Input names, function signatures, and
   the pinned tag drift between releases — a value quoted in this skill may already be stale.
3. **Adapt it** to the user's specifics. Preserve the proven structure; change only what the
   task requires. When you must go beyond what the building blocks cover, say so and explain
   what you built instead and why (this is the "custom fallback" — it's allowed, but flag it).

The reason this matters: a consumer CI workflow that pins `@v3.4` when the repo is on `@v3.5`,
or a script that calls a renamed strategy, *looks* right in review and only fails once it's
burning a real board's time slot. Grounding every artifact in a freshly-read source is the
cheapest way to avoid that.

**Pinning:** consumer workflows must pin a release tag, never `@main`. Find the current tag
with `git -C <repo> tag --sort=-creatordate | head -1` (or check GitHub releases). At the time
of writing the latest is `v3.5`, but **verify** — don't hardcode it from this sentence.

## Step 1 — Classify the request

Almost every request maps to one of three domains. Identify which (a request can span two —
e.g. "onboard my repo and I also need the board added to the lab"):

| If the user wants to…                                                                 | Domain | Read |
|---------------------------------------------------------------------------------------|--------|------|
| Run *their repo's* tests on hardware in GitHub CI; "onboard", "hw-request", "hw CI", a PR-triggered hardware job | **Consumer CI** | `references/consumer-ci.md` |
| Acquire/boot/flash/provision a board from a script or notebook; run pytest against hardware locally; drive labgrid/`adi-lg` outside GitHub | **Standalone scripts** | `references/standalone-scripts.md` |
| Bring a board online; deploy an exporter; register a self-hosted runner; add a board to the catalog; define place tags | **Exporter / coordinator infra** | `references/exporter-coordinator.md` |

If the request is ambiguous between domains, ask one sharp question rather than guessing —
"Do you want this to run in GitHub CI, or as a script you run in the lab?" decides almost
everything downstream.

## Step 2 — For Consumer CI, pick the mode

Consumer CI is the most-used and most-supported path, and it has three modes. Pick by what the
consumer's tests actually *are* (full detail in `references/consumer-ci.md`):

- **uri** — Python/pytest talking to a booted Linux board over libIIO. Tests carry
  `@pytest.mark.iio_hardware(["<part>"])` markers. Reusable workflow: `hw-request.yml`.
  Reference consumer: pyadi-iio.
- **flash** — build bare-metal no-OS firmware, JTAG-flash it, validate the serial banner.
  Boards listed in a `projects.yaml` manifest. Reusable workflow: `noos-hw-request.yml`.
  Reference consumer: no-OS.
- **matlab** — run MATLAB `runHWTests` against a booted board's URI; needs a MATLAB license on
  the runner. Boards mapped in `board_map.yaml`. Reusable workflow: `matlab-hw-request.yml`.
  Reference consumer: TransceiverToolbox.

The canonical, step-by-step onboarding recipe is **`AGENTS.md` at the repo root** — treat it as
executable and follow it; don't reconstruct the wiring from per-page docs. The copy-paste
templates live in `docs/source/onboarding-templates/`.

## Step 3 — For scripts, pick the abstraction level

Prefer the highest-level tool that does the job (detail in `references/standalone-scripts.md`):

1. **`request()` context manager** (`from adi_lg_plugins.request import request`) — reserve +
   acquire + boot + release, all automatic. Use this for "give me a booted board and a URI"
   and "flash this firmware and check the serial output." This is the default.
2. **`adi-lg` CLI** (`boot-fabric`, `boot-soc`, `provision-software`, `download-cloudsmith`, …)
   — when a one-shot command in a shell script is cleaner than Python.
3. **Raw labgrid** (`Environment → get_target → get_driver / strategy.transition`) — only when
   you need control the wrappers don't expose, or you're inside a pytest hardware test with an
   `--lg-config`. Going here is the custom fallback; reach for it last.

## Cross-cutting facts that are easy to get wrong

These bite across all three domains. Read the relevant reference file for the rest, but never
violate these:

- **Coordinator port.** `LG_COORDINATOR` / `coordinator:` is the **gRPC** endpoint, host
  **`:20408`** — *not* the REST bridge on `:8000`. Using `:8000` for reservations fails with an
  opaque HTTP 400. (The dynamic-discovery REST calls *do* use `:8000` — but that's derived
  internally, not what you put in `coordinator:`.)
- **Place matching is by tags, and missing tags fail silently.** A place must be tagged
  `daughter-board=<part> carrier=<carrier> boot-strategy=<Strategy>` (plus optional
  `runner=<label>`, `ethaddr=<mac>`). A missing or unknown tag drops the place from matching
  with no error — the matrix just comes up empty.
- **Markers are AST-parsed, so arguments must be string literals.**
  `@pytest.mark.iio_hardware(["ad9361"])` works; a variable or f-string is invisible to
  discovery and the board is silently never tested.
- **`imports: [adi_lg_plugins]` is required in every labgrid env YAML.** Upstream labgrid has
  no entry-point auto-discovery; without this key (or an explicit `import adi_lg_plugins`), ADI
  drivers/resources/strategies don't resolve by name.
- **Pin a tag.** Consumer `uses:` lines reference `@v<tag>`, never `@main`. This repo must stay
  public for cross-org callers.
- **Verify before you claim done.** For CI, the discovery preflight (`adi-lg-hw-ci
  request-matrix` / `noos-matrix` / `matlab-matrix`) proves markers + catalog + live places
  line up *without* touching hardware — run it (or tell the user to) before declaring a wiring
  correct. Don't assert a workflow "works" from reading alone.

## Reference files

Read the one(s) matching the domain from Step 1. Each is self-contained and grounded in real
file paths you should re-read for current values.

- **`references/consumer-ci.md`** — the hw-request family end to end: choosing uri/flash/matlab,
  the AGENTS.md recipe, every onboarding template, the three repo variables, the discovery
  preflight, Prism reporting, and the legacy `hw-matrix.yml` path.
- **`references/standalone-scripts.md`** — `request()` modes and return fields, the full
  `adi-lg` CLI surface, raw-labgrid acquire/boot, the strategy catalog, and the pytest
  hardware flags/markers.
- **`references/exporter-coordinator.md`** — exporter config templates, `register-hw-runners.sh`
  multi-scope registration, the board catalog, place-tag schema, and coordinator wiring.
