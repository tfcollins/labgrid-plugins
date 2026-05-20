#!/usr/bin/env bash
# Apply place tags from a manifest. Used to bootstrap the metadata that
# hw-matrix.yml dynamic_mode reads from the coordinator (`board=`, optional
# `carrier=` / `runner=`).
#
# Manifest format (yaml):
#   places:
#     vcu118_lab01:
#       board: ad9081
#       carrier: vcu118
#       runner: hw-vcu118
#     zcu102_bench3:
#       board: ad9084
#       carrier: zcu102
#
# Usage:
#   seed-place-tags.sh --coordinator 10.0.0.41:20408 \
#                      --manifest /path/to/place-tags.yaml
#
# Requires labgrid-client on PATH (or set LGCLIENT).

set -euo pipefail

COORDINATOR=""
MANIFEST=""
LGCLIENT="${LGCLIENT:-labgrid-client}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --coordinator) COORDINATOR="$2"; shift 2 ;;
        --manifest) MANIFEST="$2"; shift 2 ;;
        --labgrid-client) LGCLIENT="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

if [[ -z "$COORDINATOR" || -z "$MANIFEST" ]]; then
    echo "Both --coordinator and --manifest are required." >&2
    exit 2
fi
if [[ ! -f "$MANIFEST" ]]; then
    echo "Manifest not found: $MANIFEST" >&2
    exit 1
fi
if ! command -v "$LGCLIENT" >/dev/null 2>&1; then
    echo "labgrid-client not found (looked for: $LGCLIENT)" >&2
    exit 1
fi

# Emit one place per line, then `key=value` pairs, separated by tabs.
mapfile -t LINES < <(python3 - "$MANIFEST" <<'PY'
import sys, yaml
doc = yaml.safe_load(open(sys.argv[1])) or {}
places = doc.get("places") or {}
for place, tags in places.items():
    if not isinstance(tags, dict):
        continue
    kvs = "\t".join(f"{k}={v}" for k, v in tags.items())
    print(f"{place}\t{kvs}")
PY
)

for line in "${LINES[@]}"; do
    IFS=$'\t' read -r place rest <<< "$line"
    if [[ -z "$place" ]]; then
        continue
    fi
    # `rest` is a tab-separated string of key=value pairs; split into argv.
    IFS=$'\t' read -r -a kvs <<< "$rest"
    echo ">>> ${place}: ${kvs[*]}" >&2
    "$LGCLIENT" -x "$COORDINATOR" -p "$place" set-tags "${kvs[@]}"
done
