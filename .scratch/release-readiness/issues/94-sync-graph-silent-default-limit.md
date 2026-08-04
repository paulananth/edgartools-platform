# 94 — `mdm sync-graph` silently caps at ~200 edges when no explicit limit is given

Type: task
Status: open

## Question

Found live 2026-08-04 while resolving [ticket 06](06-define-full-chain-launch-gate.md)'s
INSTITUTIONAL_HOLDS graph-sync gap. Running `mdm sync-graph` via the
`edgartools-prod-mdm-sync-graph` state machine with empty input (`{}}`, its normal
invocation) produced a generation with only **200 total edges** (198 `MANAGES_FUND` + 2
`ISSUED_BY`) despite MDM having real, much larger counts for 7 populated relationship
types (`INSTITUTIONAL_HOLDS` alone: 50,000). Neither `--limit` nor `--limit-per-type`
states a default in the CLI `--help` text, and both resolve to `None` at the argparse
level (`edgar_warehouse/mdm/cli.py`) -- the cap is applied somewhere downstream, most
likely inside `render_graph_tables`'s SQL template (`edgar_warehouse/mdm/snowflake_graph.py`),
not yet traced to the exact line.

Confirmed the fix is just passing an explicit large `--limit-per-type` (tested `200000`):
produced a real full sync (204,281 nodes / 232,714 edges) with every populated
relationship type matching MDM's active count exactly.

**Compounding gap**: the `edgartools-prod-mdm-sync-graph` state machine's ASL only wires
`$.limit` from execution input into the ECS command override, not `$.limit_per_type` --
passing `{"limit_per_type": 200000}` as execution input was silently ignored (confirmed
via `get-execution-history`: fell through to the `RunMdmTaskDefault` branch). The only way
to get a real full sync was bypassing Step Functions entirely with a raw
`aws ecs run-task --overrides` call.

## What needs deciding

1. Where exactly does the ~200 default get applied, and should the true default for an
   unset `--limit-per-type` be unbounded (matches the CLI help text's implication) or an
   explicit, documented, much larger sane default -- either is defensible, but silent
   ~200 with no warning is not.
2. Wire `limit_per_type` (and ideally `limit`) into the state machine's Choice logic so a
   real full sync doesn't require bypassing Step Functions with a raw ECS task.
3. Same "silent small result looks identical to a real pass" shape as this ticket's own
   parent (ticket 06's `_TABLES` registration gap) and ticket 93's circuit-breaker
   miscount -- worth considering whether `sync-graph`'s completion output should warn
   when applied limits look suspiciously small relative to what a preflight pending-count
   query would show, rather than just reporting node/edge counts with no context.

## Done when

The silent-cap root cause is found and fixed (or the default is deliberately kept but
made loud/documented), `limit_per_type` is reachable through the state machine's normal
execution-input path, and a fresh default-args sync-graph run produces a real full sync
without needing an explicit override.
