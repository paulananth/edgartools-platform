# Decide gold affected-DAG refresh and status semantics

Type: grilling
Status: resolved
Blocked by: 01, 02, 05

## Question

How should a completed silver publication identify, refresh, and attest only
the affected dbt gold dependency closure while retaining correct current-state
and retirement semantics?

Decide the affected-table/model mapping, whether dbt selection or Snowflake
dynamic-table refresh is authoritative, handling of the three approved
external Explore inputs, status/history evidence for incremental versus full
recomputation, failure/retry boundaries, and the gold publication identity
bound into the Decision Watermark. Resolve how the legacy Python full-snapshot
and `EDGARTOOLS_SOURCE` paths retire without duplicating the existing dbt-gold
rewiring tickets.

## Answer

Grilled 2026-08-26. Most of this ticket's original ask turned out already
decided or already structurally satisfied by the (separate, unlabelled)
`dbt-gold-silver-rewiring` map and by design decisions baked into the
current dbt gold layer — not by anything new this ticket needed to invent.

**Legacy path retirement — not re-decided here.** This ticket's own
premise needed one correction first: "the legacy Python full-snapshot and
`EDGARTOOLS_SOURCE` paths retire" conflates two different things.
`single-path-per-layer`'s own investigation already found `EDGARTOOLS_SOURCE`'s
Python-populated dimensional export (`source_dimensional_export.py`) is a
*legitimate, permanent* part of the source layer, not legacy — only
`gold_models.py`'s DuckDB-*read* dependency (the Python builders
constructing gold tables from local DuckDB) is retiring. That retirement
is `dbt-gold-silver-rewiring`'s own Ticket 07 ("Retire `gold_models.py`
and Delete the DuckDB Gold-Build Path") — 6 of that map's 7 tickets are
already resolved, and Ticket 07 is fully unblocked and ready-for-agent.
This ticket defers to it rather than re-deciding the same retirement.

**dbt selection vs. Snowflake refresh authoritative:** Snowflake refresh
is authoritative, mirroring silver's own answer (Ticket 05) — dbt only
declares the `dynamic_table` config via a shared macro
(`gold_model_config()`), Snowflake's own refresh engine moves the data.
Confirmed live in the repo: gold models use `target_lag='DOWNSTREAM'`
(not `SNOWFLAKE_RUN_MANIFEST_TASK`, which CLAUDE.md's Phased Pipeline doc
still describes — that description is now stale for gold specifically and
needs correcting once the follow-up ticket below verifies actual live
behavior).

**Affected-table/model mapping and the three external Explore inputs:
already structurally solved, nothing new to decide.** Snowflake's
`DOWNSTREAM`-lag dynamic tables propagate refresh reactively along the
actual `ref()`-declared dependency graph — an external "which tables are
affected" computation isn't needed on top of that. Confirmed the Explore
models (`consensus_estimates` and siblings — external, non-SEC data) are
already deliberately isolated as their own DAG branch by construction
(`consensus_estimates.sql`'s own header: "Isolated DAG branch — no `ref()`
into ownership or fundamentals chains," governed by ADR 0001) — "refreshed
only when their own inputs change" (spec.md user story 68) is already true
by that isolation, not something this ticket needed to build.

**Gold's contribution to the composite Decision Watermark:** reuse
Snowflake's own native per-table refresh version/timestamp (already
tracked, queryable via refresh history) rather than invent a new manifest
or generation identity — mirrors Tickets 04/05's established pattern
(reuse `cause_reference`, reuse `ExpectedProducerSet`'s shape) of reusing
what already exists over building something new. Concrete plumbing into
the watermark itself is Ticket 09's aggregation job.

**One real, unresolved risk, flagged rather than guessed past:** whether
`target_lag='DOWNSTREAM'` is actually refreshing gold's mostly-leaf
dynamic tables with acceptable freshness could not be verified from
static dbt config alone — a leaf table with `DOWNSTREAM` lag and no
downstream dynamic-table consumer of its own may barely refresh at all,
and this was never checked against a real account in this session. Status/
history evidence, failure/retry boundaries, and a real completion barrier
(mirroring Ticket 05's Silver Landing one) all depend on knowing the
answer to this first, so none of them are decided further here — deferred,
together with the live verification itself, to new [Ticket 39](39-verify-gold-downstream-lag-and-build-completion-barrier.md).
