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
