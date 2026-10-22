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
and Silver's PostgreSQL-specific master-ID lookup remain observed gaps. RDM's
kind-catalog dependency and Silver's explicit PostgreSQL sink selection were
removed in the current checkpoints.

| Store | Normal operations and current boundary | Required work |
| --- | --- | --- |
| Rules | `rules/db.py`: save immutable version, read/list versions, prove, record exact approval, activate, resolve/export and file synchronization. `migrate()` checks PostgreSQL 16 and uses advisory locks, schema comments and triggers. | Typed indexed reads; shared native immutable/evidence decisions; destination-enforced version uniqueness, proof/approval binding and atomic activation; selected-engine migrations, grants and normal installed CLI qualification. Preserve actual operator authorization. |
| Change Journal | `change_journal/store.py`: append, get, grouped found, bounded list, verify durable receipt, status. Shared native envelope/reference/canonical/hash/receipt/read preparation; selected-engine storage has immutable history and restricted insertion. | Finish independent authorization review and installed qualification after its corrections. Frozen native migration payloads preserve initial checksums. Runtime must not administer schema, capability, readback view or principals. |
| Bookkeeping | `bookkeeping/clean/engine.py`: start/frozen run, claim/heartbeat, worker envelope/report/fail, independent verifier claim/admit, finish/resource checkpoint/generated children, wait/resume/block, checks/finalize, status/discovery, latest-capture output selection and Journal delivery. Read and completion boundaries are qualified separately. | Migrate remaining writes, profile roles, exact unbounded key storage/indexes, leases/fencing, recovery/outbox, generated scope and destination authority. `clean/database.py` still refuses non-PostgreSQL initialization. Do not remove that refusal before the entire workflow passes. |
| MDM | `mdm/clean/store.py`: policy/dataset registration, mapping versions and protected changes, batch save, outbox claim/publication verification and run status. `Store` and migration still refuse non-PostgreSQL. `merge.py` owns the normal proposal/assessment/save path. Skill-owned `database_adapter.py` supplies typed registry reads and selected-engine helper storage; pending drafts contain further native extraction. | Integrate preserved drafts after overlap review; complete normal batch transaction with scope/index validation, identity/history/relationships/survivorship and unchanged replay. Keep lease guard and business effects in the same destination transaction. Qualify normal workers, not only adapter helpers. |
| RDM | `rdm/store.py`: canonical code versions, hierarchy paths, draft/describe/approve/publish/retire/verify, immutable artifacts, lists/diffs. The normal caller now selects PostgreSQL or MySQL typed storage, with destination publication locks and immutable history. | Shared native preparation and normal migration/grant/lifecycle cases pass on both engines. Finish search edge cases and plans, then independent installed qualification; see the checkpoint below. |
| Silver | `silver_writer/database.py`: checksummed registry migration and table registration. `relational.py` supplies one typed `DatabaseSink` to the normal CLI; the legacy sink name is a compatibility alias. PostgreSQL retains its registered physical tables; MySQL owner registration creates typed target/staging tables, with DML-only runtime access and a narrow registry-lock procedure. | Reuse the sink boundary; shared native row/type/quality/load decisions and selected-destination atomic registration, append/upsert/snapshot delivery and ID refresh. Preserve exact types, all-or-nothing failure and repeated-delivery counts. Qualify registration and existing populated tables; an empty create-all is insufficient. |

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
the five-wheel import/ownership proof passed at e6c09467 in 168.26 seconds. No retained operational store,
source onboarding, configuration activation or cutover was changed.

### Silver implementation checkpoint, 2026-10-21

One typed sink now performs append/upsert/snapshot and derived ID/quality updates
on both selected engines. Tests preserve unchanged replay, atomic refusal,
source timestamps, concurrent deliveries, populated migration reruns, CLI/context
and actual key-index plans. MySQL hashes exact keys (binary keys as hex, floating
zero normalized), with original-key predicates. Shared native JSON normalization
preserves numeric equality and raw decimal text; no Python float conversion
precedes storage. Transport keeps Unicode, large integers, microseconds and
binary values in the tested logical types.

MySQL's owner creates permanent typed staging per immutable spec. The runtime
has DML rights, no registry/migration writes and no temporary-table creation
privilege; it cannot shadow registration authority. Its transaction locks the
registered table's catalog row and cleans staging in the same commit. Interrupted
implicit DDL is recovered only for the exact spec's empty matching tables and
unique key. Strict session conversion is required before a delivery.

The current checkpoint passes 21 shared cases per engine and eight additional
MySQL recovery/permission cases, plus 143 affected PostgreSQL/unit/architecture
and 11 Rust cases. Full Silver completion is still open: MySQL calendar-interval
text, configured partition indexes, remaining transport edges/native preparation,
independently installed normal caller and the real selected-engine MDM-ID caller.
Quality and configured link tests use the existing narrow ID callback; that does
not qualify the remaining PostgreSQL-only MdmIds SQL. No operational data changed.

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
adapter helper success cannot establish worker support. Silver CLI now constructs the shared `DatabaseSink`; its independently installed normal caller passed on PostgreSQL and MySQL at 9e8f8dfb. This does not qualify the remaining MDM ID integration.

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

## Native MDM integration checkpoint, 2026-10-22

Forty preserved engine/test paths were three-way integrated from the untouched
MDM draft onto the current branch. The original files still match their private
fingerprints. Deterministic records, identity decisions, fields, profiles,
relationships and matching preparation use the existing native facade; the
PostgreSQL normal caller retains ticket 120's detail/history migrations and
the later capture-reading/opaque-Unicode corrections. The removed private
matching-field reader was restored as a thin native call after unit collection
found an existing consumer.

Kinds, profile eligibility, accepted approval floors and legacy relationship
defaults now come from a build-delivered mastering catalog, with the old values
preserved. The engine fingerprint includes the loaded catalog path. Parsing
uses captured bytes; fingerprinting and policy validation refuse subsequent
file changes or a switch from the shipped fallback to a selected catalog.
New configuration tests demonstrate an invented kind/profile and unchanged
floor enforcement; they do not qualify a new kind in the legacy physical
PostgreSQL schema. No approved policy body or operational activation changed.

Evidence: 929 MDM unit cases before the drift correction, 119 affected
catalog/activation/relationship cases after it, 104 normal PostgreSQL, worker,
Unicode and configured-combination cases after the correction, and 82 storage
adapter cases on each selected engine. The source-contract Rust suite passed.
Current installed native-MDM proof is pending.

Normal MDM Store/migration and publication still require PostgreSQL. The
remaining source-specific census/cascade namespace, field and reference
selectors, and name/place reference constants, remain explicit decoupling
work. Moving the catalog is not complete MDM portability or complete removal
of source-specific engine behavior.

### RDM ordering and installed native proof follow-up

Multilingual synonyms are ordered in shared native preparation by language and full label. PostgreSQL and MySQL actual emitted queries use child-key indexes and both word indexes on an invented 5,001-code catalog; PostgreSQL plan qualification analyzes all three joined tables. The combined affected reference/resumption tests passed 50 cases per selected engine. Short/stop-word, negative-only and tokenizer parity remain open.

Installed native MDM bundle import/configured parser/master worker/verifier passed two cases (231.13 seconds), followed by streamed XML worker recovery (one case, 48.03 seconds). This remains PostgreSQL caller evidence, not MySQL normal Store qualification.

### Configured PostgreSQL kind authority

Migration 024 replaces the historical copied kind CHECK with an owner-managed
kind catalog, a foreign key and an enabled-kind trigger. Owner installation
creates generic views for added kinds. Removed kinds retain their identities
and views, while destination checks refuse new identities. Migration takes the
save advisory gate before table DDL, avoiding inverse lock order.

Thirteen PostgreSQL cases cover populated upgrade, concurrent migration/save
lock ordering, a configured invented-kind normal merge, unchanged replay,
context command and catalog write refusals. Another 100 affected integration
cases and 32 configuration/context/limit cases passed. The normal MySQL MDM
Store remains unsupported; this checkpoint does not qualify it.

The configured-kind checkpoint at 94a43464 also passed the independent five-wheel installation/import/file-ownership check outside the checkout in 178.16 seconds, including the new schema module and migration 024.
