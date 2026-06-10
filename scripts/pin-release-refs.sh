#!/usr/bin/env bash
# Pin the hw-request family's internal @main self-references to a release tag.
# Usage (on the release branch, before tagging):  scripts/pin-release-refs.sh v3
set -euo pipefail

TAG="${1:?usage: pin-release-refs.sh <tag>}"
cd "$(git rev-parse --show-toplevel)"

FAMILY=(
  .github/workflows/hw-request.yml
  .github/workflows/noos-hw-request.yml
  .github/workflows/matlab-hw-request.yml
)

for f in "${FAMILY[@]}"; do
  [ -f "$f" ] || { echo "skip (absent): $f" >&2; continue; }
  sed -i \
    -e "s#\(tfcollins/labgrid-plugins/\.github/actions/[A-Za-z0-9_-]*\)@main#\1@${TAG}#g" \
    -e "s#\(git+https://github\.com/tfcollins/labgrid-plugins\)@main#\1@${TAG}#g" \
    "$f"
done

git --no-pager diff --stat -- "${FAMILY[@]}" || true
