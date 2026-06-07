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

# ── preflight ─────────────────────────────────────────────────────────────────
hr "Preflight"

[[ -n "${MDM_DATABASE_URL:-}" ]]  || err "MDM_DATABASE_URL is not set"
[[ -n "${MDM_SILVER_DUCKDB:-}${WAREHOUSE_STORAGE_ROOT:-}" ]] \
    || err "Set MDM_SILVER_DUCKDB (local path or s3://) or WAREHOUSE_STORAGE_ROOT"

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
