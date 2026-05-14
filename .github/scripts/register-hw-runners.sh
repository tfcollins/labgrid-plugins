#!/usr/bin/env bash
# Register self-hosted GitHub Actions runners on lab hosts.
#
# This is the parameterized fork of pyadi-dt/.github/scripts/register-hw-runners.sh.
# Each lab host registers once per requested scope; a single host can serve
# multiple GitHub scopes (org or repo) by running multiple runner services side
# by side, all sharing the same labgrid lab YAML via the same LG_DIRECT_ENV path.
#
# Prereqs on the machine running this script:
#   - gh CLI authenticated against github.com with:
#       * admin:org for any org: scopes
#       * repo for any repo: scopes
#   - SSH key-based access as the target user on each lab host
#   - An interactive terminal (sudo prompts for password on the remote host)
#   - Local tools: gh, jq, ssh, scp, mktemp
#
# Usage:
#   register-hw-runners.sh \
#       --hosts-file ./hosts.tsv \
#       --scopes org:analogdevicesinc,repo:tfcollins/labgrid-plugins,repo:tfcollins/vrt49 \
#       [bq mini2]                 # optional alias filter
#
# Hosts file format (TSV, # for comments):
#   alias<TAB>ssh_target<TAB>runner_label<TAB>runner_name_base<TAB>lg_direct_env_path
#   bq    bq     hw-bq      bq      /home/tcollins/dev/dt-fix/lg_adrv9371_zc706_tftp.yaml
#   mini2 mini2  hw-mini2   mini2
#
# For each host × scope, a runner is installed in
# ~/actions-runner-<scope-slug>/ with name "<runner_name_base>-<scope-slug>"
# and labels "self-hosted,<runner_label>".

set -euo pipefail

RUNNER_VERSION="2.333.1"
RUNNER_TARBALL="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
RUNNER_URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${RUNNER_TARBALL}"

die() { echo "error: $*" >&2; exit 1; }

HOSTS_FILE=""
SCOPES=""
FILTER=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --hosts-file) HOSTS_FILE="$2"; shift 2 ;;
        --scopes) SCOPES="$2"; shift 2 ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        --) shift; FILTER+=("$@"); break ;;
        *) FILTER+=("$1"); shift ;;
    esac
done

[[ -n "$HOSTS_FILE" ]] || die "--hosts-file is required"
[[ -f "$HOSTS_FILE" ]] || die "hosts file not found: $HOSTS_FILE"
[[ -n "$SCOPES" ]] || die "--scopes is required (e.g. org:foo,repo:bar/baz)"

REQUIRED_TOOLS=(gh jq ssh scp mktemp)
missing=()
for tool in "${REQUIRED_TOOLS[@]}"; do
    command -v "$tool" >/dev/null || missing+=("$tool")
done
((${#missing[@]} > 0)) && die "missing required local tool(s): ${missing[*]}"

gh auth status -h github.com >/dev/null 2>&1 \
    || die "gh is not authenticated against github.com — run 'gh auth login' first"

# Validate each scope: confirm token has enough rights.
IFS=',' read -ra SCOPE_ARR <<<"$SCOPES"
for scope in "${SCOPE_ARR[@]}"; do
    case "$scope" in
        org:*)
            org="${scope#org:}"
            gh api "/orgs/${org}" >/dev/null 2>&1 \
                || die "cannot reach org '$org' — verify name and gh scope (admin:org)"
            ;;
        repo:*)
            repo="${scope#repo:}"
            adm=$(gh api "/repos/${repo}" --jq '.permissions.admin' 2>/dev/null || echo "")
            [[ "$adm" == "true" ]] || die "lack admin on repo '$repo' — cannot mint runner tokens"
            ;;
        *) die "unknown scope '$scope' (expected org:NAME or repo:OWNER/REPO)" ;;
    esac
done

# Read hosts file, skipping comments and blank lines.
HOSTS=()
while IFS=$'\t' read -r alias ssh_target runner_label runner_name_base lg_direct_env; do
    [[ -z "$alias" || "$alias" =~ ^# ]] && continue
    HOSTS+=("${alias}|${ssh_target}|${runner_label}|${runner_name_base}|${lg_direct_env:-}")
done < "$HOSTS_FILE"

((${#HOSTS[@]} > 0)) || die "no hosts read from $HOSTS_FILE"

# Optional CLI alias filter.
if ((${#FILTER[@]} > 0)); then
    NEW_HOSTS=()
    for entry in "${HOSTS[@]}"; do
        a="${entry%%|*}"
        for want in "${FILTER[@]}"; do
            [[ "$a" == "$want" ]] && NEW_HOSTS+=("$entry")
        done
    done
    ((${#NEW_HOSTS[@]} > 0)) || die "no hosts matched: ${FILTER[*]}"
    HOSTS=("${NEW_HOSTS[@]}")
fi

scope_slug() {
    case "$1" in
        org:*)  echo "org-${1#org:}" ;;
        repo:*) echo "repo-$(echo "${1#repo:}" | tr '/' '-')" ;;
    esac
}

scope_url() {
    case "$1" in
        org:*)  echo "https://github.com/${1#org:}" ;;
        repo:*) echo "https://github.com/${1#repo:}" ;;
    esac
}

scope_token_endpoint() {
    case "$1" in
        org:*)  echo "/orgs/${1#org:}/actions/runners/registration-token" ;;
        repo:*) echo "/repos/${1#repo:}/actions/runners/registration-token" ;;
    esac
}

echo "Registering against scopes:"
for s in "${SCOPE_ARR[@]}"; do printf '  - %s\n' "$s"; done
echo "On hosts:"
for h in "${HOSTS[@]}"; do printf '  - %s\n' "${h%%|*}"; done

REMOTE_SCRIPT=$(mktemp)
trap 'rm -f "$REMOTE_SCRIPT"' EXIT

cat > "$REMOTE_SCRIPT" <<'REMOTE'
#!/usr/bin/env bash
set -euo pipefail
: "${SCOPE_URL:?}"; : "${RUNNER_URL:?}"; : "${RUNNER_TARBALL:?}"
: "${LABEL:?}"; : "${NAME:?}"; : "${TOKEN:?}"; : "${DIR_NAME:?}"
LG_EXPORT_LINE="${LG_EXPORT_LINE:-}"

cd "$HOME"
mkdir -p "$DIR_NAME"
cd "$DIR_NAME"

if [[ ! -f "$RUNNER_TARBALL" ]]; then
    curl --fail -sSL -o "$RUNNER_TARBALL" "$RUNNER_URL"
fi
if [[ ! -x ./config.sh ]]; then
    tar xzf "$RUNNER_TARBALL"
fi

if [[ -f .runner ]]; then
    echo "-- removing existing registration in $DIR_NAME"
    ./config.sh remove --token "$TOKEN" || true
fi

./config.sh \
    --url "$SCOPE_URL" \
    --token "$TOKEN" \
    --name "$NAME" \
    --labels "self-hosted,$LABEL" \
    --unattended --replace

if [[ -n "$LG_EXPORT_LINE" ]]; then
    touch .env
    grep -v '^LG_DIRECT_ENV=' .env > .env.new 2>/dev/null || true
    echo "$LG_EXPORT_LINE" >> .env.new
    mv .env.new .env
fi

echo "-- installing service for $DIR_NAME (sudo will prompt)"
sudo ./svc.sh install "$USER"
sudo ./svc.sh start
sudo ./svc.sh status | head -5
REMOTE

REGISTRATIONS=()  # tuples "scope|name" for the final status check

for entry in "${HOSTS[@]}"; do
    IFS='|' read -r ALIAS SSH_TARGET LABEL NAME_BASE LG_DIRECT_ENV <<<"$entry"
    echo
    echo "=== host $ALIAS ($SSH_TARGET) ==="

    LG_EXPORT_LINE=""
    if [[ -n "$LG_DIRECT_ENV" ]]; then
        LG_EXPORT_LINE="LG_DIRECT_ENV=${LG_DIRECT_ENV}"
    fi

    for scope in "${SCOPE_ARR[@]}"; do
        SLUG=$(scope_slug "$scope")
        URL=$(scope_url "$scope")
        ENDPOINT=$(scope_token_endpoint "$scope")
        DIR_NAME="actions-runner-${SLUG}"
        NAME="${NAME_BASE}-${SLUG}"

        echo "-- scope=$scope dir=$DIR_NAME"
        TOKEN=$(gh api -X POST "$ENDPOINT" --jq .token)
        [[ -n "$TOKEN" ]] || die "failed to mint registration token for $scope"

        REMOTE_PATH="/tmp/register-hw-runner.$$.${SLUG}.sh"
        scp -q "$REMOTE_SCRIPT" "$SSH_TARGET:$REMOTE_PATH"

        # Run remotely with -t for sudo prompts.
        ssh -t \
            -o ControlMaster=no \
            -o ServerAliveInterval=30 \
            "$SSH_TARGET" \
            "SCOPE_URL='$URL' RUNNER_URL='$RUNNER_URL' RUNNER_TARBALL='$RUNNER_TARBALL' \
             LABEL='$LABEL' NAME='$NAME' LG_EXPORT_LINE='$LG_EXPORT_LINE' \
             TOKEN='$TOKEN' DIR_NAME='$DIR_NAME' bash '$REMOTE_PATH'; rc=\$?; rm -f '$REMOTE_PATH'; exit \$rc"

        REGISTRATIONS+=("${scope}|${NAME}")
    done
done

echo
echo "All requested runners registered. Waiting 60s for them to phone home..."
for i in $(seq 60 -5 5); do
    printf '  %ss remaining...\r' "$i"
    sleep 5
done
printf '                       \r'

echo "Querying runner status from GitHub:"
any_offline=0
for entry in "${REGISTRATIONS[@]}"; do
    IFS='|' read -r scope name <<<"$entry"
    case "$scope" in
        org:*)  list_endpoint="/orgs/${scope#org:}/actions/runners" ;;
        repo:*) list_endpoint="/repos/${scope#repo:}/actions/runners" ;;
    esac
    row=$(gh api --paginate "$list_endpoint" \
        | jq -r --arg n "$name" '.runners[]? | select(.name==$n) | "\(.status)\t\(.busy)\t\([.labels[].name]|join(","))"' \
        | head -1)
    if [[ -z "$row" ]]; then
        printf '  %-50s MISSING\n' "$scope::$name"
        any_offline=1
        continue
    fi
    IFS=$'\t' read -r status busy labels <<<"$row"
    if [[ "$status" == "online" ]]; then
        printf '  %-50s online  (busy=%s, labels=%s)\n' "$scope::$name" "$busy" "$labels"
    else
        printf '  %-50s %s   (labels=%s)\n' "$scope::$name" "$status" "$labels"
        any_offline=1
    fi
done

if (( any_offline )); then
    echo
    echo "One or more runners did not come online within 60s."
    echo "Troubleshoot on the affected host with:"
    echo "  sudo ~/actions-runner-<scope-slug>/svc.sh status"
    echo "  journalctl -u 'actions.runner.*' -n 100 --no-pager"
    exit 1
fi

echo
echo "All registered runners are online across all requested scopes."
