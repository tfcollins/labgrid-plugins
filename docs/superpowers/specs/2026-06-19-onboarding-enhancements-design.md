# Consumer Onboarding Enhancements — Design Spec

- **Date:** 2026-06-19
- **Status:** Approved (design); pending implementation plan
- **Branch:** `onboarding-enhancements` (off `main`)
- **Scope target:** onboarding for repos that consume the adi-labgrid-plugins hardware-CI flow — `AGENTS.md`, `docs/source/user-guide/*`, `docs/source/onboarding-templates/*`, `.github/workflows/*`, `adi_lg_plugins/hw_ci/*`, `scripts/*`
- **Owner:** Travis Collins

## 1. Summary

Improve the consumer-repo onboarding experience by (a) fixing correctness bugs in the shipped kit, (b) turning the documented-only "friction checklist" into enforced/automated checks (new `adi-lg-hw-ci` subcommands + workflow guards), (c) adding a scaffolder and packaging the templates, (d) hardening pin hygiene, and (e) removing deprecation/discoverability confusion in the docs. Comprehensive scope, delivered in three phases.

This spec is grounded in a five-area code review and a four-lens spec review; all accepted findings are folded in.

## 2. Current state (what's strong — preserve it)

- **`AGENTS.md`** is an executable, mode-aware recipe with a Friction checklist and a "cite, don't guess" source-of-truth list.
- **`onboarding-a-consumer-repo.rst`** mirrors it and uses `literalinclude` to pull the real template files into the docs.
- **Per-mode discovery preflight** (`adi-lg-hw-ci request-matrix|noos-matrix|matlab-matrix`) verifies markers/manifest ∩ live boards with no hardware.
- **`adi-lg-hw-ci` is an argparse CLI** (`_cmd_*` functions + `add_parser` in `adi_lg_plugins/hw_ci/cli.py`); new subcommands follow that pattern.
- **Release process exists and works:** `RELEASING.md` + `scripts/pin-release-refs.sh` pin internal `@main` self-refs (action `uses:` **and** `git+https://…@main` installs, via two `sed` rules) to the tag on a `release/v<N>` branch; `main` keeps `@main` so dev self-tests. Verified: the `v3.5` tag has clean `@v3.5` internals.
- **Env-render templates** already ship in the wheel: `adi_lg_plugins/hw_ci/templates/*.yaml` via `[tool.setuptools.package-data]`. This is a *different* directory from the onboarding templates and must not be conflated.

### Correction to the review (must not be re-introduced)
The five-area review flagged "tagged workflows re-pin internals to `@main`, so `@v3.5` doesn't freeze." **This is a false positive** — it inspected `main` (intentionally `@main`), not the tag. `pin-release-refs.sh` already pins both action refs and git-installs, and `v3.5` is clean. **Do NOT re-implement internal-ref pinning.** The real, adjacent gaps are: (1) nothing *enforces* `pin-release-refs.sh` ran before a tag, and (2) consumer-facing pin *examples/comments* have drifted to `@v3`. Both are addressed in WS-D.

## 3. Goals / Non-goals

**Goals**
- A first onboarding run fails fast with a named, actionable error (or is caught pre-PR by `doctor`) instead of silently queueing or failing deep in a runner log.
- The Friction checklist items become enforced or warned, not documented-only.
- One obvious entry point; deprecated generations self-identify.
- `pip install adi-labgrid-plugins` users can scaffold a consumer with `init`.
- Existing strengths (AGENTS.md recipe, literalinclude docs, per-mode preflight, release process) are preserved.

**Non-goals**
- No change to the reservation/boot runtime behavior of the reusable workflows beyond added guards/annotations. (In particular, `build_vars` is **not** wired through — WS-E documents it as not-wired-through; wiring it is out of scope.)
- No re-implementation of internal-ref pinning (already solved — §2 correction).
- No removal of the deprecated `hw-matrix*` workflows (banner + steer only; removal tracked separately).
- No new boot strategies, drivers, or coordinator/catalog schema changes.

## 4. Design decisions (resolved)

- **REST-port warning has ONE home:** a helper `coordinator.warn_if_rest_port(coord: str) -> None` that emits a `::warning::` (under `GITHUB_ACTIONS`) / stderr line when the coordinator string carries an explicit port `:8000`. Both WS-A (called from the matrix/preflight commands) and `doctor` call this one helper; its unit test lives with the coordinator module. The deeper "host actually answers as REST" check is a *separate, bounded* `doctor`-only probe (a GET to the REST API on the supplied host succeeding implies the gRPC port was wrong) — clearly delimited, not in the shared helper. Do NOT put port-inspection inside `_resolve_api` (it always derives `:8000` and would fire on every call).
- **Single recommended-tag source:** `adi_lg_plugins/hw_ci/_release.py` exposing `RECOMMENDED_PIN = "v3.5"`, defined as **the latest stable consumer-facing release tag**, bumped as the final step of the release flow (added to `RELEASING.md`). It is the single source the pin-lint compares against. `docs/source/conf.py` derives the `|hw_ci_pin|` RST substitution by **regex/AST-parsing `_release.py`** (NOT importing the package — conf.py does not import `adi_lg_plugins` today, and importing it triggers the driver/resource/strategy registration chain at config-eval time). The WS-D pin-lint guarantees docs == constant, so there is no silent-drift path.
- **`markers.py` refactor surface:** add `collect_marker_rejections(test_root) -> list[tuple[file, lineno, reason]]`, where a *rejection* is `_is_pytest_mark(...) is True AND the literal coercion returns None` (i.e., it IS our `iio_hardware`/`iio_carrier` marker but the arg isn't a recognized literal) — NOT merely "`_extract_marker_args` returned None" (which also covers non-marker decorators). **`harvest_markers` keeps its exact signature and accepted-spec output byte-identical** (no caller changes); `lint-markers` and the matrix commands consume `collect_marker_rejections` (linter exits non-zero; matrix commands emit `::warning::`). Also align docs: markers accept string literals **or** module-level string constants (the code already resolves the latter).
- **Templates packaged as the single source of truth (Phase 3):** `git mv docs/source/onboarding-templates/ → adi_lg_plugins/hw_ci/onboarding_templates/` (git mv preserves history/blame), add an `__init__.py` so it's importable, and ship it via `[tool.setuptools.package-data]` key `"adi_lg_plugins.hw_ci.onboarding_templates" = ["*.yml", "*.yaml", "*.py", "*.md"]` (multi-extension — a `*.yaml`-only glob would silently drop the `.yml`/`.py`/`.md` files). Add the new dir to ruff `extend-exclude` (placeholder `.py`/`.yaml` files must not be linted) and remove the now-empty docs path from it. Docs `literalinclude` directives change from `../onboarding-templates/<f>` to the source-tree relative path `../../../adi_lg_plugins/hw_ci/onboarding_templates/<f>` (docs build from a checkout, so this resolves); `init` uses `importlib.resources.files('adi_lg_plugins.hw_ci.onboarding_templates')` at runtime (works from an installed wheel). A drift-guard test asserts (i) every doc `literalinclude` path points INTO the package dir and (ii) a built wheel ships all template files. (If `init`/packaging were ever descoped, the move could be skipped — but it is in scope here.)
- **New CLI subcommands are argparse subparsers** (`_cmd_doctor`, `_cmd_lint_markers`, `_cmd_init`) with logic in testable modules (`hw_ci/doctor.py`, the `markers.py` rejection collector, `hw_ci/scaffold.py`).

## 5. Workstreams

### WS-A — Correctness fixes (Phase 1)

| Item | Change | Acceptance |
|---|---|---|
| Coordinator-port contract | Rewrite the `coordinator` input description in `.github/workflows/hw-request.yml` + `noos-hw-request.yml` to match matlab's ("gRPC `host:20408`; REST `:8000` derived automatically"); fix the `:8000` example in `hw-request.rst` → `:20408`; fix the in-file example comment at `hw-request.yml:9` (`@v3`→`@v3.5`). Add `coordinator.warn_if_rest_port` (§4) and call it from the matrix/preflight commands. | No `:8000` in the family workflow `coordinator` descriptions; the warning fires for a `:8000` value; unit test on the helper. |
| MATLAB PR-label | `docs/source/onboarding-templates/matlab-hw-request.yml` trigger `hw-test` → `hw-request` (match uri/flash + `AGENTS.md`). Also reconcile the matlab consumer destination filename so `AGENTS.md` Step 2/5, the template header, and `init`/`doctor` paths agree (pick one: `hw-matlab.yml` or `matlab-hw-request.yml`). | All three templates trigger on `hw-request`; one consistent matlab destination filename across docs + tooling. |

> Note: header comment/example pins (`@v3`/`@v3.5`) are outside `pin-release-refs.sh`'s scope and the WS-D `@main` release-guard; they are hand-maintained and caught by the WS-D pin-consistency lint.

### WS-B — Validation & automation CLI (Phase 2)

- **`adi-lg-hw-ci doctor`** (`_cmd_doctor` + `hw_ci/doctor.py`): args `--mode {uri,flash,matlab}`, `--coord`, one of `--test-root|--manifest|--board-map`, optional `--repo owner/name` (default: infer from `git remote`). Runs all applicable checks, prints a pass/fail/skip table with one actionable line per failure, exits non-zero on any failure:
  1. coordinator reachable; **REST-port warning** via the shared helper; plus the bounded "answers as REST" probe (§4);
  2. discovery matrix non-empty AND **every leg resolves to *some* runner** — the leg's own `runner` is non-empty OR the fallback `HW_REQUEST_RUNNER` label is non-empty (an empty per-leg runner is a valid designed state: `runs-on: [self-hosted, "${{ matrix.runner || inputs.runner-label }}"]`). Do NOT fail solely on an empty per-leg runner;
  3. each wanted part with a place but dropped at validation is reported with its `PlaceValidationError` reason;
  4. required repo vars present (`gh variable list`) — per mode: uri/flash/reserve = `LG_COORDINATOR`, `HW_REQUEST_RUNNER`, `HW_PREFLIGHT_RUNNER`; matlab = those + `MATLAB_BIN`;
  5. a self-hosted runner registered on the consumer scope (`gh api /repos/<repo>/actions/runners`) for **both** the `HW_REQUEST_RUNNER` and `HW_PREFLIGHT_RUNNER` labels;
  6. pin freshness vs `RECOMMENDED_PIN`.
  Checks 4–6's gh-dependent parts degrade to `SKIPPED` if `gh` is unavailable/unauth. **Exit semantics:** SKIP is not failure → a doctor with skips exits 0, but prints a final banner `N checks skipped (gh unavailable) — repo-var/runner registration NOT verified` so a green run can't give false confidence. This becomes THE Step-5 command in the docs.
- **`adi-lg-hw-ci lint-markers --test-root <path>`** (`_cmd_lint_markers`): coordinator-free; prints `file:line: marker arg is not a string literal (invisible to discovery)` for each rejected decorator (via `collect_marker_rejections`); exits non-zero if any. Recommended for the consumer's own CI + called by `doctor`.
- **Preflight var-guard:** a first step in each family workflow's preflight job that fails fast with a named `::error::` when the documented-REQUIRED inputs (`coordinator`, the two runner labels) are empty, before checkout/install.
- **Infra-failure annotations:** emit `::error title=no-board::part=<part> reason=<str(e)>` and `::error title=board-unavailable::part=<part> reason=<str(e)>` for the `NoMatchingBoard` (exit 10) and `BoardUnavailable` (exit 11) branches in `request_cli.py`, mirroring the existing `boot-failure` (exit 12) annotation's `str(e)` collapse. (`part` is in scope from the click param; the exceptions are bare subclasses — no queue-depth/elapsed fields, so none are claimed.)

### WS-C — Scaffolding (Phase 3)

- **Package templates** per §4 (git mv + `__init__.py` + multi-ext package-data + ruff exclude + literalinclude repoint + drift-guard test, incl. a built-wheel resource check).
- **`adi-lg-hw-ci init`** (`_cmd_init` + `hw_ci/scaffold.py`): `--mode {uri,flash,matlab} --dest <repo-root>` plus optional `--coordinator --runner-label --preflight-runner-label --test-root --install-cmd --matlab-bin`. Writes the mode's files to canonical destinations with placeholders substituted, idempotent (refuses overwrite without `--force`), prints the exact `gh variable set` commands + the Step-4 lab-admin prerequisites it cannot create, ends by suggesting the matching `doctor`/`lint-markers` invocation, and pins consumer `uses:` to `RECOMMENDED_PIN`.
- **`board-map.yaml` template:** a **single** matlab board-map template (matlab is the only mode using a board map), created directly in the packaged location during Phase 3, with a header comment (copy-target + `board_map.py` source-of-truth pointer + example rows with `<PLACEHOLDERS>`), and `literalinclude`d in the matlab docs section.

### WS-D — Pin hygiene (Phase 1 fixes + Phase 2 automation)

- **Phase 1:** fix drifted consumer-facing pins — `AGENTS-consumer-stub.md` (`@v3`→`@v3.5`) and the `hw-request.yml:9` comment (`@v3`→`@v3.5`); audit `docs/` + templates for other `@v3`/`@main` consumer-facing examples. (These are interim and superseded by `init`'s `RECOMMENDED_PIN` substitution in Phase 3 — reviewers need not re-litigate them.)
- **Phase 2:** create `_release.py::RECOMMENDED_PIN` **first**, then the `conf.py` regex-parse `|hw_ci_pin|` substitution, then the checks that read it. **Pin-consistency lint** (nox session + CI): fail if any consumer-facing template/stub/doc references a pin inconsistent with `RECOMMENDED_PIN` or uses `@main` in a consumer-facing example. In Phase 2 the lint covers the `docs/source/onboarding-templates/` copies (pre-move); in Phase 3 its coverage follows the files to the packaged location.
- **Release guard:** a nox/script check, invoked **only** by the release recipe (after `pin-release-refs.sh`) and/or gated to `release/*` branches — **it MUST NOT run on `main` or PRs to `main`**, where `@main` self-refs are by-design (§2). It fails if any `hw-request`-family workflow still contains an `@main` self-ref. Add its invocation as the last step in `RELEASING.md`.

### WS-E — Docs & discoverability (Phase 1)

- **Deprecation banners:** top-of-file `# DEPRECATED — use hw-request.yml@<pin>; see onboarding-a-consumer-repo` comments in `.github/workflows/hw-matrix.yml` + `hw-matrix-v2.yml`; a prominent `.. deprecated::`/warning admonition at the TOP of `hardware-ci.rst`, `hw-ci-v2.rst`, `hw-ci-bash.rst` linking the canonical onboarding page; remove/relabel the `@main` examples in `github-actions.rst`.
- **Single "start here":** an onboarding grid-item-card on `docs/source/index.rst`; reorder `docs/source/user-guide/index.rst` so `onboarding-a-consumer-repo` is first under a "Hardware CI" caption with deprecated docs in a labeled "Legacy / reference" subgroup.
- **Smaller doc fixes:** note in the composite-actions doc that hw-request-family consumers do **not** need `acquire-place` (scope its docs to the deprecated/bash path); add reserve-mode copy-paste coverage (a commented `# request-mode: reserve` knob in the uri template + a short Step-2 note + `reserve` in the stub mode list + the `INSTALL_GIT_TOKEN` mention); surface `Unknown release version → redeploy coordinator` inline at Step 5 + a pre-filled lab-admin request block; **document `projects.yaml`'s `build_vars` as not wired through the default build-cmd** (doc-only; wiring is a non-goal).

## 6. Testing strategy

- **New CLI logic is unit-tested** without a process boundary: `doctor.py` (table assembly, REST-port warning, gh-absent SKIP + exit-0 banner, the runner-resolution check incl. the empty-leg-runner-with-fallback case), `markers.py` `collect_marker_rejections` (marker-with-bad-arg vs non-marker decorator) + `lint-markers` exit codes, `scaffold.py` (placeholder substitution, idempotency/`--force`, destination paths, `RECOMMENDED_PIN` pinning). Mock `gh`/coordinator I/O.
- **Drift-guard test:** every doc `literalinclude` path points into the packaged template dir; a built wheel ships all template files.
- **Pin/release lints are pure functions** (file contents → violations) → directly testable.
- **Gate:** `nox -s lint tests` green; `nox -s docs` builds; new tests opt into the CI test list (`tests/test_cli.py` is already in CI — add there or a sibling CI runs, per `CLAUDE.md`).
- Workflow-YAML changes (var-guard, annotations) verified by YAML-lint + a smoke assertion on the rendered guard step; hardware paths stay `@pytest.mark.hardware`, out of unit scope.

## 7. Phased delivery

1. **Phase 1 (fast: correctness + docs):** WS-A; WS-D Phase-1 drifted-pin fixes (interim); WS-E (banners, start-here, small doc fixes). Edits land in `docs/source/onboarding-templates/` (pre-move). Mergeable first.
2. **Phase 2 (automation):** in order — (a) create `_release.py::RECOMMENDED_PIN`; (b) `conf.py` `|hw_ci_pin|` substitution (regex parse); (c) `doctor` (incl. check 6) + `lint-markers` + the `markers.py` rejection collector; (d) preflight var-guard + infra annotations; (e) pin-consistency lint (over the pre-move docs templates) + the release guard. Phase-2 pin-lint covers the `docs/` template copies that still exist at this phase.
3. **Phase 3 (scaffolding):** `git mv` templates to `adi_lg_plugins/hw_ci/onboarding_templates/` **preserving the Phase-1/2 edits**; add `__init__.py` + package-data + ruff exclude; repoint `literalinclude`; add the drift-guard test; create `board-map.yaml` directly in the package; implement `init`; move the pin-lint's coverage to the new location.

Each phase keeps `nox` green and is independently reviewable/mergeable. Cross-phase dependency called out: the Phase-2 pin-lint targets the pre-move template location and is repointed in Phase 3.

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| `gh`/network unavailable in `doctor` | Graceful `SKIPPED` rows + exit-0-with-partial-coverage banner; never hard-fail on tooling absence |
| conf.py coupling to the package import graph | conf.py **regex/AST-parses** `_release.py` (no `import adi_lg_plugins`); pin-lint guarantees docs==constant |
| Template move breaks `literalinclude` / loses history | `git mv` preserves history; repoint the 5 `literalinclude` paths to the package-relative path; drift-guard test asserts the paths point into the package |
| Packaged templates dropped from the wheel | multi-ext package-data glob + `__init__.py` + a built-wheel resource test |
| placeholder `.py`/`.yaml` templates linted as source | add the packaged template dir to ruff `extend-exclude` |
| `markers.py` refactor changes harvest output | `harvest_markers` signature/output unchanged; rejections are an additive `collect_marker_rejections`; covered by tests |
| Re-introducing the (already-solved) internal-pin rewrite | Explicit §2 correction; WS-D scoped to enforcement only |
| Release guard false-failing on `main` | Guard runs ONLY in the release recipe / `release/*`, never on `main`/PR (§5 WS-D) |
| Workflow var-guard false-fail | Guard only the documented-REQUIRED inputs (coordinator + the two runner labels) |

## 9. Out of scope

Removing deprecated `hw-matrix*` workflows; reservation/boot runtime changes (incl. wiring `build_vars`); catalog/place schema changes; new boot strategies/drivers; the coordinator web app.

## 10. References

- Five-area onboarding review + four-lens spec review (2026-06-19); all accepted findings folded in.
- `AGENTS.md`; `docs/source/user-guide/onboarding-a-consumer-repo.rst`.
- `RELEASING.md`; `scripts/pin-release-refs.sh` (internal-pin mechanism — already correct; `sed` lines rewrite `actions/*@main` + `git+https…@main`).
- `adi_lg_plugins/hw_ci/cli.py` (argparse `_cmd_*` + `add_parser`), `markers.py` (`_is_pytest_mark`, `_extract_marker_args`, `harvest_markers`), `coordinator.py` (`resolve_coordinator`, `_resolve_api`), `request_cli.py` (exit 10/11/12 + boot-failure annotation), `request/errors.py` (bare `NoMatchingBoard`/`BoardUnavailable`), `board_map.py`.
- `.github/workflows/{hw-request,noos-hw-request,matlab-hw-request,hw-matrix,hw-matrix-v2}.yml`; `.github/actions/{acquire-place,setup-uv-venv}`.
- `pyproject.toml` (`[tool.setuptools.package-data]` for `hw_ci.templates`; ruff `extend-exclude`); `docs/source/conf.py`.
- Templates: `docs/source/onboarding-templates/*` (→ `adi_lg_plugins/hw_ci/onboarding_templates/*` in Phase 3).
