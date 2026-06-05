"""``adi-lg-hw-ci`` command line entry point.

Subcommands consumed by the v2 reusable workflow:

* ``discover``           — query coordinator + harvest pytest markers +
                           emit the matrix include list as JSON (stdout)
                           plus a human-readable summary (stderr).
* ``render-env``         — render the labgrid env yaml for a single place
                           to a file. Run inside each matrix shard before
                           the shard's pytest invocation.
* ``resolve-resources``  — read UART + JTAG facts off a booted place and
                           emit ``KEY=VALUE`` lines for a bash / non-Python
                           test driver to consume (see
                           :doc:`/user-guide/hw-ci-bash`).

The subcommands wrap the typed surface in
:mod:`adi_lg_plugins.hw_ci.{coordinator,intersect,render_env,resolve}` so
the same logic is unit-tested without a process boundary.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import coordinator as coord_mod
from . import markers as markers_mod
from . import render_env as render_mod
from .intersect import intersect
from .schema import KNOWN_STRATEGIES


def _cmd_discover(args: argparse.Namespace) -> int:
    coord = coord_mod.resolve_coordinator(args.coord)
    places, skipped = coord_mod.list_live_places(
        coord,
        timeout=args.timeout,
        force_cli=args.force_cli,
    )

    if skipped:
        print(
            f"# {len(skipped)} place(s) skipped at validation:",
            file=sys.stderr,
        )
        for name, reason in skipped:
            print(f"#   - {name}: {reason}", file=sys.stderr)

    markers = markers_mod.harvest_markers(
        args.test_root,
        marker=args.marker,
    )
    if not markers:
        print(
            "# no tests with the marker filter — empty matrix",
            file=sys.stderr,
        )

    entries = intersect(markers, places, skip_acquired=not args.include_acquired)
    matrix = {"include": [e.as_matrix_dict() for e in entries]}

    if args.github_output:
        gh_out = os.environ.get("GITHUB_OUTPUT")
        if not gh_out:
            print(
                "warning: --github-output given but $GITHUB_OUTPUT is unset",
                file=sys.stderr,
            )
        else:
            with open(gh_out, "a", encoding="utf-8") as f:
                f.write(f"matrix={json.dumps(matrix)}\n")
                f.write(f"count={len(entries)}\n")

    # stdout: always emit the JSON (so the CLI works outside GHA)
    print(json.dumps(matrix, indent=2))

    # Human-readable summary on stderr
    print(
        f"# discovery: {len(places)} live place(s), "
        f"{len(markers)} marked test(s), "
        f"{len(entries)} matrix entries",
        file=sys.stderr,
    )
    for e in entries:
        print(
            f"#   - {e.place}: {e.daughter_board} on {e.carrier} "
            f"({e.boot_strategy}) [{len(e.tests)} test(s)]",
            file=sys.stderr,
        )
    if not entries and markers and places:
        wanted = sorted({h for spec in markers.values() for h in spec.iio_hardware})
        offered = sorted({p.daughter_board for p in places})
        print(
            f"# project wants {wanted}; coordinator has {offered} — no overlap right now",
            file=sys.stderr,
        )
    return 0


def _emit_matrix(
    matrix: dict,
    *,
    count: int,
    missing: list[str],
    kind: str,
    github_output: bool,
) -> None:
    """Write the matrix to $GITHUB_OUTPUT (when asked), print it to stdout, and
    emit a ``::warning::`` annotation per missing item. Shared by request-matrix
    and noos-matrix so the GH-output + annotation tail lives in one place."""
    if github_output:
        gh_out = os.environ.get("GITHUB_OUTPUT")
        if gh_out:
            with open(gh_out, "a", encoding="utf-8") as f:
                f.write(f"matrix={json.dumps(matrix)}\n")
                f.write(f"count={count}\n")
        else:
            print("warning: --github-output given but $GITHUB_OUTPUT is unset", file=sys.stderr)

    print(json.dumps(matrix, indent=2))
    for item in missing:
        print(
            f"::warning::{kind}: {item!r} is wanted but no live board matches on the "
            f"coordinator — skipping",
            file=sys.stderr,
        )


def _cmd_request_matrix(args: argparse.Namespace) -> int:
    """Emit a part-keyed matrix: wanted parts (from markers) that have a live
    board (per GET /api/match). Missing parts are surfaced as GH annotations."""
    from adi_lg_plugins.request import match_client

    from .coordinator import _resolve_api
    from .request_matrix import build_request_matrix

    coord = coord_mod.resolve_coordinator(args.coord)
    # LG_COORDINATOR is the gRPC coordinator (e.g. host:20408); the REST API
    # /api/match lives on host:8000 — derive it the same way request() does.
    api = _resolve_api(coord)
    markers = markers_mod.harvest_markers(args.test_root, marker=args.marker)
    wanted = sorted({h for spec in markers.values() for h in spec.iio_hardware})

    def probe(part: str):
        try:
            return match_client.get_match(api, part=part)
        except Exception as e:  # noqa: BLE001 - a probe failure must not crash discovery
            print(f"# /api/match probe failed for {part!r}: {e}", file=sys.stderr)
            return None

    result = build_request_matrix(wanted, probe)
    # Each leg names the runner label its board is co-located with; the
    # workflow falls back to its default runner-label when this is empty.
    matrix = {"include": [{"part": leg.part, "runner": leg.runner or ""} for leg in result.parts]}

    _emit_matrix(
        matrix,
        count=len(result.parts),
        missing=result.missing,
        kind="request-matrix",
        github_output=args.github_output,
    )
    print(
        f"# request-matrix: {len(wanted)} wanted part(s), {len(result.parts)} available",
        file=sys.stderr,
    )
    return 0


def _cmd_noos_matrix(args: argparse.Namespace) -> int:
    """Emit a no-os project matrix: manifest projects that map to a live
    flash-capable board (per GET /api/match?mode=flash). Each leg carries the
    project to build, the part to request, the carrier, and the runner."""
    from adi_lg_plugins.request import match_client

    from .coordinator import _resolve_api
    from .noos_manifest import build_noos_matrix, load_noos_manifest

    coord = coord_mod.resolve_coordinator(args.coord)
    # LG_COORDINATOR is the gRPC coordinator; /api/match is the REST API on :8000.
    api = _resolve_api(coord)
    projects = load_noos_manifest(args.manifest)

    def probe(part: str, carrier: str):
        try:
            return match_client.get_match(api, part=part, carrier=carrier, mode="flash")
        except Exception as e:  # noqa: BLE001 - a probe failure must not crash discovery
            print(f"# /api/match probe failed for {part!r}/{carrier!r}: {e}", file=sys.stderr)
            return None

    legs, missing = build_noos_matrix(projects, probe)
    matrix = {
        "include": [
            {
                "part": leg.part,
                "noos_project": leg.noos_project,
                "carrier": leg.carrier,
                "runner": leg.runner or "",
                "board": leg.board or "",
                "release": leg.release or "",
                "validate_banner": leg.validate_banner,
                "build_vars": leg.build_vars,
            }
            for leg in legs
        ]
    }

    _emit_matrix(
        matrix,
        count=len(legs),
        missing=missing,
        kind="noos-matrix",
        github_output=args.github_output,
    )
    print(
        f"# noos-matrix: {len(projects)} project(s), {len(legs)} buildable on a live board",
        file=sys.stderr,
    )
    return 0


def _cmd_render_env(args: argparse.Namespace) -> int:
    coord = coord_mod.resolve_coordinator(args.coord)
    places, _skipped = coord_mod.list_live_places(
        coord,
        force_cli=args.force_cli,
    )
    match = next((p for p in places if p.name == args.place), None)
    if match is None:
        print(
            f"error: place {args.place!r} not found (or invalid tags). "
            f"Live places: {[p.name for p in places]}",
            file=sys.stderr,
        )
        return 2
    out_path = Path(args.out)
    render_mod.render_env_to(match, out_path)
    print(f"wrote {out_path}", file=sys.stderr)
    return 0


def _cmd_resolve_resources(args: argparse.Namespace) -> int:
    from . import resolve as resolve_mod

    resolved = resolve_mod.resolve_from_env(args.config, target_name=args.target)
    out_text = resolve_mod.render_github_output(resolved)

    if args.out == "github":
        gh_out = os.environ.get("GITHUB_OUTPUT")
        if not gh_out:
            print(
                "warning: --out github given but $GITHUB_OUTPUT is unset",
                file=sys.stderr,
            )
        else:
            with open(gh_out, "a", encoding="utf-8") as f:
                f.write(out_text)

    # stdout: always emit the KEY=VALUE lines (so the CLI works outside GHA)
    print(out_text, end="")
    return 0


def _cmd_list_strategies(_args: argparse.Namespace) -> int:
    strats = sorted(KNOWN_STRATEGIES)
    templates = render_mod.list_strategy_templates()
    print(json.dumps({"strategies": strats, "templates": templates}, indent=2))
    missing = sorted(set(strats) - set(templates))
    if missing:
        print(
            "# templates missing for strategies: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="adi-lg-hw-ci",
        description="Discovery-driven HW-CI matrix tooling.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pd = sub.add_parser("discover", help="emit matrix include list")
    pd.add_argument(
        "--coord",
        default=None,
        help="coordinator URL (default: $LG_COORDINATOR / $ADI_LG_COORDINATOR)",
    )
    pd.add_argument("--test-root", required=True, help="caller repo root to collect tests from")
    pd.add_argument("--marker", default="iio_hardware", help="top-level pytest marker to harvest")
    # --pytest-bin retained as a deprecated no-op so existing callers
    # don't break; AST harvest doesn't shell out to pytest.
    pd.add_argument("--pytest-bin", default=None, help=argparse.SUPPRESS)
    pd.add_argument("--timeout", type=float, default=15.0)
    pd.add_argument(
        "--force-cli", action="store_true", help="skip REST, go straight to labgrid-client"
    )
    pd.add_argument(
        "--include-acquired",
        action="store_true",
        help="(debug) include acquired places in the matrix",
    )
    pd.add_argument(
        "--github-output",
        action="store_true",
        help="also append matrix=… count=… to $GITHUB_OUTPUT",
    )
    pd.set_defaults(func=_cmd_discover)

    pr = sub.add_parser("render-env", help="render env yaml for a place from its tags")
    pr.add_argument("--coord", default=None)
    pr.add_argument("--place", required=True)
    pr.add_argument("--out", required=True)
    pr.add_argument("--force-cli", action="store_true")
    pr.set_defaults(func=_cmd_render_env)

    prr = sub.add_parser(
        "resolve-resources",
        help="print UART/JTAG resource facts for a booted place",
    )
    prr.add_argument("--config", required=True, help="rendered env yaml (from render-env)")
    prr.add_argument("--target", default="main", help="target name in the env yaml")
    prr.add_argument(
        "--out",
        choices=["stdout", "github"],
        default="stdout",
        help="github = also append KEY=VALUE lines to $GITHUB_OUTPUT",
    )
    prr.set_defaults(func=_cmd_resolve_resources)

    pl = sub.add_parser(
        "list-strategies", help="dump known boot-strategy class names + which have render templates"
    )
    pl.set_defaults(func=_cmd_list_strategies)

    pm = sub.add_parser(
        "request-matrix", help="emit a part-keyed matrix for the hw-request workflow"
    )
    pm.add_argument("--test-root", required=True, help="path to the consumer's test directory")
    pm.add_argument("--marker", default="iio_hardware", help="hardware-gating marker name")
    pm.add_argument(
        "--coord", default=None, help="coordinator host:port (default: $LG_COORDINATOR)"
    )
    pm.add_argument(
        "--github-output",
        action="store_true",
        help="also write matrix=/count= to $GITHUB_OUTPUT",
    )
    pm.set_defaults(func=_cmd_request_matrix)

    pn = sub.add_parser(
        "noos-matrix",
        help="emit a no-os project matrix (manifest ∩ live flash-capable boards)",
    )
    pn.add_argument("--manifest", required=True, help="path to the no-os hw-ci projects.yaml")
    pn.add_argument(
        "--coord", default=None, help="coordinator host:port (default: $LG_COORDINATOR)"
    )
    pn.add_argument(
        "--github-output",
        action="store_true",
        help="also write matrix=/count= to $GITHUB_OUTPUT",
    )
    pn.set_defaults(func=_cmd_noos_matrix)

    ns = p.parse_args(argv)
    return ns.func(ns)


if __name__ == "__main__":
    sys.exit(main())
