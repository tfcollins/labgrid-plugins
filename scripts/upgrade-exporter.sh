#!/usr/bin/env bash
#
# upgrade-exporter.sh — migrate a labgrid *exporter* host from the labgrid
# fork to upstream labgrid (>=25.0) and register the ADI plugins.
#
# WHY: upstream labgrid has no entry-point plugin auto-discovery, so an
# exporter must (a) run upstream labgrid + have adi-labgrid-plugins installed
# in the SAME python env, and (b) `import adi_lg_plugins` at startup so the
# ADI resource classes (KuiperRelease, XilinxDeviceJTAG, VesyncOutlet, ...)
# register. This script does both, for whichever env type the exporter uses
# (system python --user / venv / uv tool), then restarts the service.
#
# RUN AS YOUR NORMAL USER (the one that owns the exporter service, e.g.
# tcollins) — NOT under sudo. The script calls `sudo` only for the service
# restart and will prompt for your password there. It is idempotent.
#
#   ./upgrade-exporter.sh            # upgrade this host's exporter
#   ADI_BRANCH=main ./upgrade-exporter.sh   # after #46 merges, use main
#   DRY_RUN=1 ./upgrade-exporter.sh  # print what it would do, change nothing
#
set -euo pipefail

BRANCH="${ADI_BRANCH:-feat/upstream-labgrid}"
PKG_URL="git+https://github.com/tfcollins/labgrid-plugins.git@${BRANCH}"
PKG_SPEC="adi-labgrid-plugins @ ${PKG_URL}"
LABGRID_SPEC="labgrid>=25.0"
SVC="labgrid-exporter.service"
DRY="${DRY_RUN:-0}"

run() { echo "+ $*"; [ "$DRY" = 1 ] || "$@"; }

if [ "$(id -u)" = 0 ]; then
  echo "ERROR: run as your normal user, not sudo (pip --user would target root)." >&2
  exit 2
fi

echo "== labgrid exporter upgrade on $(hostname) =="

# 1. Locate the python that runs the exporter service.
PY="$(pgrep -af 'labgrid-exporter' | grep -oE '[^ ]*/python[0-9.]*' | head -1 || true)"
[ -z "$PY" ] && { echo "ERROR: no running labgrid-exporter found." >&2; exit 1; }
echo "exporter python : $PY"
echo "current labgrid : $("$PY" -c 'import labgrid;print(labgrid.__version__)' 2>/dev/null || echo '?')"

# Locate uv (not always on a non-interactive ssh PATH).
UV="$(command -v uv 2>/dev/null || true)"
[ -z "$UV" ] && [ -x "$HOME/.local/bin/uv" ] && UV="$HOME/.local/bin/uv"

# 2. Install upstream labgrid + adi plugins into that env, by env type.
if echo "$PY" | grep -q '/uv/tools/'; then
  echo "env type        : uv tool"
  [ -z "$UV" ] && { echo "ERROR: uv not found (needed for uv-tool env)." >&2; exit 1; }
  run "$UV" tool install "labgrid==25.0.1" --with "${PKG_SPEC}" --force
elif [ "$("$PY" -c 'import sys;print(sys.prefix!=sys.base_prefix)')" = "True" ]; then
  echo "env type        : venv ($("$PY" -c 'import sys;print(sys.prefix)'))"
  # The venv may lack pip, so install via uv targeting that interpreter.
  [ -z "$UV" ] && { echo "ERROR: uv not found (needed for venv without pip)." >&2; exit 1; }
  run "$UV" pip install --python "$PY" -U "${LABGRID_SPEC}" "${PKG_SPEC}"
else
  echo "env type        : system python (user-site, PEP668 override)"
  run "$PY" -m pip install --user --break-system-packages -U "${LABGRID_SPEC}" "${PKG_SPEC}"
fi

# 3. Drop the registration hook into the env's own site-packages (no root).
#    Use a .pth file, NOT sitecustomize/usercustomize: a system
#    /usr/lib/pythonX/sitecustomize.py shadows any env-level sitecustomize,
#    whereas site.py executes the `import` line of EVERY .pth in every site
#    dir — so it can't be shadowed.
if [ "$("$PY" -c 'import sys;print(sys.prefix==sys.base_prefix)')" = "True" ]; then
  HOOK_DIR="$("$PY" -c 'import site;print(site.getusersitepackages())')"
else
  HOOK_DIR="$("$PY" -c 'import site;print(site.getsitepackages()[0])')"
fi
HOOK="$HOOK_DIR/adi_lg_plugins_register.pth"
echo "registration hook: $HOOK (.pth)"
if [ "$DRY" != 1 ]; then
  mkdir -p "$HOOK_DIR"
  # .pth: a line beginning with `import` is executed at interpreter startup.
  echo 'import adi_lg_plugins' > "$HOOK"
fi

# 4. Verify upstream + registration in the exporter python BEFORE restart.
#    Run from /tmp so a checkout on the current dir can't mask the result.
echo "== verify (pre-restart) =="
( cd /tmp && "$PY" -c "import labgrid;print('labgrid =>', labgrid.__version__)" )
( cd /tmp && "$PY" - <<'PYV'
import sys
from labgrid.factory import target_factory   # .pth hook already imported adi_lg_plugins
assert "adi_lg_plugins" in sys.modules, "registration .pth did not run"
names = ("KuiperRelease","XilinxDeviceJTAG","VesyncOutlet","TFTPServerResource","MassStorageDevice","CloudsmithRelease")
print("registered =>", {n: (n in target_factory.resources) for n in names})
PYV
)

# 5. Restart the service (needs root).
echo "== restart $SVC (sudo) =="
run sudo systemctl restart "$SVC"
[ "$DRY" = 1 ] || sleep 4
run sudo systemctl --no-pager --lines=6 status "$SVC" || true

echo
echo "== done on $(hostname). Now confirm its resources re-registered on the coordinator:"
echo "   labgrid-client -x 10.0.0.41:20408 resources | grep '^$(hostname)/'"
