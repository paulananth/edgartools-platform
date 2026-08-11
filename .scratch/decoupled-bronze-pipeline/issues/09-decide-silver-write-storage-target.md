# Decide silver's write/storage target

Type: grilling
Status: resolved
Blocked by: 01

## Question

This map's destination already locks bronze capture as an independently-
scaling, fetch-only process and silver as an independent async consumer.
Within that silver consumer, there are two sub-steps with very different
scaling profiles, currently fused: **parse** (bronze bytes -> typed
records — CPU-bound, no correctness constraint, should scale to full
parallelism regardless of storage backend) and **commit-to-store** (the
step that's actually constrained today — see [Investigate silver DuckDB's
current concurrent-write model](01-research-silver-duckdb-concurrent-write-model.md)).

Given ticket 01's findings on what the DuckDB concurrent-writer race
actually is and whether sharding already solves it, decide silver's write
target:

(a) **Keep DuckDB, fix the concurrency model** — e.g. per-shard writers
with a defined promotion/merge step, if ticket 01 shows that's sufficient
and cheap relative to a storage-target migration.

(b) **Move silver's write target to Snowflake** — native `MERGE` already
handles concurrent writers; would eliminate the DuckDB write-serialization
constraint entirely rather than needing to solve it. Trade-off: silver's
current consumers (MDM's `ShardedSilverReader`, warehouse-side gold build
reading `silver.duckdb` directly) would need to read from Snowflake
instead — a bigger blast radius than ticket 08's gold-only question.

(c) **Pluggable/dual target** — support both, chosen per deployment or per
migration phase, not a single locked answer.

This is silver's mirror of [Decide whether gold compute stays in
Python/DuckDB or moves into Snowflake SQL](08-decide-gold-compute-location.md)
— the two may end up with related or even identical answers (if silver
moves to Snowflake, gold computing "in Snowflake SQL" becomes far more
natural, since it would no longer need a separate Python read of
`silver.duckdb` at all), so resolve this one first and revisit ticket 08 in
light of it if the answer changes ticket 08's premise.

## Answer

**(a) Keep DuckDB, fix the concurrency model.** Decided 2026-08-11 on
engineering-cost grounds, with one deliberately-accepted open risk stated
below rather than papered over.

**Why:** [Investigate silver DuckDB's current concurrent-write
model](01-research-silver-duckdb-concurrent-write-model.md) found two
concurrent-write patterns already proven safe and running in production
against DuckDB-backed silver — ETag-guarded merge/promote/retry, and an
isolated-producer-plus-single-reducer pattern
(`identity_refresh_publication.py`). The one real gap
(`_publish_shard_if_remote`, `warehouse_orchestrator.py:1210-1252`, lacks
the ETag guard `_publish_silver_database_if_remote` already has) was
confirmed via a `/gof-refactor-reviewer` pass to be a small, mechanical fix
— reuse existing `StorageLocation` primitives (`read_object_version`,
`write_staged_bytes`, `promote_staged`, all already implemented in
`object_storage.py`), not new machinery. A `/gof-pattern-selector` pass on
the same code found no new GoF pattern is needed for the fix either —
Extract Function covers the shard-promotion gap; the per-event-vs-per-run
question is a trigger-wiring change to the existing reducer, not a class
restructuring.

**Concrete direction this sets:** (1) extract the ETag-guarded
stage-then-promote sequence out of `_publish_silver_database_if_remote`
into a shared helper both the monolith and shard paths call; (2) generalize
`identity_refresh_publication.py`'s isolated-producer+reducer pattern to
fire per-event (currently one-shot-per-run) as the mechanism async silver
consumers merge into canonical silver.

**Accepted risk, not resolved by this ticket:** ticket 01 explicitly could
not measure whether this approach's cost profile (sequential reduce against
a growing DuckDB file) holds up against Snowflake-native concurrent `MERGE`
at whatever event frequency [Research AWS messaging substrate
options](02-research-messaging-substrate-options.md) lands on. Decided to
proceed anyway rather than block on that research, on the reasoning that
reversing a working, documented decision later — if ticket 02's frequency
numbers turn out to demand it — is cheaper than building a second storage
path speculatively now. If ticket 02 surfaces event frequencies where this
assumption looks shaky, re-open this ticket rather than silently drifting
past it.

**Implication for [Decide whether gold compute stays in Python/DuckDB or
moves into Snowflake SQL](08-decide-gold-compute-location.md):** since
silver's canonical store is staying DuckDB, gold compute option (b) — real
dbt transformation reading bronze-adjacent data directly in Snowflake —
loses its main enabler (there's no silver-shaped data landing natively in
Snowflake for dbt to read independent of Python's export). This pulls
ticket 08 toward its option (a), formalizing the current Python-compute +
Snowflake-mirror split as intentional, though ticket 08 itself remains
open and unresolved — this is context for whoever works it next, not a
resolution by proxy.
