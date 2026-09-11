Type: grilling
Status: ready-for-agent

## Question

`bootstrap-fundamentals` (all 4 modes: `entity-facts`, `per-filing`,
`thirteenf`, `company-identity`) is deliberately excluded from
`SOURCE_EXPORT_COMMANDS` (per its own module docstring: "Gold is built
once by `gold-refresh` after all batches complete") — but that also means
it never calls `write_landing_export` at all, on any run, ever. Confirmed
live: every `load_history` execution's Stage 1B (`FetchEntityFacts`/
`FetchPerFilingFundamentals`/`FetchThirteenFHoldings`) runs this command
in production, and the full `load_history` state-machine definition has
no landing-export step anywhere downstream (`gold-refresh`/`FactPublishtoGold`
doesn't have one either — checked directly, zero landing-export code in
`workflows/gold_refresh.py`). So content this command writes to canonical
silver never reaches Snowflake `EDGARTOOLS_SILVER` through any ordinary
path, permanently, not just historically.

Ticket 15 already fixed the *historical* version of this shape (pre-existing
content that predates the landing-zone write path) via a one-time sweep
(`backfill-silver-landing-historical`). This is the *ongoing* version:
every future `bootstrap-fundamentals` run reopens the same gap for its own
new content, forever, until this is fixed structurally or someone
periodically reruns the historical backfill by hand.

**Live evidence (2026-09-11, v1-agent-grade-feature-inputs Ticket 02):** a
real `bootstrap-fundamentals --mode entity-facts` window added 37 CIKs /
593,470 `sec_financial_fact` rows to canonical silver. Snowflake
`EDGARTOOLS_SILVER.SEC_FINANCIAL_FACT` stayed at exactly 21 CIKs / 434,805
rows before and after — zero rows landed.

Decide: should `bootstrap-fundamentals` be wired into the ongoing
`write_landing_export` path directly (and if so, per-window like the
generic bronze-capture path, or batched once at the end of all Stage 1B
windows — `MaxConcurrency:1` sequencing makes either shape possible), or
is a scheduled/periodic re-run of `backfill-silver-landing-historical`
(e.g. as its own light Step Functions state, or a cron) an acceptable
standing operational answer instead of a code change? Either answer needs
to also cover `company-identity` mode and the ADV/Firm Roster ingestion
commands this ticket didn't check line-by-line (only entity-facts/per-filing/
thirteenf were confirmed via the state-machine grep — worth a quick pass to
see whether `FetchAdvBulk`/`FetchFirmRoster` share this same shape or
already export correctly).

## Context

Surfaced while resolving
[v1-agent-grade-feature-inputs Ticket 02](../../v1-agent-grade-feature-inputs/issues/02-prove-one-entity-facts-window-publishes.md)
(prove one `load_history` Stage 1B entity-facts window publishes) — that
ticket recorded the finding narrowly for its own scope and pointed here
for the structural fix, per its own "record the exact remaining refresh
step" acceptance criterion rather than deciding the fix unilaterally.
[Ticket 03](../../v1-agent-grade-feature-inputs/issues/03-backfill-as-of-decision-features-for-the-universe.md)
(the full-universe fundamentals backfill) is blocked on having *some*
answer here before it runs at scale, or it will reproduce this gap for
the entire universe instead of 37 CIKs.

Related but distinct from
[Ticket 15](15-root-cause-per-table-silver-landing-ingestion-gap.md) (the
historical/one-time version of this shape) and
[Ticket 14](14-load-silver-landing-task-suspended-zero-rows.md) (a bug in
the ongoing incremental path for `sec_company_ticker` specifically,
already fixed) — this ticket is about `bootstrap-fundamentals` never
being wired to the ongoing path *at all*, for any of its 4 modes, not a
bug in an existing wiring.
