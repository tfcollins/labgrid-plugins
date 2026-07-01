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
    status: str,
    seconds: int,
    message: str = "",
) -> str:
    """Return a JUnit XML string with one testcase for this place's boot.

    ``classname`` groups by carrier (``lab-infra.<carrier>``); ``name`` uniquely
    identifies the board (``<mode>:<part>@<place>``). ``status`` is one of
    ``"pass"``, ``"fail"``, or ``"skip"``:

    * ``"pass"`` — no child element.
    * ``"fail"`` — a ``<failure>`` element carries the collapsed ``message``.
    * ``"skip"`` — a neutral ``<skipped>`` element (contention / board vanished
      between preflight and the leg); a JUnit ``<skipped>`` does not fail the run.
    """
    if status not in ("pass", "fail", "skip"):
        raise ValueError(f"unknown status {status!r}")
    failures = 1 if status == "fail" else 0
    skipped = 1 if status == "skip" else 0
    classname = f"lab-infra.{carrier}" if carrier else "lab-infra"
    name = f"{mode}:{part}@{place}"
    inner = ""
    if status == "fail":
        msg = message or "boot failed"
        inner = f"\n      <failure message={quoteattr(msg)}>{escape(msg)}</failure>\n    "
    elif status == "skip":
        msg = message or "skipped"
        inner = f"\n      <skipped message={quoteattr(msg)}/>\n    "
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<testsuites>\n"
        f'  <testsuite name="infra-boot-smoke" tests="1" failures="{failures}" '
        f'errors="0" skipped="{skipped}" time="{seconds}">\n'
        f"    <testcase classname={quoteattr(classname)} name={quoteattr(name)} "
        f'time="{seconds}">{inner}</testcase>\n'
        "  </testsuite>\n"
        "</testsuites>\n"
    )
