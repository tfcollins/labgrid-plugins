#!/usr/bin/env python3
"""Query the labgrid coordinator REST API and emit a GHA matrix JSON.

Reads:
  $COORDINATOR_API_URL     e.g. http://coordinator-host:8000
  ci/hardware_targets.yml  carrier -> {lg_env, tests, runner_labels, python_version}

Writes (to $GITHUB_OUTPUT):
  matrix=<json>            {"include": [{place, carrier, lg_env, tests,
                                         runner_labels, python_version}, ...]}
  has_places=true|false

Also appends a human-readable summary to $GITHUB_STEP_SUMMARY (if set).

Exits non-zero only on operator errors (missing env var, malformed dispatch
map, unreachable coordinator). An empty coordinator is a successful run
with has_places=false.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

import yaml

DEFAULT_PYTHON_VERSION = "3.12"
REPO_ROOT = Path(__file__).resolve().parent.parent
DISPATCH_PATH = REPO_ROOT / "ci" / "hardware_targets.yml"


def load_dispatch(path: Path = DISPATCH_PATH) -> dict[str, dict]:
    """Load the board -> config map from ``ci/hardware_targets.yml``."""
    doc = yaml.safe_load(path.read_text()) or {}
    boards = doc.get("boards") or {}
    if not isinstance(boards, dict):
        raise ValueError(f"{path}: 'boards' must be a mapping, got {type(boards).__name__}")
    return boards


def fetch_places(api_url: str, timeout: float = 15.0) -> list[dict]:
    """GET /api/places and return the decoded JSON list."""
    url = api_url.rstrip("/") + "/api/places"
    with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310 - trusted lab URL
        return json.load(r)


def dispatch(
    places: list[dict],
    boards: dict[str, dict],
) -> tuple[list[dict], list[tuple[str, str | None, str]]]:
    """Build (matrix, skipped) from places + dispatch map.

    Returns:
        matrix: list of per-place job descriptors, ready for GHA.
        skipped: list of (place_name, board_or_None, reason) tuples.
    """
    matrix: list[dict] = []
    skipped: list[tuple[str, str | None, str]] = []

    for p in places:
        name = p.get("name")
        if not name:
            skipped.append(("<unnamed>", None, "place has no name"))
            continue
        tags = p.get("tags") or {}
        carrier = tags.get("carrier")
        if p.get("acquired"):
            skipped.append((name, carrier, f"acquired by {p['acquired']}"))
            continue
        if not carrier:
            skipped.append((name, None, "no carrier tag"))
            continue
        cfg = boards.get(carrier)
        if not cfg:
            skipped.append((name, carrier, "no entry in ci/hardware_targets.yml"))
            continue
        matrix.append(
            {
                "place": name,
                "carrier": carrier,
                "lg_env": cfg["lg_env"],
                "tests": list(cfg["tests"]),
                "runner_labels": list(cfg["runner_labels"]),
                "python_version": cfg.get("python_version", DEFAULT_PYTHON_VERSION),
            }
        )

    return matrix, skipped


def format_summary(
    api_url: str,
    matrix: list[dict],
    skipped: list[tuple[str, str | None, str]],
) -> str:
    """Render the $GITHUB_STEP_SUMMARY markdown block."""
    lines = [
        "## Hardware-test discovery",
        f"- coordinator: `{api_url}`",
        f"- dispatched: {len(matrix)} place(s)",
    ]
    for m in matrix:
        lines.append(f"  - `{m['place']}` ({m['carrier']}) -> {', '.join(m['tests'])}")
    if skipped:
        lines.append(f"- skipped: {len(skipped)} place(s)")
        for name, carrier, why in skipped:
            tag = f"carrier={carrier}" if carrier else "untagged"
            lines.append(f"  - `{name}` ({tag}): {why}")
    return "\n".join(lines) + "\n"


def write_outputs(matrix: list[dict]) -> None:
    """Write the matrix + has_places lines to $GITHUB_OUTPUT (if set)."""
    payload = json.dumps({"include": matrix})
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if not gh_out:
        print(f"matrix={payload}")
        print(f"has_places={'true' if matrix else 'false'}")
        return
    with open(gh_out, "a") as f:
        f.write(f"matrix={payload}\n")
        f.write(f"has_places={'true' if matrix else 'false'}\n")


def write_summary(summary: str) -> None:
    """Append the markdown summary to $GITHUB_STEP_SUMMARY (if set)."""
    gh_sum = os.environ.get("GITHUB_STEP_SUMMARY")
    if not gh_sum:
        print(summary, end="")
        return
    with open(gh_sum, "a") as f:
        f.write(summary)


def main(argv: list[str] | None = None) -> int:
    api_url = os.environ.get("COORDINATOR_API_URL")
    if not api_url:
        print("COORDINATOR_API_URL is not set", file=sys.stderr)
        return 2

    boards = load_dispatch()
    places = fetch_places(api_url)
    matrix, skipped = dispatch(places, boards)

    write_outputs(matrix)
    write_summary(format_summary(api_url, matrix, skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
