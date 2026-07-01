"""Render a single infra boot-smoke outcome as a one-testcase JUnit document.

The leg runs ``adi-lg request`` (which owns the boot + all failure annotations)
and passes its pass/fail here to produce the JUnit the report + Prism steps
consume. Kept a pure string function so it is unit-tested without a process.
"""

from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr


def render_boot_junit(
    *,
    place: str,
    part: str,
    carrier: str,
    mode: str,
    ok: bool,
    seconds: int,
    message: str = "",
) -> str:
    """Return a JUnit XML string with one testcase for this place's boot.

    ``classname`` groups by carrier (``lab-infra.<carrier>``); ``name`` uniquely
    identifies the board (``<mode>:<part>@<place>``). On failure a ``<failure>``
    element carries the collapsed ``message``.
    """
    failures = 0 if ok else 1
    classname = f"lab-infra.{carrier}" if carrier else "lab-infra"
    name = f"{mode}:{part}@{place}"
    inner = ""
    if not ok:
        msg = message or "boot failed"
        inner = f"\n      <failure message={quoteattr(msg)}>{escape(msg)}</failure>\n    "
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<testsuites>\n"
        f'  <testsuite name="infra-boot-smoke" tests="1" failures="{failures}" '
        f'errors="0" skipped="0" time="{seconds}">\n'
        f"    <testcase classname={quoteattr(classname)} name={quoteattr(name)} "
        f'time="{seconds}">{inner}</testcase>\n'
        "  </testsuite>\n"
        "</testsuites>\n"
    )
