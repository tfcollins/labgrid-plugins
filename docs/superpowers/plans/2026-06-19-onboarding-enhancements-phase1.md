# Onboarding Enhancements — Phase 1 Implementation Plan (correctness + docs)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the fast, high-value onboarding fixes — the coordinator port/var contract, the MATLAB trigger-label bug, consumer-facing pin drift, and the deprecation/discoverability doc cleanup — so a new consumer's first run stops failing on documented-but-unenforced gotchas.

**Architecture:** One small library helper + its wiring (`coordinator.warn_if_rest_port`, called by the four discovery commands) plus a set of exact doc/YAML/template edits. No new subsystems; Phase 2 (CLI automation) and Phase 3 (scaffolder/packaging) follow in their own plans.

**Tech Stack:** Python 3.10+ (argparse `adi-lg-hw-ci` CLI), pytest, ruff, nox (uv backend), Sphinx (rst docs), GitHub Actions YAML.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-06-19-onboarding-enhancements-design.md`. This plan implements **Phase 1** (WS-A, WS-D Phase-1 pin fixes, WS-E).
- **Branch:** `onboarding-enhancements` (already created off `main`; the spec is committed there). Do NOT create another branch.
- **Canonical coordinator var/port:** consumers set repo var **`LG_COORDINATOR`** = the **gRPC** coordinator `host:20408`. The REST API (`:8000`) is **derived automatically**. Never show `:8000` as a `coordinator` value or input description; never tell a consumer to set `ADI_LG_COORDINATOR` (it remains a CLI env *fallback* only).
- **Canonical consumer pin:** `@v3.5` (current release tag). Consumer-facing `uses:`/examples/comments use `@v3.5`; never `@main` in a consumer-facing example (the deprecated hw-matrix examples are the only exception and must be labeled deprecated).
- **Do NOT** touch the reusable workflows' *internal* `@main` self-refs (handled at release time by `scripts/pin-release-refs.sh`; `main` keeps `@main` by design).
- **MATLAB trigger label** is `hw-request` (same as uri/flash), matching `AGENTS.md`.
- **Gates:** `nox -s lint` clean; `nox -s tests -- <file>` green for the touched test; `nox -s docs` builds clean after rst changes. (If running tools directly: `pip install -e ".[dev,docs]"` first, then `python -m pytest <file>`, `ruff check .`, `sphinx-build -b html docs/source docs/_build`.)
- New tests must be in a file CI runs (`.github/workflows/tests.yml` runs an explicit list incl. `tests/hw_ci/test_coordinator_resolve_api.py`).

## File structure (Phase 1)

| File | Responsibility | Change |
|---|---|---|
| `adi_lg_plugins/hw_ci/coordinator.py` | coordinator resolution | + `warn_if_rest_port(coord)` helper, + `import sys` |
| `adi_lg_plugins/hw_ci/cli.py` | CLI commands | call the helper in the 4 discovery commands |
| `tests/hw_ci/test_coordinator_resolve_api.py` | coordinator unit tests (CI-listed) | + 3 tests for the helper |
| `.github/workflows/hw-request.yml`, `noos-hw-request.yml` | reusable workflows | fix `coordinator` input descriptions; fix `@v3`/`:8000` example |
| `docs/source/onboarding-templates/matlab-hw-request.yml` | matlab template | `hw-test` → `hw-request` |
| `docs/source/onboarding-templates/AGENTS-consumer-stub.md` | consumer stub | `@v3` → `@v3.5` (+ reserve note) |
| `docs/source/onboarding-templates/hw-request-uri.yml`, `projects.yaml` | templates | reserve knob; build_vars note |
| `docs/source/user-guide/{hardware-ci,hw-ci-v2,hw-ci-bash,github-actions,hw-request,onboarding-a-consumer-repo}.rst` | docs | deprecation banners, var/port fixes, recipe polish, discoverability |
| `docs/source/user-guide/index.rst`, `docs/source/index.rst` | doc nav | "start here" entry + toctree grouping |
| `.github/workflows/hw-matrix.yml`, `hw-matrix-v2.yml` | deprecated workflows | `# DEPRECATED` header comment |
| `AGENTS.md` | recipe | stale-coordinator symptom + lab-admin block |

---

### Task 1: `coordinator.warn_if_rest_port` helper + wiring

**Files:**
- Modify: `adi_lg_plugins/hw_ci/coordinator.py` (add `import sys`; add helper after `resolve_coordinator`)
- Modify: `adi_lg_plugins/hw_ci/cli.py` (`_cmd_discover`, `_cmd_request_matrix`, `_cmd_noos_matrix`, `_cmd_matlab_matrix`)
- Test: `tests/hw_ci/test_coordinator_resolve_api.py` (append 3 tests)

**Interfaces:**
- Produces: `warn_if_rest_port(coord: str) -> None` — emits a `::warning::` (under `$GITHUB_ACTIONS`) / `warning:` (stderr) line iff `coord`'s explicit port is `8000`; never raises.

- [ ] **Step 1: Write the failing tests** — append to `tests/hw_ci/test_coordinator_resolve_api.py`:

```python
def test_warn_if_rest_port_warns_on_8000(capsys):
    from adi_lg_plugins.hw_ci.coordinator import warn_if_rest_port

    warn_if_rest_port("10.0.0.41:8000")
    assert "REST port :8000" in capsys.readouterr().err


def test_warn_if_rest_port_silent_on_grpc(capsys):
    from adi_lg_plugins.hw_ci.coordinator import warn_if_rest_port

    warn_if_rest_port("10.0.0.41:20408")
    assert capsys.readouterr().err == ""


def test_warn_if_rest_port_github_annotation(capsys, monkeypatch):
    from adi_lg_plugins.hw_ci.coordinator import warn_if_rest_port

    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    warn_if_rest_port("http://host:8000")
    assert capsys.readouterr().err.startswith("::warning::")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/hw_ci/test_coordinator_resolve_api.py -k warn_if_rest_port -v`
Expected: FAIL — `ImportError: cannot import name 'warn_if_rest_port'`.

- [ ] **Step 3: Add `import sys` and the helper** to `adi_lg_plugins/hw_ci/coordinator.py`. Add `import sys` to the import block (after `import subprocess`), and add this function immediately after `resolve_coordinator` (after line 162):

```python
def warn_if_rest_port(coord: str) -> None:
    """Warn when the coordinator address carries the REST port ``:8000``.

    ``LG_COORDINATOR`` must be the gRPC coordinator (e.g. ``host:20408``); a
    value ending in ``:8000`` is the REST API port, which passes discovery but
    fails at gRPC reservation. Emits a GitHub ``::warning::`` under Actions,
    else a stderr ``warning:`` line. Inspection only — never raises.
    """
    base = coord.split("://", 1)[-1]
    port = base.rsplit(":", 1)[-1] if ":" in base else ""
    if port != "8000":
        return
    msg = (
        f"coordinator {coord!r} uses the REST port :8000 — LG_COORDINATOR should be "
        "the gRPC coordinator (e.g. host:20408); the REST API is derived automatically"
    )
    prefix = "::warning::" if os.environ.get("GITHUB_ACTIONS") else "warning: "
    print(f"{prefix}{msg}", file=sys.stderr)
```

- [ ] **Step 4: Wire it into the four discovery commands** in `adi_lg_plugins/hw_ci/cli.py`. In each of `_cmd_discover`, `_cmd_request_matrix`, `_cmd_noos_matrix`, `_cmd_matlab_matrix`, immediately after the `coord = coord_mod.resolve_coordinator(args.coord)` line, add:

```python
    coord_mod.warn_if_rest_port(coord)
```

(Four insertions — one per command, at lines ~40, ~147, ~189, ~238.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/hw_ci/test_coordinator_resolve_api.py -v`
Expected: PASS (existing tests + the 3 new ones).

- [ ] **Step 6: Lint**

Run: `ruff check adi_lg_plugins/hw_ci/coordinator.py adi_lg_plugins/hw_ci/cli.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add adi_lg_plugins/hw_ci/coordinator.py adi_lg_plugins/hw_ci/cli.py tests/hw_ci/test_coordinator_resolve_api.py
git commit -m "feat(hw_ci): warn when coordinator uses the REST :8000 port"
```

---

### Task 2: Coordinator port/var contract in workflows + docs

**Files:**
- Modify: `.github/workflows/hw-request.yml` (lines 9, 11, 17)
- Modify: `.github/workflows/noos-hw-request.yml` (line 21)
- Modify: `docs/source/user-guide/hw-request.rst` (line 31)
- Modify: `docs/source/user-guide/github-actions.rst` (canonicalize `vars.ADI_LG_COORDINATOR`)

- [ ] **Step 1: Fix `hw-request.yml`.** Replace line 9:

```yaml
#       uses: tfcollins/labgrid-plugins/.github/workflows/hw-request.yml@v3  # bump when a new release tags
```
with
```yaml
#       uses: tfcollins/labgrid-plugins/.github/workflows/hw-request.yml@v3.5  # bump when a new release tags
```

Replace line 11:
```yaml
#         coordinator: "10.0.0.41:8000"
```
with
```yaml
#         coordinator: "10.0.0.41:20408"
```

Replace line 17:
```yaml
        description: "Coordinator host:port for the REST API (GET /api/match) and reservations."
```
with
```yaml
        description: "gRPC coordinator host:port (e.g. host:20408); the REST API (:8000) is derived automatically."
```

- [ ] **Step 2: Fix `noos-hw-request.yml`.** Replace line 21:

```yaml
        description: "Coordinator host:port for /api/match (REST)."
```
with
```yaml
        description: "gRPC coordinator host:port (e.g. host:20408); the REST API (:8000) is derived automatically."
```

- [ ] **Step 3: Fix the `hw-request.rst` example.** Replace line 31:

```rst
         coordinator: "10.0.0.41:8000"
```
with
```rst
         coordinator: "10.0.0.41:20408"
```

- [ ] **Step 4: Canonicalize the coordinator var name in doc caller examples.** In `docs/source/user-guide/github-actions.rst`, replace every caller-example occurrence of `vars.ADI_LG_COORDINATOR` with `vars.LG_COORDINATOR`:

Run: `sed -i 's/vars\.ADI_LG_COORDINATOR/vars.LG_COORDINATOR/g' docs/source/user-guide/github-actions.rst`

- [ ] **Step 5: Verify**

Run:
```bash
grep -nE 'coordinator.*:8000|REST API \(GET' .github/workflows/hw-request.yml .github/workflows/noos-hw-request.yml docs/source/user-guide/hw-request.rst
grep -n 'vars.ADI_LG_COORDINATOR' docs/source/user-guide/github-actions.rst
```
Expected: both commands print nothing (no REST `:8000` in the family workflow/`hw-request.rst` `coordinator` lines; no `vars.ADI_LG_COORDINATOR` left).

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/hw-request.yml .github/workflows/noos-hw-request.yml docs/source/user-guide/hw-request.rst docs/source/user-guide/github-actions.rst
git commit -m "fix(hw_ci): coordinator input is gRPC :20408 (not REST :8000); canonical LG_COORDINATOR var"
```

---

### Task 3: MATLAB PR-trigger label

**Files:**
- Modify: `docs/source/onboarding-templates/matlab-hw-request.yml` (line 22)

- [ ] **Step 1: Fix the trigger label.** Replace line 22:

```yaml
      contains(github.event.pull_request.labels.*.name, 'hw-test')
```
with
```yaml
      contains(github.event.pull_request.labels.*.name, 'hw-request')
```

- [ ] **Step 2: Verify all three templates trigger on the same label**

Run: `grep -rn "labels.\*.name, 'hw-" docs/source/onboarding-templates/`
Expected: all three (hw-request-uri.yml, noos-hw-request-flash.yml, matlab-hw-request.yml) show `'hw-request'`; no `'hw-test'`.

- [ ] **Step 3: Commit**

```bash
git add docs/source/onboarding-templates/matlab-hw-request.yml
git commit -m "fix(onboarding): matlab template triggers on the hw-request label (was hw-test)"
```

---

### Task 4: Consumer-facing pin drift (`@v3` → `@v3.5`)

**Files:**
- Modify: `docs/source/onboarding-templates/AGENTS-consumer-stub.md` (line 12)
- Audit: `docs/source/onboarding-templates/`, `docs/source/user-guide/` for stray consumer-facing `@v3` (non-deprecated)

- [ ] **Step 1: Fix the stub pin.** In `docs/source/onboarding-templates/AGENTS-consumer-stub.md`, replace line 12:

```markdown
  `tfcollins/labgrid-plugins/.github/workflows/<hw-request | noos-hw-request>.yml@v3`
```
with
```markdown
  `tfcollins/labgrid-plugins/.github/workflows/<hw-request | noos-hw-request | matlab-hw-request>.yml@v3.5`
```

- [ ] **Step 2: Audit for other consumer-facing `@v3` (not `@v3.5`, not deprecated hw-matrix).**

Run: `grep -rn '@v3\b' docs/source/onboarding-templates/ docs/source/user-guide/ AGENTS.md | grep -v '@v3\.'`
Expected: no output after the stub fix (any remaining hit on a non-deprecated consumer pin must be changed to `@v3.5`).

- [ ] **Step 3: Commit**

```bash
git add docs/source/onboarding-templates/AGENTS-consumer-stub.md
git commit -m "docs(onboarding): pin consumer stub to @v3.5 (+ list matlab workflow)"
```

---

### Task 5: Deprecation banners on the hw-matrix family + v1/v2 docs

**Files:**
- Modify: `.github/workflows/hw-matrix.yml`, `.github/workflows/hw-matrix-v2.yml` (header comment)
- Modify: `docs/source/user-guide/hardware-ci.rst`, `hw-ci-v2.rst`, `hw-ci-bash.rst` (top admonition)

- [ ] **Step 1: Banner the deprecated workflow files.** In `.github/workflows/hw-matrix.yml`, insert after line 1 (`name: HW matrix (reusable)`):

```yaml

# DEPRECATED — do not use for new consumers. Use hw-request.yml@v3.5 instead.
# See docs/source/user-guide/onboarding-a-consumer-repo.rst.
```

In `.github/workflows/hw-matrix-v2.yml`, insert after line 1 (`name: HW matrix v2 (reusable, discovery-driven)`):

```yaml

# DEPRECATED — do not use for new consumers. Use hw-request.yml@v3.5 instead.
# See docs/source/user-guide/onboarding-a-consumer-repo.rst.
```

- [ ] **Step 2: Banner the deprecated docs.** In `docs/source/user-guide/hardware-ci.rst`, insert immediately after the title underline (after line 2, before the existing `.. note::`):

```rst

.. deprecated:: v3
   The ``hw-matrix`` family is deprecated. New consumers should use the
   ``hw-request`` family — see :doc:`onboarding-a-consumer-repo`. This page is
   retained for repos that have not migrated yet.
```

Apply the **same** admonition block after the title underline of `docs/source/user-guide/hw-ci-v2.rst` (after line 2) and `docs/source/user-guide/hw-ci-bash.rst` (after line 2).

- [ ] **Step 3: Verify**

Run:
```bash
grep -c 'DEPRECATED' .github/workflows/hw-matrix.yml .github/workflows/hw-matrix-v2.yml
grep -l '.. deprecated::' docs/source/user-guide/hardware-ci.rst docs/source/user-guide/hw-ci-v2.rst docs/source/user-guide/hw-ci-bash.rst
```
Expected: each workflow shows `1`; all three rst files are listed.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/hw-matrix.yml .github/workflows/hw-matrix-v2.yml docs/source/user-guide/hardware-ci.rst docs/source/user-guide/hw-ci-v2.rst docs/source/user-guide/hw-ci-bash.rst
git commit -m "docs: mark hw-matrix family + v1/v2 pages deprecated (steer to hw-request)"
```

---

### Task 6: Single "start here" — discoverability

**Files:**
- Modify: `docs/source/index.rst` (add onboarding grid-item-card)
- Modify: `docs/source/user-guide/index.rst` (regroup toctree)

- [ ] **Step 1: Add the onboarding card to `index.rst`.** Insert this card into the `.. grid:: 2` block, immediately after the "Developer Guide" card (after line 36):

```rst

    .. grid-item-card:: Hardware CI — Onboarding
        :link: user-guide/onboarding-a-consumer-repo
        :link-type: doc

        Wire a consumer repo onto the lab hardware-CI flow — start here.
```

- [ ] **Step 2: Regroup the user-guide toctree.** Replace the entire toctree block in `docs/source/user-guide/index.rst` (lines 6-26) with grouped toctrees that put onboarding first and quarantine the legacy pages:

```rst
.. toctree::
   :maxdepth: 2
   :caption: Core

   drivers
   resources
   strategies
   cli
   mcp

.. toctree::
   :maxdepth: 2
   :caption: Hardware CI

   onboarding-a-consumer-repo
   github-actions
   hw-request
   hardware-ci-runner-setup

.. toctree::
   :maxdepth: 2
   :caption: Coordinator & exporters

   coordinator
   coordinator-testing
   web-dashboard
   exporter-setup
   exporter-deployment

.. toctree::
   :maxdepth: 1
   :caption: Legacy / reference (deprecated)

   hardware-ci
   hw-ci-v2
   hw-ci-bash

.. toctree::
   :maxdepth: 2

   examples
```

- [ ] **Step 3: Verify the docs build**

Run: `nox -s docs`  (or `pip install -e ".[docs]" && sphinx-build -b html docs/source docs/_build`)
Expected: builds with no new warnings/errors; every page in the toctrees resolves (no "document isn't included in any toctree").

- [ ] **Step 4: Commit**

```bash
git add docs/source/index.rst docs/source/user-guide/index.rst
git commit -m "docs: surface onboarding as the HW-CI start point; group + quarantine legacy docs"
```

---

### Task 7: Recipe polish — stale-coordinator symptom, lab-admin block, acquire-place + build_vars notes

**Files:**
- Modify: `AGENTS.md` (Step 5 + Step 4 lab-admin block)
- Modify: `docs/source/user-guide/onboarding-a-consumer-repo.rst` (Step 5 symptom)
- Modify: `docs/source/user-guide/github-actions.rst` (acquire-place scoping note)
- Modify: `docs/source/onboarding-templates/projects.yaml` (build_vars note)

- [ ] **Step 1: Surface the stale-coordinator symptom inline at Step 5 in `AGENTS.md`.** In the Step-5 "Success =" paragraph (after line 137, the sentence ending "…that means the catalog/place is missing — Step 4)."), append:

```markdown
> If a board prints `Unknown release version`, the coordinator catalog is stale — ask the lab admin to **redeploy the coordinator** after the catalog merge.
```

- [ ] **Step 2: Add a copy-paste lab-admin request block to `AGENTS.md` Step 4.** Immediately after the "A live place tagged…" bullet (after line 108), insert:

````markdown

  Hand the lab admin this (fill the placeholders) so the catalog + place round-trip is one message:

  ```text
  Please add to coordinator/api/board_catalog.yaml: a <part> entry (uri: image; flash: flash block),
  and create a live place tagged: daughter-board=<part> carrier=<carrier> boot-strategy=<Strategy>
  (+ runner=<label> if board-pinned). Redeploy the coordinator after merging.
  ```
````

- [ ] **Step 3: Mirror the symptom in the human guide.** In `docs/source/user-guide/onboarding-a-consumer-repo.rst`, in the Step-5 success sentence (after line 202, "…fix it in Step 4)."), append:

```rst

If a board reports ``Unknown release version``, the coordinator catalog is stale — ask the lab
admin to redeploy the coordinator after the catalog merge.
```

- [ ] **Step 4: Scope `acquire-place` in `github-actions.rst`.** Find the composite-actions section that documents `acquire-place` (grep: `grep -n 'acquire-place' docs/source/user-guide/github-actions.rst`) and add this note directly under its heading/first paragraph:

```rst

.. note::

   ``acquire-place`` is only for the deprecated bash / ``hw-matrix`` flow. **hw-request-family
   consumers do not need it** — reservation + release are handled inside the reusable workflow
   by ``adi-lg request``.
```

- [ ] **Step 5: Note `build_vars` is not wired through.** In `docs/source/onboarding-templates/projects.yaml`, replace line 14:

```yaml
    build_vars: {}                 # optional extra `make` vars, e.g. {EXAMPLE: iio_example}
```
with
```yaml
    build_vars: {}                 # NOT wired through the default build-cmd — override the
                                   # `build-cmd` workflow input to pass extra make vars.
```

- [ ] **Step 6: Verify**

Run:
```bash
grep -n 'Unknown release version' AGENTS.md docs/source/user-guide/onboarding-a-consumer-repo.rst
grep -n 'do not need it' docs/source/user-guide/github-actions.rst
grep -n 'NOT wired through' docs/source/onboarding-templates/projects.yaml
nox -s docs
```
Expected: the grep hits are present; docs build clean.

- [ ] **Step 7: Commit**

```bash
git add AGENTS.md docs/source/user-guide/onboarding-a-consumer-repo.rst docs/source/user-guide/github-actions.rst docs/source/onboarding-templates/projects.yaml
git commit -m "docs(onboarding): stale-coordinator symptom + lab-admin block; scope acquire-place; build_vars note"
```

---

### Task 8: Reserve-mode copy-paste coverage

**Files:**
- Modify: `docs/source/onboarding-templates/hw-request-uri.yml` (commented reserve knob)
- Modify: `docs/source/onboarding-templates/AGENTS-consumer-stub.md` (mode list + reserve note)
- Modify: `docs/source/user-guide/onboarding-a-consumer-repo.rst` (Step-2 reserve note)

- [ ] **Step 1: Add a commented reserve-mode knob to the uri template.** In `docs/source/onboarding-templates/hw-request-uri.yml`, immediately after line 39 (`      preflight-runner-label: ${{ vars.HW_PREFLIGHT_RUNNER }}`), insert:

```yaml
      # Reserve mode — for suites that drive boot themselves via labgrid (pytest plugin
      # + LG_ENV, e.g. per-test DTBs). Uncomment to reserve the board without booting it.
      # Private deps: pass an INSTALL_GIT_TOKEN secret (see the hub github-actions docs).
      # request-mode: "reserve"
```

- [ ] **Step 2: Add `reserve` to the stub mode list.** In `docs/source/onboarding-templates/AGENTS-consumer-stub.md`, replace line 9:

```markdown
## How this repo is wired (mode: `<uri | flash | matlab>`)
```
with
```markdown
## How this repo is wired (mode: `<uri | flash | matlab | reserve>`)
```

- [ ] **Step 3: Add a Step-2 reserve note to the human guide.** In `docs/source/user-guide/onboarding-a-consumer-repo.rst`, at the end of the "uri mode" section (immediately before the "flash mode" header at line 96), insert:

```rst

.. admonition:: Reserve mode (drive boot yourself)
   :class: tip

   Suites that boot the board themselves via labgrid (the pytest plugin + ``LG_ENV``, e.g.
   per-test DTBs) use the same uri workflow with ``request-mode: "reserve"`` — the board is
   reserved but not booted. See :doc:`hw-request` "Reserve mode". For private dependencies,
   pass an ``INSTALL_GIT_TOKEN`` secret (see :doc:`github-actions`).
```

- [ ] **Step 4: Verify**

Run:
```bash
grep -n 'request-mode: "reserve"' docs/source/onboarding-templates/hw-request-uri.yml
grep -n 'reserve' docs/source/onboarding-templates/AGENTS-consumer-stub.md
grep -n 'Reserve mode' docs/source/user-guide/onboarding-a-consumer-repo.rst
nox -s docs
```
Expected: all grep hits present; docs build clean.

- [ ] **Step 5: Commit**

```bash
git add docs/source/onboarding-templates/hw-request-uri.yml docs/source/onboarding-templates/AGENTS-consumer-stub.md docs/source/user-guide/onboarding-a-consumer-repo.rst
git commit -m "docs(onboarding): reserve-mode copy-paste coverage (uri knob + stub + guide)"
```

---

## Self-Review

**Spec coverage (Phase 1 scope):**
- WS-A coordinator-port contract → Task 1 (warning) + Task 2 (descriptions/example/var). ✓
- WS-A matlab label → Task 3. ✓
- WS-A var-name drift (review finding #1, under-specified in spec) → Task 2 Step 4. ✓ (gap filled)
- WS-D Phase-1 pin fixes → Task 4. ✓
- WS-E deprecation banners → Task 5; single start-here → Task 6; acquire-place/build_vars/stale-coordinator/lab-admin → Task 7; reserve-mode → Task 8. ✓
- Deferred to later phases (NOT in this plan): `doctor`/`lint-markers`/var-guard/infra-annotations (Phase 2); `_release.py`/pin-lint/release-guard (Phase 2); packaging + `init` + board-map template (Phase 3).

**Placeholder scan:** the `<…>` tokens in edited templates/docs are intentional consumer placeholders, not plan placeholders. No "TBD/TODO/implement later" in the plan. Every code/edit step shows exact content.

**Type/string consistency:** `warn_if_rest_port(coord: str) -> None` used identically in coordinator.py, the 4 cli.py call sites, and the tests. Canonical `LG_COORDINATOR` / `@v3.5` / `hw-request` strings used consistently across tasks and match the Global Constraints.

**Note for reviewers:** Task 4's stub pin and Task 8's stub mode-list edits both touch `AGENTS-consumer-stub.md`; if executed out of order, re-base the later edit on the former. The stub pin is interim — Phase 3's `init`/`RECOMMENDED_PIN` will supersede the literal pin.
