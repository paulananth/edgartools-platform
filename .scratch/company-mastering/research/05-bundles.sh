#!/usr/bin/env bash
# Ticket 05, step 5: one Name Census and one bundle per captured chunk, with
# the production commands (`mdm name-census`, `mdm prepare-clean-company`).
# The census counts only its own capture's filers; `prepare-clean-company`
# refuses a census of any other capture. No active rule reads it, so it
# changes no outcome here; it makes name-rule numbers from this run
# worthless, and none are reported. The network is blocked throughout.
#
#   bash .scratch/company-mastering/research/05-bundles.sh <work-dir> <gleif-dir> <first> <last>
set -euo pipefail
W=$1
G=$2
FIRST=$3
LAST=$4
LANDING=$W/silver-landing
MANIFESTS=$LANDING/manifests/workflow_name=silver_landing_bootstrap_batch/business_date=2026-09-26
TICKERS=$LANDING/manifests/workflow_name=silver_landing_reference_catalog/business_date=2026-09-02/run_id=local-cm05-tickers-20260902/run_manifest.json
BLOCK=(env HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9
  https_proxy=http://127.0.0.1:9 http_proxy=http://127.0.0.1:9
  AWS_ACCESS_KEY_ID=blocked AWS_SECRET_ACCESS_KEY=blocked)
mkdir -p "$W/census" "$W/bundles"
for n in $(seq "$FIRST" "$LAST"); do
  M=$MANIFESTS/run_id=local-cm05-chunk$n/run_manifest.json
  if [ ! -f "$W/census/chunk$n.json" ]; then
    date "+chunk$n census start %H:%M:%S"
    "${BLOCK[@]}" uv run --no-sync edgar-warehouse mdm name-census \
      --landing-root "$LANDING" --landing-manifest "$M" \
      --gleif-archive "$G/01-20260911-1600-gleif-goldencopy-lei2-golden-copy.json.zip" \
      --gleif-metadata "$W/gleif-metadata.json" \
      --gleif-sha256 1b6cd9cda3f94269fd406ee481842ea042b699e95eb5b8124b1496d4fda36a6a \
      --output "$W/census/chunk$n.json" > "$W/census/chunk$n.log" 2>&1
  fi
  date "+chunk$n prepare start %H:%M:%S"
  "${BLOCK[@]}" uv run --no-sync edgar-warehouse mdm prepare-clean-company \
    --landing-root "$LANDING" --landing-manifest "$M" \
    --ticker-manifest "$TICKERS" --name-census "$W/census/chunk$n.json" \
    --output "$W/bundles/chunk$n" \
    --as-of 2026-09-26T15:00:00Z --revision 0 --limit 1000 > "$W/bundles/chunk$n.log" 2>&1
  date "+chunk$n done %H:%M:%S"
done
