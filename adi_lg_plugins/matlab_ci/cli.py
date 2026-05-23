"""``adi-lg-matlab`` command line entry point.

Two subcommands, the MATLAB analogue of ``adi-lg-hw-ci``:

* ``discover`` — query the coordinator, intersect live places with the
                 toolbox's board map, and emit the GHA matrix include
                 list as JSON (and optionally ``$GITHUB_OUTPUT``).
* ``run``      — boot a place, resolve its libIIO URI, launch MATLAB
                 with ``IIO_URI`` set, copy the JUnit output, and
                 (optionally) acquire/release the place around the run.

``run`` works two ways:

* **place mode** (``--coord --place --board-map``): resolve the MATLAB
  board name from the board map and the boot strategy from the place's
  tags, rendering the env yaml from the place's ``boot-strategy`` tag.
* **config mode** (``--config --matlab-board --boot-strategy``): skip
  the coordinator entirely and run against a labgrid yaml you supply —
  useful locally or against a static lab bench.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from adi_lg_plugins.hw_ci import coordinator as coord_mod
from adi_lg_plugins.hw_ci import render_env as render_mod

from .board_map import load_board_map
from .discover import discover
from .run import run_matlab_tests

# Re-exported into this module's namespace so the value is importable and
# the symbol is monkeypatchable in tests.
__all__ = ["main", "run_matlab_tests"]


# --- reservation helpers (shell out to labgrid-client) -------------------


def _acquire_place(coord: str, place: str) -> None:
    subprocess.run(
        ["labgrid-client", "-x", coord, "-p", place, "acquire"],
        check=True,
    )


def _release_place(coord: str, place: str) -> None:
    # Best-effort: a failed release shouldn't mask the test outcome.
    subprocess.run(
        ["labgrid-client", "-x", coord, "-p", place, "release"],
        check=False,
    )


# --- discover ------------------------------------------------------------


def _cmd_discover(args: argparse.Namespace) -> int:
    coord = coord_mod.resolve_coordinator(args.coord)
    places, skipped = coord_mod.list_live_places(coord, force_cli=args.force_cli)

    for name, reason in skipped:
        print(f"# skipped place {name}: {reason}", file=sys.stderr)

    board_map = load_board_map(args.board_map)
    entries = discover(board_map, places, skip_acquired=not args.include_acquired)
    matrix = {"include": [e.as_matrix_dict() for e in entries]}

    if args.github_output:
        gh_out = os.environ.get("GITHUB_OUTPUT")
        if not gh_out:
            print("warning: --github-output given but $GITHUB_OUTPUT is unset", file=sys.stderr)
        else:
            with open(gh_out, "a", encoding="utf-8") as f:
                f.write(f"matrix={json.dumps(matrix)}\n")
                f.write(f"count={len(entries)}\n")

    print(json.dumps(matrix, indent=2))

    print(
        f"# discovery: {len(places)} live place(s), {len(entries)} matrix entries",
        file=sys.stderr,
    )
    for e in entries:
        print(
            f"#   - {e.place}: {e.daughter_board} on {e.carrier} -> {e.matlab_board}",
            file=sys.stderr,
        )
    if not entries and places:
        offered = sorted({p.daughter_board for p in places})
        mapped = sorted({en.daughter_board for en in board_map.entries})
        print(
            f"# board map covers {mapped}; coordinator has {offered} — no overlap right now",
            file=sys.stderr,
        )
    return 0


# --- run -----------------------------------------------------------------


def _resolve_run_target(args: argparse.Namespace, tmpdir: str) -> tuple[Path, str, str, str | None]:
    """Return (config_path, matlab_board, boot_strategy, place_name).

    ``place_name`` is ``None`` in config mode (nothing to acquire/release).
    Raises :class:`SystemExit` (via argparse-style errors) on bad inputs.
    """
    if args.config:
        if not args.matlab_board or not args.boot_strategy:
            raise _CliError("--config mode requires --matlab-board and --boot-strategy")
        return Path(args.config), args.matlab_board, args.boot_strategy, None

    if not args.coord or not args.place or not args.board_map:
        raise _CliError("place mode requires --coord, --place and --board-map")

    coord = coord_mod.resolve_coordinator(args.coord)
    places, _skipped = coord_mod.list_live_places(coord, force_cli=args.force_cli)
    match = next((p for p in places if p.name == args.place), None)
    if match is None:
        raise _CliError(
            f"place {args.place!r} not found (or invalid tags); "
            f"live places: {[p.name for p in places]}"
        )

    board_map = load_board_map(args.board_map)
    matlab_board = board_map.lookup(match)
    if matlab_board is None:
        raise _CliError(
            f"place {args.place!r} (daughter-board={match.daughter_board}) "
            f"has no entry in board map {args.board_map}"
        )

    # --boot-strategy in place mode overrides the place's tag (useful when
    # the lab tagged a place with a strategy that doesn't drive a real boot
    # for our purposes — e.g. BootZynq7000JTAGRecovery — and the consumer
    # wants to render a different template like BootFPGASoCTFTP without the
    # lab admin retagging). The override is propagated both into the
    # rendered env yaml AND the run kwarg via dataclasses.replace.
    if args.boot_strategy:
        from dataclasses import replace

        match = replace(match, boot_strategy=args.boot_strategy)

    config = Path(tmpdir) / f"env-{match.name}.yaml"
    render_mod.render_env_to(match, config)
    return config, matlab_board, match.boot_strategy, match.name


class _CliError(Exception):
    """User-facing CLI error; mapped to a non-zero exit with a message."""


def _cmd_run(args: argparse.Namespace) -> int:
    coord = coord_mod.resolve_coordinator(args.coord) if args.coord else None
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            config, matlab_board, boot_strategy, place_name = _resolve_run_target(args, tmpdir)
        except _CliError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2

        acquire = args.acquire and place_name is not None
        if acquire:
            _acquire_place(coord, place_name)
        try:
            result = run_matlab_tests(
                config=config,
                matlab_board=matlab_board,
                boot_strategy=boot_strategy,
                repo_dir=args.repo_dir,
                matlab_bin=args.matlab,
                target_name=args.target,
                reached_state=args.reached_state,
                network_resource=args.network_resource,
                junit_dest=args.junit,
                skip_boot=args.skip_boot,
            )
        finally:
            if acquire:
                _release_place(coord, place_name)

    print(
        f"# MATLAB exited {result.returncode} (board={result.matlab_board}, uri={result.uri})",
        file=sys.stderr,
    )
    return result.returncode


# --- argparse wiring -----------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="adi-lg-matlab",
        description="Run MATLAB toolbox hardware tests against labgrid-managed boards.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pd = sub.add_parser("discover", help="emit MATLAB HW-CI matrix include list")
    pd.add_argument("--coord", default=None, help="coordinator URL (default: $LG_COORDINATOR)")
    pd.add_argument("--board-map", required=True, help="path to the toolbox board-map YAML")
    pd.add_argument("--force-cli", action="store_true", help="skip REST, use labgrid-client")
    pd.add_argument("--include-acquired", action="store_true", help="(debug) include busy places")
    pd.add_argument("--github-output", action="store_true", help="append to $GITHUB_OUTPUT")
    pd.set_defaults(func=_cmd_discover)

    pr = sub.add_parser("run", help="boot a place and run MATLAB HW tests against it")
    # place mode
    pr.add_argument("--coord", default=None, help="coordinator URL (default: $LG_COORDINATOR)")
    pr.add_argument("--place", default=None, help="coordinator place to boot (place mode)")
    pr.add_argument("--board-map", default=None, help="board-map YAML (place mode)")
    pr.add_argument("--force-cli", action="store_true")
    pr.add_argument(
        "--acquire",
        action="store_true",
        help="acquire the place before and release it after (place mode)",
    )
    # config mode
    pr.add_argument("--config", default=None, help="labgrid env yaml (config mode)")
    pr.add_argument("--matlab-board", default=None, help="MATLAB board name (config mode)")
    pr.add_argument(
        "--boot-strategy",
        default=None,
        help="boot strategy class (config mode: required; place mode: optional, "
        "overrides the place's boot-strategy tag)",
    )
    # shared
    pr.add_argument("--repo-dir", required=True, help="toolbox checkout dir (cwd for MATLAB)")
    pr.add_argument("--matlab", default="matlab", help="MATLAB binary path (default: matlab)")
    pr.add_argument("--target", default="main", help="labgrid target name (default: main)")
    pr.add_argument("--reached-state", default="shell", help="strategy state to reach")
    pr.add_argument("--network-resource", default="NetworkService", help="resource holding the IP")
    pr.add_argument("--junit", default=None, help="copy MATLAB JUnit output here")
    pr.add_argument(
        "--skip-boot",
        action="store_true",
        help="skip the strategy boot transition (board is already up); "
        "still resolves NetworkService URI",
    )
    pr.set_defaults(func=_cmd_run)

    ns = p.parse_args(argv)
    return ns.func(ns)


if __name__ == "__main__":
    sys.exit(main())
