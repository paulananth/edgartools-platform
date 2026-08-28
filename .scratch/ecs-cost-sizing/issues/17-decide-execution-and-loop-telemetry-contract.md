# Decide the Execution and Loop Telemetry Contract

Type: grilling
Status: resolved
Blocked by: 10, 12, 13

## Question

What durable metrics and identifiers must every workflow, stage, and loop emit
so value, throughput, cost, and regressions can be compared without manual log
reconstruction?

Decide a minimal contract covering execution and release identity, workflow
and stage name, task definition and image digest, loop item type and count,
selected/attempted/committed/exported/skipped/rejected/retried/deduplicated
records, duration, peak CPU/memory, outcome, output manifest, and cost
attribution keys. Choose the durable source for each field and define how a
missing counter fails the optimization gate rather than being interpreted as
zero.

## Answer

Every decision below is a direct fix for a specific instrumentation gap
Tickets 11, 12, or 13 hit and had to work around by hand this session — this
contract exists so future tickets don't repeat that reconstruction work.

**1. Durable source of record.** Every workflow's already-written manifest
(the S3/Snowflake mechanism `gold_refresh`/`seed_universe` already use) must
carry record-level counts (selected/attempted/committed/exported/skipped/
rejected/retried/deduplicated), not just cost/duration fields.
**CloudWatch structured logs stop being treated as the ledger of record** —
they remain useful for live operational debugging, but their 7-day
retention is exactly why Ticket 13 could cost two 17-day-old relationship
backfills exactly (Step Functions' 90-day history) while their insert
counts were simply gone. The manifest is durable indefinitely; the log
group is not.

**2. Distributed Map child traceability.** Every Map's `ItemProcessor` must
receive and propagate the **parent execution name** into its own
structured-log context and any manifest it writes. This closes Ticket 12's
single biggest finding — a child's `$$.Execution.Name` is its own generated
UUID today, uncorrelated to the parent, forcing a wall-clock-window
heuristic (never actually built) to attribute child-level cost or logs back
to a parent run.

**3. MDM's missing per-run binding.** Confirmed real, not closed here:
Ticket 11's gate 3 found Snowflake-native chains (gold, ticker reference)
bindable to a specific run via `SNOWFLAKE_REFRESH_STATUS`, while MDM has no
per-run column on any table — genuinely unbindable, not just
under-instrumented. Decided this needs fixing, but it's schema work on live
Postgres/Snowflake-mirrored tables, not a manifest/logging change — too
large to fold into this contract. **Split into Ticket 27**, its own
follow-up.

**4. Missing-counter fail-closed rule** (the ticket's own explicit ask).
Every record-count field in the manifest schema is **required and
non-nullable** — a write that can't populate them fails schema validation
outright, rather than silently landing a manifest with an implicit zero.
This makes "missing" structurally distinguishable from "genuinely processed
zero records," instead of relying on a report author remembering to write
"not reconstructable" in prose (which is exactly what this map's own
tickets had to do, repeatedly, this session).

**5. Step-Functions-bypass visibility.** The manifest schema adds a
`triggered_via` field (`step_functions` / `direct_cli` / `ecs_run_task` /
etc.). Ticket 11 found 2 real production writes with no Step Functions
execution at all, and gate 6 explicitly accepted this bypass path as
intentional rather than closing it. Without this field, every future
report built on this contract would silently exclude bypass writes, the
same way this session's own reports had to caveat around them by hand.
Cheap addition; keeps an already-accepted design choice from becoming an
invisible reporting gap.

**Out of this map's planning-only scope, per its own Notes**: building the
actual manifest schema, wiring it into every workflow builder, and adding
schema validation are all real code changes — a follow-up implementation
effort, same pattern as every other decision this map has produced. Item 3
alone gets its own ticket (27) since it's schema work on live data stores,
not logging.
