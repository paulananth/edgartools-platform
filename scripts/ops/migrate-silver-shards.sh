#!/usr/bin/env bash
# migrate-silver-shards.sh — one-time migration from monolithic silver.duckdb to 4 CIK-band shards
#
# Usage:
#   migrate-silver-shards.sh <source-path> <output-dir> [--band-boundaries '<json>']
#
# Arguments:
#   source-path    Path to the monolithic silver.duckdb file (local path)
#   output-dir     Directory to write shard-{0..3}.duckdb and shard-manifest.json
#
# Optional flags passed through to edgar-warehouse migrate-silver-shards:
#   --band-boundaries  JSON array of custom band boundaries (override dev-DB defaults)
#
# IMPORTANT — run the production CIK percentile query FIRST:
#   See docs/runbook.md for the SQL query that computes p25/p50/p75 CIK quartiles
#   from the production silver.duckdb. Pass the result via --band-boundaries if
#   the production quartiles differ from the dev defaults:
#     p25 = 1053917  (shard-0: 0 – 1053917)
#     p50 = 1523562  (shard-1: 1053918 – 1523562)
#     p75 = 1819990  (shard-2: 1523563 – 1819990)
#               max  (shard-3: 1819991 – 9999999)
#
# After migration, verify the output before deploying:
#   1. Inspect shard-manifest.json — check shard_count, band boundaries, and checksums
#   2. Run a spot check: duckdb shard-0.duckdb -c "SELECT COUNT(*) FROM sec_company"
#   3. Upload shards to S3 and update the deployment manifest per D-12 in 09-CONTEXT.md

set -euo pipefail

if [ $# -lt 2 ]; then
  echo "Usage: migrate-silver-shards.sh <source-path> <output-dir> [extra edgar-warehouse args...]" >&2
  echo "" >&2
  echo "Example:" >&2
  echo "  migrate-silver-shards.sh /data/silver.duckdb /data/shards/" >&2
  echo "  migrate-silver-shards.sh /data/silver.duckdb /data/shards/ \\" >&2
  echo "    --band-boundaries '[{\"shard_index\":0,\"cik_min\":0,\"cik_max\":1053917},...]'" >&2
  exit 1
fi

SOURCE="$1"
OUTPUT_DIR="$2"
shift 2

echo "=== edgar-warehouse migrate-silver-shards ===" >&2
echo "Source:     $SOURCE" >&2
echo "Output dir: $OUTPUT_DIR" >&2
echo "" >&2

uv run edgar-warehouse migrate-silver-shards \
  --source "$SOURCE" \
  --output-dir "$OUTPUT_DIR" \
  "$@"
