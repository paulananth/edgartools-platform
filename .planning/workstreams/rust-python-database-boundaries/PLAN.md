# Rust, Python, and database boundaries

## One goal

Assign platform responsibilities to Rust, Python, and the database, and identify existing SQL computation that can safely move into code. Optimize the complete pipeline while preserving correctness, recovery, and the AWS architecture.

Status: proposed architecture and execution plan, based on source inspection. No runtime change, benchmark, database qualification, or deployment was performed for this plan.

Baseline: fetched `origin/main`, commit `51b45916018f48f30b76c582fe61e23365587026`, on 2026-10-11. Branch: `codex/rust-python-database-boundaries`. Dedicated worktree: `/Users/aneenaananth/projects/edgartools-platform-rust-python-database-boundaries`. The shared checkout and its dirty files were preserved. This work owns only this planning directory; the inherited `fix-pipelines` active-workstream pointer is not changed.

## Proposed boundary

**Rust computes bounded data transformations. Python coordinates the work and implements evolving domain policy. Databases select stored data efficiently and enforce durable state transitions.**

There is no technical rule that orchestration must use Python forever. Here, “must remain Python” means preserve the existing CLI, integrations, and operator contracts for this work. Likewise, a computation being possible in Rust is not evidence that moving it improves the pipeline.

| Work | Recommended home | Current evidence and decision |
|---|---|---|
| Configured XML/JSON/CSV/container reading, projection, coercion, predicates, lookup membership, record rejection | Rust | `crates/source-contract/src/lib.rs:143`; retain configured engine and source-specific limits. |
| Streaming framing and native projection | Rust kernel, Python transport and authenticated publication | `crates/source-contract/src/python.rs:158`, `edgar_warehouse/rules/source_engine.py:54`; EOF and verification must precede publication. |
| Large grouping, distinct-member counting, sorting, bounded local joins | Rust candidate after profiling | `edgar_warehouse/workers/source_reduction.py:94` and `source_combine.py` currently compute in Python. Preserve order, null rules, output hashes, limits, and failure semantics. |
| CLI, AWS/SEC/S3 transport, retries, Bookkeeping workers, manifests, verification, SQLAlchemy/Snowflake integrations | Python | `edgar_warehouse/workers/source_read.py:276`, `edgar_warehouse/mdm/clean/store.py:461`; preserve existing integration surface. |
| Source adapters and custom steps using Python APIs | Python, behind existing facade | `edgar_warehouse/rules/steps.py:1`; callbacks are a last resort. Pure hot callbacks can become configured native primitives after parity qualification. |
| Identity replay, match proposals, survivorship, relationship policy, review decisions | Python initially | `edgar_warehouse/mdm/clean/merge.py:197` and calls to `identity`, `matching`, `survivorship`, `relationships`; these are already application computations. Port only an independently measurable pure kernel. |
| Versioned rule bodies, policies, source mappings, reference data | Rules configuration with durable registration/approval | Keep policy out of hard-coded Rust/Python source. Rules authority and approval enforcement retain their current owner. |
| Bounded indexed lookup of stored evidence, decisions, entities, relationships | PostgreSQL | `edgar_warehouse/mdm/migrations/012_key_join_lookups.sql:26`; avoid exporting full tables for application filtering. |
| Atomic MDM commit, generations/checkpoints, proposal freshness, uniqueness, history, fencing, outbox metadata | PostgreSQL | `014_outbox_names_batch.sql:39`, `013_proposal_effects_hash.sql:19`, `015_company_fields_once.sql:26`; keep a restricted write API. |
| Rule approval and immutable history enforcement; Change Journal append/idempotency | PostgreSQL | `rules/migrations/003_approval_on_evidence.sql`; `change_journal/migrations/001_event.sql:14`. Application prechecks supplement these guarantees. |
| Warehouse joins, lag/rank/window calculations, cross-company factors and dynamic-table refresh | Snowflake/dbt | `models/gold/financial_derived.sql:33`, `financial_factors.sql:6`, `institutional_holdings.sql:9`; retain database computation by default. |

## What database work can move into code?

Yes: computations that depend only on explicit immutable inputs can move. Code may also prepare a proposed write. Database enforcement must still validate the proposed write against current state inside its transaction. Moving SQL text into a Python module does not move its execution out of the database.

| Existing database work | Can it move? | Proposed treatment and qualification requirement |
|---|---|---|
| `mdm.entity_name(body)` and `mdm.relationship_holds(body, at)` in migration 006 | Pure computation can move | Use pure Python equivalents when preparing application artifacts, or Rust if hot. Retain SQL versions while views/query consumers need them. Preserve missing/empty values, periods, timezone and boundary semantics. A small function alone is unlikely to justify migration. |
| Outbox JSON assembly in `mdm.outbox_delivery`, migration 014:23 | Conditional candidate | Publisher can construct the payload from the immutable committed batch plus consumer. Retain database claim ordering, leases, expected hash, verification state, and old stored-payload handling. Preserve existing JSONB hash bytes or explicitly version the protocol; Python JSON spelling is not interchangeable with PostgreSQL JSONB text. Prefer a publisher experiment over moving authoritative commit hashing first. |
| Request shaping and structural validation in `mdm.write_batch` | Preparation can move; enforcement stays | Python already prepares requests. Native checks can accelerate repeated processing, but DB bounds, source authority, collisions, and stale-state checks remain for every writer. Do not grant direct table DML to bypass functions. |
| Company field extraction from the projection in `mdm.record_company_version`, migration 015 | Conditional candidate | Code can prepare scalar columns from the projection. Database still closes/opens versions atomically and checks consistency with the canonical body. Measure round trips, transferred bytes, parameter overhead and write cost; today's deduplication change may already solve the larger cost. |
| Canonical JSON and hashing in `journal.canonical`, migration 001:4 | Producer computation already belongs in code; DB validation stays | Inspect producer canonicalization alongside DB rules. Preserve hash and canonical-body checks and append identity collision detection. Only port producer computation to Rust after byte-level parity for Unicode, integers, floats, null and ordering. |
| `mdm.match_proposal_snapshot(scope)`, migration 012:73 | Keep authoritative snapshot in DB | Application can consume a bounded snapshot, but the commit path must recheck it under the current locking protocol. Outside-transaction hashing cannot replace the freshness check. Profile query and hashing costs separately. |
| `mdm.readings_naming`, `mdm.decisions_naming`, context joins and parent-chain traversal | Retain DB selection by default | Indexed selection stays near stored data. Rust may walk an already-loaded bounded closure; use a consistent snapshot and unchanged closure completeness checks. Moving recursive SQL wholesale needs evidence that retrieval plus code traversal beats the indexed query. |
| Bookkeeping claims, role authorization, destination lease validation at commit | Keep DB enforcement | `bookkeeping/clean/migrations/destination_guard.sql:8` and `:29` enforce stale fences and expiry. Python decides when to request work; server time, row locking and deferred commit validation remain authoritative. |
| Snowflake row-local formulas, such as ratios | Technically movable, conditional candidate | A versioned Python/Rust kernel could compute them before export. Preserve SQL decimal precision, scale, null/zero semantics and refresh dependencies. Test using fixed inputs against SQL outputs. |
| Snowflake YoY/TTM, peer percentiles and ownership ranking | Keep SQL for this plan | These depend on history or a population. Code migration would also need dependency closure, late-arrival/restatement handling, publication and refresh machinery. Include data extraction and re-ingestion costs in any future comparison. |

The invariant is **prepare in code; validate and commit at the destination**. A Python-controlled transaction can technically preserve database atomicity, but replacing the current restricted function API would require redesigning grants and independently proving every enforcement path. That is a larger change than extracting a pure computation.

PostgreSQL releases row locks at transaction end, and `FOR UPDATE` coordinates competing writers; keep checks and dependent writes within that protection. See [PostgreSQL 16 locking](https://www.postgresql.org/docs/16/explicit-locking.html). Uniqueness, foreign keys and checks remain database constraints; see [PostgreSQL 16 constraints](https://www.postgresql.org/docs/16/ddl-constraints.html). These support the concurrency boundary; the extraction recommendations above are project-specific design judgments.

## Design review

`gof-refactor-reviewer` is available and was applied to the facade, merge stage, callback bridge and relevant git history. Overall verdict: retain existing seams; no new GoF hierarchy is justified by this review.

- `SourceEngine` (`rules/source_engine.py:98`) already supplies the adapter/facade between Python callers and native reading. `python.rs:109` reacquires the GIL for custom steps, while `:177` releases it for native reading. The useful investigation is batching/callback/materialization cost, not additional wrapper classes.
- Merge Stage (`mdm/clean/merge.py:197`) coordinates domain computation and the Store boundary. Its proposal/apply work changed in `4ace81d3` and size handling in `9a72285b`; retain that contract rather than adding a generic Strategy class for language selection.
- Stored-key lookup tuning in `c16968be` centralized selection used by closure and snapshot; migration 012 records the prior scan cost and the new indexed lookup behavior. Keep the shared query. Reimplementing its selection independently would introduce drift and extra data movement.

The cost of preserving these seams is continued Python/native conversion and some SQL-specific behavior. That cost should be measured before paying the migration and semantic duplication cost of a replacement.

Earlier parser memory recommended Rust+Python and described an incomplete 200-filing 13F run. That is historical context, not current qualification: this branch has newer native framing/projection work (`337e737e`, `716cb999`, `f8f7876e`, `3368da36`). This plan makes no current speedup claim from those older measurements.

## Execution sequence

Each later execution ticket must have its own current checklist, ownership check, baseline and acceptance evidence. These are planned stages, not completed implementation work.

1. **Establish a component and full-path baseline.** Pin the source artifacts, active rule versions, runtime digest and database state. Measure reading, native/Python conversion, combine/reduce, closure lookup, domain computation, serialization, DB commit, outbox materialization and delivery separately. Capture wall time, CPU, peak RSS, input/output bytes, SQL calls and lock duration. Include small and large workloads, serial/2/4 workers, malformed final input, retries and no-change runs. Long scans need an announced duration and elapsed-time reporting. Offline profiling should precede any separately authorized live qualification.
2. **Choose one measured pure kernel.** First evaluate `source_reduction.tables` because its bounded grouping/counting state is explicit. It is a candidate, not a promised bottleneck. If SQL computation dominates instead, compare outbox assembly or Company extraction; if indexed selection dominates, tune SQL first. Publish the measured choice before a port.
3. **Extract behind the existing facade.** Keep orchestration, authentication, persisted contracts and operator output in Python. Add a native batch interface only for the selected computation. Avoid one Python callback per row when a bounded batch is sufficient. Pin native code/binary changes in the execution digest. No database connections or external requests inside the pure kernel.
4. **Qualify exact behavior.** Compare tables, deferred records, rejection codes, ordering, scalar types, canonical bytes and hashes. Cover null versus missing, integer bounds, decimal precision, Unicode, duplicate keys, ties, last-occurrence order, byte/key/member budgets and late EOF failures. Reuse existing tests; add differential cases at the boundary. For SQL extraction, compare the original SQL and code on the same fixed snapshot.
5. **Prove persistence and recovery remain intact.** Run real PostgreSQL 16 with restricted roles. Competing writers, stale assessments, expired/replaced leases, duplicate batch/event keys, rollback after partial preparation, and crash between commit and publication must retain current outcomes. Batch, history, checkpoint and required outbox rows commit together. Bookkeeping, Rules, MDM and Change Journal have separate transactions; preserve idempotent delivery reconciliation across databases and S3.
6. **Decide from full-path results.** Adopt only if output/rejection parity is exact, bounds and recovery hold, and improvement remains after transport/conversion/persistence costs. Proposed gate: at least 20% median end-to-end wall-time improvement over five equivalent trials, no material p95 latency regression, and no more than 10% peak-RSS growth. These are proposed decision thresholds, not measured results or previously agreed requirements. If they fail, retain the current implementation and record the result.
7. **Cut over one path and retain recovery.** Recheck current branch/ownership and the overlap guard. Use the reviewed configuration/execution version; preserve existing durable batches, receipts and archived payload compatibility. One authoritative writer remains active. Roll back new executions to the prior compatible version while reconciling already committed work; never remove commit checks or undo history to roll back a compute port.

## Validation targets for later implementation

| Change | Existing coverage to reuse |
|---|---|
| Native reading and bridge | `crates/source-contract/tests/`, `tests/engine/test_source_engine.py`, `test_source_stream_worker.py`, `test_source_input_pins.py` |
| Combine/reduce kernel | `tests/engine/test_source_combine.py`, `test_source_nested_combine.py`, `test_source_reduction.py` |
| Domain-policy kernel | `tests/mdm/test_clean_survivorship.py`, `test_clean_identity_correction.py`, `tests/integration/test_mdm_merge_worker_postgres.py` |
| Outbox/materialization or Company preparation | `tests/integration/test_clean_outbox_names_batch.py`, `test_clean_company_versions.py`, `test_clean_relationship_version_postgres.py` |
| Transaction guards and authority | `tests/integration/test_configured_bookkeeping_postgres.py`, `test_rules_approval_postgres.py`, `test_change_journal_postgres.py`, `test_change_journal_independence_postgres.py` |
| Snowflake formula experiment | Compile/test affected dbt models and compare fixed SQL outputs; use `SNOW_CONNECTION=snowconn` for any separately authorized dev verification. |

## Completion definition

This planning ticket is complete when the responsibility matrix, database extraction classification, source/history evidence and execution gates are recorded and checked. Implementation is a subsequent task. The first proposed execution is a bounded profiling baseline, followed by one measured kernel; a whole-platform Rust rewrite or wholesale removal of stored functions is not supported by the evidence reviewed here.
