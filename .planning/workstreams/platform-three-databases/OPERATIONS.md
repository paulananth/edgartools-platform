# Selected-database operation inventory

This is a code inventory, not a claim that the platform runs on all three
engines. PostgreSQL, MySQL and SQL Server remain selected. The normal caller,
owner migration, runtime rights, installed package and populated upgrade must
agree before an operation is qualified. Company, Person and Security follow
completion of the portability work.

| Store | Normal operations and current boundary | Required work |
| --- | --- | --- |
| Rules | `rules/db.py`: save immutable version, read/list versions, prove, record exact approval, activate, resolve/export and file synchronization. `migrate()` checks PostgreSQL 16 and uses advisory locks, schema comments and triggers. | Typed indexed reads; shared native immutable/evidence decisions; destination-enforced version uniqueness, proof/approval binding and atomic activation; selected-engine migrations, grants and normal installed CLI qualification. Preserve actual operator authorization. |
| Change Journal | `change_journal/store.py`: append, get, grouped found, bounded list, verify durable receipt, status. Shared native envelope/reference/canonical/hash/receipt/read preparation; selected-engine storage has immutable history and restricted insertion. | Finish independent authorization review and installed qualification after its corrections. Frozen native migration payloads preserve initial checksums. Runtime must not administer schema, capability, readback view or principals. |
| Bookkeeping | `bookkeeping/clean/engine.py`: start/frozen run, claim/heartbeat, worker envelope/report/fail, independent verifier claim/admit, finish/resource checkpoint/generated children, wait/resume/block, checks/finalize, status/discovery, latest-capture output selection and Journal delivery. Read and completion boundaries are qualified separately. | Migrate remaining writes, profile roles, exact unbounded key storage/indexes, leases/fencing, recovery/outbox, generated scope and destination authority. `clean/database.py` still refuses non-PostgreSQL initialization. Do not remove that refusal before the entire workflow passes. |
| MDM | `mdm/clean/store.py`: policy/dataset registration, mapping versions and protected changes, batch save, outbox claim/publication verification and run status. `Store` and migration still refuse non-PostgreSQL. `merge.py` owns the normal proposal/assessment/save path. Skill-owned `database_adapter.py` supplies typed registry reads and selected-engine helper storage; pending drafts contain further native extraction. | Integrate preserved drafts after overlap review; complete normal batch transaction with scope/index validation, identity/history/relationships/survivorship and unchanged replay. Keep lease guard and business effects in the same destination transaction. Qualify normal workers, not only adapter helpers. |
| RDM | `rdm/store.py`: canonical code versions, hierarchy paths, draft/describe/approve/publish/retire/verify, immutable artifacts, lists/diffs. `rdm/database.py` requires PostgreSQL 16; normal code uses PostgreSQL JSON casts and advisory publication locks. | Shared native deterministic code/hierarchy validation and reduction; typed reads and destination-enforced immutable versions, exact approvals and current publication. Qualify selected-engine migration/grants and normal CLI. |
| Silver | `silver_writer/database.py`: checksummed registry migration and table registration. `sink.py` supplies spec/read/write/link-key/ID-refresh methods through `Sink`, with `PostgresSink` selected explicitly by `cli.py`. Current sink uses PostgreSQL COPY, temporary tables, casts, advisory/table locking and conflict handling. | Reuse the sink boundary; shared native row/type/quality/load decisions and selected-destination atomic registration, append/upsert/snapshot delivery and ID refresh. Preserve exact types, all-or-nothing failure and repeated-delivery counts. Qualify registration and existing populated tables; an empty create-all is insufficient. |

## Operation placement

- Rust owns deterministic preparation: canonical content/hashes, checks, source
  mapping/combination, work planning, match/merge/survivorship and hierarchy/load
  decisions. Existing Python computation must be migrated deliberately, not
  silently described as native.
- Python owns CLI/configuration/artifact I/O, connections, bounded transport and
  retry orchestration. Reuse each existing facade and SQLAlchemy models rather
  than introduce a parallel platform API.
- Each destination owns durable storage, exact uniqueness, authoritative
  observations/locks, privilege checks, fences and atomic state changes. A
  prepared next state never authorizes a stale or forged transition.
- PostgreSQL deferred lease checks cannot be assumed on the other engines.
  `bookkeeping/clean/destinations.py` and `destination_guard.sql` remain an
  explicit gap: the complete destination transaction must retain lease validity
  through commit. A start-of-transaction check alone does not prove that.

## Installed callers and execution

The independent Journal and Bookkeeping wheels must ship the same canonical
source and all frozen migrations plus the native control wheel. Their runtime
must remain free of source/domain packages. The full data-skill bundle, native
worker runtime inputs, image cache inputs and selected drivers must also be
qualified. MDM's merge/publication workers construct the normal `Store`, so
adapter helper success cannot establish worker support. Silver CLI still
constructs `PostgresSink`; a separate helper sink would not replace that caller.

Health/connectivity and migration CLI checks must observe the selected engine
and actual installed schema/build. Frozen legacy PostgreSQL migrations remain
historical upgrade inputs; active caller SQL is inventoried separately. Never
rename a PostgreSQL-only path as portable while retaining its function calls.

## Proof boundaries

Use invented records for engine/adversarial tests. Qualify real migrations
against populated isolated schemas and check actual indexed plans. Keep owner
and runtime separate. Test role removal, forged/stale observations, concurrent
identities, late rollback, killed-worker recovery and unchanged retries before
normal operational readiness. Preserve retained source stores.

Captured-input onboarding tests and proving runs remain after configuration
freeze. No new provider request, approval, activation, hosted cutover or merge
is implied by engine qualification.
