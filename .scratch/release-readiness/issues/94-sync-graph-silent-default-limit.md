# 94 — `mdm sync-graph` silently caps at ~200 edges when no explicit limit is given

Type: task
Status: partially resolved (2026-08-20) — see `## Answer`. Items 2 and 3 done
and live in code; item 1's root cause corrected below (was misattributed);
a bigger, related bug found and fixed along the way (`run_companies`
plateau); one new decision (deploy-time defaults for 4 production machines)
deliberately NOT made here — flagged for the user, not implemented.

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

## Answer

**Item 1 (root cause) — corrected, not what this ticket originally said.**
This ticket's own text said the ~200 cap was "most likely inside
`render_graph_tables`'s SQL template ... not yet traced to the exact
line." Traced it live: it isn't in `snowflake_graph.py` at all. It's
`MDM_GRAPH_LIMIT=200` / `MDM_RUN_LIMIT=100`, plain deploy-script defaults
(`infra/scripts/deploy-aws-application.sh:213-214`), introduced in commit
`d3c24f4f` as a small-scale bump (100→200) for early testing and never
revisited for production scale. Confirmed live against the actual deployed
ASL: **4 production state machines bake `--limit 100`/`--limit 200`
unconditionally into their `MdmRun`/`MdmBackfill`/`MdmSync` states with no
per-execution override path at all** — `edgartools-prod-load-history`,
`edgartools-prod-daily-incremental`, `edgartools-prod-bootstrap`,
`edgartools-prod-mdm-gold`. By contrast, `edgartools-prod-silver-mdm-gold`,
`edgartools-prod-bronze-seed-silver-gold` (both branches),
`edgartools-prod-ownership-mdm-gold`, and `edgartools-prod-residual-holds-graph`
are all unbounded or pass an explicit large `--limit-per-type` (the
residual-holds machine already establishes a good precedent:
`--limit-per-type 200000`). **Whether to change the 4 affected machines'
baked-in defaults is a real, still-open decision — not made or implemented
in this pass.** See "Not done here" below.

**Item 2 (wire `limit_per_type` through the state machine) — was already
done before this pass, just never reflected in this ticket.** Commit
`11f700f1` (2026-08-04) added `mdm_workflow_limit_per_type_command_expression`
and a `HasLimitPerTypeOverride` Choice; confirmed live in the current
`edgartools-prod-mdm-utility` machine's `mdm_sync_graph_RunMdmTaskWithLimitPerType`
branch (the standalone `edgartools-prod-mdm-sync-graph` machine this
ticket's own discovery notes reference no longer exists — deleted by
state-machine-consolidation ticket 05, superseded by `mdm-utility`).

**Item 3 (warn on suspiciously small results) — implemented this pass.**
`SnowflakeGraphSyncExecutor.sync()` (`edgar_warehouse/mdm/snowflake_graph.py`)
now runs 2 cheap preflight `COUNT(*)` queries (against the Snowflake MDM
mirror's `MDM_ENTITY`/`MDM_RELATIONSHIP_INSTANCE`, same `WHERE` filters the
main query uses, minus the limit/QUALIFY) *before* the main build script —
but only when `limit`/`limit_per_type` was actually requested (an unbounded
sync can't be suspiciously capped, so the extra round trip is skipped
entirely otherwise). If the applied node/edge count falls short of the
preflight available count, emits a structured `mdm_sync_graph_result_capped`
event (`edgar_warehouse.mdm.observability.emit_mdm_event`, same convention
used elsewhere in this module) and surfaces `capped_below_available` /
`available_node_count` / `available_edge_count` directly in the CLI's own
JSON payload (`_snowflake_graph_sync_payload`, `edgar_warehouse/mdm/cli.py`)
so an operator reading only captured stdout (e.g. a Step Functions task
result) doesn't need stderr access to tell "capped" from "complete."

**A second, more consequential bug found and fixed along the way, via the
`/diagnosing-bugs` discipline** (not something this ticket originally
asked for, but load-bearing for item 1's real-world impact): `run_companies(limit=N)`
without `--resume-ledger-run-id` — exactly what all 4 affected machines'
`MdmRun` state calls — fell back to a bare `SELECT * FROM sec_company
LIMIT N`, no `WHERE`, no `ORDER BY`. Since `CompanyResolver` idempotently
skips/reuses already-resolved CIKs rather than erroring, repeated calls
with the same `--limit` **plateaued on the same first N rows in table scan
order, never making cumulative progress** — the identical shape already
documented and fixed for relationship-derivation's own source query
(`_bounded_relationship_sql`'s docstring in the same file), but never
ported to company resolution itself. Built a real feedback loop (a
`SilverDatabase`-backed DuckDB fixture — deliberately not the
substring-matched `StubSilver` used elsewhere in this test package, which
ignores `LIMIT`/params entirely and would have masked this exact bug, the
same "stub silently mirrors a bug instead of the real schema" trap
CLAUDE.md's INSTITUTIONAL_HOLDS incident already documents): 3 successive
`limit=2` calls against a 5-company universe never resolved past the same
first 2 CIKs. **Fixed** by porting the same growing-window pattern
(`_bounded_relationship_sql`, stable `ORDER BY cik` + an existing-count-scaled
`LIMIT`) already used for relationship-derivation: over-fetch a window past
the already-resolved prefix, exclude already-resolved CIKs via
`_company_cik_set()` (an existing helper, already used elsewhere in this
file for exactly this "give me every known CIK" purpose), then cap at
`limit` genuinely-new candidates — same bounded-cost-per-call contract as
before, but the window now actually advances on repeat calls. Confirmed via
the same repro script: 3 calls of `limit=2` against the same 5-company
universe now resolve 2, 2, 1 — all 5, no waste, no plateau.

**Tests:** `tests/mdm/test_run_companies_bounded_limit_progress.py` (new,
3 tests — cumulative progress across repeated calls, bounded-cost contract
still holds for a single call, clean termination once the universe is fully
resolved), `tests/mdm/test_snowflake_graph_migration.py` (3 new tests for
the capped-warning behavior: emits when capped, doesn't false-positive when
applied equals available, skips the preflight queries entirely when
unbounded; plus updates to 1 existing test whose fixed `fetchone()` sequence
needed extending for the new preflight queries), `tests/mdm/test_cli_snowflake_graph.py`
(1 new test for `capped_below_available` surfacing in the CLI JSON payload,
plus an assertion addition to the existing sync-graph CLI test). Full
`tests/mdm/` suite: 520 passed (up from 518 pre-fix), no regressions. Full
repo suite: see commit for the final count.

**Not done here — a new, real, still-open decision, deliberately not made
unilaterally:** whether `load_history`/`daily_incremental`/`bootstrap`/`mdm_gold`'s
baked-in `--limit 100`/`--limit 200` should change — to unbounded (matching
the other 4 machines that already work this way), to an explicit large
value (matching `residual_holds_graph`'s own `--limit-per-type 200000`
precedent), or to a Choice-gated execution-input override (matching
`mdm-utility`'s pattern). This is a genuine cost/behavior tradeoff (longer
task runtime, more Snowflake compute per run) affecting 4 live production
Step Functions definitions, not a pure bug fix — out of scope for this
pass per explicit user direction during triage (surfaced as a finding,
not acted on). The `run_companies` plateau fix above makes the *existing*
`--limit 100`/`--limit 200` values behave correctly (cumulative progress
instead of a permanent plateau) regardless of how this follow-on decision
resolves, so it stands on its own either way.

**Not yet deployed** — code-only change as of this entry; both fixes need
a warehouse+MDM image rebuild/push and redeploy (`edgar_warehouse/mdm/**`
changed) to take effect in prod, per CLAUDE.md's image-rebuild table.
