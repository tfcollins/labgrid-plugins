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

# Rewrite a labgrid-plugins pin to RECOMMENDED_PIN. _LG_PIN covers the workflow `uses:`
# AND the `git+https://...labgrid-plugins.git@v..` install (the `[\w./-]*?` consumes `.git`).
# _YML_PIN additionally catches the consumer-stub's bracketed `<...>.yml@v..` form, which the
# first pattern can't (the `<...>` contains spaces/pipes). Both are anchored on
# `labgrid-plugins` so a foreign `.yml@v..` ref (another org's pinned workflow) is left alone.
_LG_PIN = re.compile(r"(tfcollins/labgrid-plugins[\w./-]*?)@v[\w.]+")
_YML_PIN = re.compile(r"(labgrid-plugins[^@\n]*?\.yml)@v[\w.]+")


def _read(name: str) -> str:
    return (resources.files(_ANCHOR) / name).read_text(encoding="utf-8")


def _rewrite_pins(text: str) -> str:
    """Pin every labgrid-plugins workflow/install/stub reference to RECOMMENDED_PIN."""
    text = _LG_PIN.sub(rf"\1@{RECOMMENDED_PIN}", text)
    return _YML_PIN.sub(rf"\1@{RECOMMENDED_PIN}", text)


def render_template(
    name: str, *, test_root: str | None = None, install_cmd: str | None = None
) -> str:
    text = _rewrite_pins(_read(name))
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
