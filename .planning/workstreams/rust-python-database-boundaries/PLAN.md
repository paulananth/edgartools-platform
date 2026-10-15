# Rust, Python, and database boundaries

## Goal and status

Use Rust for generic configured computation, Python for callers and all custom
code, and databases for durable storage and authoritative shared-state enforcement.
Programs prepare effects; the destination validates and commits them atomically.

This is a completed architecture-planning ticket, refreshed against main
`82f4e5ce` on 2026-10-14. It changes documentation only. Existing implementation
and qualification records are linked below; this ticket neither implements a new
kernel nor claims a new benchmark, PostgreSQL qualification or deployment.

The original proposal was inspected at `51b45916` and committed as `9d3dfeba`.
The requested rebase preserves that proposal's history; this revision supersedes
its outdated recommendations. The inherited `fix-pipelines` pointer and unrelated
worktrees are untouched. Completion owns this directory and the related corrections
in the [canonical responsibility map](../../../docs/architecture/runtime-responsibilities.md).

## Accepted responsibility boundary

**The configured core belongs in Rust. All custom code stays Python.**
Versioned Rules express source mappings and domain policy; choosing an execution
language does not grant authority to approve or activate those rules. Python owns
CLI commands, AWS/SEC/S3 transport, workers, retries, artifact authentication,
independent verification, database clients, orchestration and recovery decisions.

Databases provide storage, indexes, constraints and transactions that arbitrate
current shared state. Python may issue transactional SQL through the current
restricted APIs. Do not move business policy into stored functions by default,
and do not remove locking, uniqueness, history, leases or fencing as a side effect
of moving computation into programs. Retain database computation for a storage
invariant or demonstrated complete-path efficiency, including transfer and refresh
costs. Existing SQL alone is not evidence that it is the preferred future owner.

The canonical map supplies the detailed placement contract. The
[platform skill](../../../skills/data-platform/SKILL.md) states the native kernel,
Python caller/custom-code and database authority boundary. A separate focused
skill correction in [PR979](https://github.com/paulananth/edgartools-platform/pull/979)
distinguishes contract2 native publication preparation from contract3 SQL
preparation. Neither change alters approval or activation procedures.

## Current implementation, checked after rebase

| Responsibility | Current owner and inspected source | Remaining boundary |
|---|---|---|
| Configured parsing, projection, coercion, assertions and framing | Rust [engine](../../../crates/source-contract/src/lib.rs) and [PyO3 bridge](../../../crates/source-contract/src/python.rs), reached through Python [SourceEngine](../../../edgar_warehouse/rules/source_engine.py) | Python authenticates transport/artifacts and supplies supported custom callbacks; conversion and callback costs still matter. |
| Materialized combinations, collections, ordering and joins | Rust [combination kernel](../../../crates/source-contract/src/combination.rs); Python [source_combine](../../../edgar_warehouse/workers/source_combine.py), `_documents`, calls the facade | Python retains input/output authentication and opaque payload/canonical callbacks. PR921 already delivered this port. |
| Complete-set reduction | Rust [reduction kernel](../../../crates/source-contract/src/reduction.rs) through `ReductionEngine`; Python [source_reduction](../../../edgar_warehouse/workers/source_reduction.py), `tables`, exhausts authenticated input streams | PR911 already delivered the native kernel; PR978 allows several declared sources/tables. Retain finalization only after complete successful exhaustion. |
| Accepted identity-decision replay | Rust [identity kernel](../../../crates/source-contract/src/identity.rs); Python [identity.replay](../../../edgar_warehouse/mdm/clean/identity.py) prepares metadata and time semantics | Replay does not infer a merge from field priority or acquire policy authority. PR920 already delivered this port. |
| Eligible field/profile claim ranking | Rust [ranking kernel](../../../crates/source-contract/src/survivorship.rs), called from Python [survivorship](../../../edgar_warehouse/mdm/clean/survivorship.py), `_select_values` | Source-history folding, profile qualification, authority/time preparation and canonical value comparison remain Python. Do not describe all survivorship as native. |
| Publication object preparation | Contract2 uses Rust [PostgreSQL JSONB preparation](../../../crates/source-contract/src/postgres_jsonb.rs); contract3 obtains SQL-built `payload_text` through [migration018](../../../edgar_warehouse/mdm/migrations/018_publish_changed_records.sql) and the view updated by020. Python [payloads.prepare](../../../edgar_warehouse/mdm/clean/payloads.py) checks either path against the committed expected hash | PR925 delivered contract2 preparation, not every later publication contract. Preserve raw numeric spelling, changed-record order/flags and stored bytes. The database derives expected hashes and commits publication intent. |
| Merge orchestration, matching, quality and relationship projection | Python [MergeStage](../../../edgar_warehouse/mdm/clean/merge.py), [matching](../../../edgar_warehouse/mdm/clean/matching.py), [quality](../../../edgar_warehouse/mdm/clean/quality.py), [relationships](../../../edgar_warehouse/mdm/clean/relationships.py) and [scope](../../../edgar_warehouse/mdm/clean/scope.py) | Future reusable configured kernels belong in Rust after qualification. All source-specific/custom behavior stays Python. |
| Indexed selection and authoritative writes | PostgreSQL [lookup migration012](../../../edgar_warehouse/mdm/migrations/012_key_join_lookups.sql), restricted Store APIs and [migration020](../../../edgar_warehouse/mdm/migrations/020_merge_record_by_record.sql) | Preserve destination current-state checks, atomic effects/history/checkpoints and proposal lifecycle. Read the latest migrations, not only the original function definition. |
| Warehouse formulas and history/population-wide analytics | Current Snowflake [dbt models](../../../infra/snowflake/dbt/edgartools_gold/models) | A program-side replacement is conditional on exact semantics, complete dependency/history handling, refresh/publication and measured total cost. SQL is the current implementation, not a permanent placement exemption. |

Existing evidence, with its own scope and dates:
[reduction results](../rust-configured-reduction/RESULTS.md),
[merge-kernel results](../rust-configured-merging/RESULTS.md),
[join results](../rust-configured-joins/RESULTS.md), and
[publication placement decisions](../database-computation-preparation/DECISIONS.md).
Those records are not new qualification performed by this planning ticket.

## Changes that supersede the original proposal

1. **Several proposed ports are already implemented.** Combining, reduction,
   accepted identity replay, field ranking and publication preparation must not
   be scheduled again as new work. Distinguish each native kernel from remaining
   Python preparation, callbacks, orchestration and policy authority.
   Publication is contract-specific: contract3 SQL materialization remains a
   separate code-placement candidate; the Python `payload_text` path bypasses
   native object construction while retaining the committed-hash check.
2. **Proposal freshness no longer uses a whole-scope snapshot.**
   [Migration020](../../../edgar_warehouse/mdm/migrations/020_merge_record_by_record.sql)
   drops `mdm.match_proposal_snapshot(jsonb)`. `MergeStage._execute` acquires the
   Merge Stage transaction lock and computes/records the proposal and batch in
   the same transaction. `apply_assessment` recomputes an earlier proposal under
   that lock; `save_batch` rejects mismatched assessed effects and already-used
   proposals. Preserve this complete protocol. Do not recreate the retired
   snapshot or replace transaction authority with an unchecked cached digest.
3. **Merge Stage size refusals were removed.**
   [Migration019](../../../edgar_warehouse/mdm/migrations/019_merge_stage_no_limit.sql)
   and PR960 remove Merge Stage closure/projection/request/proposal size refusals;
   PR963 scopes replay and projection to affected masters and links. Existing
   input batching, shape checks and read-back bounds remain. Benchmarks use
   bounded samples; they do not introduce a new total-work ceiling or a limit
   inferred from a local machine. Bookkeeping's separate protocol bounds remain
   under the operator's MDM-only ruling.
4. **An ownership requirement is not proof of a repaired implementation.**
   Database authority must ultimately authenticate fencing and current-state
   transitions. The [Bookkeeping plan](../bookkeeping-p2-autoplan/PLAN.md) and
   [follow-ups](../../../TODOS.md) retain separate P1 work on destination proof
   authentication and complete runtime fingerprints. This architecture ticket
   does not close those findings or qualify a per-unit Bookkeeping fast path.
5. **The old example thresholds are not adopted release requirements.**
   The original 20%/10% examples were proposed, not accepted or measured here.
   Set workload-specific acceptance criteria in each execution ticket. A CPU
   optimization needs complete-path benefit; a placement change for simpler
   program ownership may instead document acceptable performance and resource
   costs explicitly, consistently with the canonical map.

## Remaining database-to-code candidates

| Work | Treatment before any future port |
|---|---|
| Contract3 changed-record publication shaping in migration018/020 | Still SQL computation, unlike the native contract2 path. A program-side replacement must preserve forced-publication flags, changed-record membership/order, numeric spelling, exact bytes/hashes, no-change behavior and compatibility. Database change records, expected hashes and atomic intent remain authoritative. |
| `entity_name` and `relationship_holds` in [migration006](../../../edgar_warehouse/mdm/migrations/006_relationship_context.sql) | Pure evaluation is movable. Retain SQL query/view consumers until replaced; qualify null/empty, timezone and half-open interval behavior. A small helper alone does not justify a new subsystem. |
| Company scalar extraction from canonical projections in [migration015](../../../edgar_warehouse/mdm/migrations/015_company_fields_once.sql) | Programs may prepare fields; database consistency, close/open version transitions and atomic history remain authoritative. Measure transferred bytes, parameters and total write cost. |
| Producer canonicalization and hashing for [Change Journal](../../../edgar_warehouse/change_journal/store.py) | A reusable Rust primitive is possible; preserve the existing byte protocol and independent database validation. MDM JSONB text and compact producer JSON are distinct protocols. |
| Relationship traversal and population/history-dependent analytics | Compare complete indexed retrieval plus program computation with current SQL. Preserve snapshot/closure completeness, interval/cycle semantics, late-arrival dependencies and publication. |
| Request validation, locks, constraints, leases and atomic effects | Programs can preflight and prepare. Destination enforcement remains mandatory for every writer; moving SQL text into Python still executes it in the database. Any restricted-API redesign needs separate grant/concurrency/recovery proof. |

## Sequence for a later execution ticket

1. Pin current artifacts, Rules, runtime inputs and stored state. Measure reading,
   conversion, combine/reduce, scope retrieval, remaining policy computation,
   serialization, commit and delivery on the complete caller path. Announce long
   work; local test invocations remain below the repository's five-minute limit.
2. Choose one measured, still-unported generic kernel or database preparation
   step. Compare algorithm/query improvements before changing language. The
   historical proposal to start by porting reduction is superseded by PR911.
3. Reuse the facade and current Python caller interfaces. Add no per-row callback
   framework, language-selection hierarchy or external requests in a pure kernel.
   Runtime artifacts and code dependencies must remain reproducibly identified.
4. Qualify exact outputs, types, ordering, null/missing rules, rejection behavior,
   canonical bytes/hashes, late EOF, all applicable bounds and error paths. For
   SQL extraction, compare original SQL and program output on the same inputs.
5. For a changed persistence/authority boundary, use real PostgreSQL16 with
   restricted roles. Prove competing writers, stale effects, expired/replaced
   leases, idempotent replay, rollback and lost acknowledgements. MDM, Rules,
   Bookkeeping, Change Journal and S3 do not share a single atomic transaction.
6. Run installed caller paths and complete-path cost measurements, including
   serial/2-worker/4-worker comparison where concurrency is relevant. Adopt only
   when the recorded execution-ticket criteria pass; otherwise retain the current
   implementation and publish the result.
7. Update operational skills only for qualified capability/interface changes.
   Follow existing operator review and activation rules. Preserve old committed
   artifacts and reconcile in-flight writes during rollback; do not undo durable
   history or remove destination checks.

## Design review and completion

Applied `gof-refactor-reviewer` to current source and change history. The existing
`SourceEngine` facade, Rust kernels, Python workers and Store boundary already
supply the required seams. PR911/920/921/925 extend those seams; PR960/963 change
MDM scope and transaction behavior without introducing a language-dispatch
hierarchy. Adding another Proxy/Strategy/Mediator layer would add conversion,
indirection and duplicated authority without an evidenced present-day benefit.
Retain the current design; measure remaining conversion/callback costs.

Completion means the rebased planning artifacts and canonical map agree with
current source, existing skill guidance and the operator's storage-first ruling,
with verification and a reviewable PR. New ports, full performance qualification,
provider requests, AWS deployment and activation remain separate work.

Fresh documentation/source checks and their limits are recorded in
[verification](VERIFICATION.md).
