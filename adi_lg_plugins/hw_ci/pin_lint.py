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
    paths: list[str | Path], recommended: str
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
                ref = m.group(1).rstrip("\"'`).,;:")
                if ref != recommended:
                    out.append((str(p), i, ref))
    return out


def find_main_self_refs(paths: list[str | Path]) -> list[tuple[str, int]]:
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
