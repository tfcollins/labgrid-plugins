# Onboarding Enhancements — Phase 2 Implementation Plan (validation & automation)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the onboarding "friction checklist" from documented-only into enforced/automated checks: a one-pass `adi-lg-hw-ci doctor`, a `lint-markers` linter, a fail-fast workflow var-guard, GH annotations for the two infra failures, and a single-source release pin with consistency + release-guard lints.

**Architecture:** New testable modules under `adi_lg_plugins/hw_ci/` (`_release.py`, `doctor.py`, `pin_lint.py`) plus additions to existing `markers.py`, `cli.py`, `tools/request_cli.py`, the three reusable workflows, `noxfile.py`, and `docs/source/conf.py`. External deps (`gh`, coordinator HTTP) are injected so logic is unit-tested without a process boundary or network.

**Tech Stack:** Python 3.10+ (argparse `adi-lg-hw-ci`; Click `adi-lg request`), pytest (capsys/monkeypatch + CliRunner), ruff, nox, Sphinx, GitHub Actions YAML, `gh` CLI.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-06-19-onboarding-enhancements-design.md`. This plan implements **Phase 2** (WS-B + WS-D Phase-2 automation). Phase 1 is already merged to `main`.
- **Branch:** `onboarding-enhancements-phase2` (already created off `main`). Do NOT create another branch.
- **Environment:** use the project venv — `.venv/bin/python -m pytest …`, `.venv/bin/ruff …`, `.venv/bin/sphinx-build …`. Deps pre-installed; everything runs under the default sandbox with **NO network**; do NOT use `nox`/`pip`. A harmless `kasadriver not registered` line prints on import — ignore it.
- **`RECOMMENDED_PIN`** lives in `adi_lg_plugins/hw_ci/_release.py` (value `"v3.5"`), defined as the latest stable consumer-facing release tag, bumped as the final release step. It is the single source the pin-lint + doctor compare against. `conf.py` reads it by **regex-parsing the file (no package import)**.
- **`doctor` gh-dependent checks degrade to SKIP** when `gh` is absent/unauth (never hard-fail on tooling absence); a SKIP is not a failure, but doctor prints a partial-coverage banner so a green run can't mislead.
- **`doctor` runner check:** a leg resolves if its own `runner` is non-empty OR the fallback `runner-label`/`HW_REQUEST_RUNNER` is non-empty — do NOT fail on an empty per-leg runner alone.
- **Infra annotations** carry only `part` + `reason` (the exceptions are bare; no queue-depth/elapsed) and mirror the existing boot-failure block's `" ".join(str(e).split())` collapse, gated on `GITHUB_ACTIONS == "true"`.
- **`markers.harvest_markers` signature/accepted output stays byte-identical**; rejection collection is the additive `collect_marker_rejections`.
- **Release guard runs ONLY in the release recipe / on `release/*`** — never on `main`/PR (where internal `@main` self-refs are by design).
- New tests go in `tests/hw_ci/` and must be added to the CI list in `.github/workflows/tests.yml` (it runs an explicit file list).
- **Gates:** `.venv/bin/ruff check .` clean; touched tests green; `.venv/bin/sphinx-build -b html docs/source /tmp/p2docs` builds.

## File structure (Phase 2)

| File | Responsibility |
|---|---|
| `adi_lg_plugins/hw_ci/_release.py` (new) | `RECOMMENDED_PIN` single source |
| `docs/source/conf.py` (modify) | `|hw_ci_pin|` rst substitution via regex read of `_release.py` |
| `adi_lg_plugins/hw_ci/markers.py` (modify) | `+ collect_marker_rejections` |
| `adi_lg_plugins/hw_ci/cli.py` (modify) | `+ _cmd_lint_markers`, `+ _cmd_doctor` subparsers |
| `adi_lg_plugins/tools/request_cli.py` (modify) | no-board / board-unavailable GH annotations |
| `.github/workflows/{hw-request,noos-hw-request,matlab-hw-request}.yml` (modify) | preflight var-guard step |
| `adi_lg_plugins/hw_ci/doctor.py` (new) | `CheckResult`, checks, table/exit, `run_doctor` |
| `adi_lg_plugins/hw_ci/pin_lint.py` (new) | `find_consumer_pin_violations`, `find_main_self_refs` |
| `noxfile.py` (modify) | `lint_pins`, `release_guard` sessions |
| `RELEASING.md` (modify) | release-guard invocation |
| `tests/hw_ci/test_*` (new) + `.github/workflows/tests.yml` (modify) | unit tests, CI-listed |

---

### Task 1: `_release.py` single-source pin + `conf.py` substitution

**Files:**
- Create: `adi_lg_plugins/hw_ci/_release.py`
- Modify: `docs/source/conf.py` (append substitution block)
- Test: `tests/hw_ci/test_release_pin.py` (new)

**Interfaces:**
- Produces: `adi_lg_plugins.hw_ci._release.RECOMMENDED_PIN: str` (value `"v3.5"`).

- [ ] **Step 1: Write the failing test** — create `tests/hw_ci/test_release_pin.py`:

```python
import re
from pathlib import Path


def test_recommended_pin_value():
    from adi_lg_plugins.hw_ci._release import RECOMMENDED_PIN

    assert RECOMMENDED_PIN == "v3.5"
    assert re.fullmatch(r"v\d+(\.\d+)*", RECOMMENDED_PIN)


def test_conf_substitution_reads_release_without_import():
    # conf.py must derive |hw_ci_pin| by regex-parsing _release.py (no package import).
    conf = Path("docs/source/conf.py").read_text(encoding="utf-8")
    assert "hw_ci_pin" in conf
    assert "_release.py" in conf
    assert "import adi_lg_plugins" not in conf
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_release_pin.py -v`
Expected: FAIL — `ModuleNotFoundError: adi_lg_plugins.hw_ci._release`.

- [ ] **Step 3: Create `_release.py`:**

```python
"""Single source for the consumer-facing release pin.

``RECOMMENDED_PIN`` is the latest STABLE release tag consumers should pin the
reusable workflows to (``uses: …@<pin>``). Bump it as the final step of a
release (see RELEASING.md). The docs ``|hw_ci_pin|`` substitution and the
pin-consistency lint both read this value, so a release bump touches one line.
"""

from __future__ import annotations

RECOMMENDED_PIN = "v3.5"
```

- [ ] **Step 4: Append the substitution block to the END of `docs/source/conf.py`:**

```python

# --- Hardware-CI recommended pin substitution -------------------------------
# Derive |hw_ci_pin| from the single source (adi_lg_plugins/hw_ci/_release.py)
# WITHOUT importing the package (its __init__ pulls the driver/resource/strategy
# registration chain, unsafe at config-eval time). Regex-parse the constant.
import re as _re  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_release_src = (
    _Path(__file__).resolve().parents[2] / "adi_lg_plugins" / "hw_ci" / "_release.py"
).read_text(encoding="utf-8")
_pin_match = _re.search(r'RECOMMENDED_PIN\s*=\s*"([^"]+)"', _release_src)
rst_epilog = f"\n.. |hw_ci_pin| replace:: {_pin_match.group(1) if _pin_match else 'v3.5'}\n"
```

- [ ] **Step 5: Run the test + a docs build**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_release_pin.py -v && .venv/bin/sphinx-build -b html docs/source /tmp/p2docs 2>&1 | tail -3`
Expected: tests PASS; `build succeeded.`

- [ ] **Step 6: Add the test to CI.** In `.github/workflows/tests.yml`, add a line to the `nox -s tests -- \` file list (after `tests/hw_ci/test_coordinator_resolve_api.py \`):

```
          tests/hw_ci/test_release_pin.py \
```

- [ ] **Step 7: Commit**

```bash
git add adi_lg_plugins/hw_ci/_release.py docs/source/conf.py tests/hw_ci/test_release_pin.py .github/workflows/tests.yml
git commit -m "feat(hw_ci): RECOMMENDED_PIN single source + docs |hw_ci_pin| substitution"
```

---

### Task 2: `markers.collect_marker_rejections`

**Files:**
- Modify: `adi_lg_plugins/hw_ci/markers.py` (add function; `harvest_markers` unchanged)
- Test: `tests/hw_ci/test_markers_rejections.py` (new)

**Interfaces:**
- Consumes: existing `_is_pytest_mark`, `_literal_str_list`, `_module_str_bindings` (markers.py).
- Produces: `collect_marker_rejections(test_root, *, markers=("iio_hardware","iio_carrier")) -> list[tuple[str, int, str]]` — `(relative_path, lineno, reason)` for every decorator that IS one of `markers` but whose first arg isn't a recognized literal.

- [ ] **Step 1: Write the failing test** — create `tests/hw_ci/test_markers_rejections.py`:

```python
from pathlib import Path

from adi_lg_plugins.hw_ci.markers import collect_marker_rejections, harvest_markers


def _write(tmp_path: Path, body: str) -> Path:
    d = tmp_path / "hw"
    d.mkdir()
    (d / "test_x.py").write_text("import pytest\n" + body, encoding="utf-8")
    return d


def test_flags_fstring_marker(tmp_path):
    root = _write(
        tmp_path,
        'PART = "ad9081"\n'
        "@pytest.mark.iio_hardware([f'{PART}_tdd'])\n"
        "def test_a():\n    pass\n",
    )
    rej = collect_marker_rejections(root)
    assert len(rej) == 1
    path, lineno, reason = rej[0]
    assert path == "test_x.py"
    assert "iio_hardware" in reason and "string literal" in reason


def test_accepts_literal_and_module_binding(tmp_path):
    root = _write(
        tmp_path,
        'hardware = ["ad9081"]\n'
        "@pytest.mark.iio_hardware(hardware)\n"
        "def test_a():\n    pass\n"
        '@pytest.mark.iio_hardware(["ad7768"])\n'
        "def test_b():\n    pass\n",
    )
    assert collect_marker_rejections(root) == []


def test_ignores_non_marker_decorators(tmp_path):
    root = _write(
        tmp_path,
        "@pytest.fixture\n@some.other(thing)\n"
        '@pytest.mark.iio_hardware(["ad9081"])\n'
        "def test_a():\n    pass\n",
    )
    assert collect_marker_rejections(root) == []
    # harvest still works unchanged
    assert any(k.endswith("::test_a") for k in harvest_markers(root))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_markers_rejections.py -v`
Expected: FAIL — `ImportError: cannot import name 'collect_marker_rejections'`.

- [ ] **Step 3: Add the function** to `adi_lg_plugins/hw_ci/markers.py` (after `harvest_markers`):

```python
def collect_marker_rejections(
    test_root: str | Path,
    *,
    markers: tuple[str, ...] = ("iio_hardware", "iio_carrier"),
) -> list[tuple[str, int, str]]:
    """Find marker decorators that ARE ``iio_hardware``/``iio_carrier`` but whose
    first argument is not a recognized string literal (or module-level literal
    binding) — exactly the forms ``harvest_markers`` silently drops.

    Returns a list of ``(relative_path, lineno, reason)``. A *non-marker*
    decorator is never a rejection; only ``_is_pytest_mark`` matches with a
    non-literal first arg are reported.
    """
    root = Path(test_root).resolve()
    rejections: list[tuple[str, int, str]] = []
    for py in sorted(root.rglob("test_*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        bindings = _module_str_bindings(tree)
        rel = str(py.relative_to(root))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for name in markers:
                if not _is_pytest_mark(node.func, name):
                    continue
                if not node.args:
                    continue  # bare marker — nothing to reject
                if _literal_str_list(node.args[0], bindings=bindings, lineno=node.lineno) is None:
                    rejections.append(
                        (rel, node.lineno, f"{name} arg is not a string literal (invisible to discovery)")
                    )
    return rejections
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_markers_rejections.py tests/hw_ci/test_markers_ast.py -v`
Expected: PASS (new tests + existing markers tests unaffected).

- [ ] **Step 5: Add the test to CI** — in `.github/workflows/tests.yml`, after the line added in Task 1:

```
          tests/hw_ci/test_markers_rejections.py \
```

- [ ] **Step 6: Commit**

```bash
git add adi_lg_plugins/hw_ci/markers.py tests/hw_ci/test_markers_rejections.py .github/workflows/tests.yml
git commit -m "feat(hw_ci): collect_marker_rejections (non-literal markers invisible to discovery)"
```

---

### Task 3: `adi-lg-hw-ci lint-markers` subcommand

**Files:**
- Modify: `adi_lg_plugins/hw_ci/cli.py` (`_cmd_lint_markers` + subparser)
- Test: `tests/hw_ci/test_lint_markers_cli.py` (new)

**Interfaces:**
- Consumes: `markers.collect_marker_rejections` (Task 2).
- Produces: CLI `adi-lg-hw-ci lint-markers --test-root <path>` → prints `file:line: reason` to stderr per rejection; exit 1 if any, else 0.

- [ ] **Step 1: Write the failing test** — create `tests/hw_ci/test_lint_markers_cli.py`:

```python
from adi_lg_plugins.hw_ci.cli import main


def _write(tmp_path, body):
    d = tmp_path / "hw"
    d.mkdir()
    (d / "test_x.py").write_text("import pytest\n" + body, encoding="utf-8")
    return str(d)


def test_lint_markers_clean_exit_zero(tmp_path, capsys):
    root = _write(tmp_path, '@pytest.mark.iio_hardware(["ad9081"])\ndef test_a():\n    pass\n')
    rc = main(["lint-markers", "--test-root", root])
    assert rc == 0


def test_lint_markers_reports_and_exits_one(tmp_path, capsys):
    root = _write(tmp_path, "@pytest.mark.iio_hardware(PART)\ndef test_a():\n    pass\n")
    rc = main(["lint-markers", "--test-root", root])
    assert rc == 1
    err = capsys.readouterr().err
    assert "test_x.py:2:" in err
    assert "string literal" in err
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_lint_markers_cli.py -v`
Expected: FAIL — `argparse` errors with `invalid choice: 'lint-markers'` (SystemExit).

- [ ] **Step 3: Add the command function** to `adi_lg_plugins/hw_ci/cli.py` (after `_cmd_list_strategies`):

```python
def _cmd_lint_markers(args: argparse.Namespace) -> int:
    """Flag iio_hardware/iio_carrier markers whose args are not string literals
    (silently invisible to discovery). Coordinator-free; CI/pre-commit friendly."""
    rejections = markers_mod.collect_marker_rejections(args.test_root)
    for path, lineno, reason in rejections:
        print(f"{path}:{lineno}: {reason}", file=sys.stderr)
    if rejections:
        print(
            f"# lint-markers: {len(rejections)} non-literal marker(s) — invisible to discovery",
            file=sys.stderr,
        )
        return 1
    print("# lint-markers: all hardware markers are string literals", file=sys.stderr)
    return 0
```

- [ ] **Step 4: Register the subparser** in `main()` (after the `list-strategies` parser block, before `request-matrix`):

```python
    plm = sub.add_parser(
        "lint-markers",
        help="flag iio_hardware/iio_carrier markers that aren't string literals",
    )
    plm.add_argument("--test-root", required=True, help="path to the consumer's test directory")
    plm.set_defaults(func=_cmd_lint_markers)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_lint_markers_cli.py -v && .venv/bin/ruff check adi_lg_plugins/hw_ci/cli.py`
Expected: tests PASS; ruff clean.

- [ ] **Step 6: Add the test to CI** — `.github/workflows/tests.yml`, after Task 2's line:

```
          tests/hw_ci/test_lint_markers_cli.py \
```

- [ ] **Step 7: Commit**

```bash
git add adi_lg_plugins/hw_ci/cli.py tests/hw_ci/test_lint_markers_cli.py .github/workflows/tests.yml
git commit -m "feat(hw_ci): adi-lg-hw-ci lint-markers subcommand"
```

---

### Task 4: Infra-failure GH annotations (no-board / board-unavailable)

**Files:**
- Modify: `adi_lg_plugins/tools/request_cli.py` (the `NoMatchingBoard` + `BoardUnavailable` except blocks, ~lines 185-190)
- Test: `tests/hw_ci/test_request_cli_annotations.py` (new)

**Interfaces:**
- Produces: under `GITHUB_ACTIONS == "true"`, `adi-lg request` emits `::error title=no-board::part=<part> reason=<collapsed str(e)>` (exit 10) and `::error title=board-unavailable::part=<part> reason=<collapsed str(e)>` (exit 11), mirroring the existing boot-failure annotation.

- [ ] **Step 1: Write the failing test** — create `tests/hw_ci/test_request_cli_annotations.py`:

```python
from unittest.mock import patch

from click.testing import CliRunner

from adi_lg_plugins.request import BoardUnavailable, NoMatchingBoard
from adi_lg_plugins.tools.request_cli import request_cmd


def _invoke(exc, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    with patch("adi_lg_plugins.tools.request_cli.request", side_effect=exc):
        return CliRunner().invoke(request_cmd, ["--part", "ad9081", "--wait", "0"])


def test_no_board_annotation(monkeypatch):
    res = _invoke(NoMatchingBoard("unknown part ad9081"), monkeypatch)
    assert res.exit_code == 10
    assert "::error title=no-board::part=ad9081 reason=unknown part ad9081" in res.output


def test_board_unavailable_annotation(monkeypatch):
    res = _invoke(BoardUnavailable("no free board within 0s"), monkeypatch)
    assert res.exit_code == 11
    assert "::error title=board-unavailable::part=ad9081 reason=no free board within 0s" in res.output


def test_no_annotation_outside_actions(monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    with patch("adi_lg_plugins.tools.request_cli.request", side_effect=NoMatchingBoard("x")):
        res = CliRunner().invoke(request_cmd, ["--part", "ad9081", "--wait", "0"])
    assert res.exit_code == 10
    assert "::error" not in res.output
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_request_cli_annotations.py -v`
Expected: FAIL — no `::error title=no-board::` in output (only the rich red line is printed today).

- [ ] **Step 3: Edit the two except blocks** in `adi_lg_plugins/tools/request_cli.py`. Replace:

```python
    except NoMatchingBoard as e:
        console.print(f"[bold red]No matching board: {e}[/bold red]")
        sys.exit(EXIT_NO_MATCH)
    except BoardUnavailable as e:
        console.print(f"[bold red]Board unavailable: {e}[/bold red]")
        sys.exit(EXIT_UNAVAILABLE)
```

with:

```python
    except NoMatchingBoard as e:
        console.print(f"[bold red]No matching board: {e}[/bold red]")
        if os.environ.get("GITHUB_ACTIONS") == "true":
            reason = " ".join(str(e).split())
            click.echo(f"::error title=no-board::part={part} reason={reason}")
        sys.exit(EXIT_NO_MATCH)
    except BoardUnavailable as e:
        console.print(f"[bold red]Board unavailable: {e}[/bold red]")
        if os.environ.get("GITHUB_ACTIONS") == "true":
            reason = " ".join(str(e).split())
            click.echo(f"::error title=board-unavailable::part={part} reason={reason}")
        sys.exit(EXIT_UNAVAILABLE)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_request_cli_annotations.py tests/test_request_cli.py -v`
Expected: PASS (new tests + existing request-cli tests unaffected).

- [ ] **Step 5: Add the test to CI** — `.github/workflows/tests.yml`, after Task 3's line:

```
          tests/hw_ci/test_request_cli_annotations.py \
```

- [ ] **Step 6: Commit**

```bash
git add adi_lg_plugins/tools/request_cli.py tests/hw_ci/test_request_cli_annotations.py .github/workflows/tests.yml
git commit -m "feat(request): GH ::error annotations for no-board and board-unavailable"
```

---

### Task 5: Preflight var-guard in the three reusable workflows

**Files:**
- Modify: `.github/workflows/hw-request.yml`, `noos-hw-request.yml`, `matlab-hw-request.yml` (add a first step to each `preflight` job)
- Test: `tests/hw_ci/test_workflow_var_guard.py` (new — YAML-loads each workflow and asserts the guard step)

**Interfaces:**
- Produces: each family workflow's `preflight` job has a first `run` step that fails fast with a named `::error::` when `inputs.coordinator` or `inputs.runner-label` is empty.

- [ ] **Step 1: Write the failing test** — create `tests/hw_ci/test_workflow_var_guard.py`:

```python
from pathlib import Path

import yaml

WORKFLOWS = [
    ".github/workflows/hw-request.yml",
    ".github/workflows/noos-hw-request.yml",
    ".github/workflows/matlab-hw-request.yml",
]


def test_preflight_has_var_guard_first_step():
    for wf in WORKFLOWS:
        data = yaml.safe_load(Path(wf).read_text(encoding="utf-8"))
        preflight = data["jobs"]["preflight"]
        first = preflight["steps"][0]
        run = first.get("run", "")
        assert "inputs.coordinator" in run, f"{wf}: guard missing coordinator check"
        assert "inputs.runner-label" in run, f"{wf}: guard missing runner-label check"
        assert "::error::" in run, f"{wf}: guard not emitting ::error::"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_workflow_var_guard.py -v`
Expected: FAIL — the first preflight step is `actions/checkout@v4`, not a guard.

- [ ] **Step 3: Add the guard step** as the FIRST step of the `preflight:` job in each of the three workflows. In each file, the `preflight:` job's `steps:` currently begins with `- uses: actions/checkout@v4`. Insert this block immediately before that line (matching the existing 6-space step indentation):

```yaml
      - name: Validate required inputs
        run: |
          [ -n "${{ inputs.coordinator }}" ] || { echo "::error::coordinator is empty — set vars.LG_COORDINATOR (gRPC :20408)"; exit 1; }
          [ -n "${{ inputs.runner-label }}" ] || { echo "::error::runner-label is empty — set vars.HW_REQUEST_RUNNER"; exit 1; }
```

(All three family workflows expose both `coordinator` and `runner-label` inputs, so the same block applies verbatim to each.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_workflow_var_guard.py -v`
Expected: PASS (all three workflows).

- [ ] **Step 5: Add the test to CI** — `.github/workflows/tests.yml`, after Task 4's line:

```
          tests/hw_ci/test_workflow_var_guard.py \
```

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/hw-request.yml .github/workflows/noos-hw-request.yml .github/workflows/matlab-hw-request.yml tests/hw_ci/test_workflow_var_guard.py .github/workflows/tests.yml
git commit -m "feat(hw_ci): fail-fast preflight guard for empty coordinator/runner-label"
```

---

### Task 6: `doctor` core module (checks + table + exit), non-gh checks

**Files:**
- Create: `adi_lg_plugins/hw_ci/doctor.py`
- Test: `tests/hw_ci/test_doctor_core.py` (new)

**Interfaces:**
- Consumes: `coordinator.warn_if_rest_port` / `list_live_places` / `_resolve_api`, `markers.harvest_markers`, `request_matrix.build_request_matrix`, `request.match_client.get_match`, `_release.RECOMMENDED_PIN`.
- Produces:
  - `CheckResult` dataclass: `name: str`, `status: str` (`"PASS"|"FAIL"|"SKIP"`), `detail: str = ""`.
  - `PASS = "PASS"`, `FAIL = "FAIL"`, `SKIP = "SKIP"` constants.
  - `format_table(results: list[CheckResult]) -> str`
  - `exit_code(results: list[CheckResult]) -> int` (1 if any FAIL else 0)
  - `skipped_banner(results) -> str | None`
  - `check_discovery(mode, *, coord, test_root=None, manifest=None, board_map=None, fallback_runner, probe=None, lister=None) -> CheckResult`
  - `check_pin(repo_root=".") -> CheckResult`

- [ ] **Step 1: Write the failing test** — create `tests/hw_ci/test_doctor_core.py`:

```python
from adi_lg_plugins.hw_ci import doctor
from adi_lg_plugins.hw_ci.doctor import CheckResult, FAIL, PASS, SKIP


def test_exit_code_and_table():
    results = [CheckResult("a", PASS), CheckResult("b", SKIP, "gh missing")]
    assert doctor.exit_code(results) == 0
    results.append(CheckResult("c", FAIL, "boom"))
    assert doctor.exit_code(results) == 1
    table = doctor.format_table(results)
    assert "a" in table and "PASS" in table and "FAIL" in table and "boom" in table


def test_skipped_banner():
    assert doctor.skipped_banner([CheckResult("a", PASS)]) is None
    banner = doctor.skipped_banner([CheckResult("a", SKIP), CheckResult("b", SKIP)])
    assert "2 check" in banner and "NOT verified" in banner


class _Match:
    def __init__(self, satisfiable, runner=None):
        self.satisfiable = satisfiable
        self.runner = runner


def test_check_discovery_uri_pass_with_fallback_runner(tmp_path):
    d = tmp_path / "hw"
    d.mkdir()
    (d / "test_x.py").write_text(
        'import pytest\n@pytest.mark.iio_hardware(["ad9081"])\ndef test_a():\n    pass\n',
        encoding="utf-8",
    )
    # board satisfiable but no per-leg runner -> resolves via fallback
    res = doctor.check_discovery(
        "uri", coord="h:20408", test_root=str(d), fallback_runner="hw-lab",
        probe=lambda part: _Match(True, runner=None),
    )
    assert res.status == PASS


def test_check_discovery_uri_fail_no_runner(tmp_path):
    d = tmp_path / "hw"
    d.mkdir()
    (d / "test_x.py").write_text(
        'import pytest\n@pytest.mark.iio_hardware(["ad9081"])\ndef test_a():\n    pass\n',
        encoding="utf-8",
    )
    res = doctor.check_discovery(
        "uri", coord="h:20408", test_root=str(d), fallback_runner="",
        probe=lambda part: _Match(True, runner=None),
    )
    assert res.status == FAIL
    assert "runner" in res.detail


def test_check_discovery_empty_matrix_fails(tmp_path):
    d = tmp_path / "hw"
    d.mkdir()
    (d / "test_x.py").write_text(
        'import pytest\n@pytest.mark.iio_hardware(["ad9081"])\ndef test_a():\n    pass\n',
        encoding="utf-8",
    )
    res = doctor.check_discovery(
        "uri", coord="h:20408", test_root=str(d), fallback_runner="hw-lab",
        probe=lambda part: _Match(False),
    )
    assert res.status == FAIL


def test_check_pin_flags_stale(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "hw.yml").write_text(
        "uses: tfcollins/labgrid-plugins/.github/workflows/hw-request.yml@v3.4\n",
        encoding="utf-8",
    )
    res = doctor.check_pin(repo_root=str(tmp_path))
    assert res.status == FAIL
    assert "v3.4" in res.detail
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_doctor_core.py -v`
Expected: FAIL — `ModuleNotFoundError: adi_lg_plugins.hw_ci.doctor`.

- [ ] **Step 3: Create `adi_lg_plugins/hw_ci/doctor.py`:**

```python
"""One-pass onboarding validator backing ``adi-lg-hw-ci doctor``.

Each check returns a :class:`CheckResult`; external dependencies (coordinator
HTTP, ``gh``) are injected so the logic is unit-tested without a process
boundary. The gh-dependent checks live in this module too (Task 7) but degrade
to SKIP when ``gh`` is unavailable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ._release import RECOMMENDED_PIN

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str = ""


def exit_code(results: list[CheckResult]) -> int:
    return 1 if any(r.status == FAIL for r in results) else 0


def format_table(results: list[CheckResult]) -> str:
    width = max((len(r.name) for r in results), default=4)
    lines = [f"{r.status:<4}  {r.name:<{width}}  {r.detail}".rstrip() for r in results]
    return "\n".join(lines)


def skipped_banner(results: list[CheckResult]) -> str | None:
    n = sum(1 for r in results if r.status == SKIP)
    if not n:
        return None
    return f"{n} check(s) skipped (gh unavailable) — repo-var/runner registration NOT verified"


def _discovery_legs(mode, *, coord, test_root, manifest, board_map, probe, lister):
    """Return (legs, missing, dropped) for the mode, using injected I/O.

    Each leg is a dict with at least ``part`` and ``runner`` keys. ``dropped`` is
    the list of (place_name, reason) for places rejected at validation.
    """
    from . import coordinator as coord_mod
    from . import markers as markers_mod
    from .board_map import build_matlab_matrix, load_board_map
    from .noos_manifest import build_noos_matrix, load_noos_manifest
    from .request_matrix import build_request_matrix

    dropped: list[tuple[str, str]] = []
    if mode == "uri":
        if probe is None:
            from adi_lg_plugins.request import match_client

            api = coord_mod._resolve_api(coord)
            probe = lambda part: match_client.get_match(api, part=part)  # noqa: E731
        markers = markers_mod.harvest_markers(test_root)
        wanted = sorted({h for spec in markers.values() for h in spec.iio_hardware})
        result = build_request_matrix(wanted, probe)
        legs = [{"part": leg.part, "runner": leg.runner or ""} for leg in result.parts]
        return legs, list(result.missing), dropped
    if mode == "flash":
        if probe is None:
            from adi_lg_plugins.request import match_client

            api = coord_mod._resolve_api(coord)
            probe = lambda part, carrier: match_client.get_match(  # noqa: E731
                api, part=part, carrier=carrier, mode="flash"
            )
        projects = load_noos_manifest(manifest)
        legs_raw, missing = build_noos_matrix(projects, probe)
        legs = [{"part": leg.part, "runner": leg.runner or ""} for leg in legs_raw]
        return legs, list(missing), dropped
    if mode == "matlab":
        places, dropped = (lister or coord_mod.list_live_places)(coord)
        legs_raw, skipped = build_matlab_matrix(places, load_board_map(board_map))
        legs = [{"part": leg.part, "runner": leg.runner or ""} for leg in legs_raw]
        return legs, list(skipped), dropped
    raise ValueError(f"unknown mode {mode!r}")


def check_discovery(
    mode,
    *,
    coord,
    test_root=None,
    manifest=None,
    board_map=None,
    fallback_runner,
    probe=None,
    lister=None,
) -> CheckResult:
    """Discovery matrix is non-empty AND every leg resolves to some runner
    (its own ``runner`` or the non-empty fallback). Dropped places are surfaced."""
    try:
        legs, missing, dropped = _discovery_legs(
            mode, coord=coord, test_root=test_root, manifest=manifest,
            board_map=board_map, probe=probe, lister=lister,
        )
    except Exception as e:  # noqa: BLE001 - report, don't crash the doctor
        return CheckResult("discovery", FAIL, f"discovery error: {e}")

    extra = ""
    if dropped:
        extra = "; dropped: " + ", ".join(f"{n} ({r})" for n, r in dropped)
    if not legs:
        miss = f" (wanted-but-missing: {', '.join(missing)})" if missing else ""
        return CheckResult("discovery", FAIL, f"empty matrix — no live board{miss}{extra}")
    no_runner = [leg["part"] for leg in legs if not leg["runner"] and not fallback_runner]
    if no_runner:
        return CheckResult(
            "discovery", FAIL,
            f"no runner for: {', '.join(no_runner)} (set a place `runner` tag or runner-label){extra}",
        )
    return CheckResult("discovery", PASS, f"{len(legs)} leg(s){extra}")


def check_pin(repo_root: str | Path = ".") -> CheckResult:
    """All consumer workflow pins to this repo's reusable workflows equal RECOMMENDED_PIN."""
    wf_dir = Path(repo_root) / ".github" / "workflows"
    if not wf_dir.is_dir():
        return CheckResult("pin", SKIP, "no .github/workflows in this repo")
    pat = re.compile(r"tfcollins/labgrid-plugins/\.github/workflows/[\w.-]+@(\S+)")
    stale: list[str] = []
    for f in sorted(wf_dir.glob("*.yml")) + sorted(wf_dir.glob("*.yaml")):
        for m in pat.finditer(f.read_text(encoding="utf-8")):
            if m.group(1) != RECOMMENDED_PIN:
                stale.append(f"{f.name}@{m.group(1)}")
    if stale:
        return CheckResult("pin", FAIL, f"pins != {RECOMMENDED_PIN}: {', '.join(stale)}")
    return CheckResult("pin", PASS, f"pinned @{RECOMMENDED_PIN}")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_doctor_core.py -v && .venv/bin/ruff check adi_lg_plugins/hw_ci/doctor.py`
Expected: tests PASS; ruff clean.

- [ ] **Step 5: Add the test to CI** — `.github/workflows/tests.yml`, after Task 5's line:

```
          tests/hw_ci/test_doctor_core.py \
```

- [ ] **Step 6: Commit**

```bash
git add adi_lg_plugins/hw_ci/doctor.py tests/hw_ci/test_doctor_core.py .github/workflows/tests.yml
git commit -m "feat(hw_ci): doctor core — discovery + pin checks, table, exit semantics"
```

---

### Task 7: `doctor` gh-backed checks + `_cmd_doctor` wiring

**Files:**
- Modify: `adi_lg_plugins/hw_ci/doctor.py` (gh wrapper + repo-var/runner-scope checks + `run_doctor`)
- Modify: `adi_lg_plugins/hw_ci/cli.py` (`_cmd_doctor` + subparser)
- Test: `tests/hw_ci/test_doctor_gh.py` (new)

**Interfaces:**
- Consumes: Task 6's `CheckResult`/checks.
- Produces:
  - `REQUIRED_VARS: dict[str, list[str]]` keyed by mode.
  - `check_repo_vars(repo, mode, *, gh=run_gh) -> CheckResult`
  - `check_runner_scope(repo, labels, *, gh=run_gh) -> CheckResult`
  - `run_gh(args: list[str]) -> tuple[int, str]` (returns `(returncode, stdout)`; `(127, "")` if `gh` absent)
  - `run_doctor(args) -> int` and CLI `adi-lg-hw-ci doctor --mode … --coord … [--repo …] [--test-root|--manifest|--board-map …] [--runner-label …]`.

- [ ] **Step 1: Write the failing test** — create `tests/hw_ci/test_doctor_gh.py`:

```python
from adi_lg_plugins.hw_ci import doctor
from adi_lg_plugins.hw_ci.doctor import FAIL, PASS, SKIP


def test_repo_vars_skip_when_gh_absent():
    res = doctor.check_repo_vars("o/r", "uri", gh=lambda args: (127, ""))
    assert res.status == SKIP


def test_repo_vars_pass_when_all_present():
    out = "LG_COORDINATOR\nHW_REQUEST_RUNNER\nHW_PREFLIGHT_RUNNER\n"
    res = doctor.check_repo_vars("o/r", "uri", gh=lambda args: (0, out))
    assert res.status == PASS


def test_repo_vars_fail_when_missing():
    out = "LG_COORDINATOR\nHW_REQUEST_RUNNER\n"  # missing HW_PREFLIGHT_RUNNER
    res = doctor.check_repo_vars("o/r", "uri", gh=lambda args: (0, out))
    assert res.status == FAIL
    assert "HW_PREFLIGHT_RUNNER" in res.detail


def test_matlab_requires_matlab_bin():
    out = "LG_COORDINATOR\nHW_REQUEST_RUNNER\nHW_PREFLIGHT_RUNNER\n"
    res = doctor.check_repo_vars("o/r", "matlab", gh=lambda args: (0, out))
    assert res.status == FAIL and "MATLAB_BIN" in res.detail


def test_runner_scope_pass():
    out = '{"runners":[{"labels":[{"name":"hw-lab"}]}]}'
    res = doctor.check_runner_scope("o/r", ["hw-lab"], gh=lambda args: (0, out))
    assert res.status == PASS


def test_runner_scope_fail_missing_label():
    out = '{"runners":[{"labels":[{"name":"other"}]}]}'
    res = doctor.check_runner_scope("o/r", ["hw-lab"], gh=lambda args: (0, out))
    assert res.status == FAIL
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_doctor_gh.py -v`
Expected: FAIL — `AttributeError: module … has no attribute 'check_repo_vars'`.

- [ ] **Step 3: Append the gh layer to `adi_lg_plugins/hw_ci/doctor.py`:**

```python
import json
import shutil
import subprocess

REQUIRED_VARS = {
    "uri": ["LG_COORDINATOR", "HW_REQUEST_RUNNER", "HW_PREFLIGHT_RUNNER"],
    "flash": ["LG_COORDINATOR", "HW_REQUEST_RUNNER", "HW_PREFLIGHT_RUNNER"],
    "matlab": ["LG_COORDINATOR", "HW_REQUEST_RUNNER", "HW_PREFLIGHT_RUNNER", "MATLAB_BIN"],
}


def run_gh(args: list[str]) -> tuple[int, str]:
    """Run ``gh <args>``; return (returncode, stdout). (127, "") if gh is absent."""
    if shutil.which("gh") is None:
        return (127, "")
    try:
        proc = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=30, check=False
        )
        return (proc.returncode, proc.stdout)
    except (OSError, subprocess.SubprocessError):
        return (127, "")


def check_repo_vars(repo: str, mode: str, *, gh=run_gh) -> CheckResult:
    rc, out = gh(["variable", "list", "--repo", repo])
    if rc != 0:
        return CheckResult("repo-vars", SKIP, "gh unavailable/unauthenticated")
    present = {line.split("\t", 1)[0].split()[0] for line in out.splitlines() if line.strip()}
    missing = [v for v in REQUIRED_VARS[mode] if v not in present]
    if missing:
        return CheckResult("repo-vars", FAIL, f"missing: {', '.join(missing)}")
    return CheckResult("repo-vars", PASS, "all required vars set")


def check_runner_scope(repo: str, labels: list[str], *, gh=run_gh) -> CheckResult:
    rc, out = gh(["api", f"/repos/{repo}/actions/runners"])
    if rc != 0:
        return CheckResult("runner-scope", SKIP, "gh unavailable/unauthenticated")
    try:
        runners = json.loads(out).get("runners", [])
    except (ValueError, AttributeError):
        return CheckResult("runner-scope", SKIP, "could not parse gh runner list")
    have = {lbl["name"] for r in runners for lbl in r.get("labels", [])}
    missing = [lbl for lbl in labels if lbl and lbl not in have]
    if missing:
        return CheckResult("runner-scope", FAIL, f"no runner labelled: {', '.join(missing)}")
    return CheckResult("runner-scope", PASS, f"runner(s) for: {', '.join(sorted(have & set(labels)))}")


def _infer_repo() -> str | None:
    rc, out = run_gh(["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])
    return out.strip() if rc == 0 and out.strip() else None


def run_doctor(args) -> int:
    from . import coordinator as coord_mod

    coord = coord_mod.resolve_coordinator(args.coord)
    coord_mod.warn_if_rest_port(coord)
    repo = args.repo or _infer_repo()
    fallback = args.runner_label or ""

    results = [
        check_discovery(
            args.mode, coord=coord, test_root=args.test_root, manifest=args.manifest,
            board_map=args.board_map, fallback_runner=fallback,
        ),
        check_pin(),
    ]
    if repo:
        results.append(check_repo_vars(repo, args.mode))
        results.append(check_runner_scope(repo, ["HW_REQUEST_RUNNER", "HW_PREFLIGHT_RUNNER"]))
    else:
        results.append(CheckResult("repo-vars", SKIP, "no --repo and gh could not infer it"))
        results.append(CheckResult("runner-scope", SKIP, "no --repo and gh could not infer it"))

    import sys

    print(format_table(results), file=sys.stderr)
    banner = skipped_banner(results)
    if banner:
        print(f"# {banner}", file=sys.stderr)
    return exit_code(results)
```

> Note: `check_runner_scope` is given the literal var *names* as a placeholder set in `run_doctor`; the actual runner *labels* come from the repo vars' values when available — keeping this check label-name-based is the documented best-effort (full value resolution is a future refinement). The unit tests pin the label-matching logic.

- [ ] **Step 4: Wire `_cmd_doctor` + subparser** in `adi_lg_plugins/hw_ci/cli.py`. Add the command (after `_cmd_lint_markers`):

```python
def _cmd_doctor(args: argparse.Namespace) -> int:
    from .doctor import run_doctor

    return run_doctor(args)
```

Register the subparser (after the `lint-markers` parser, before `request-matrix`):

```python
    pdoc = sub.add_parser(
        "doctor", help="validate the whole onboarding chain in one pass"
    )
    pdoc.add_argument("--mode", choices=["uri", "flash", "matlab"], required=True)
    pdoc.add_argument("--coord", default=None, help="coordinator host:port (default: $LG_COORDINATOR)")
    pdoc.add_argument("--repo", default=None, help="owner/name (default: infer via gh)")
    pdoc.add_argument("--test-root", default=None, help="[uri] consumer test directory")
    pdoc.add_argument("--manifest", default=None, help="[flash] projects.yaml path")
    pdoc.add_argument("--board-map", default=None, help="[matlab] board_map.yaml path")
    pdoc.add_argument("--runner-label", default=None, help="fallback runner label (vars.HW_REQUEST_RUNNER)")
    pdoc.set_defaults(func=_cmd_doctor)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_doctor_gh.py tests/hw_ci/test_doctor_core.py -v && .venv/bin/ruff check adi_lg_plugins/hw_ci/doctor.py adi_lg_plugins/hw_ci/cli.py`
Expected: tests PASS; ruff clean. (`run_doctor` itself is exercised end-to-end in the final manual check; its building blocks are unit-tested.)

- [ ] **Step 6: Add the test to CI** — `.github/workflows/tests.yml`, after Task 6's line:

```
          tests/hw_ci/test_doctor_gh.py \
```

- [ ] **Step 7: Commit**

```bash
git add adi_lg_plugins/hw_ci/doctor.py adi_lg_plugins/hw_ci/cli.py tests/hw_ci/test_doctor_gh.py .github/workflows/tests.yml
git commit -m "feat(hw_ci): doctor gh-backed repo-var/runner checks + adi-lg-hw-ci doctor command"
```

---

### Task 8: Pin-consistency lint (`pin_lint` + nox `lint_pins`)

**Files:**
- Create: `adi_lg_plugins/hw_ci/pin_lint.py`
- Modify: `noxfile.py` (`lint_pins` session)
- Modify: `.github/workflows/tests.yml` (run the new test)
- Test: `tests/hw_ci/test_pin_lint.py` (new)

**Interfaces:**
- Consumes: `_release.RECOMMENDED_PIN`.
- Produces: `find_consumer_pin_violations(paths: list[str | Path], recommended: str) -> list[tuple[str, int, str]]` — `(file, lineno, found)` for any consumer-facing `tfcollins/labgrid-plugins/.github/workflows/…@<ref>` where `<ref>` != `recommended` (includes `@main`). `CONSUMER_PIN_PATHS: list[str]` — the non-deprecated consumer-facing files to scan.

- [ ] **Step 1: Write the failing test** — create `tests/hw_ci/test_pin_lint.py`:

```python
from adi_lg_plugins.hw_ci.pin_lint import find_consumer_pin_violations


def test_flags_stale_and_main(tmp_path):
    f = tmp_path / "x.yml"
    f.write_text(
        "uses: tfcollins/labgrid-plugins/.github/workflows/hw-request.yml@v3.4\n"
        "uses: tfcollins/labgrid-plugins/.github/workflows/noos-hw-request.yml@main\n",
        encoding="utf-8",
    )
    viol = find_consumer_pin_violations([f], "v3.5")
    assert len(viol) == 2
    founds = {v[2] for v in viol}
    assert founds == {"v3.4", "main"}


def test_clean_when_matches(tmp_path):
    f = tmp_path / "x.yml"
    f.write_text(
        "uses: tfcollins/labgrid-plugins/.github/workflows/hw-request.yml@v3.5\n",
        encoding="utf-8",
    )
    assert find_consumer_pin_violations([f], "v3.5") == []


def test_ignores_other_refs(tmp_path):
    f = tmp_path / "x.yml"
    f.write_text("uses: actions/checkout@v4\n", encoding="utf-8")
    assert find_consumer_pin_violations([f], "v3.5") == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_pin_lint.py -v`
Expected: FAIL — `ModuleNotFoundError: adi_lg_plugins.hw_ci.pin_lint`.

- [ ] **Step 3: Create `adi_lg_plugins/hw_ci/pin_lint.py`:**

```python
"""Pin-hygiene lints over consumer-facing examples + the release workflows.

Pure functions (file contents -> violations) so they are directly testable and
reusable by both the ``lint_pins`` nox session and the release guard.
"""

from __future__ import annotations

import re
from pathlib import Path

# Consumer-facing files that must pin to RECOMMENDED_PIN (non-deprecated only —
# the hw-matrix/v1/v2 docs legitimately reference older refs and are excluded).
CONSUMER_PIN_PATHS = [
    "docs/source/onboarding-templates/hw-request-uri.yml",
    "docs/source/onboarding-templates/noos-hw-request-flash.yml",
    "docs/source/onboarding-templates/matlab-hw-request.yml",
    "docs/source/onboarding-templates/AGENTS-consumer-stub.md",
    "docs/source/user-guide/onboarding-a-consumer-repo.rst",
    "docs/source/user-guide/hw-request.rst",
    "AGENTS.md",
]

_CONSUMER_REF = re.compile(r"tfcollins/labgrid-plugins/\.github/workflows/[\w.-]+@(\S+)")
_SELF_REF = re.compile(
    r"tfcollins/labgrid-plugins/\.github/(?:workflows|actions)/[\w./-]+@(main)\b"
    r"|git\+https://github\.com/tfcollins/labgrid-plugins@(main)\b"
)


def find_consumer_pin_violations(
    paths, recommended: str
) -> list[tuple[str, int, str]]:
    """``(file, lineno, found_ref)`` for each consumer-facing reusable-workflow
    reference whose pin != ``recommended`` (``@main`` counts as a violation)."""
    out: list[tuple[str, int, str]] = []
    for p in paths:
        p = Path(p)
        if not p.is_file():
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for m in _CONSUMER_REF.finditer(line):
                ref = m.group(1).rstrip('"').rstrip("'").rstrip("`")
                if ref != recommended:
                    out.append((str(p), i, ref))
    return out


def find_main_self_refs(paths) -> list[tuple[str, int]]:
    """``(file, lineno)`` for any internal ``@main`` self-reference (action ``uses:``
    or ``git+https…@main`` install) — used by the release guard to prove
    ``pin-release-refs.sh`` ran before tagging. MUST NOT be run on ``main``."""
    out: list[tuple[str, int]] = []
    for p in paths:
        p = Path(p)
        if not p.is_file():
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if _SELF_REF.search(line):
                out.append((str(p), i))
    return out
```

- [ ] **Step 4: Add the `lint_pins` nox session** to `noxfile.py` (after the `docs` session):

```python
@nox.session(venv_backend="none")
def lint_pins(session):
    """Fail if any consumer-facing example pins != RECOMMENDED_PIN (or uses @main)."""
    from adi_lg_plugins.hw_ci._release import RECOMMENDED_PIN
    from adi_lg_plugins.hw_ci.pin_lint import CONSUMER_PIN_PATHS, find_consumer_pin_violations

    violations = find_consumer_pin_violations(CONSUMER_PIN_PATHS, RECOMMENDED_PIN)
    for f, line, found in violations:
        session.log(f"{f}:{line}: consumer pin @{found} != @{RECOMMENDED_PIN}")
    if violations:
        session.error(f"{len(violations)} stale consumer pin(s)")
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_pin_lint.py -v && .venv/bin/ruff check adi_lg_plugins/hw_ci/pin_lint.py noxfile.py`
Expected: tests PASS; ruff clean.

- [ ] **Step 6: Add the test to CI** — `.github/workflows/tests.yml`, after Task 7's line:

```
          tests/hw_ci/test_pin_lint.py \
```

- [ ] **Step 7: Commit**

```bash
git add adi_lg_plugins/hw_ci/pin_lint.py noxfile.py tests/hw_ci/test_pin_lint.py .github/workflows/tests.yml
git commit -m "feat(hw_ci): pin-consistency lint (consumer examples vs RECOMMENDED_PIN)"
```

---

### Task 9: Release guard (`find_main_self_refs` + nox `release_guard` + RELEASING.md)

**Files:**
- Modify: `noxfile.py` (`release_guard` session)
- Modify: `RELEASING.md` (add the guard step)
- Test: `tests/hw_ci/test_release_guard.py` (new)

**Interfaces:**
- Consumes: `pin_lint.find_main_self_refs` (Task 8).
- Produces: `nox -s release_guard` — fails if any family workflow still has an `@main` self-ref (proves `pin-release-refs.sh` ran). Release-recipe / `release/*` only — NOT for `main`.

- [ ] **Step 1: Write the failing test** — create `tests/hw_ci/test_release_guard.py`:

```python
from adi_lg_plugins.hw_ci.pin_lint import find_main_self_refs


def test_detects_main_action_ref(tmp_path):
    f = tmp_path / "wf.yml"
    f.write_text(
        "      - uses: tfcollins/labgrid-plugins/.github/actions/setup-uv-venv@main\n",
        encoding="utf-8",
    )
    assert find_main_self_refs([f]) == [(str(f), 1)]


def test_detects_main_git_install(tmp_path):
    f = tmp_path / "wf.yml"
    f.write_text(
        '          "adi-labgrid-plugins @ git+https://github.com/tfcollins/labgrid-plugins@main"\n',
        encoding="utf-8",
    )
    assert len(find_main_self_refs([f])) == 1


def test_clean_when_pinned(tmp_path):
    f = tmp_path / "wf.yml"
    f.write_text(
        "      - uses: tfcollins/labgrid-plugins/.github/actions/setup-uv-venv@v3.5\n",
        encoding="utf-8",
    )
    assert find_main_self_refs([f]) == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_release_guard.py -v`
Expected: FAIL — `ImportError: cannot import name 'find_main_self_refs'` IF Task 8 not yet applied; otherwise it should already PASS (the function exists). If it passes immediately, that confirms Task 8's function — proceed.

- [ ] **Step 3: Add the `release_guard` nox session** to `noxfile.py` (after `lint_pins`):

```python
@nox.session(venv_backend="none")
def release_guard(session):
    """RELEASE-ONLY. Fail if any hw-request-family workflow still has an @main
    self-ref (i.e. scripts/pin-release-refs.sh was not run). MUST NOT run on
    main — main keeps @main by design."""
    from adi_lg_plugins.hw_ci.pin_lint import find_main_self_refs

    family = [
        ".github/workflows/hw-request.yml",
        ".github/workflows/noos-hw-request.yml",
        ".github/workflows/matlab-hw-request.yml",
    ]
    refs = find_main_self_refs(family)
    for f, line in refs:
        session.log(f"{f}:{line}: internal @main self-ref — run scripts/pin-release-refs.sh")
    if refs:
        session.error(f"{len(refs)} unpinned @main self-ref(s) — not release-ready")
```

- [ ] **Step 4: Document the guard in `RELEASING.md`.** After the `scripts/pin-release-refs.sh v<N>` line (step 2), add a new verification step:

```markdown
2b. `nox -s release_guard` — verify no `@main` self-refs remain (do NOT run on main).
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/hw_ci/test_release_guard.py -v && .venv/bin/ruff check noxfile.py`
Expected: PASS; ruff clean.

- [ ] **Step 6: Add the test to CI** — `.github/workflows/tests.yml`, after Task 8's line:

```
          tests/hw_ci/test_release_guard.py \
```

- [ ] **Step 7: Commit**

```bash
git add noxfile.py RELEASING.md tests/hw_ci/test_release_guard.py .github/workflows/tests.yml
git commit -m "feat(hw_ci): release guard — fail on @main self-refs at release time"
```

---

## Self-Review

**Spec coverage (Phase 2):**
- WS-B `doctor` → Tasks 6 + 7 (discovery/pin core; gh repo-var/runner-scope + CLI). ✓
- WS-B `lint-markers` + `markers.collect_marker_rejections` → Tasks 2, 3. ✓
- WS-B preflight var-guard → Task 5. ✓
- WS-B infra annotations → Task 4. ✓
- WS-D `_release.RECOMMENDED_PIN` + conf.py substitution → Task 1. ✓
- WS-D pin-consistency lint → Task 8; release guard → Task 9. ✓
- Spec ordering honored: Task 1 (`RECOMMENDED_PIN`) precedes Tasks 6/7 (doctor pin check) and 8 (pin-lint). ✓
- Deferred to Phase 3 (NOT here): packaged templates, `init`, board-map template.

**Placeholder scan:** no TBD/TODO. The one prose "future refinement" note (runner-scope label resolution) is an explicit, bounded scope statement with the behavior fully specified + tested, not a placeholder. Every code step shows complete code.

**Type/name consistency:** `CheckResult(name,status,detail)` + `PASS/FAIL/SKIP` constants used identically across Tasks 6/7 and tests. `collect_marker_rejections` signature/return matches across Tasks 2/3. `find_consumer_pin_violations`/`find_main_self_refs` signatures match across Tasks 8/9. `RECOMMENDED_PIN` import path identical everywhere.

**Notes for reviewers:** Tasks 1–9 each append a line to the `tests.yml` CI file list — if executed out of order, just ensure each new test file ends up listed. Task 9 Step 2 may PASS immediately (its function ships in Task 8) — that's expected; proceed to add the session + RELEASING note. `run_doctor`'s end-to-end path (live coordinator + `gh`) is validated manually in the final review, not unit-tested (its building blocks are).
