# Selected-database operation inventory

This is a code inventory, not a claim that the platform runs on all three
engines. The operator's 2026-10-21 priority is completion of MDM, RDM and Silver
on PostgreSQL and MySQL; SQL Server follows last. Other store work proceeds
only when a demonstrated dependency blocks those three stores. The normal caller,
owner migration, runtime rights, installed package and populated upgrade must
agree before an operation is qualified. Company, Person and Security follow
completion of the portability work.

Entity-specific choices belong in configuration: kinds, profiles, identifiers,
fields, source priorities, relationships and matching/selection rules. Shared
code must accept configured kinds without a new branch or entity-name constant.
RDM and Silver must not import MDM's entity catalog to decide their own storage
behavior. Cross-store lookups use an explicit narrow interface; SQL syntax,
locking, constraints and grants stay at the selected storage boundary. Current
MDM `evidence.py` kind/profile constants and `activation.py` kind-specific bars,
RDM's imports of MDM's kind catalog, Silver's explicit `PostgresSink` caller and
PostgreSQL-specific master-ID lookup are observed gaps, not completed support.

| Store | Normal operations and current boundary | Required work |
| --- | --- | --- |
| Rules | `rules/db.py`: save immutable version, read/list versions, prove, record exact approval, activate, resolve/export and file synchronization. `migrate()` checks PostgreSQL 16 and uses advisory locks, schema comments and triggers. | Typed indexed reads; shared native immutable/evidence decisions; destination-enforced version uniqueness, proof/approval binding and atomic activation; selected-engine migrations, grants and normal installed CLI qualification. Preserve actual operator authorization. |
| Change Journal | `change_journal/store.py`: append, get, grouped found, bounded list, verify durable receipt, status. Shared native envelope/reference/canonical/hash/receipt/read preparation; selected-engine storage has immutable history and restricted insertion. | Finish independent authorization review and installed qualification after its corrections. Frozen native migration payloads preserve initial checksums. Runtime must not administer schema, capability, readback view or principals. |
| Bookkeeping | `bookkeeping/clean/engine.py`: start/frozen run, claim/heartbeat, worker envelope/report/fail, independent verifier claim/admit, finish/resource checkpoint/generated children, wait/resume/block, checks/finalize, status/discovery, latest-capture output selection and Journal delivery. Read and completion boundaries are qualified separately. | Migrate remaining writes, profile roles, exact unbounded key storage/indexes, leases/fencing, recovery/outbox, generated scope and destination authority. `clean/database.py` still refuses non-PostgreSQL initialization. Do not remove that refusal before the entire workflow passes. |
| MDM | `mdm/clean/store.py`: policy/dataset registration, mapping versions and protected changes, batch save, outbox claim/publication verification and run status. `Store` and migration still refuse non-PostgreSQL. `merge.py` owns the normal proposal/assessment/save path. Skill-owned `database_adapter.py` supplies typed registry reads and selected-engine helper storage; pending drafts contain further native extraction. | Integrate preserved drafts after overlap review; complete normal batch transaction with scope/index validation, identity/history/relationships/survivorship and unchanged replay. Keep lease guard and business effects in the same destination transaction. Qualify normal workers, not only adapter helpers. |
| RDM | `rdm/store.py`: canonical code versions, hierarchy paths, draft/describe/approve/publish/retire/verify, immutable artifacts, lists/diffs. The normal caller now selects PostgreSQL or MySQL typed storage, with destination publication locks and immutable history. | Shared native preparation and normal migration/grant/lifecycle cases pass on both engines. Finish search edge cases and plans, then independent installed qualification; see the checkpoint below. |
| Silver | `silver_writer/database.py`: checksummed registry migration and table registration. `sink.py` supplies spec/read/write/link-key/ID-refresh methods through `Sink`, with `PostgresSink` selected explicitly by `cli.py`. Current sink uses PostgreSQL COPY, temporary tables, casts, advisory/table locking and conflict handling. | Reuse the sink boundary; shared native row/type/quality/load decisions and selected-destination atomic registration, append/upsert/snapshot delivery and ID refresh. Preserve exact types, all-or-nothing failure and repeated-delivery counts. Qualify registration and existing populated tables; an empty create-all is insufficient. |

## Operation placement

### RDM implementation checkpoint, 2026-10-21

The normal version caller now uses typed queries on PostgreSQL and MySQL.
Canonical version bytes, paths, exact summaries/code ordering and search-result
selection run in the shared native control library. MySQL retains unbounded
binary-exact text with tuple-hash indexes and original-field predicates; its
frozen migration enforces version/content guards, foreign keys and one current
publication. PostgreSQL retains its frozen history and receives migration 003
to lock a content edit's version against concurrent approval.

RDM no longer imports MDM's entity catalog or connection implementation.
Namespace reservation reads the existing context configuration; connection
selection and exact JSON/UTC transport are neutral shared modules. The runtime
has no migration-metadata writes. MySQL DDL recovery preserves a checksum-bound
incomplete marker, revokes runtime writes before dropping guards and restores
access only after successful installation. Adversarial grant and interruption
cases pass, including failure against populated published history.

The current checkpoint passes 34 shared cases on each engine and seven MySQL
DDL/security cases. Basic word/phrase/alternative/exclusion and literal-fallback
search cases pass; eight native scoring cases agree with the PostgreSQL
reference. Search is not fully qualified: short/stop-word candidate behavior,
negative-only queries, compound tokens, multilingual ordering and actual search
plans remain. The data wheel explicitly includes both new neutral modules;
independent installed proof remains pending. No retained operational store,
source onboarding, configuration activation or cutover was changed.

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
