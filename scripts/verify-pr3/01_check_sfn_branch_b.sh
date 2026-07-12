#!/usr/bin/env bash
# ── PR-3 Stage 1 — Step Function Branch B structural integrity ──
#
# Authoritative offline gate.  Extracts write_load_history_definition() from
# infra/scripts/deploy-aws-application.sh, runs it with placeholder ARNs (no AWS
# calls — the function only writes JSON), then validates the generated
# load_history ASL:
#   - ComputeWindows routes to Stage1Parallel (not the old WindowedBootstrap)
#   - Stage1Parallel is a Parallel state with exactly 2 branches
#   - Branch A (ownership) runs bootstrap-next, terminal Map, MaxConcurrency=1
#   - Branch B (fundamentals) runs bootstrap-fundamentals per-filing -> entity-facts
#   - Branch B uses --cik-offset/--cik-limit windowing (no --cik-list)
#   - Branch B Maps Catch -> BranchBComplete (AD-13: partial failure accepted)
#   - MDM chain still follows Stage1Parallel
#
# No Snowflake creds, no AWS creds, no network.

# shellcheck disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/00_lib.sh"

DEPLOY_SCRIPT="${REPO_ROOT}/infra/scripts/deploy-aws-application.sh"

step "Stage 1 — Step Function Branch B structural integrity"

require_file "$DEPLOY_SCRIPT"
require_command awk

# ── 1. File-level sanity: function exists ─────────────────────────────
if grep -q '^write_load_history_definition() {' "$DEPLOY_SCRIPT"; then
    ok "write_load_history_definition() defined in deploy-aws-application.sh"
else
    fail_check "write_load_history_definition() not found in deploy script"
    print_summary "1 sfn-branch-b-structure"
    exit 1
fi

# ── 2. Extract the function in isolation ──────────────────────────────
# The deploy script runs deployment at top-level (no main guard), so we cannot
# source it directly.  Extract just this function: print from its opening line
# through the closing brace that follows the function's `PY` heredoc terminator.
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT
FN_FILE="${WORKDIR}/fn.sh"
OUT_JSON="${WORKDIR}/load_history.json"

awk '
    /^write_load_history_definition\(\) \{/ { f = 1 }
    f { print }
    f && /^PY$/ { p = 1; next }
    f && p && /^\}/ { exit }
' "$DEPLOY_SCRIPT" > "$FN_FILE"

if [[ -s "$FN_FILE" ]] && tail -n1 "$FN_FILE" | grep -q '^}'; then
    ok "extracted write_load_history_definition() ($(wc -l < "$FN_FILE" | tr -d ' ') lines)"
else
    fail_check "function extraction failed (empty or unterminated)"
    print_summary "1 sfn-branch-b-structure"
    exit 1
fi

# ── 3. Run the function with placeholder inputs (writes JSON only) ─────
cat > "${WORKDIR}/run.sh" <<RUN
set -euo pipefail
PLACEHOLDER_ACCOUNT_ID="\$(printf '%012d' 0)"
CLUSTER_ARN="arn:aws:ecs:us-east-1:\${PLACEHOLDER_ACCOUNT_ID}:cluster/verify-pr3"
BRONZE_BUCKET_NAME="verify-pr3-bronze"
PUBLIC_SUBNET_IDS_JSON='["subnet-aaaa","subnet-bbbb"]'
SECURITY_GROUP_IDS_JSON='["sg-aaaa"]'
MDM_RUN_LIMIT="1000"
MDM_GRAPH_LIMIT="1000"
MDM_SEED_UNIVERSE_TRACKING_STATUS="bootstrap_pending"
source "$FN_FILE"
write_load_history_definition "$OUT_JSON" \
  "arn:wh-small" "arn:wh-medium" "arn:mdm-small" "arn:mdm-medium" "arn:wh-large"
RUN

if bash "${WORKDIR}/run.sh"; then
    ok "write_load_history_definition() produced load_history JSON"
else
    fail_check "write_load_history_definition() failed to run"
    print_summary "1 sfn-branch-b-structure"
    exit 1
fi

require_file "$OUT_JSON"

# ── 4. Validate JSON structure ────────────────────────────────────────
# The Python validator prints one PASS/FAIL line per check (machine-readable
# "PASS <msg>" / "FAIL <msg>"); the bash loop converts each into ok/fail_check
# so they roll into the stage summary.
VALIDATOR="${WORKDIR}/validate.py"
cat > "$VALIDATOR" <<'PY'
import json, sys

d = json.load(open(sys.argv[1]))
S = d["States"]
results = []

def chk(cond, msg):
    results.append(("PASS" if cond else "FAIL", msg))

chk(S.get("ComputeWindows", {}).get("Next") == "Stage1Parallel",
    "ComputeWindows routes to Stage1Parallel")
chk("Stage1Parallel" in S, "Stage1Parallel state present")
chk("WindowedBootstrap" not in S,
    "old top-level WindowedBootstrap removed from States")

sp = S.get("Stage1Parallel", {})
chk(sp.get("Type") == "Parallel", "Stage1Parallel.Type == Parallel")
chk(sp.get("ResultPath", "MISSING") is None, "Stage1Parallel.ResultPath is null")
chk(sp.get("Next") == "MdmRun", "Stage1Parallel.Next == MdmRun")
branches = sp.get("Branches", [])
chk(len(branches) == 2, "Stage1Parallel has exactly 2 branches")

if len(branches) == 2:
    # ── Branch A (ownership) ──
    bA = branches[0]
    chk(bA.get("StartAt") == "WindowedBootstrap", "Branch A StartAt == WindowedBootstrap")
    wb = bA.get("States", {}).get("WindowedBootstrap", {})
    chk(wb.get("Type") == "Map", "Branch A WindowedBootstrap is a Map")
    chk(wb.get("End") is True and "Next" not in wb,
        "Branch A WindowedBootstrap terminal (End=true, no Next)")
    chk(wb.get("MaxConcurrency") == 1, "Branch A MaxConcurrency == 1")
    try:
        cmdA = wb["ItemProcessor"]["States"]["RunWindow"]["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    except Exception:
        cmdA = ""
    chk("'bootstrap-next'" in cmdA, "Branch A command runs bootstrap-next")

    # ── Branch B (fundamentals) ──
    bB = branches[1]
    chk(bB.get("StartAt") == "FundamentalsPerFiling", "Branch B StartAt == FundamentalsPerFiling")
    bBs = bB.get("States", {})
    chk(all(k in bBs for k in ("FundamentalsPerFiling", "FundamentalsEntityFacts", "BranchBComplete")),
        "Branch B has FundamentalsPerFiling + FundamentalsEntityFacts + BranchBComplete")
    fpf = bBs.get("FundamentalsPerFiling", {})
    fef = bBs.get("FundamentalsEntityFacts", {})
    chk(fpf.get("Type") == "Map" and fef.get("Type") == "Map", "Branch B stages are Maps")
    chk(fpf.get("MaxConcurrency") == 1 and fef.get("MaxConcurrency") == 1,
        "Branch B Maps MaxConcurrency == 1")
    chk(fpf.get("Next") == "FundamentalsEntityFacts", "per-filing -> entity-facts")
    chk(fef.get("End") is True and "Next" not in fef,
        "entity-facts terminal Map (End=true, no Next)")
    bc = bBs.get("BranchBComplete", {})
    chk(bc.get("Type") == "Pass" and bc.get("End") is True, "BranchBComplete is terminal Pass")
    for nm in ("FundamentalsPerFiling", "FundamentalsEntityFacts"):
        c = bBs.get(nm, {}).get("Catch", [])
        good = bool(c) and c[0].get("Next") == "BranchBComplete" and c[0].get("ErrorEquals") == ["States.ALL"]
        chk(good, f"{nm} Catch routes States.ALL -> BranchBComplete (AD-13)")
    try:
        cmdPF = fpf["ItemProcessor"]["States"]["RunFundamentalsPerFiling"]["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    except Exception:
        cmdPF = ""
    try:
        cmdEF = fef["ItemProcessor"]["States"]["RunFundamentalsEntityFacts"]["Parameters"]["Overrides"]["ContainerOverrides"][0]["Command.$"]
    except Exception:
        cmdEF = ""
    chk("'bootstrap-fundamentals'" in cmdPF and "'per-filing'" in cmdPF,
        "per-filing command: bootstrap-fundamentals --mode per-filing")
    chk("'bootstrap-fundamentals'" in cmdEF and "'entity-facts'" in cmdEF,
        "entity-facts command: bootstrap-fundamentals --mode entity-facts")
    chk("'--cik-offset'" in cmdPF and "'--cik-limit'" in cmdPF and "'--cik-list'" not in cmdPF,
        "Branch B windows via --cik-offset/--cik-limit (no --cik-list)")

# ── MDM chain intact ──
chk(S.get("MdmRun", {}).get("Next") == "MdmBackfill", "MdmRun present, chains to MdmBackfill")
chk("GoldRefresh" in S and "WriteRunSummary" in S, "GoldRefresh + WriteRunSummary still present")

for status, msg in results:
    print(f"{status}\t{msg}")

sys.exit(0 if all(s == "PASS" for s, _ in results) else 1)
PY

# Drive the validator; convert each PASS/FAIL line into a stage check.
while IFS=$'\t' read -r status msg; do
    case "$status" in
        PASS) ok "$msg" ;;
        FAIL) fail_check "$msg" ;;
        *)    [[ -n "$status" ]] && warn "validator: $status $msg" ;;
    esac
done < <(py_run "$VALIDATOR" "$OUT_JSON" || true)

print_summary "1 sfn-branch-b-structure"
