"""``adi-lg-hw-ci`` command line entry point.

Two subcommands consumed by the v2 reusable workflow:

* ``discover``    — query coordinator + harvest pytest markers + emit
                    the matrix include list as JSON (stdout) plus a
                    human-readable summary (stderr).
* ``render-env``  — render the labgrid env yaml for a single place to
                    a file. Run inside each matrix shard before the
                    shard's pytest invocation.

Both subcommands wrap the typed surface in
:mod:`adi_lg_plugins.hw_ci.{coordinator,intersect,render_env}` so the
same logic is unit-tested without a process boundary.
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
        pytest_bin=args.pytest_bin,
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
            f"# project wants {wanted}; coordinator has {offered} "
            f"— no overlap right now",
            file=sys.stderr,
        )
    return 0


def _cmd_render_env(args: argparse.Namespace) -> int:
    coord = coord_mod.resolve_coordinator(args.coord)
    places, _skipped = coord_mod.list_live_places(
        coord, force_cli=args.force_cli,
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


def _cmd_list_strategies(_args: argparse.Namespace) -> int:
    strats = sorted(KNOWN_STRATEGIES)
    templates = render_mod.list_strategy_templates()
    print(
        json.dumps({"strategies": strats, "templates": templates}, indent=2)
    )
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
    pd.add_argument("--coord", default=None,
                    help="coordinator URL (default: $LG_COORDINATOR / "
                         "$ADI_LG_COORDINATOR)")
    pd.add_argument("--test-root", required=True,
                    help="caller repo root to collect tests from")
    pd.add_argument("--marker", default="iio_hardware",
                    help="top-level pytest marker to harvest")
    pd.add_argument("--pytest-bin", default=None)
    pd.add_argument("--timeout", type=float, default=15.0)
    pd.add_argument("--force-cli", action="store_true",
                    help="skip REST, go straight to labgrid-client")
    pd.add_argument("--include-acquired", action="store_true",
                    help="(debug) include acquired places in the matrix")
    pd.add_argument("--github-output", action="store_true",
                    help="also append matrix=… count=… to $GITHUB_OUTPUT")
    pd.set_defaults(func=_cmd_discover)

    pr = sub.add_parser("render-env",
                        help="render env yaml for a place from its tags")
    pr.add_argument("--coord", default=None)
    pr.add_argument("--place", required=True)
    pr.add_argument("--out", required=True)
    pr.add_argument("--force-cli", action="store_true")
    pr.set_defaults(func=_cmd_render_env)

    pl = sub.add_parser("list-strategies",
                        help="dump known boot-strategy class names + "
                             "which have render templates")
    pl.set_defaults(func=_cmd_list_strategies)

    ns = p.parse_args(argv)
    return ns.func(ns)


if __name__ == "__main__":
    sys.exit(main())
