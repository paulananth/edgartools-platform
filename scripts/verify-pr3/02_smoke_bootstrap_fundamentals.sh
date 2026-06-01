#!/usr/bin/env bash
# ── PR-3 Stage 2 — bootstrap-fundamentals CLI + windowing smoke ──
#
# Offline gate (deterministic, no network):
#   - CLI accepts --cik-offset/--cik-limit and makes --cik-list optional
#   - explicit --cik-list still parses
#   - _resolve_fundamentals_ciks windows an explicit list offset-then-limit
#     (mirrors Branch A bootstrap-next so both branches process identical windows)
#   - _validate_window_args rejects negative offset / non-positive limit
#
# Best-effort (skipped gracefully on network/MDM constraints):
#   - a real per-filing run for one CIK against a throwaway silver shard,
#     asserting the command exits 0 and the fundamentals tables are created.

# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/00_lib.sh"

step "Stage 2 — bootstrap-fundamentals CLI + windowing smoke"

# ── Offline CLI + helper checks (the gate) ────────────────────────────
CHECKER="$(mktemp)"
trap 'rm -f "$CHECKER"' EXIT
cat > "$CHECKER" <<'PY'
import sys

results = []
def chk(cond, msg):
    results.append(("PASS" if cond else "FAIL", msg))

# 1–2. CLI surface
try:
    import edgar_warehouse.cli as cli
    p = cli.build_parser()
    ns = p.parse_args(["bootstrap-fundamentals", "--mode", "entity-facts",
                       "--cik-offset", "500", "--cik-limit", "500"])
    chk(ns.command == "bootstrap-fundamentals" and ns.cik_offset == 500
        and ns.cik_limit == 500 and ns.cik_list is None,
        "CLI: --cik-offset/--cik-limit parse; --cik-list optional")
    ns2 = p.parse_args(["bootstrap-fundamentals", "--cik-list", "320193,789019"])
    chk(ns2.cik_list == [320193, 789019] and ns2.cik_offset == 0 and ns2.cik_limit is None,
        "CLI: explicit --cik-list still parses (offset=0, limit=None)")
except Exception as exc:
    chk(False, f"CLI parse raised: {exc!r}")

# 3. Windowing helper (explicit list path — no MDM/network needed)
try:
    from edgar_warehouse.application.commands.bootstrap_fundamentals import (
        _resolve_fundamentals_ciks,
    )
    sliced = _resolve_fundamentals_ciks(
        raw_cik_list=[10, 20, 30, 40, 50, 60], cik_offset=2, cik_limit=3
    )
    chk(sliced == [30, 40, 50], f"windowing: offset=2 limit=3 -> [30,40,50] (got {sliced})")
    nolimit = _resolve_fundamentals_ciks(
        raw_cik_list=[1, 2, 3], cik_offset=1, cik_limit=None
    )
    chk(nolimit == [2, 3], f"windowing: offset=1 no-limit -> [2,3] (got {nolimit})")
    full = _resolve_fundamentals_ciks(raw_cik_list=[7, 8], cik_offset=0, cik_limit=None)
    chk(full == [7, 8], f"windowing: offset=0 no-limit -> unchanged (got {full})")
except Exception as exc:
    chk(False, f"_resolve_fundamentals_ciks raised: {exc!r}")

# 4. Window-arg validation rejects bad input
try:
    from edgar_warehouse.application.commands.bootstrap_fundamentals import (
        _resolve_fundamentals_ciks as _rf,
    )
    bad_offset = False
    try:
        _rf(raw_cik_list=[1, 2], cik_offset=-1, cik_limit=None)
    except Exception:
        bad_offset = True
    chk(bad_offset, "validation: negative --cik-offset rejected")
    bad_limit = False
    try:
        _rf(raw_cik_list=[1, 2], cik_offset=0, cik_limit=0)
    except Exception:
        bad_limit = True
    chk(bad_limit, "validation: non-positive --cik-limit rejected")
except Exception as exc:
    chk(False, f"validation checks raised: {exc!r}")

for status, msg in results:
    print(f"{status}\t{msg}")
sys.exit(0 if all(s == "PASS" for s, _ in results) else 1)
PY

while IFS=$'\t' read -r status msg; do
    case "$status" in
        PASS) ok "$msg" ;;
        FAIL) fail_check "$msg" ;;
        *)    [[ -n "$status" ]] && warn "checker: $status $msg" ;;
    esac
done < <(py_run "$CHECKER" || true)

# ── Best-effort real per-filing run (non-fatal) ───────────────────────
# Apple (CIK 320193) files 8-K + DEF 14A regularly.  With an explicit
# --cik-list the run takes the raw-list path (no MDM needed).  A cold local
# shard has no bronze artifacts, so 0 filings processed is fine — we only
# assert the command exits 0 and creates the fundamentals tables.
step "Stage 2 (best-effort) — local per-filing run, CIK 320193"

SMOKE_DIR="$(mktemp -d)"
SMOKE_SHARD="${SMOKE_DIR}/silver/fundamentals/shard-0.duckdb"
mkdir -p "$(dirname "$SMOKE_SHARD")"

# Build the runner as an explicit argv array.  00_lib.sh sets IFS=$'\n\t'
# (no space), so an unquoted default like `uv run edgar-warehouse` would NOT
# word-split — it would be treated as one command name (rc=127).  Split on
# spaces explicitly, falling back to the default array.
if [[ -n "${EDGAR_WAREHOUSE_CMD:-}" ]]; then
    IFS=' ' read -r -a EW_CMD <<<"$EDGAR_WAREHOUSE_CMD"
else
    EW_CMD=(uv run edgar-warehouse)
fi

set +e
SMOKE_OUT="${SMOKE_DIR}/run.out"
( cd "$REPO_ROOT" && \
  "${EW_CMD[@]}" bootstrap-fundamentals \
    --cik-list 320193 --mode per-filing --cik-limit 1 \
    --fundamentals-silver-path "$SMOKE_SHARD" --run-id verify-pr3-smoke \
) >"$SMOKE_OUT" 2>&1
SMOKE_RC=$?
set -e

if [[ $SMOKE_RC -eq 0 && -f "$SMOKE_SHARD" ]]; then
    ok "real per-filing run exited 0 and created the fundamentals shard"
    # Verify the two per-filing tables exist in the shard.
    set +e
    TABLES_OK=$(py_run - "$SMOKE_SHARD" <<'PY'
import sys
try:
    import duckdb
    con = duckdb.connect(sys.argv[1], read_only=True)
    names = {r[0].lower() for r in con.execute("SHOW TABLES").fetchall()}
    con.close()
    need = {"sec_earnings_release", "sec_executive_record"}
    print("YES" if need.issubset(names) else f"NO missing={need - names}")
except Exception as exc:
    print(f"ERR {exc!r}")
PY
)
    set -e
    if [[ "$TABLES_OK" == "YES" ]]; then
        ok "shard contains sec_earnings_release + sec_executive_record"
    else
        warn "could not confirm per-filing tables ($TABLES_OK) — non-fatal"
    fi
else
    warn "best-effort per-filing run skipped/failed (rc=$SMOKE_RC) — non-fatal (network/MDM/bronze may be unavailable)"
    warn "last lines of run output:"
    tail -n 5 "$SMOKE_OUT" 2>/dev/null | sed 's/^/      /' >&2 || true
fi

rm -rf "$SMOKE_DIR" 2>/dev/null || true

print_summary "2 bootstrap-fundamentals-smoke"
