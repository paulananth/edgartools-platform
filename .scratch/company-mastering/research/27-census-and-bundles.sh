#!/usr/bin/env bash
# Ticket 27, steps 4 and 5, with the production commands and the network
# blocked:
#   4. one Name Census over all 69 captures (every SEC filer in the pinned
#      bronze copy) and the full GLEIF Golden Copy (`mdm name-census`,
#      repeatable --landing-manifest since ticket 26);
#   5. one bundle for each of the seven cohort captures (ticket 05's 7,000
#      filers), from that census (`mdm prepare-clean-company`).
#
#   bash .scratch/company-mastering/research/27-census-and-bundles.sh
set -euo pipefail
W=$HOME/.local/share/edgartools/clean-mdm/proving/cm27
G=$HOME/.local/share/edgartools/clean-mdm/research/gleif-20260911-1600
LANDING=$W/silver-landing
MANIFESTS=$LANDING/manifests/workflow_name=silver_landing_bootstrap_batch/business_date=2026-09-29
TICKERS=$LANDING/manifests/workflow_name=silver_landing_reference_catalog/business_date=2026-09-02/run_id=local-cm27-tickers-20260902/run_manifest.json
BLOCK=(env HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9
  https_proxy=http://127.0.0.1:9 http_proxy=http://127.0.0.1:9
  AWS_ACCESS_KEY_ID=blocked AWS_SECRET_ACCESS_KEY=blocked)
ARGS=()
for n in $(seq 1 69); do
  ARGS+=(--landing-manifest "$MANIFESTS/run_id=local-cm27-chunk$n/run_manifest.json")
done
if [ ! -f "$W/census.json" ]; then
  date "+census start %H:%M:%S"
  "${BLOCK[@]}" uv run --no-sync edgar-warehouse mdm name-census \
    --landing-root "$LANDING" "${ARGS[@]}" \
    --gleif-archive "$G/01-20260911-1600-gleif-goldencopy-lei2-golden-copy.json.zip" \
    --gleif-metadata "$W/gleif-metadata.json" \
    --gleif-sha256 1b6cd9cda3f94269fd406ee481842ea042b699e95eb5b8124b1496d4fda36a6a \
    --output "$W/census.json" > "$W/census.log" 2>&1
  date "+census done %H:%M:%S"
fi
mkdir -p "$W/bundles"
for n in $(seq 1 7); do
  [ -d "$W/bundles/chunk$n" ] && continue
  "${BLOCK[@]}" uv run --no-sync edgar-warehouse mdm prepare-clean-company \
    --landing-root "$LANDING" --landing-manifest "$MANIFESTS/run_id=local-cm27-chunk$n/run_manifest.json" \
    --ticker-manifest "$TICKERS" --name-census "$W/census.json" \
    --output "$W/bundles/chunk$n" \
    --as-of 2026-09-29T15:00:00Z --revision 0 --limit 1000 > "$W/bundles/chunk$n.log" 2>&1
  date "+chunk$n bundle done %H:%M:%S"
done
