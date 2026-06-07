#!/usr/bin/env bash
# full-universe-sync.sh
#
# Runs the complete MDM pipeline locally (Option B, step-by-step):
#   1. Entity resolution  — companies, advisers, persons, securities, funds
#   2. Backfill           — patches NULL issuer_entity_id, creates ISSUED_BY/MANAGES_FUND
#   3. Relationships      — all 11 types (INSTITUTIONAL_HOLDS capped separately)
#   4. Graph sync         — materialises Snowflake graph-ready node/edge tables
#   5. Verify             — asserts node/edge counts > 0
#   6. Counts snapshot    — prints final relationship breakdown
#
# Usage:
#   ./scripts/ops/full-universe-sync.sh                      # full universe, no caps
#   ./scripts/ops/full-universe-sync.sh --limit 500          # cap entities + rels per type
#   ./scripts/ops/full-universe-sync.sh --limit 500 --dry-run
#   ./scripts/ops/full-universe-sync.sh --skip-entities      # skip step 1 (entities current)
#   ./scripts/ops/full-universe-sync.sh --skip-graph-sync    # derive only, no Snowflake push

set -euo pipefail

# ── defaults ─────────────────────────────────────────────────────────────────
LIMIT=""                   # --limit N  caps entities-per-type AND target-per-type
SKIP_ENTITIES=false
SKIP_GRAPH_SYNC=false
DRY_RUN=false
INSTITUTIONAL_HOLDS_CAP=5000   # separate OOM-safe cap for the largest table

# ── parse args ────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --limit)            LIMIT="$2";            shift 2 ;;
        --limit=*)          LIMIT="${1#*=}";        shift   ;;
        --skip-entities)    SKIP_ENTITIES=true;     shift   ;;
        --skip-graph-sync)  SKIP_GRAPH_SYNC=true;   shift   ;;
        --dry-run)          DRY_RUN=true;           shift   ;;
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
# Supports two credential sources (checked in order):
#   1. MDM_SNOWFLAKE_* / DBT_SNOWFLAKE_* env vars
#   2. ~/.snowflake/connections.toml  [snowconn]  (or SNOWFLAKE_CONNECTION)
#
# When using connections.toml, MDM_SNOWFLAKE_DATABASE must still be set because
# the connection entry does not include the database name.  Example:
#   export MDM_SNOWFLAKE_DATABASE=EDGARTOOLS_DEV
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

[[ -n "${MDM_DATABASE_URL:-}" ]]  || err "MDM_DATABASE_URL is not set"
[[ -n "${MDM_SILVER_DUCKDB:-}${WAREHOUSE_STORAGE_ROOT:-}" ]] \
    || err "Set MDM_SILVER_DUCKDB (local path or s3://) or WAREHOUSE_STORAGE_ROOT"

# Validate Snowflake creds now — before any long-running steps — unless the
# user is intentionally skipping graph sync.
[[ "$SKIP_GRAPH_SYNC" == "true" ]] || check_snowflake_env

info "MDM_DATABASE_URL  = ${MDM_DATABASE_URL%%@*}@***"
info "MDM_SILVER_DUCKDB = ${MDM_SILVER_DUCKDB:-<via WAREHOUSE_STORAGE_ROOT>}"
info "LIMIT             = ${LIMIT:-none (full universe)}"
info "TARGET_PER_TYPE   = $TARGET_PER_TYPE"
info "INSTITUTIONAL_HOLDS_CAP = $INSTITUTIONAL_HOLDS_CAP"
info "SKIP_ENTITIES     = $SKIP_ENTITIES"
info "SKIP_GRAPH_SYNC   = $SKIP_GRAPH_SYNC"
info "DRY_RUN           = $DRY_RUN"

STARTED=$(date +%s)

# ── step 1: entity resolution ─────────────────────────────────────────────────
if [[ "$SKIP_ENTITIES" == "false" ]]; then
    hr "Step 1 — Entity resolution"
    ENTITY_ARGS=(edgar-warehouse mdm run --entity-type all)
    [[ -n "$LIMIT" ]] && ENTITY_ARGS+=(--limit "$LIMIT")
    run "entity resolution" uv run "${ENTITY_ARGS[@]}"
else
    hr "Step 1 — Entity resolution  [SKIPPED]"
    info "Assuming MDM entities are already current"
fi

# ── step 2: backfill (NULL issuer_entity_id → ISSUED_BY / MANAGES_FUND) ───────
hr "Step 2 — Backfill"
BACKFILL_LIMIT=${LIMIT:-10000}
run "backfill" uv run edgar-warehouse mdm backfill-relationships --limit "$BACKFILL_LIMIT"

# ── step 3a: derive 10 types (all except INSTITUTIONAL_HOLDS) ─────────────────
hr "Step 3a — Derive relationships (10 types)"
run "derive relationships (10 types)" uv run edgar-warehouse mdm derive-relationships \
    --relationship-type IS_INSIDER          \
    --relationship-type HOLDS               \
    --relationship-type COMPANY_HOLDS       \
    --relationship-type ISSUED_BY           \
    --relationship-type IS_ENTITY_OF        \
    --relationship-type HAS_PARENT_COMPANY  \
    --relationship-type MANAGES_FUND        \
    --relationship-type IS_PERSON_OF        \
    --relationship-type EMPLOYED_BY         \
    --relationship-type AUDITED_BY          \
    --target-per-type "$TARGET_PER_TYPE"

# ── step 3b: derive INSTITUTIONAL_HOLDS (OOM-safe separate run) ───────────────
hr "Step 3b — Derive INSTITUTIONAL_HOLDS (capped at $INSTITUTIONAL_HOLDS_CAP)"
# NOTE: sec_thirteenf_holding is the largest silver table (Vanguard/BlackRock have
# tens of thousands of positions per quarter). Running it separately with a lower
# cap guards against ECS memory exhaustion until the batch-by-CIK fix lands (06-03).
run "derive INSTITUTIONAL_HOLDS" uv run edgar-warehouse mdm derive-relationships \
    --relationship-type INSTITUTIONAL_HOLDS \
    --target-per-type "$INSTITUTIONAL_HOLDS_CAP"

# ── step 4: Snowflake graph sync ──────────────────────────────────────────────
if [[ "$SKIP_GRAPH_SYNC" == "false" ]]; then
    hr "Step 4 — Snowflake graph sync"
    run "sync-graph" uv run edgar-warehouse mdm sync-graph \
        --limit-per-type "$TARGET_PER_TYPE"
else
    hr "Step 4 — Snowflake graph sync  [SKIPPED]"
fi

# ── step 5: verify ────────────────────────────────────────────────────────────
if [[ "$SKIP_GRAPH_SYNC" == "false" ]]; then
    hr "Step 5 — Verify graph"
    run "verify-graph" uv run edgar-warehouse mdm verify-graph
fi

# ── step 6: counts snapshot ───────────────────────────────────────────────────
hr "Step 6 — Final counts"
if [[ "$DRY_RUN" == "false" ]]; then
    uv run edgar-warehouse mdm counts 2>/dev/null \
        | python3 -c "
import sys, json
d = json.load(sys.stdin)
print()
print(f\"  {'TYPE':<30} {'ACTIVE':>8}  {'PENDING_SYNC':>12}\")
print('  ' + '-'*56)
for k, v in sorted(d.get('relationships_by_type', {}).items()):
    print(f\"  {k:<30} {v['active']:>8}  {v['pending_graph_sync']:>12}\")
print()
"
fi

# ── done ──────────────────────────────────────────────────────────────────────
ELAPSED=$(( $(date +%s) - STARTED ))
printf '\n\e[1;32m══ Done in %dm %ds ══\e[0m\n\n' $((ELAPSED/60)) $((ELAPSED%60))
