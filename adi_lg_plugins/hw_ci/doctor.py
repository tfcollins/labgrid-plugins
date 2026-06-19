"""One-pass onboarding validator backing ``adi-lg-hw-ci doctor``.

Each check returns a :class:`CheckResult`; external dependencies (coordinator
HTTP, ``gh``) are injected so the logic is unit-tested without a process
boundary. The gh-dependent checks live in this module too (Task 7) but degrade
to SKIP when ``gh`` is unavailable.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
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
            mode,
            coord=coord,
            test_root=test_root,
            manifest=manifest,
            board_map=board_map,
            probe=probe,
            lister=lister,
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
            "discovery",
            FAIL,
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
    found_any = False
    for f in sorted(wf_dir.glob("*.yml")) + sorted(wf_dir.glob("*.yaml")):
        for m in pat.finditer(f.read_text(encoding="utf-8")):
            found_any = True
            if m.group(1) != RECOMMENDED_PIN:
                stale.append(f"{f.name}@{m.group(1)}")
    if not found_any:
        return CheckResult("pin", SKIP, "no labgrid-plugins workflow pins found")
    if stale:
        return CheckResult("pin", FAIL, f"pins != {RECOMMENDED_PIN}: {', '.join(stale)}")
    return CheckResult("pin", PASS, f"pinned @{RECOMMENDED_PIN}")


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
    labels = [lbl for lbl in labels if lbl]
    if not labels:
        return CheckResult(
            "runner-scope", SKIP, "no runner-label given to verify (pass --runner-label)"
        )
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
    return CheckResult(
        "runner-scope", PASS, f"runner(s) for: {', '.join(sorted(have & set(labels)))}"
    )


def _infer_repo() -> str | None:
    rc, out = run_gh(["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])
    return out.strip() if rc == 0 and out.strip() else None


def run_doctor(args) -> int:
    from . import coordinator as coord_mod

    try:
        coord = coord_mod.resolve_coordinator(args.coord)
        coord_mod.warn_if_rest_port(coord)
    except RuntimeError:
        coord = None
    repo = args.repo or _infer_repo()
    fallback = args.runner_label or ""

    results = []
    if coord is None:
        results.append(
            CheckResult(
                "discovery",
                FAIL,
                "no coordinator — set LG_COORDINATOR (gRPC :20408) or pass --coord",
            )
        )
    else:
        results.append(
            check_discovery(
                args.mode,
                coord=coord,
                test_root=args.test_root,
                manifest=args.manifest,
                board_map=args.board_map,
                fallback_runner=fallback,
            )
        )
    results.append(check_pin())
    if repo:
        results.append(check_repo_vars(repo, args.mode))
        runner_labels = [args.runner_label] if args.runner_label else []
        results.append(check_runner_scope(repo, runner_labels))
    else:
        results.append(CheckResult("repo-vars", SKIP, "no --repo and gh could not infer it"))
        results.append(CheckResult("runner-scope", SKIP, "no --repo and gh could not infer it"))

    print(format_table(results), file=sys.stderr)
    banner = skipped_banner(results)
    if banner:
        print(f"# {banner}", file=sys.stderr)
    return exit_code(results)
