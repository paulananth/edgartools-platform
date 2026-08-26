# Decide silver delta publication and scope-completion semantics

Type: grilling
Status: resolved
Blocked by: 01, 02, 04

## Question

How should collision-free producer outputs become one complete, current
Snowflake silver publication while processing only the Change Propagation Run's
Affected-Key Closure?

Decide producer/window/attempt/file identities, immutable landing paths and
checksums, table-specific upsert/retirement/replacement behavior, content-hash
no-op suppression, parser-version reprocessing, concurrent producer ordering,
retry-after-partial-load, and the barrier that proves every expected file was
loaded and every affected dbt silver table reached the run's publication
identity. The answer must eliminate mutable same-key Parquet/manifests and must
not store the source-consumption cursor inside the silver state being produced.

## Answer

Grilled 2026-08-25/26, cross-checked against the settled Silver-on-Snowflake
Migration map (named in this map's own Notes as "inputs, not questions to
reopen"). Most of this ticket's original ask turned out already decided
there; the real remaining work was two genuine gaps that map's own tickets
either sidestepped or never touched.

**Already settled by the other map — not reopened:** producer/window/
attempt/file identities (plain append-only `INSERT`, `parse_sequence` as a
Snowflake `SEQUENCE`); immutable landing paths (the append-only
`EDGARTOOLS_SILVER_LANDING` schema); concurrent producer ordering ("there's
no promotion-race conflict class left to replace at all" — the entire
ETag/promote-with-retry/candidate-canonical-merge apparatus retired
outright); retry-after-partial-load (`COPY INTO`'s own `LOAD_HISTORY`
tracking makes re-running it against already-loaded files a no-op by
default — confirmed in that map's Ticket 07, not something this ticket
needed to add anything to). "Eliminate mutable same-key Parquet/manifests"
and "don't store the source-consumption cursor in silver state" are both
already structurally true: landing is strictly append-only with no
mutation path at all, and consumption cursors (`source_observation_cursor`)
live entirely in the Postgres acquisition ledger, never in Snowflake
silver.

**Content-hash no-op suppression / parser-version reprocessing: confirmed
moot, not silently missing.** Append + "latest row per key wins" already
absorbs both a duplicate resubmission and a reinterpretation harmlessly —
worst case is one redundant landing row and one redundant dbt refresh,
never a wrong answer. Building suppression logic to avoid that would
optimize a cost that hasn't been shown to matter.

**Gap 1 — table-specific retirement, genuinely open and this ticket's real
job.** The Snowflake-native design's window-function collapse
(`ROW_NUMBER() OVER (PARTITION BY key ORDER BY parse_sequence DESC) = 1`)
structurally cannot represent "this key was retired" — an append-only
landing zone only ever records rows that exist; absence of a new row is
indistinguishable from "nothing changed." The one table the other map
special-cased (`sec_company_ticker`, reasoned as "removal semantics
moot... a row simply stops being latest") only works because of that
table's own coarse write granularity; it does not generalize to real
per-record retirement (a Lifecycle-Diff-proved scope shrink). Decided: a
new **Silver Landing Retirement Record** (CONTEXT.md term added) — a
single shared companion landing table (`source_family`, `target_table`,
`business_key`, `cause_reference`, `retired_at`, `parse_sequence`), written
directly by the source family's own acquisition code the moment it proves
a Scope Completion shrink (it already has both the old and new complete
scope membership in hand at ingestion time — no new diff computation
needed anywhere). Every dbt silver model's collapse anti-joins against a
"latest event per business key" view over this one table via one shared
macro, mirroring the existing "one shared macro every model already flows
through" pattern (`silver_model_config.sql`). Chosen over (a) uniform
`is_retired`/`retired_at` columns added to all ~30 landing tables directly
— that would force fake/null values into unrelated `NOT NULL` business
columns 30 times over — and over (b) a Snowflake Stream reacting to Scope
Completion, which would need something holding the *prior* scope's
membership to diff against, when the source family already has both sets
in hand at write time.

**Gap 2 — the completion barrier, genuinely open, distinct from the
already-decided `target_lag = '6 hours'` refresh schedule.** A fixed lag
is an eventual-consistency SLA, not a proof — it doesn't answer "did every
expected file for this Run actually land." Decided: reuse the existing
`ProcessingLedger`/`SilverFinalizer`/`ExpectedProducerSet` mechanism
(Ticket 19) rather than invent a parallel Snowflake-only check — a
Snowflake-specific expected-producer row is sealed at discovery time
(mirroring today's DuckDB `sec_raw_object` producer), and a new read-back
step verifies it by checking `COUNT(*) WHERE cause_reference = ...`
against the landing table instead of DuckDB's `get_raw_object`. This is a
drop-in generalization of an already-proven, already-tested mechanism, not
a second system duplicating the same verification concept.

**Deliberately deferred to a follow-up task ticket** (plan-don't-do
discipline — this is a decision ticket, not an implementation ticket): the
concrete DDL for the `Silver Landing Retirement Record` table and its
shared dbt macro, the concrete Snowflake-producer extension to
`ExpectedProducerSpec`/`SilverFinalizer`, and wiring both into the first
migrated source family that actually needs retirement (none of the
currently-migrated families — `submissions`, `company_facts`,
`reference_catalog`, `adv_bulk_dataset`/`adv_filing` — have exercised a
real per-record retirement path yet; `reference_catalog`'s existing
delete-then-insert only proves the *local candidate* side, not the
Snowflake landing side this decision targets).
