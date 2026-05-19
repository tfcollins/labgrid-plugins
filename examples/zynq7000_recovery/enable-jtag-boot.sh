#!/bin/bash
# Wire a ZC706 (or other Zynq-7000) place for JTAG-bootstrap + SD-boot CI.
#
# Run on the *exporter host* where the board's USB cables live. Adds the
# resources that BootZynq7000JTAGRecovery needs (XilinxDeviceJTAG,
# XilinxVivadoTool, TFTPServerResource) to the labgrid exporter config,
# restarts the exporter, then updates the coordinator-side tags on the
# named place so hw-matrix dynamic_mode routes through the new strategy.
#
# Re-runnable. Backs up the previous exporter.yaml. Asks for sudo once.
#
# Usage:
#   ./enable-jtag-boot.sh <place-name> <coordinator-host:port>
#
# Defaults assume a bq-style setup; override via env:
#   EXPORTER_GROUP=tlab      # YAML key for the resource group
#   VIVADO_PATH=/opt/Xilinx/Vivado/2023.2
#   TFTP_ROOT=/var/lib/tftpboot
#   EXPORTER_YAML=/etc/labgrid/exporter.yaml
#   EXPORTER_SERVICE=labgrid-exporter
#   LABGRID_CLIENT=$HOME/.cache/hw-ci/venv/bin/labgrid-client

set -euo pipefail

PLACE="${1:-bq}"
COORDINATOR="${2:-10.0.0.41:20408}"

EXPORTER_GROUP="${EXPORTER_GROUP:-tlab}"
VIVADO_PATH="${VIVADO_PATH:-/opt/Xilinx/Vivado/2023.2}"
VIVADO_VERSION="$(basename "$VIVADO_PATH")"
TFTP_ROOT="${TFTP_ROOT:-/var/lib/tftpboot}"
EXPORTER_YAML="${EXPORTER_YAML:-/etc/labgrid/exporter.yaml}"
EXPORTER_SERVICE="${EXPORTER_SERVICE:-labgrid-exporter}"
LABGRID_CLIENT="${LABGRID_CLIENT:-$HOME/.cache/hw-ci/venv/bin/labgrid-client}"

log() { printf '[enable-jtag-boot] %s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

# Resolve a routable IPv4 for the TFTPServerResource. Falls back to
# the env override TFTP_ADDRESS if set.
if [[ -n "${TFTP_ADDRESS:-}" ]]; then
    TFTP_ADDRESS_RESOLVED="$TFTP_ADDRESS"
else
    TFTP_ADDRESS_RESOLVED="$(hostname -I | awk '{print $1}')"
fi
[[ -n "$TFTP_ADDRESS_RESOLVED" ]] || die "could not resolve a local IP for TFTP"

# ---- 1. preflight checks ----------------------------------------------------
log "preflight"
[[ -f "$EXPORTER_YAML" ]] || die "exporter yaml not found: $EXPORTER_YAML"
[[ -x "$VIVADO_PATH/bin/xsdb" ]] || die "xsdb not found at $VIVADO_PATH/bin/xsdb"
[[ -d "$TFTP_ROOT" ]] || die "TFTP root missing: $TFTP_ROOT"
[[ -x "$LABGRID_CLIENT" ]] || die "labgrid-client missing: $LABGRID_CLIENT"
command -v sudo >/dev/null || die "sudo required"

# Confirm the place exists and the exporter is registered.
if ! "$LABGRID_CLIENT" -x "$COORDINATOR" places 2>/dev/null | grep -q "^${PLACE}$"; then
    die "place '$PLACE' not registered on coordinator $COORDINATOR"
fi
log "place=$PLACE coordinator=$COORDINATOR tftp_address=$TFTP_ADDRESS_RESOLVED vivado=$VIVADO_PATH"

# ---- 2. patch exporter.yaml -------------------------------------------------
# Skip if the resources are already present (idempotent re-run).
if sudo grep -q '^[[:space:]]*XilinxDeviceJTAG:' "$EXPORTER_YAML" && \
   sudo grep -q '^[[:space:]]*XilinxVivadoTool:' "$EXPORTER_YAML" && \
   sudo grep -q '^[[:space:]]*TFTPServerResource:' "$EXPORTER_YAML"; then
    log "exporter.yaml already has JTAG/Vivado/TFTP — skipping edit"
else
    BACKUP="${EXPORTER_YAML}.bak.$(date +%Y%m%d-%H%M%S)"
    log "backing up exporter.yaml → $BACKUP"
    sudo cp "$EXPORTER_YAML" "$BACKUP"

    log "appending JTAG/Vivado/TFTP resources under group '$EXPORTER_GROUP'"
    sudo python3 - "$EXPORTER_YAML" "$EXPORTER_GROUP" "$VIVADO_PATH" "$VIVADO_VERSION" \
                  "$TFTP_ADDRESS_RESOLVED" "$TFTP_ROOT" <<'PY'
import sys
import yaml

path, group, vivado_path, vivado_version, tftp_addr, tftp_root = sys.argv[1:7]
with open(path) as f:
    doc = yaml.safe_load(f) or {}

# exporter.yaml is one or more exporter blocks at top level, each
# containing groups; we walk every group that matches `group` and merge
# our resources in. With more than one exporter block the merge is
# applied to whichever block carries that group name.
added_any = False
for exporter_name, exporter_block in doc.items():
    if not isinstance(exporter_block, dict) or group not in exporter_block:
        continue
    g = exporter_block[group]
    if not isinstance(g, dict):
        continue
    g.setdefault("XilinxDeviceJTAG", {
        "cls": "XilinxDeviceJTAG",
        "root_target": 1,
    })
    g.setdefault("XilinxVivadoTool", {
        "cls": "XilinxVivadoTool",
        "vivado_path": vivado_path,
        "xsdb_path": f"{vivado_path}/bin/xsdb",
        "version": vivado_version,
    })
    g.setdefault("TFTPServerResource", {
        "cls": "TFTPServerResource",
        "address": tftp_addr,
        "port": 69,
        "root": tftp_root,
    })
    added_any = True
    print(f"[enable-jtag-boot] merged into {exporter_name}/{group}", file=sys.stderr)

if not added_any:
    raise SystemExit(
        f"no exporter group named {group!r} found in {path}; "
        "set EXPORTER_GROUP to the right key and re-run"
    )

with open(path, "w") as f:
    yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=False)
PY
fi

# ---- 3. restart exporter ----------------------------------------------------
log "restarting $EXPORTER_SERVICE"
sudo systemctl restart "$EXPORTER_SERVICE"
sleep 3
if ! systemctl is-active --quiet "$EXPORTER_SERVICE"; then
    die "$EXPORTER_SERVICE failed to come back up — check 'journalctl -u $EXPORTER_SERVICE -n 50'"
fi
log "$EXPORTER_SERVICE active"

# Give the exporter a few seconds to re-register resources on the coordinator.
sleep 5

# ---- 4. verify new resources visible on coordinator -------------------------
log "verifying new resources are exposed for $PLACE"
SHOW="$("$LABGRID_CLIENT" -x "$COORDINATOR" -p "$PLACE" show 2>&1)"
for cls in XilinxDeviceJTAG XilinxVivadoTool TFTPServerResource; do
    if ! grep -q "$cls" <<<"$SHOW"; then
        log "WARN: $cls not yet visible on coordinator (exporter may need another moment)"
    else
        log "  ✓ $cls"
    fi
done

# ---- 5. update place tags for hw-matrix dynamic_mode -----------------------
log "updating place tags"
# Preserve existing tags except disabled / boot-strategy, then set the new ones.
EXISTING="$("$LABGRID_CLIENT" -x "$COORDINATOR" -p "$PLACE" show 2>&1 \
            | awk -F: '/^[[:space:]]*tags:/ {sub(/^[[:space:]]*tags:[[:space:]]*/, ""); print}')"
NEW_TAGS=""
IFS=',' read -ra parts <<<"$EXISTING"
for kv in "${parts[@]}"; do
    kv="${kv# }"; kv="${kv% }"
    [[ -z "$kv" ]] && continue
    k="${kv%%=*}"
    case "$k" in
        disabled|boot-strategy) continue ;;
    esac
    NEW_TAGS="$NEW_TAGS $kv"
done
NEW_TAGS="$NEW_TAGS boot-strategy=BootZynq7000JTAGRecovery disabled="

log "running: labgrid-client -p $PLACE set-tags $NEW_TAGS"
"$LABGRID_CLIENT" -x "$COORDINATOR" -p "$PLACE" set-tags $NEW_TAGS

log "final tags:"
"$LABGRID_CLIENT" -x "$COORDINATOR" -p "$PLACE" show 2>&1 | awk '/^[[:space:]]*tags:/ {print "  " $0}'

cat <<EOF
[enable-jtag-boot] done.

$PLACE is now configured for the BootZynq7000JTAGRecovery + 'shell' state path:
  - exporter.yaml advertises XilinxDeviceJTAG / XilinxVivadoTool / TFTPServerResource
  - place tags: boot-strategy=BootZynq7000JTAGRecovery, disabled=(cleared)

Next: trigger the pyadi-iio Hardware Tests workflow. hw-matrix dynamic_mode
should pick $PLACE up, fetch its env yaml at tier=boot, and the
boot-and-discover script will drive Strategy.transition("shell"). The SD
content is reused across runs — no recovery dd unless the SD goes corrupt
again.

To roll back: restore $EXPORTER_YAML from the .bak file printed above,
restart $EXPORTER_SERVICE, and re-set the tags with the old values
(boot-strategy=BootFPGASoCSSH, disabled=<reason>).
EOF
