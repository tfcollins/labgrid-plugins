#!/usr/bin/env bash
# Bump the tfcollins/labgrid fork pin in both pyproject.toml files to the same SHA.
# Usage: scripts/bump-labgrid.sh <40-char-sha>
#        scripts/bump-labgrid.sh --tip          (resolves current tip of tfcollins/plugin-support)
set -euo pipefail

if [ $# -ne 1 ]; then
    echo "Usage: $0 <40-char-sha>|--tip" >&2
    exit 2
fi

REPO_ROOT=$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)
cd "$REPO_ROOT"

NEW_SHA="$1"
if [ "$NEW_SHA" = "--tip" ]; then
    NEW_SHA=$(git ls-remote https://github.com/tfcollins/labgrid.git refs/heads/tfcollins/plugin-support | awk '{print $1}')
    if [ -z "$NEW_SHA" ]; then
        echo "Failed to resolve tip of tfcollins/plugin-support" >&2
        exit 1
    fi
    echo "Resolved tip: $NEW_SHA"
fi

if ! echo "$NEW_SHA" | grep -Eq '^[a-f0-9]{40}$'; then
    echo "Error: $NEW_SHA is not a 40-char SHA" >&2
    exit 1
fi

for f in pyproject.toml coordinator/api/pyproject.toml; do
    if [ ! -f "$f" ]; then
        echo "Error: $f not found (run from labgrid-plugins repo root)" >&2
        exit 1
    fi
    sed -i -E "s|(tfcollins/labgrid\.git@)[^\"]+|\1${NEW_SHA}|g" "$f"
    echo "Updated $f"
done

# Re-resolve any uv lockfiles so the new SHA is captured.
if command -v uv >/dev/null 2>&1; then
    if [ -f uv.lock ]; then
        uv lock --upgrade-package labgrid
    fi
    if [ -f coordinator/api/uv.lock ]; then
        (cd coordinator/api && uv lock --upgrade-package labgrid)
    fi
fi

echo
echo "Pinned both pyproject.toml files to labgrid @ $NEW_SHA"
echo "Review with: git diff pyproject.toml coordinator/api/pyproject.toml"
