#!/usr/bin/env bash
# sync-relationships.sh
#
# Derives + syncs relationships only — skips entity resolution.
# Use this after entities are already populated (e.g. the day after a full
# universe sync) or when iterating on a specific relationship type.
#
#   1. Derive 10 types  (all except INSTITUTIONAL_HOLDS)
#   2. Derive INSTITUTIONAL_HOLDS  (separate OOM-safe cap)
#   3. Snowflake graph sync
#   4. Counts snapshot
#
# Usage:
#   ./scripts/ops/sync-relationships.sh
#   ./scripts/ops/sync-relationships.sh --limit 500
#   ./scripts/ops/sync-relationships.sh --type EMPLOYED_BY --type AUDITED_BY
#   ./scripts/ops/sync-relationships.sh --skip-graph-sync
#   ./scripts/ops/sync-relationships.sh --limit 500 --dry-run

set -euo pipefail

# ── defaults ──────────────────────────────────────────────────────────────────
LIMIT=""
SKIP_GRAPH_SYNC=false
DRY_RUN=false
TYPES=()                          # empty = all 11 types
INSTITUTIONAL_HOLDS_CAP=5000

# ── parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --limit)            LIMIT="$2";                         shift 2 ;;
        --limit=*)          LIMIT="${1#*=}";                    shift   ;;
        --type)             TYPES+=("$2");                      shift 2 ;;
        --type=*)           TYPES+=("${1#*=}");                 shift   ;;
        --skip-graph-sync)  SKIP_GRAPH_SYNC=true;               shift   ;;
        --dry-run)          DRY_RUN=true;                       shift   ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

TARGET_PER_TYPE=${LIMIT:-10000}

# ── helpers ───────────────────────────────────────────────────────────────────
hr() { printf '\n\e[1;36m══ %s ══\e[0m\n' "$1"; }
ok() { printf '  \e[32m✓\e[0m  %s\n' "$1"; }
info() { printf '  ·  %s\n' "$1"; }
err() { printf '\n\e[31m✗  %s\e[0m\n' "$1" >&2; exit 1; }
ts() { date '+%H:%M:%S'; }

run() {
    local label="$1"; shift
    info "$(ts)  $*"
    if [[ "$DRY_RUN" == "true" ]]; then
        info "[dry-run] skipped"
        return 0
    fi
    "$@" || err "$label failed (exit $?)"
    ok "$label"
}

# ── snowflake preflight ───────────────────────────────────────────────────────
_sf_env() { local a="MDM_SNOWFLAKE_$1" b="DBT_SNOWFLAKE_$1"; echo "${!a:-${!b:-}}"; }

# Resolve the Snowflake CLI connection name via Python's tomllib (regex-based
# bash grep on TOML section headers is fragile across grep implementations —
# BSD grep on macOS handles \[ \] in BRE differently than GNU grep).
# Prints the connection name if found in ~/.snowflake/connections.toml, else "".
_snowflake_cli_connection() {
    SNOWFLAKE_CONNECTION="${SNOWFLAKE_CONNECTION:-}" python3 - <<'PYEOF' 2>/dev/null
import os, pathlib

home = pathlib.Path.home()
conn_name = os.environ.get("SNOWFLAKE_CONNECTION", "")

if not conn_name:
    cfg = home / ".snowflake" / "config.toml"
    if cfg.exists():
        try:
            import tomllib
            conn_name = tomllib.load(cfg.open("rb")).get("default_connection_name", "")
        except Exception:
            pass
conn_name = conn_name or "snowconn"

p = home / ".snowflake" / "connections.toml"
if not p.exists():
    print("", end="")
else:
    try:
        import tomllib
        found = conn_name in tomllib.load(p.open("rb"))
    except Exception:
        import re
        found = bool(re.search(r"^\[" + re.escape(conn_name) + r"\]", p.read_text(), re.MULTILINE))
    print(conn_name if found else "", end="")
PYEOF
}

check_snowflake_env() {
    local has_env=false conn_name=""

    [[ -n "$(_sf_env ACCOUNT)" ]] && has_env=true

    if [[ "$has_env" == "false" ]]; then
        conn_name="$(_snowflake_cli_connection)"
        [[ -n "$conn_name" ]] && export SNOWFLAKE_CONNECTION="$conn_name"
    fi

    if [[ "$has_env" == "false" && -z "$conn_name" ]]; then
        printf '\n\e[31m✗  Snowflake credentials not found.\e[0m\n' >&2
        printf '   Option A — env vars:\n' >&2
        printf '     export MDM_SNOWFLAKE_ACCOUNT=...\n' >&2
        printf '     export MDM_SNOWFLAKE_USER=...\n' >&2
        printf '     export MDM_SNOWFLAKE_PASSWORD=...\n' >&2
        printf '     export MDM_SNOWFLAKE_DATABASE=EDGARTOOLS_DEV\n' >&2
        printf '     export MDM_SNOWFLAKE_WAREHOUSE=...\n' >&2
        printf '   Option B — Snowflake CLI config (~/.snowflake/connections.toml):\n' >&2
        printf '     export MDM_SNOWFLAKE_DATABASE=EDGARTOOLS_DEV  # only missing piece\n' >&2
        printf '   Or re-run with --skip-graph-sync to skip Snowflake steps.\n\n' >&2
        exit 1
    fi

    if [[ -n "$conn_name" && -z "$(_sf_env DATABASE)" ]]; then
        printf '\n\e[31m✗  MDM_SNOWFLAKE_DATABASE is not set.\e[0m\n' >&2
        printf '   Using ~/.snowflake/connections.toml [%s] for other creds,\n' "$conn_name" >&2
        printf '   but the database is not in the connection entry.\n' >&2
        printf '     export MDM_SNOWFLAKE_DATABASE=EDGARTOOLS_DEV\n' >&2
        printf '   Or re-run with --skip-graph-sync.\n\n' >&2
        exit 1
    fi

    if [[ "$has_env" == "true" ]]; then
        info "Snowflake creds   = env vars"
    else
        info "Snowflake creds   = ~/.snowflake/connections.toml [$conn_name]"
    fi
    info "Snowflake DB      = $(_sf_env DATABASE)"
}

# ── preflight ─────────────────────────────────────────────────────────────────
hr "Preflight"

[[ -n "${MDM_DATABASE_URL:-}" ]] || err "MDM_DATABASE_URL is not set"
[[ -n "${MDM_SILVER_DUCKDB:-}${WAREHOUSE_STORAGE_ROOT:-}" ]] \
    || err "Set MDM_SILVER_DUCKDB (local path or s3://) or WAREHOUSE_STORAGE_ROOT"
[[ "$SKIP_GRAPH_SYNC" == "true" ]] || check_snowflake_env

# Resolve which types to run
ALL_STANDARD_TYPES=(
    IS_INSIDER HOLDS COMPANY_HOLDS ISSUED_BY IS_ENTITY_OF
    HAS_PARENT_COMPANY MANAGES_FUND IS_PERSON_OF EMPLOYED_BY AUDITED_BY
)

if [[ ${#TYPES[@]} -gt 0 ]]; then
    # Explicit --type flags: split INSTITUTIONAL_HOLDS out if present
    STANDARD_TYPES=()
    RUN_INSTITUTIONAL=false
    for t in "${TYPES[@]}"; do
        if [[ "$t" == "INSTITUTIONAL_HOLDS" ]]; then
            RUN_INSTITUTIONAL=true
        else
            STANDARD_TYPES+=("$t")
        fi
    done
else
    STANDARD_TYPES=("${ALL_STANDARD_TYPES[@]}")
    RUN_INSTITUTIONAL=true
fi

info "MDM_DATABASE_URL      = ${MDM_DATABASE_URL%%@*}@***"
info "MDM_SILVER_DUCKDB     = ${MDM_SILVER_DUCKDB:-<via WAREHOUSE_STORAGE_ROOT>}"
info "TARGET_PER_TYPE       = $TARGET_PER_TYPE"
info "INSTITUTIONAL_HOLDS_CAP = $INSTITUTIONAL_HOLDS_CAP"
info "RUN_INSTITUTIONAL     = $RUN_INSTITUTIONAL"
info "TYPES (standard)      = ${STANDARD_TYPES[*]:-none}"
info "SKIP_GRAPH_SYNC       = $SKIP_GRAPH_SYNC"
info "DRY_RUN               = $DRY_RUN"

STARTED=$(date +%s)

# ── step 1: derive standard relationship types ────────────────────────────────
if [[ ${#STANDARD_TYPES[@]} -gt 0 ]]; then
    hr "Step 1 — Derive relationships (${#STANDARD_TYPES[@]} types)"
    DERIVE_ARGS=(uv run edgar-warehouse mdm derive-relationships)
    for t in "${STANDARD_TYPES[@]}"; do
        DERIVE_ARGS+=(--relationship-type "$t")
    done
    DERIVE_ARGS+=(--target-per-type "$TARGET_PER_TYPE")
    run "derive (standard types)" "${DERIVE_ARGS[@]}"
else
    hr "Step 1 — Derive standard types  [SKIPPED — none selected]"
fi

# ── step 2: derive INSTITUTIONAL_HOLDS (OOM-safe separate run) ────────────────
if [[ "$RUN_INSTITUTIONAL" == "true" ]]; then
    hr "Step 2 — Derive INSTITUTIONAL_HOLDS (cap: $INSTITUTIONAL_HOLDS_CAP)"
    info "sec_thirteenf_holding is the largest silver table — running separately"
    info "with a lower cap until the batch-by-CIK fix lands in plan 06-03."
    run "derive INSTITUTIONAL_HOLDS" uv run edgar-warehouse mdm derive-relationships \
        --relationship-type INSTITUTIONAL_HOLDS \
        --target-per-type "$INSTITUTIONAL_HOLDS_CAP"
else
    hr "Step 2 — INSTITUTIONAL_HOLDS  [SKIPPED]"
fi

# ── step 3: Snowflake graph sync ──────────────────────────────────────────────
if [[ "$SKIP_GRAPH_SYNC" == "false" ]]; then
    hr "Step 3 — Snowflake graph sync"
    SYNC_ARGS=(uv run edgar-warehouse mdm sync-graph --limit-per-type "$TARGET_PER_TYPE")
    # If specific types were requested, scope the sync to match
    if [[ ${#TYPES[@]} -gt 0 ]]; then
        for t in "${TYPES[@]}"; do
            SYNC_ARGS+=(--relationship-type "$t")
        done
    fi
    run "sync-graph" "${SYNC_ARGS[@]}"
else
    hr "Step 3 — Snowflake graph sync  [SKIPPED]"
fi

# ── step 4: counts snapshot ───────────────────────────────────────────────────
hr "Step 4 — Counts"
if [[ "$DRY_RUN" == "false" ]]; then
    uv run edgar-warehouse mdm counts 2>/dev/null \
        | python3 -c "
import sys, json
d = json.load(sys.stdin)
print()
print(f\"  {'TYPE':<30} {'ACTIVE':>8}  {'PENDING_SYNC':>12}\")
print('  ' + '-'*56)
for k, v in sorted(d.get('relationships_by_type', {}).items()):
    flag = '  ← pending' if v['pending_graph_sync'] > 0 else ''
    print(f\"  {k:<30} {v['active']:>8}  {v['pending_graph_sync']:>12}{flag}\")
print()
"
fi

# ── done ──────────────────────────────────────────────────────────────────────
ELAPSED=$(( $(date +%s) - STARTED ))
printf '\n\e[1;32m══ Done in %dm %ds ══\e[0m\n\n' $((ELAPSED/60)) $((ELAPSED%60))
