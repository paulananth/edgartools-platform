# 04 — Manual End-to-End Validation

Type: task
Status: open
Blocked by: 02
Blocks: 06

## Task

Before any automated fetch is built, manually validate ticket 02's parser
decision against real data end-to-end, per the blocker doc's step 3: stage
the already-downloaded (or freshly re-fetched, per the blocker doc's re-fetch
command) July 2026 registered + exempt archives to S3, hand-build an
`ingest-relationship-sources` source manifest, run it as an ECS task
(requires the full `silver.duckdb` — must run in AWS, same lesson as the
Ticket 20 freeze rebuild that motivated the `mdm
build-relationship-release-manifest` S3-streaming command this session),
and confirm:

- `sec_adv_filing` / `sec_adv_office` / `sec_adv_disclosure_event` row counts
  jump from the current near-zero baseline to thousands, matching the new
  parser's target format.
- `mdm run --entity-type adviser --entity-type fund` →
  `mdm derive-relationships` → `mdm sync-graph` →
  `mdm verify-graph --skip-native-app` → `mdm graph-activate` → final
  `mdm verify-graph` produce real adviser/fund nodes and (if ticket 02 kept
  `MANAGES_FUND`) real edges in the graph — not just the placeholder 112
  nodes / 1 edge counts left over from this session's Ticket-20-driven graph
  refresh.

## Answer

(pending — records what was actually run, row counts observed, and any
findings that change ticket 02's decision)
