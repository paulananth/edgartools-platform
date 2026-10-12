# Rust, Python, and database responsibilities

Status: agreed architecture and current implementation map. Evidence refreshed
against main `9bed91fd`, 2026-10-12, plus the locally qualified publication
preparation slice (delivery status in its ticket). Complete-set
reduction is merged (#911); accepted merge replay and field ranking are merged
and CI-qualified (#920). Materialized collections/joins are merged and
CI-qualified (#921), with exact cached Company/whole-census parity. The local
and installed qualifications are recorded separately. Deployment and activation are separate gates.
Publication preparation now uses native object construction and UTF-8 bytes
through Python callers; its PostgreSQL qualification is recorded separately
from CI/merge in [its ticket](../../.planning/workstreams/database-computation-preparation/TICKET.md).
Current owners describe code execution, not production qualification.

## Responsibility map

**Configured core engine in Rust; callers and all custom code in Python.**
Rust owns generic configured execution: parsing, projection, coercion,
validation, combination/reduction, matching, identity replay, field survivorship
and relationship computation. Domain policy is versioned configuration consumed
by that engine. Python owns CLI, orchestration, integrations, retries,
verification, database clients and custom functions for unsupported operations. Databases
provide durable storage and the mechanisms that protect it: indexed retrieval,
constraints, transactions and concurrency control. The Rust engine computes
configured decisions and effects; Python coordinates them, supplies custom
behavior and drives recovery. The database stores results/history and
atomically enforces conditions that depend on current shared state.

**Default generic configured computation to Rust through Python callers.**
All custom code stays Python, even when it is CPU-intensive; measurements can
justify a reusable Rust engine primitive, not moving source-specific callbacks
to Rust. Add new generic behavior to the core with a versioned configuration
contract. Keep a computation in the database only
when it protects a storage invariant inside the write transaction, or measured
end-to-end evidence shows programs cannot perform it as effectively after data
transfer, memory, synchronization and refresh costs. Being implemented in SQL
today is not sufficient reason to keep it there.

Programs can perform every transformation discussed here. The database's
advantage is access to indexes and authoritative shared state under transactions.
For example, two workers can both observe a free lease; a conditional update or
lock must decide which one acquires it atomically. Python can issue that SQL
inside a transaction. This does not require business policy in stored functions.
The existing restricted function API remains until an alternative proves the
same grants, transactional checks and recovery guarantees.

Use existing interfaces when assigning new work. Express source mappings and
approved policy in versioned Rules configuration; the language executing a rule
does not acquire authority to approve or activate it.

Parsing and complete-set reduction use the Rust engine. Accepted identity
replay and configured field/profile eligibility and ranking now use native
kernels through Python. Materialized collections/joins now use native configured
computation and opaque Python payloads. Source revision folding,
canonical value comparison/materialization, matching/quality and relationship
projection remain Python pending their qualified ports. Python retains timestamp
and age preparation, policy authority, profile qualification and orchestration.
All custom code stays Python. New non-parsing custom extension points require
separate implementation and qualification; no such interface is added here.
See [merge qualification](../../.planning/workstreams/rust-configured-merging/RESULTS.md), [join qualification](../../.planning/workstreams/rust-configured-joins/RESULTS.md)
and [reduction qualification](../../.planning/workstreams/rust-configured-reduction/RESULTS.md).

All evidence links are repository-relative; names identify the inspected
functions. Migration prerequisites apply before replacing the current owner.

| Responsibility | Current owner and evidence | Recommended owner | Migration prerequisites / skill impact |
|---|---|---|---|
| Configured parsing, projection, coercion, assertions and record deferral | Rust: [source-contract](../../crates/source-contract/src/lib.rs), `Engine`; Python boundary: [SourceEngine](../../edgar_warehouse/rules/source_engine.py) | Rust kernel behind Python facade | Preserve types, rejection codes, ordinals, context and lookup bounds. Update READING only when interface, configuration, limits or verification changes. |
| JSON/XML framing and native record projection | Rust scans through [PyO3](../../crates/source-contract/src/python.rs), `scan_json_array` / `scan_xml_records`; Python supplies streams and callbacks | Rust computation; Python transport, authentication and publication | Exhaust valid EOF and authenticate all input before publishing. GIL release does not remove callback or row-materialization costs. No interface change here. |
| Keyed collection, sorting, distinctness and local joins | Rust: [combination](../../crates/source-contract/src/combination.rs), `combine_tables`; Python [source_combine](../../edgar_warehouse/workers/source_combine.py), `_documents`, authenticates and bounds input/output | Rust configured core; Python worker/caller | Preserve stable sorting, first/last/one, exact typed identities, null policy and aggregate budgets. Python canonical callbacks/payload access still hold the GIL; Rust scalar sorts release it. COMBINING records retained Python object overhead. See join qualification before performance claims. |
| Complete-set grouping, counts, member exclusion and samples | Rust: [reduction kernel](../../crates/source-contract/src/reduction.rs); Python [source_reduction](../../edgar_warehouse/workers/source_reduction.py), `tables`, authenticates/traverses inputs | Rust configured core; Python worker/caller | Preserve complete-input authentication, last source occurrence, lexical output, uncapped counts, state/key/member budgets and late-failure behavior. COMBINING documents native state and 1,024-row conversion batches; payload limits do not establish an RSS bound. |
| CLI, AWS/S3/SEC integrations, workers, retries, artifacts and independent verification | Python: [CLI](../../edgar_warehouse/cli.py), [source_read](../../edgar_warehouse/workers/source_read.py), [Store](../../edgar_warehouse/mdm/clean/store.py), `deliver_one` | Python | Preserve command surfaces, authenticated receipts, retry identity and verifier independence. No new operational commands. |
| All custom steps | Python functions registered in [STEPS](../../edgar_warehouse/rules/steps.py); Rust callback bridge in `python.rs` | Python only; Rust invokes supported callbacks | Preserve callback types, errors, execution identity and Mode 6 approval. Measure GIL/conversion overhead. New non-parsing extension points need their own implementation; source-specific custom code remains Python. |
| Merge coordination and policy configuration | Python: [MergeStage](../../edgar_warehouse/mdm/clean/merge.py), `_execute`; approved policy is configuration | Python caller coordinates; versioned Rules configure Rust execution | Preserve proposal identities, provenance, reviews and policy versions. Approval/activation process stays as implemented. |
| Identity consolidation and decision replay | Rust: [identity kernel](../../crates/source-contract/src/identity.rs); Python [identity](../../edgar_warehouse/mdm/clean/identity.py), `replay`, prepares metadata and preserves payload references | Rust generic core | Preserve deterministic survivor selection, dependencies, reversals, exclusions and as-of semantics. |
| Source revision replay and field/profile survivorship | Rust [ranking](../../crates/source-contract/src/survivorship.rs) behind Python [survivorship](../../edgar_warehouse/mdm/clean/survivorship.py), `select_fields`; `current_claims`, authority, freshness preparation and canonical comparisons remain Python | Rust generic core executing configured authority rules | Preserve unknown/clear/retract behavior, type/field priorities, ties and disagreement evidence. |
| Matching and quality evaluation | Python: [matching](../../edgar_warehouse/mdm/clean/matching.py), `propose`; [quality](../../edgar_warehouse/mdm/clean/quality.py), `apply` | Rust supported configured evaluation; Python candidate retrieval, coordination and custom tests/fixes | Preserve normalization, eligibility, ambiguity, withholding/exception outcomes and provenance. Generic core additions are Rust; all custom functions are Python. |
| Relationship projection and temporal graph processing | Python: [relationships](../../edgar_warehouse/mdm/clean/relationships.py), `project`, `_ultimate_parent_history` | Rust generic core executing configured relationship policy | Preserve interval boundaries, conflict/cycle outcomes and historical paths. Profile pairwise overlap loops and repeated traversal; optimize algorithms without changing evidence. |
| Stored-key lookup and closure retrieval | PostgreSQL: [012_key_join_lookups](../../edgar_warehouse/mdm/migrations/012_key_join_lookups.sql), `readings_naming`, `decisions_naming`; Python `load_closure` consumes results | Database indexed selection; Python bounded closure orchestration | Preserve complete closure, scope snapshot and consistent-state semantics. Exporting whole tables to filter in code requires separate evidence. |
| Freshness, atomic MDM effects, checkpoints, histories and publication claims | PostgreSQL: [013](../../edgar_warehouse/mdm/migrations/013_proposal_effects_hash.sql), `save_batch`; [014](../../edgar_warehouse/mdm/migrations/014_outbox_names_batch.sql), `write_batch`, `claim_outbox`; [015](../../edgar_warehouse/mdm/migrations/015_company_fields_once.sql), version writes | Database enforcement; Python prepares requests and delivers publications | Keep restricted write APIs, locks, hash checks and atomic batch/checkpoint/outbox writes. Required PG16 concurrency/recovery qualification below. |
| Lease claims, fencing and destination expiry | PostgreSQL [Bookkeeping migrations](../../edgar_warehouse/bookkeeping/clean/migrations) and [destination_guard](../../edgar_warehouse/bookkeeping/clean/migrations/destination_guard.sql), `authorize`, `valid_at_commit`; Python workers request authority | Database durable authority and server-time checks; Python retry/recovery control | Preserve resource ordering, stale-token rejection and deferred expiry check at commit. |
| Rules approval/history and Change Journal append/idempotency | PostgreSQL [approval trigger](../../edgar_warehouse/rules/migrations/003_approval_on_evidence.sql), `govern_version`; [journal](../../edgar_warehouse/change_journal/migrations/001_event.sql), `append`, unique producer/event key and immutability trigger | Database enforcement; Python clients and operator decisions | Keep evidence requirement, immutable rule bodies/history and journal collision checks. Separate stores require idempotent delivery reconciliation. |
| Warehouse joins, historical comparisons, ownership rankings and refresh dependencies | Snowflake/dbt: [financial_derived](../../infra/snowflake/dbt/edgartools_gold/models/gold/financial_derived.sql), [financial_factors](../../infra/snowflake/dbt/edgartools_gold/models/gold/financial_factors.sql), [institutional_holdings](../../infra/snowflake/dbt/edgartools_gold/models/gold/institutional_holdings.sql) | Rust for reusable configured computation; Python for custom formulas; SQL only with demonstrated efficiency | Existing dbt stays until qualified replacement. Compare complete dependency closure, restatements, late arrivals, decimal semantics and extraction/re-ingestion/refresh costs. Preserve AWS native S3 pull; changing that deployment architecture requires a separate operator decision. |

## Existing database computation

**Movable** means pure computation over explicit inputs can be prepared in code;
it does not authorize removal of SQL consumers or destination checks.
**Conditionally movable** requires protocol/consumer changes and qualification.
**Retained** means storage/concurrency enforcement remains in the database.
Retrieval retained for efficiency must be justified against program-side work;
current indexed lookup history provides evidence, not a permanent exemption.
Moving SQL text into a Python module still executes that computation in SQL.

| Existing work / current owner | Classification and recommended owner | Prerequisites before migration |
|---|---|---|
| PostgreSQL `entity_name` and `relationship_holds` in [006](../../edgar_warehouse/mdm/migrations/006_relationship_context.sql) | Movable pure evaluation: Rust configured core; Python only for custom behavior | Keep SQL functions for query/view consumers until replaced. Match SQL coalesce (empty text does not fall through), missing/null, retired/derived flags, timestamp casts and half-open periods. Accept explicit timezone-normalized inputs. |
| PostgreSQL outbox JSON assembly in [014](../../edgar_warehouse/mdm/migrations/014_outbox_names_batch.sql), `outbox_delivery` | Active publication preparation moved to Rust [JSONB object preparation](../../crates/source-contract/src/postgres_jsonb.rs), behind Python [payloads](../../edgar_warehouse/mdm/clean/payloads.py); [016](../../edgar_warehouse/mdm/migrations/016_publication_inputs.sql) exposes indexed immutable inputs | Preserve raw PostgreSQL numeric scale/precision and existing payloads; compare final bytes with the committed expected hash before sending. DB retains independent expected-hash derivation at commit, claim ordering, fencing and atomic intent. Existing view/claim APIs remain compatible for frozen runtimes. See [placement decisions and qualification](../../.planning/workstreams/database-computation-preparation/DECISIONS.md). |
| PostgreSQL request structure checks in `write_batch` | Movable configured preflight: Rust; Python custom checks; retained authoritative validation: DB | Preparation already happens in Python. Every writer still faces DB bounds, source authority, collisions and stale-state checks through restricted functions. Preflight cannot replace these checks. |
| PostgreSQL scalar extraction from Company projection in [015](../../edgar_warehouse/mdm/migrations/015_company_fields_once.sql), `record_company_version` | Conditionally movable configured preparation: Rust through Python caller; retained version transitions: DB | Keep canonical-body/scalar consistency, alias routing, microsecond version progression and atomic close/open. Compare total round trips, parameters and bytes after existing deduplication improvements. |
| PostgreSQL `journal.canonical` and envelope hashing in [001_event](../../edgar_warehouse/change_journal/migrations/001_event.sql) | Movable generic canonicalization/hashing: Rust; current Python producer in [journal store](../../edgar_warehouse/change_journal/store.py); retained canonical/hash validation: DB | Native producer port needs exact Unicode/key ordering, numeric spelling, null and byte parity. MDM compact Python JSON and PostgreSQL JSONB text are distinct protocols. Retain append uniqueness and conflicting-key rejection. |
| PostgreSQL `match_proposal_snapshot` in [012](../../edgar_warehouse/mdm/migrations/012_key_join_lookups.sql), rechecked by `save_batch` in 013 | Retained: DB authoritative snapshot and freshness | An application may consume a bounded snapshot, but commit must recheck live dependencies under the locking protocol. Outside-transaction hashing is not a freshness guarantee. |
| PostgreSQL indexed key joins in 012 | Retained indexed retrieval: DB; program computes closure | Lookup tuning in `c16968be` supports using storage indexes instead of exporting whole tables. Reassess if a bounded program-side alternative is more effective; preserve consistent snapshots and closure completeness. |
| PostgreSQL relationship-context shaping and parent-chain traversal in 006 | Conditionally movable generic traversal/shaping: Rust through Python caller; database retrieves necessary indexed records | Compare bounded bulk retrieval plus traversal against recursive SQL; preserve consistent snapshot, complete closure, hop/cycle limits and evidence. Retain SQL only if it demonstrates an effective retrieval/computation advantage. |
| PostgreSQL uniqueness, role authorization, lease/fence enforcement, history, checkpoints and atomic effects | Retained: DB | Application checks supplement destination enforcement. Prove competing writers, expiry, collisions and recovery with restricted roles before any API redesign. |
| Snowflake row-local formulas, e.g. `safe_ratio` usage in `financial_factors` | Movable pure formulas: Rust configured primitives; Python custom formulas; current SQL unchanged | Compare fixed SQL/code inputs for decimal precision/scale, zero/null behavior and identical outputs. Qualify refresh dependencies, consumers and publication costs before adoption. |
| Snowflake historical joins/windows and ownership rankings | Conditionally movable: Rust configured core with Python callers/custom functions; retain SQL only with demonstrated full-path efficiency | Programs need complete affected population/history, deterministic tie-breaking and late-arrival/restatement refresh machinery. Measure transfer, memory and publication costs before selecting the implementation. |

## Qualification required for later ports

1. Pin artifacts, contracts, policies, native binary/execution digest and database
   snapshot. Measure CPU, wall time, peak RSS, conversion, transferred bytes,
   SQL calls and lock duration on bounded small/large workloads. Compare serial,
   2-worker and 4-worker full paths where concurrency is relevant. Use measured cost and migration risk
   to sequence configured core migrations; no speedup is claimed here.
2. Compare exact values/types, ordering, null/missing behavior, rejection codes,
   canonical bytes/hashes, provenance and receipts. Exercise duplicate keys,
   ties, Unicode, integer/decimal edges, every bound and malformed final input.
   Reuse [engine tests](../../tests/engine) and [MDM tests](../../tests/mdm);
   include original SQL versus code on fixed inputs for SQL extraction.
3. Use real PostgreSQL 16 and restricted worker/verifier roles for stale
   assessments, simultaneous writers, replaced/expired leases, duplicate
   batches/events, rollback and lost acknowledgements. Batch effects, history,
   checkpoint and required outbox rows stay atomic within MDM. Rules,
   Bookkeeping, MDM, Change Journal and S3 do not share one atomic commit;
   preserve idempotent delivery/reconciliation and crash recovery between them.
4. Qualify installed consumer paths and replay before retiring an active
   caller. Preserve compatibility with already committed batches and payloads.
   Require unchanged semantic, bounds, concurrency and recovery guarantees.
   A CPU optimization must demonstrate full-path improvement. A placement change
   for simpler program ownership may instead demonstrate acceptable performance
   and resource costs; record that tradeoff explicitly. Set measured acceptance
   thresholds in that execution ticket; this map introduces no arbitrary threshold.
5. Update affected operational skill commands/examples against the qualified
   implementation, then follow existing operator review, approval and activation.

## Skill impact

| Skill document | Update now | Trigger for later changes |
|---|---|---|
| [data-platform/SKILL.md](../../skills/data-platform/SKILL.md) | Add architecture boundaries, placement guidance and qualification requirement | Update capability statements only after implementation and installed-path proof. |
| [READING.md](../../skills/data-platform/READING.md) | None: native interfaces, configuration, limits and verifier behavior are unchanged | A reading interface/configuration/bounds/authentication change requires corresponding examples and qualification. |
| [COMBINING.md](../../skills/data-platform/COMBINING.md) | Reduction and materialized collections/joins reflect Rust computation, Python payload/canonical overhead, unchanged bounds and independent verification | Update when grammar, bounds, authentication, materialization or verification actually change. |
| [data-onboarding](../../skills/data-onboarding/SKILL.md) and [refining-rules](../../skills/refining-rules/SKILL.md) | None: authoring, test qualification, operator approval and activation steps are unchanged | Change only when those actual steps change; implementation language alone does not change Rules authority. |

Architecture boundaries guide new work; current kernel capabilities and their qualification are recorded separately. Existing Mode 6
Python custom steps and all operator commands/examples remain valid as written.
Shared skill edits require ownership inspection and `scripts/dev/overlap_guard.sh`
before edits, commits and pushes. The detailed evidence in this map is for a
repository checkout; installed agents use the boundary guidance in the platform skill.

## Design review

Applied `gof-refactor-reviewer` to the existing facade, callback bridge, combine/
reduce and Merge Stage code and history. Verdict: retain existing seams; no
new GoF hierarchy is warranted. `SourceEngine` already adapts the native engine.
Merge Stage prepares effects through Store; the database validates persistence.

Relevant history: `3368da36` authenticated incremental reading; `716cb999`
native XML projection; `c16968be` indexed lookup joins; `9a72285b` bounded MDM
batch-size handling; `4ace81d3` eliminated duplicate outbox/Company writes.
These show real costs addressed at existing boundaries. Additional dispatch
classes would add indirection and migration risk without measured benefit.
Keeping these seams leaves conversion and SQL serialization costs to measure;
it avoids duplicating transaction authority or hardcoding configured domain policy.
