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
from .board_map import build_matlab_matrix, load_board_map
from .build_noos import build_noos
from .intersect import intersect
from .kuiper_xsa import fetch_board_xsa
from .schema import KNOWN_STRATEGIES


def _cmd_discover(args: argparse.Namespace) -> int:
    coord = coord_mod.resolve_coordinator(args.coord)
    coord_mod.warn_if_rest_port(coord)
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
    missing_msg: str = "{item!r} is wanted but no live board matches on the coordinator",
) -> None:
    """Write the matrix to $GITHUB_OUTPUT (when asked), print it to stdout, and
    emit a ``::warning::`` annotation per missing item. Shared by request-matrix,
    noos-matrix, and matlab-matrix so the GH-output + annotation tail lives in
    one place. ``missing_msg`` is a ``str.format`` template receiving ``item``;
    the default covers the wanted-part-missing case — callers whose ``missing``
    items mean something else (e.g. matlab-matrix's live-but-unmapped places)
    must pass a truthful wording."""
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
            f"::warning::{kind}: {missing_msg.format(item=item)} — skipping",
            file=sys.stderr,
        )


def _cmd_request_matrix(args: argparse.Namespace) -> int:
    """Emit a part-keyed matrix: wanted parts (from markers) that have a live
    board (per GET /api/match). Missing parts are surfaced as GH annotations."""
    from adi_lg_plugins.request import match_client

    from .coordinator import _resolve_api
    from .request_matrix import build_request_matrix

    coord = coord_mod.resolve_coordinator(args.coord)
    coord_mod.warn_if_rest_port(coord)
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
    coord_mod.warn_if_rest_port(coord)
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
                "kuiper_xsa_dir": leg.kuiper_xsa_dir or "",
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


def _cmd_matlab_matrix(args: argparse.Namespace) -> int:
    """Emit a MATLAB CI matrix: live places that resolve to a MATLAB board (via the
    consumer's board map). Each leg carries the part/carrier to request + the
    matlab_board to pass to runHWTests. Live places with no board-map entry are
    annotated as skipped (the toolbox has no test entry point for them)."""
    coord = coord_mod.resolve_coordinator(args.coord)
    coord_mod.warn_if_rest_port(coord)
    board_map = load_board_map(args.board_map)
    places, _bad = coord_mod.list_live_places(coord)

    legs, skipped = build_matlab_matrix(places, board_map)
    matrix = {
        "include": [
            {
                "part": leg.part,
                "carrier": leg.carrier,
                "runner": leg.runner or "",
                "matlab_board": leg.matlab_board,
            }
            for leg in legs
        ]
    }
    _emit_matrix(
        matrix,
        count=len(legs),
        missing=skipped,
        kind="matlab-matrix",
        github_output=args.github_output,
        # `skipped` holds *live* places with no board_map entry — the default
        # "no live board matches" wording would be untrue for them.
        missing_msg="live place {item!r} has no board_map entry",
    )
    print(
        f"# matlab-matrix: {len(places)} live place(s), {len(legs)} testable, "
        f"{len(skipped)} skipped (no board_map entry)",
        file=sys.stderr,
    )
    return 0


def _cmd_all_places_matrix(args: argparse.Namespace) -> int:
    """Emit a boot-smoke matrix of EVERY live place on the coordinator.

    Infra-health discovery: no consumer markers/manifest. A coordinator that is
    unreachable or has zero live places fails (exit 3) so the daily job's
    preflight goes red at a single loud point. Acquired places are skipped with a
    ``::notice::`` (contention, not breakage)."""
    from .all_places import build_all_places_matrix

    coord = coord_mod.resolve_coordinator(args.coord)
    coord_mod.warn_if_rest_port(coord)
    try:
        places, skipped_invalid = coord_mod.list_live_places(coord)
    except Exception as e:  # noqa: BLE001 - an unreachable coordinator must fail loudly, not crash
        print(f"::error title=coordinator-unreachable::{coord}: {e}", file=sys.stderr)
        return 3

    legs, acquired = build_all_places_matrix(places)
    matrix = {"include": [leg.as_matrix_dict() for leg in legs]}
    _emit_matrix(
        matrix,
        count=len(legs),
        missing=[],
        kind="all-places-matrix",
        github_output=args.github_output,
    )
    for name in acquired:
        print(
            f"::notice::all-places-matrix: {name} is acquired — skipping this run", file=sys.stderr
        )
    for name, reason in skipped_invalid:
        print(f"::warning::all-places-matrix: place {name!r} skipped ({reason})", file=sys.stderr)
    if not places:
        print(
            "::error title=no-live-places::coordinator returned zero live places",
            file=sys.stderr,
        )
        return 3
    print(
        f"# all-places-matrix: {len(places)} live place(s), {len(legs)} bootable leg(s), "
        f"{len(acquired)} acquired",
        file=sys.stderr,
    )
    return 0


def _cmd_boot_junit(args: argparse.Namespace) -> int:
    """Render a single boot outcome to a one-testcase JUnit file."""
    from .boot_junit import render_boot_junit

    xml = render_boot_junit(
        place=args.place,
        part=args.part,
        carrier=args.carrier,
        mode=args.mode,
        ok=args.status == "pass",
        seconds=args.seconds,
        message=args.message,
    )
    Path(args.out).write_text(xml, encoding="utf-8")
    print(f"wrote {args.out}", file=sys.stderr)
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


def _cmd_doctor(args: argparse.Namespace) -> int:
    from .doctor import run_doctor

    return run_doctor(args)


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


def _parse_build_vars(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"--build-var must be K=V, got {pair!r}")
        key, _, value = pair.partition("=")
        out[key] = value
    return out


def _cmd_build_noos(args: argparse.Namespace) -> int:
    """Build a no-os project for HW CI (Vivado env + Kuiper .xsa + make)."""
    build_noos(
        project=args.project,
        carrier=args.carrier,
        board=args.board,
        release=args.release,
        build_vars=_parse_build_vars(args.build_var),
        noos_root=args.noos_root,
        xsa_dir=args.xsa_dir,
    )
    return 0


def _cmd_fetch_xsa(args: argparse.Namespace) -> int:
    """Fetch a board's system_top.xsa from the Kuiper image; print its path."""
    xsa = fetch_board_xsa(
        args.release,
        args.board,
        args.carrier,
        cache_dir=args.out,
        xsa_dir=args.xsa_dir,
    )
    print(xsa)
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

    plm = sub.add_parser(
        "lint-markers",
        help="flag iio_hardware/iio_carrier markers that aren't string literals",
    )
    plm.add_argument("--test-root", required=True, help="path to the consumer's test directory")
    plm.set_defaults(func=_cmd_lint_markers)

    pinit = sub.add_parser("init", help="scaffold a consumer repo's hw-CI files for a mode")
    pinit.add_argument("--mode", choices=["uri", "flash", "matlab"], required=True)
    pinit.add_argument("--dest", required=True, help="consumer repo root to write into")
    pinit.add_argument(
        "--test-root", default=None, help="[uri] value for <TEST_ROOT> (e.g. test/hw)"
    )
    pinit.add_argument(
        "--install-cmd",
        default=None,
        help="[uri] value for <YOUR_INSTALL_ARGS> in the install step",
    )
    pinit.add_argument(
        "--force", action="store_true", help="overwrite existing files at the destination"
    )
    pinit.set_defaults(func=_cmd_init)

    pdoc = sub.add_parser("doctor", help="validate the whole onboarding chain in one pass")
    pdoc.add_argument("--mode", choices=["uri", "flash", "matlab"], required=True)
    pdoc.add_argument(
        "--coord", default=None, help="coordinator host:port (default: $LG_COORDINATOR)"
    )
    pdoc.add_argument("--repo", default=None, help="owner/name (default: infer via gh)")
    pdoc.add_argument("--test-root", default=None, help="[uri] consumer test directory")
    pdoc.add_argument("--manifest", default=None, help="[flash] projects.yaml path")
    pdoc.add_argument("--board-map", default=None, help="[matlab] board_map.yaml path")
    pdoc.add_argument(
        "--runner-label", default=None, help="fallback runner label (vars.HW_REQUEST_RUNNER)"
    )
    pdoc.set_defaults(func=_cmd_doctor)

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

    pmm = sub.add_parser(
        "matlab-matrix",
        help="emit a MATLAB CI matrix from a board map + live coordinator places",
    )
    pmm.add_argument("--board-map", required=True, help="path to the consumer's board_map.yaml")
    pmm.add_argument("--coord", default=None)
    pmm.add_argument(
        "--github-output", action="store_true", help="also write matrix=/count= to $GITHUB_OUTPUT"
    )
    pmm.set_defaults(func=_cmd_matlab_matrix)

    pap = sub.add_parser(
        "all-places-matrix",
        help="emit a boot-smoke matrix of every live place (infra health)",
    )
    pap.add_argument(
        "--coord", default=None, help="coordinator host:port (default: $LG_COORDINATOR)"
    )
    pap.add_argument(
        "--github-output", action="store_true", help="also write matrix=/count= to $GITHUB_OUTPUT"
    )
    pap.set_defaults(func=_cmd_all_places_matrix)

    pbj = sub.add_parser("boot-junit", help="render a boot outcome to a one-testcase JUnit file")
    pbj.add_argument("--place", required=True)
    pbj.add_argument("--part", required=True)
    pbj.add_argument("--carrier", default="")
    pbj.add_argument("--mode", default="uri")
    pbj.add_argument("--status", choices=["pass", "fail"], required=True)
    pbj.add_argument("--seconds", type=int, default=0)
    pbj.add_argument("--message", default="")
    pbj.add_argument("--out", required=True, help="path to write the JUnit XML to")
    pbj.set_defaults(func=_cmd_boot_junit)

    pb = sub.add_parser("build-noos", help="build a no-os project for HW CI (env + Kuiper .xsa)")
    pb.add_argument("--project", required=True, help="projects/<project> to build")
    pb.add_argument("--carrier", required=True, help="FPGA carrier (e.g. zc706)")
    pb.add_argument("--board", required=True, help="canonical daughter-board (e.g. adrv9371)")
    pb.add_argument(
        "--release", required=True, help="Kuiper release for the .xsa (e.g. 2023_R2_P1)"
    )
    pb.add_argument("--validate", default=None, help="on-target banner (informational here)")
    pb.add_argument(
        "--build-var", action="append", default=[], help="extra make var K=V (repeatable)"
    )
    pb.add_argument("--noos-root", default=".", help="no-os checkout root (default cwd)")
    pb.add_argument("--xsa-dir", default=None, help="pin the Kuiper boot folder, skip FAT search")
    pb.set_defaults(func=_cmd_build_noos)

    px = sub.add_parser("fetch-xsa", help="extract a board's system_top.xsa from the Kuiper image")
    px.add_argument("--release", required=True, help="Kuiper release (e.g. 2023_R2_P1)")
    px.add_argument("--board", required=True, help="canonical daughter-board (e.g. adrv9009)")
    px.add_argument("--carrier", required=True, help="FPGA carrier (e.g. zc706)")
    px.add_argument("--out", default=None, help="xsa cache dir (default ~/.labgrid/kuiper_xsa)")
    px.add_argument("--xsa-dir", default=None, help="pin the Kuiper boot folder, skip FAT search")
    px.set_defaults(func=_cmd_fetch_xsa)

    ns = p.parse_args(argv)
    return ns.func(ns)


if __name__ == "__main__":
    sys.exit(main())
