# Onboarding Enhancements — Phase 3 Implementation Plan (scaffolder + packaging)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the onboarding templates inside the wheel and add an `adi-lg-hw-ci init` scaffolder so a `pip install adi-labgrid-plugins` user can drop a consumer repo's hw-CI files (placeholders filled + the current pin) in one command — plus the missing matlab `board-map.yaml` template.

**Architecture:** `git mv` the templates into a new packaged subpackage `adi_lg_plugins/hw_ci/onboarding_templates/` (the single source of truth; docs `literalinclude` from there), then a pure `hw_ci/scaffold.py` (read packaged template → substitute → write) behind a new `adi-lg-hw-ci init` argparse subcommand.

**Tech Stack:** Python 3.10+ (argparse `adi-lg-hw-ci`, `importlib.resources`), setuptools package-data, pytest, ruff, Sphinx.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-06-19-onboarding-enhancements-design.md`. This plan implements **Phase 3** (WS-C). Phases 1 & 2 are merged to `main`.
- **Branch:** `onboarding-enhancements-phase3` (already created off `main`). Do NOT create another branch.
- **Environment:** project venv — `.venv/bin/python -m pytest …`, `.venv/bin/ruff …`, `.venv/bin/sphinx-build …`. Deps pre-installed; default sandbox, NO network; do NOT use `nox`/`pip`. Ignore the `kasadriver` import line.
- **CI lint gate (learn from Phase 2):** the `test (3.x)` CI job runs `nox -s lint` = **`ruff check .` AND `ruff format --check .`** repo-wide. So after writing any Python, **run `.venv/bin/ruff format <file>` (write) THEN `.venv/bin/ruff check .` + `.venv/bin/ruff format --check .`** before committing — a format-check failure fails CI even when `ruff check` passes (E501 is ignored, but `ruff format` still reflows long lines).
- **Single source of truth:** the templates live ONLY in `adi_lg_plugins/hw_ci/onboarding_templates/` after Task 1. Docs `literalinclude` that directory (no second copy; replace any inline duplicate). The directory is ruff-`extend-exclude`d (placeholder `.py`/`.yaml` must not be linted).
- **`RECOMMENDED_PIN`** (`adi_lg_plugins/hw_ci/_release.py`, currently `v3.5`) is the pin `init` writes into consumer `uses:`/install refs.
- **Matlab consumer destination filename is `hw-matlab.yml`** (matches AGENTS.md + the template header); source template is `matlab-hw-request.yml`. The board-map source template is `board-map.yaml` (hyphen) but its consumer destination is `test/hw_ci/board_map.yaml` (**underscore** — what `board_map.py` loads). Preserve that intentional rename.
- New tests go in `tests/hw_ci/` and are added to the CI file list in `.github/workflows/tests.yml`.
- **Gates:** `ruff check .` + `ruff format --check .` clean; touched tests green; `sphinx-build` builds.

## File structure (Phase 3)

| File | Change |
|---|---|
| `docs/source/onboarding-templates/*` → `adi_lg_plugins/hw_ci/onboarding_templates/*` | `git mv` (7 files, history preserved) |
| `adi_lg_plugins/hw_ci/onboarding_templates/__init__.py` (new) | make it an importable subpackage |
| `adi_lg_plugins/hw_ci/onboarding_templates/board-map.yaml` (new, Task 2) | matlab board-map template |
| `pyproject.toml` | add package-data glob; update the ruff `extend-exclude` element |
| `docs/source/user-guide/onboarding-a-consumer-repo.rst` | repoint 5 `literalinclude`; replace inline matlab board-map block with a literalinclude (Task 2); fix 2 prose refs; add an `init` tip (Task 4) |
| `AGENTS.md`, `CLAUDE.md`, `.claude/skills/hardware-test-automation/*` | fix tracked prose `onboarding-templates/` path references |
| `adi_lg_plugins/hw_ci/pin_lint.py` | repoint the 4 `CONSUMER_PIN_PATHS` template entries |
| `adi_lg_plugins/hw_ci/scaffold.py` (new) | `init` engine |
| `adi_lg_plugins/hw_ci/cli.py` | `_cmd_init` + `init` subparser |
| `tests/hw_ci/test_*` (new) + `.github/workflows/tests.yml` | drift-guard, scaffold, init tests |

---

### Task 1: Move templates into the package (single source of truth)

**Files:**
- Move: `docs/source/onboarding-templates/` → `adi_lg_plugins/hw_ci/onboarding_templates/` (`git mv`)
- Create: `adi_lg_plugins/hw_ci/onboarding_templates/__init__.py`
- Modify: `pyproject.toml`; `docs/source/user-guide/onboarding-a-consumer-repo.rst`; `adi_lg_plugins/hw_ci/pin_lint.py`; tracked prose refs (AGENTS.md, CLAUDE.md, `.claude/skills/hardware-test-automation/*`)
- Test: `tests/hw_ci/test_onboarding_templates_packaged.py` (new)

**Interfaces:**
- Produces: the package resource anchor `adi_lg_plugins.hw_ci.onboarding_templates` with all 7 templates importable via `importlib.resources.files(...)`.

- [ ] **Step 1: Write the failing drift-guard test** — create `tests/hw_ci/test_onboarding_templates_packaged.py`:

```python
from importlib import resources
from pathlib import Path

EXPECTED = {
    "AGENTS-consumer-stub.md",
    "board-catalog-entry.yaml",
    "conftest-iio-uri.py",
    "hw-request-uri.yml",
    "matlab-hw-request.yml",
    "noos-hw-request-flash.yml",
    "projects.yaml",
}


def test_templates_are_importable_resources():
    root = resources.files("adi_lg_plugins.hw_ci.onboarding_templates")
    names = {p.name for p in root.iterdir() if p.name != "__init__.py"}
    assert EXPECTED <= names, f"missing packaged templates: {EXPECTED - names}"


def test_literalincludes_point_into_the_package():
    rst = Path("docs/source/user-guide/onboarding-a-consumer-repo.rst").read_text(encoding="utf-8")
    assert "../onboarding-templates/" not in rst  # no old docs-local path remains
    for line in rst.splitlines():
        if "literalinclude::" in line and "onboarding_templates" in line:
            rel = line.split("literalinclude::", 1)[1].strip()
            target = (Path("docs/source/user-guide") / rel).resolve()
            assert target.is_file(), f"literalinclude target missing: {target}"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_onboarding_templates_packaged.py -v`
Expected: FAIL — `importlib` can't find `adi_lg_plugins.hw_ci.onboarding_templates`.

- [ ] **Step 3: Move the directory + make it a subpackage**

```bash
git mv docs/source/onboarding-templates adi_lg_plugins/hw_ci/onboarding_templates
printf '"""Packaged copy-paste onboarding templates (read via importlib.resources)."""\n' > adi_lg_plugins/hw_ci/onboarding_templates/__init__.py
git add adi_lg_plugins/hw_ci/onboarding_templates/__init__.py
```

(`[tool.setuptools.packages.find]` already includes `adi_lg_plugins.*` with `namespaces = true`, so the new `__init__.py` subpackage is auto-discovered — no `packages.find` edit needed.)

- [ ] **Step 4: Ship them in the wheel + exclude from ruff.** In `pyproject.toml`, under `[tool.setuptools.package-data]` add (after the `"adi_lg_plugins.hw_ci.templates"` line):

```toml
# Onboarding copy-paste templates (read via importlib.resources by `adi-lg-hw-ci init`).
"adi_lg_plugins.hw_ci.onboarding_templates" = ["*.yml", "*.yaml", "*.py", "*.md"]
```

And in the ruff `extend-exclude` list (a single-element list today: `["docs/source/onboarding-templates"]`), replace just that one string element with `"adi_lg_plugins/hw_ci/onboarding_templates"` (preserving any sibling entries if present):

```toml
extend-exclude = ["adi_lg_plugins/hw_ci/onboarding_templates"]
```

- [ ] **Step 5: Repoint the docs `literalinclude` paths.** In `docs/source/user-guide/onboarding-a-consumer-repo.rst`, the 5 directives use `.. literalinclude:: ../onboarding-templates/<f>`. Rewrite each to the source-tree path (docs build from the checkout):

Run: `sed -i 's#\.\./onboarding-templates/#../../../adi_lg_plugins/hw_ci/onboarding_templates/#g' docs/source/user-guide/onboarding-a-consumer-repo.rst`

(The `../` prefix means this sed touches ONLY the 5 literalinclude lines; the 2 bare-prose refs at rst lines 179/228 lack `../` and are handled in Step 7.)

- [ ] **Step 6: Update `pin_lint.CONSUMER_PIN_PATHS`.** In `adi_lg_plugins/hw_ci/pin_lint.py`, replace the **four** `docs/source/onboarding-templates/` entries (the three workflow templates + the AGENTS stub) with the four package-path equivalents (leave the `docs/source/user-guide/...rst` and `AGENTS.md` entries unchanged):

```python
    "adi_lg_plugins/hw_ci/onboarding_templates/hw-request-uri.yml",
    "adi_lg_plugins/hw_ci/onboarding_templates/noos-hw-request-flash.yml",
    "adi_lg_plugins/hw_ci/onboarding_templates/matlab-hw-request.yml",
    "adi_lg_plugins/hw_ci/onboarding_templates/AGENTS-consumer-stub.md",
```

- [ ] **Step 7: Fix all tracked prose path references.** Discover every remaining TRACKED reference (excluding the immutable spec/plan records under `docs/superpowers/`):

Run: `git grep -n 'onboarding-templates/' -- ':!docs/superpowers/'`

This lists the prose hits to fix (verified set): `AGENTS.md` (lines 7, 37, 43, 75, 104), `CLAUDE.md` (line 130), `docs/source/user-guide/onboarding-a-consumer-repo.rst` (lines 179, 228), and `.claude/skills/hardware-test-automation/{SKILL.md, references/consumer-ci.md, references/exporter-coordinator.md}`. In each, replace the **directory portion** `onboarding-templates` → `adi_lg_plugins/hw_ci/onboarding_templates` (keep the hyphenated *filenames* and the `docs/source/` → drop it; e.g. `docs/source/onboarding-templates/AGENTS-consumer-stub.md` → `adi_lg_plugins/hw_ci/onboarding_templates/AGENTS-consumer-stub.md`, and the bare `onboarding-templates/board-catalog-entry.yaml` → `adi_lg_plugins/hw_ci/onboarding_templates/board-catalog-entry.yaml`).

- [ ] **Step 8: Verify no stale references + lint + docs build**

Run:
```bash
git grep -n 'onboarding-templates' -- ':!docs/superpowers/'
.venv/bin/python -m pytest tests/hw_ci/test_onboarding_templates_packaged.py -v
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/sphinx-build -b html docs/source /tmp/p3docs 2>&1 | tail -3
```
Expected: the `git grep` prints **nothing** (every tracked, non-superpowers ref now uses `onboarding_templates`); tests PASS; ruff check + format clean; docs `build succeeded.`

- [ ] **Step 9: Confirm pin-lint still covers the moved templates**

Run: `.venv/bin/python -c "from pathlib import Path; from adi_lg_plugins.hw_ci.pin_lint import CONSUMER_PIN_PATHS, find_consumer_pin_violations; from adi_lg_plugins.hw_ci._release import RECOMMENDED_PIN; print('missing:', [p for p in CONSUMER_PIN_PATHS if not Path(p).is_file()]); print('violations:', find_consumer_pin_violations(CONSUMER_PIN_PATHS, RECOMMENDED_PIN))"`
Expected: `missing: []` and `violations: []`.

- [ ] **Step 10: Add the test to CI** — `.github/workflows/tests.yml`, add to the `nox -s tests --` list (after `tests/hw_ci/test_release_guard.py`):

```
          tests/hw_ci/test_onboarding_templates_packaged.py \
```

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "refactor(hw_ci): package onboarding templates (single source; docs literalinclude from package)"
```

---

### Task 2: Matlab `board-map.yaml` template

**Files:**
- Create: `adi_lg_plugins/hw_ci/onboarding_templates/board-map.yaml`
- Modify: `docs/source/user-guide/onboarding-a-consumer-repo.rst` (replace the inline matlab board-map code-block with a literalinclude)
- Test: extend `tests/hw_ci/test_onboarding_templates_packaged.py`

- [ ] **Step 1: Add board-map to the drift-guard test.** In `tests/hw_ci/test_onboarding_templates_packaged.py`, add `"board-map.yaml",` to the `EXPECTED` set.

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_onboarding_templates_packaged.py::test_templates_are_importable_resources -v`
Expected: FAIL — `board-map.yaml` missing from packaged resources.

- [ ] **Step 3: Create the template** `adi_lg_plugins/hw_ci/onboarding_templates/board-map.yaml`:

```yaml
# Template — copy into <consumer-repo>/test/hw_ci/board_map.yaml; replace <PLACEHOLDERS>.
#
# matlab-mode board map: resolves each live place's (daughter-board, carrier, hdl-config)
# to the MATLAB board name passed to runHWTests(). `adi-lg-hw-ci matlab-matrix` intersects
# this with live coordinator places; most-specific entry wins (a row with more keys beats a
# row with fewer). Live places with no matching entry are annotated + skipped.
#
# Schema (source of truth): adi_lg_plugins/hw_ci/board_map.py (load_board_map).
boards:
  - {carrier: <CARRIER>, daughter-board: <PART>, matlab_board: <MATLAB_BOARD>}
  # Less-specific fallback (matches the part on any carrier):
  # - {daughter-board: <PART>, matlab_board: <MATLAB_BOARD>}
  #
  # Example (proven):
  # - {carrier: zcu102, daughter-board: adrv9002, matlab_board: zynqmp-zcu102-rev10-adrv9002-vcmos}
  # - {daughter-board: pluto, matlab_board: pluto}
```

- [ ] **Step 4: Replace the inline matlab board-map code-block with a literalinclude (single source).** In `docs/source/user-guide/onboarding-a-consumer-repo.rst`, the matlab "Board map" paragraph is followed by an inline schema example:

```rst
.. code-block:: yaml

   boards:
     - {carrier: zcu102, daughter-board: adrv9002, matlab_board: zynqmp-zcu102-rev10-adrv9002-vcmos}
     - {daughter-board: pluto, matlab_board: pluto}
```

Replace that entire `.. code-block:: yaml` block (the directive + its 3 indented body lines) with:

```rst
.. literalinclude:: ../../../adi_lg_plugins/hw_ci/onboarding_templates/board-map.yaml
   :language: yaml
```

(Do NOT leave the inline block in place — that would duplicate the schema. The literalinclude now sources it from the packaged template.)

- [ ] **Step 5: Run the test + lint + docs build**

Run:
```bash
.venv/bin/python -m pytest tests/hw_ci/test_onboarding_templates_packaged.py -v
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/sphinx-build -b html docs/source /tmp/p3docs 2>&1 | tail -3
```
Expected: tests PASS; ruff clean; docs `build succeeded.`

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(onboarding): packaged matlab board-map.yaml template + literalinclude"
```

---

### Task 3: `scaffold.py` — the init engine

**Files:**
- Create: `adi_lg_plugins/hw_ci/scaffold.py`
- Test: `tests/hw_ci/test_scaffold.py` (new)

**Interfaces:**
- Consumes: packaged templates (Task 1/2), `_release.RECOMMENDED_PIN`.
- Produces:
  - `MODE_FILES: dict[str, list[tuple[str, str]]]` — mode → `(template_name, dest_relpath)` list. (`AGENTS-consumer-stub.md → AGENTS.md` is appended for every mode.)
  - `render_template(name, *, test_root=None, install_cmd=None) -> str` — read packaged template, rewrite labgrid-plugins pins to `RECOMMENDED_PIN`, substitute `<TEST_ROOT>`/`<YOUR_INSTALL_ARGS>` when given.
  - `scaffold(mode, dest, *, test_root=None, install_cmd=None, force=False) -> list[Path]` — atomic: pre-checks all dests, raises `FileExistsError` if any exists (unless `force`), then writes.
  - `next_steps(mode) -> str` — post-scaffold guidance (gh var commands, lab-admin prereqs, a real per-mode `doctor`/`lint-markers` command).

- [ ] **Step 1: Write the failing test** — create `tests/hw_ci/test_scaffold.py`:

```python
from pathlib import Path

import pytest

from adi_lg_plugins.hw_ci import scaffold
from adi_lg_plugins.hw_ci._release import RECOMMENDED_PIN


def test_render_substitutes_and_pins():
    out = scaffold.render_template(
        "hw-request-uri.yml", test_root="test/hw", install_cmd='uv pip install -e ".[test]"'
    )
    assert "<TEST_ROOT>" not in out and "test/hw" in out
    assert "<YOUR_INSTALL_ARGS>" not in out
    assert f"hw-request.yml@{RECOMMENDED_PIN}" in out  # workflow pin
    assert f"labgrid-plugins.git@{RECOMMENDED_PIN}" in out  # git+https install pin


def test_render_pins_the_stub_placeholder_ref():
    # The stub's `<...>.yml@v3.5` ref must also be pinned to RECOMMENDED_PIN.
    out = scaffold.render_template("AGENTS-consumer-stub.md")
    assert f".yml@{RECOMMENDED_PIN}" in out


def test_scaffold_uri_writes_expected_files(tmp_path):
    written = scaffold.scaffold("uri", str(tmp_path), test_root="test/hw")
    rels = sorted(str(p.relative_to(tmp_path)) for p in written)
    assert rels == sorted([".github/workflows/hw-request.yml", "test/hw/conftest.py", "AGENTS.md"])


def test_scaffold_matlab_uses_hw_matlab_and_board_map_dests(tmp_path):
    rels = {str(p.relative_to(tmp_path)) for p in scaffold.scaffold("matlab", str(tmp_path))}
    assert ".github/workflows/hw-matlab.yml" in rels
    assert "test/hw_ci/board_map.yaml" in rels  # underscore dest


def test_scaffold_refuses_overwrite_without_force(tmp_path):
    scaffold.scaffold("uri", str(tmp_path), test_root="t")
    with pytest.raises(FileExistsError):
        scaffold.scaffold("uri", str(tmp_path), test_root="t")
    assert scaffold.scaffold("uri", str(tmp_path), test_root="t", force=True)


def test_next_steps_has_real_command_per_mode():
    for mode in ("uri", "flash", "matlab"):
        msg = scaffold.next_steps(mode)
        assert "gh variable set" in msg and "LG_COORDINATOR" in msg
        assert f"doctor --mode {mode}" in msg
        assert "..." not in msg  # no placeholder ellipsis shipped in guidance
    assert "MATLAB_BIN" in scaffold.next_steps("matlab")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_scaffold.py -v`
Expected: FAIL — `ModuleNotFoundError: adi_lg_plugins.hw_ci.scaffold`.

- [ ] **Step 3: Create `adi_lg_plugins/hw_ci/scaffold.py`** (the code below is pre-wrapped to ruff's 100-col style; still run `ruff format` in Step 4 before `--check`):

```python
"""`adi-lg-hw-ci init` engine: read packaged onboarding templates, substitute
placeholders + the current release pin, and write them into a consumer repo."""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path

from ._release import RECOMMENDED_PIN

_ANCHOR = "adi_lg_plugins.hw_ci.onboarding_templates"

# mode -> [(packaged template name, destination path relative to the repo root)].
# NOTE: matlab's source template is board-map.yaml (hyphen) but the consumer dest is
# board_map.yaml (underscore) — that's what board_map.py loads; keep the rename.
MODE_FILES: dict[str, list[tuple[str, str]]] = {
    "uri": [
        ("hw-request-uri.yml", ".github/workflows/hw-request.yml"),
        ("conftest-iio-uri.py", "test/hw/conftest.py"),
    ],
    "flash": [
        ("noos-hw-request-flash.yml", ".github/workflows/hw-request.yml"),
        ("projects.yaml", "tools/hw_ci/projects.yaml"),
    ],
    "matlab": [
        ("matlab-hw-request.yml", ".github/workflows/hw-matlab.yml"),
        ("board-map.yaml", "test/hw_ci/board_map.yaml"),
    ],
}

# Rewrite any labgrid-plugins pin to RECOMMENDED_PIN. _LG_PIN covers the workflow `uses:`
# AND the `git+https://...labgrid-plugins.git@v..` install (the `[\w./-]*?` consumes `.git`).
# _YML_PIN additionally catches the consumer-stub's bracketed `<...>.yml@v..` form, which the
# first pattern can't (the `<...>` contains spaces/pipes).
_LG_PIN = re.compile(r"(tfcollins/labgrid-plugins[\w./-]*?)@v[\w.]+")
_YML_PIN = re.compile(r"(\.yml)@v[\w.]+")


def _read(name: str) -> str:
    return (resources.files(_ANCHOR) / name).read_text(encoding="utf-8")


def render_template(
    name: str, *, test_root: str | None = None, install_cmd: str | None = None
) -> str:
    text = _read(name)
    text = _LG_PIN.sub(rf"\1@{RECOMMENDED_PIN}", text)
    text = _YML_PIN.sub(rf"\1@{RECOMMENDED_PIN}", text)
    # <TEST_ROOT> appears only in hw-request-uri.yml; conftest is copied verbatim, so these
    # replaces are intentional no-ops for templates that don't carry the placeholder.
    if test_root is not None:
        text = text.replace("<TEST_ROOT>", test_root)
    if install_cmd is not None:
        text = text.replace("<YOUR_INSTALL_ARGS>", install_cmd)
    return text


def scaffold(
    mode: str,
    dest: str | Path,
    *,
    test_root: str | None = None,
    install_cmd: str | None = None,
    force: bool = False,
) -> list[Path]:
    if mode not in MODE_FILES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {sorted(MODE_FILES)}")
    files = [*MODE_FILES[mode], ("AGENTS-consumer-stub.md", "AGENTS.md")]
    root = Path(dest)
    targets = [(name, root / rel) for name, rel in files]
    if not force:
        clashes = [str(out) for _, out in targets if out.exists()]
        if clashes:
            raise FileExistsError(f"refusing to overwrite (pass force=True): {', '.join(clashes)}")
    written: list[Path] = []
    for name, out in targets:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            render_template(name, test_root=test_root, install_cmd=install_cmd),
            encoding="utf-8",
        )
        written.append(out)
    return written


_DOCTOR_ARGS = {
    "uri": "--test-root test/hw --runner-label <runner-label>",
    "flash": "--manifest tools/hw_ci/projects.yaml --runner-label <runner-label>",
    "matlab": "--board-map test/hw_ci/board_map.yaml --runner-label <runner-label>",
}


def next_steps(mode: str) -> str:
    lines = [
        "Next steps:",
        "1. Set the repo variables (Settings -> Secrets and variables -> Actions -> Variables):",
        "   gh variable set LG_COORDINATOR --body '<host>:20408'   # gRPC, NOT REST :8000",
        "   gh variable set HW_REQUEST_RUNNER --body '<runner-label>'",
        "   gh variable set HW_PREFLIGHT_RUNNER --body '<coordinator-runner-label>'",
    ]
    if mode == "matlab":
        lines.append("   gh variable set MATLAB_BIN --body '/opt/MATLAB/R2025b/bin/matlab'")
    lines += [
        "2. Ask a lab admin to add a board_catalog.yaml entry + a live place per part.",
        "3. Fill the remaining <PLACEHOLDERS> in the written files.",
        "4. Verify before opening a PR (no hardware needed):",
        f"   adi-lg-hw-ci doctor --mode {mode} --coord <host>:20408 {_DOCTOR_ARGS[mode]}",
    ]
    if mode == "uri":
        lines.append("   adi-lg-hw-ci lint-markers --test-root test/hw")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Format, then run the tests + lint gate**

Run:
```bash
.venv/bin/ruff format adi_lg_plugins/hw_ci/scaffold.py
.venv/bin/python -m pytest tests/hw_ci/test_scaffold.py -v
.venv/bin/ruff check adi_lg_plugins/hw_ci/scaffold.py && .venv/bin/ruff format --check adi_lg_plugins/hw_ci/scaffold.py
```
Expected: tests PASS; ruff check + format clean.

- [ ] **Step 5: Add the test to CI** — `.github/workflows/tests.yml`, after Task 1's line:

```
          tests/hw_ci/test_scaffold.py \
```

- [ ] **Step 6: Commit**

```bash
git add adi_lg_plugins/hw_ci/scaffold.py tests/hw_ci/test_scaffold.py .github/workflows/tests.yml
git commit -m "feat(hw_ci): scaffold engine for adi-lg-hw-ci init (packaged templates -> consumer files)"
```

---

### Task 4: `adi-lg-hw-ci init` CLI command

**Files:**
- Modify: `adi_lg_plugins/hw_ci/cli.py` (`_cmd_init` + subparser)
- Modify: `docs/source/user-guide/onboarding-a-consumer-repo.rst` (an `init` tip)
- Test: `tests/hw_ci/test_init_cli.py` (new)

**Interfaces:**
- Consumes: `scaffold.scaffold` / `scaffold.next_steps` (Task 3).
- Produces: CLI `adi-lg-hw-ci init --mode {uri,flash,matlab} --dest <repo-root> [--test-root … --install-cmd … --force]` → writes files, prints each written path + the next-steps guidance to stderr; exit 0 on success, 1 if a file exists without `--force`.

- [ ] **Step 1: Write the failing test** — create `tests/hw_ci/test_init_cli.py`:

```python
from adi_lg_plugins.hw_ci.cli import main


def test_init_uri_writes_files_and_guidance(tmp_path, capsys):
    rc = main(["init", "--mode", "uri", "--dest", str(tmp_path), "--test-root", "test/hw"])
    assert rc == 0
    assert (tmp_path / ".github/workflows/hw-request.yml").is_file()
    assert (tmp_path / "test/hw/conftest.py").is_file()
    assert (tmp_path / "AGENTS.md").is_file()
    err = capsys.readouterr().err
    assert "gh variable set" in err and "doctor" in err


def test_init_refuses_existing_without_force(tmp_path):
    main(["init", "--mode", "uri", "--dest", str(tmp_path), "--test-root", "test/hw"])
    assert main(["init", "--mode", "uri", "--dest", str(tmp_path), "--test-root", "test/hw"]) == 1


def test_init_force_overwrites(tmp_path):
    main(["init", "--mode", "uri", "--dest", str(tmp_path), "--test-root", "test/hw"])
    rc = main(["init", "--mode", "uri", "--dest", str(tmp_path), "--test-root", "test/hw", "--force"])
    assert rc == 0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_init_cli.py -v`
Expected: FAIL — argparse `invalid choice: 'init'`.

- [ ] **Step 3: Add `_cmd_init`** to `adi_lg_plugins/hw_ci/cli.py` (after `_cmd_lint_markers`):

```python
def _cmd_init(args: argparse.Namespace) -> int:
    """Scaffold a consumer repo's hw-CI files for a chosen mode."""
    from . import scaffold

    try:
        written = scaffold.scaffold(
            args.mode,
            args.dest,
            test_root=args.test_root,
            install_cmd=args.install_cmd,
            force=args.force,
        )
    except FileExistsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    for path in written:
        print(f"wrote {path}", file=sys.stderr)
    print("", file=sys.stderr)
    print(scaffold.next_steps(args.mode), file=sys.stderr)
    return 0
```

- [ ] **Step 4: Register the subparser** in `main()` (after the `lint-markers` parser, before `doctor`):

```python
    pinit = sub.add_parser("init", help="scaffold a consumer repo's hw-CI files for a mode")
    pinit.add_argument("--mode", choices=["uri", "flash", "matlab"], required=True)
    pinit.add_argument("--dest", required=True, help="consumer repo root to write into")
    pinit.add_argument("--test-root", default=None, help="[uri] value for <TEST_ROOT> (e.g. test/hw)")
    pinit.add_argument(
        "--install-cmd", default=None, help="[uri] value for <YOUR_INSTALL_ARGS> in the install step"
    )
    pinit.add_argument(
        "--force", action="store_true", help="overwrite existing files at the destination"
    )
    pinit.set_defaults(func=_cmd_init)
```

- [ ] **Step 5: Format, then run the tests + lint gate**

Run:
```bash
.venv/bin/ruff format adi_lg_plugins/hw_ci/cli.py
.venv/bin/python -m pytest tests/hw_ci/test_init_cli.py -v
.venv/bin/ruff check adi_lg_plugins/hw_ci/cli.py && .venv/bin/ruff format --check adi_lg_plugins/hw_ci/cli.py
```
Expected: tests PASS; ruff check + format clean.

- [ ] **Step 6: Add the test to CI** — `.github/workflows/tests.yml`, after Task 3's line:

```
          tests/hw_ci/test_init_cli.py \
```

- [ ] **Step 7: Document `init` in the onboarding recipe.** In `docs/source/user-guide/onboarding-a-consumer-repo.rst`, just after the "Step 2 — what you'll touch" table, add:

```rst

.. tip::

   Instead of copying templates by hand, scaffold them with the packaged CLI::

      pip install adi-labgrid-plugins
      adi-lg-hw-ci init --mode uri --dest . --test-root test/hw

   It writes the mode's files (pinned to the current release), then prints the repo
   variables to set and the ``doctor``/``lint-markers`` commands to verify with.
```

- [ ] **Step 8: Docs build + commit**

Run: `.venv/bin/sphinx-build -b html docs/source /tmp/p3docs 2>&1 | tail -3`
Expected: `build succeeded.`

```bash
git add adi_lg_plugins/hw_ci/cli.py tests/hw_ci/test_init_cli.py docs/source/user-guide/onboarding-a-consumer-repo.rst .github/workflows/tests.yml
git commit -m "feat(hw_ci): adi-lg-hw-ci init command + onboarding-guide tip"
```

---

## Self-Review

**Spec coverage (Phase 3 / WS-C):**
- Package the templates (git mv + `__init__.py` + multi-ext package-data + ruff exclude + literalinclude repoint + drift test) → Task 1. ✓
- `init` scaffolder (modes, placeholder substitution, atomic idempotent/`--force`, RECOMMENDED_PIN incl. the stub placeholder ref, next-steps with gh vars + lab-admin + real per-mode doctor/lint-markers) → Tasks 3, 4. ✓
- matlab `board-map.yaml` template + literalinclude (replacing the inline duplicate) → Task 2. ✓

**Ripples handled (from the grounded plan review):** `pin_lint.CONSUMER_PIN_PATHS` repointed (Task 1 Step 6, verified Step 9); ALL tracked prose refs swept via `git grep` incl. `CLAUDE.md` + the tracked `.claude/skills/*` (Step 7-8); the inline matlab schema is replaced not duplicated (Task 2 Step 4); the stub's `<…>.yml@v..` pin is rewritten by `_YML_PIN` (Task 3); scaffold is atomic; `next_steps` ships real per-mode commands (no `...`); `_GIT_PIN_RE` dropped (redundant). The CI `ruff format --check` trap is pre-empted: every Python task `ruff format`s before `--check`.

**Placeholder scan:** the `<…>` tokens are intentional consumer placeholders in templates/guidance, not plan placeholders. No TBD/TODO. Every code step shows complete code.

**Type/name consistency:** `scaffold(mode, dest, *, test_root, install_cmd, force)`, `render_template(name, *, test_root, install_cmd)`, `next_steps(mode)`, `MODE_FILES`, `_DOCTOR_ARGS` used identically across Task 3 (definition), Task 4 (CLI), and the tests. Matlab dest `hw-matlab.yml` + `board_map.yaml` (underscore) consistent across Global Constraints, MODE_FILES, and tests.

**Ordering:** Task 1 (move) precedes the package-anchor reads in 2-4; Task 2 (board-map) precedes Task 3's matlab scaffold test (which writes `board_map.yaml`). Plan order 1→2→3→4.
