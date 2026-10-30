# Complete the normal Bookkeeping storage lifecycle on PostgreSQL and MySQL

Status: normal PostgreSQL/MySQL control implemented and locally qualified; committed-install qualification, review, publication and CI remain open.
Base: d18cbbb8c; branch codex/bookkeeping-storage-portability-20261029.
Parent: control-store-portability and platform-three-databases.

## Parts

- [x] Reconcile live ownership and normal control callers; retain existing PostgreSQL guarantees and all selected-engine read/completion/resume evidence — 2026-10-30 00:48 ET: live code/history and overlap checks; source workers use destination-owned capabilities, with no import/call of the legacy caller-held guard. Historical migrations unchanged.
- [x] Demonstrate the normal configured initialization/start failure on MySQL, using isolated databases and restricted worker/verifier logins — 2026-10-30 00:48 ET: normal owner initialization first failed on the missing configured-database argument; subsequent real default-driver, missing lifecycle capability, timestamp and migration/read boundaries were reproduced before fixes.
- [ ] Implement owner migration, independent package contents, restricted runtime grants and profile duties on both engines.
- [x] Complete ordinary start/claim/renew/report/verify/admit, delivery and finalization with actual normal callers — 2026-10-30 00:48 ET: selected-engine normal API flows pass; initial independent control-only CLI proofs passed from empty stores on both engines with two external workload profiles and separate logins (48.41/51.17 seconds, PostgreSQL run also included eight architecture cases).
- [x] Qualify immutable frozen work, exact large integers/Unicode, issuer duties, stale/missing fences, expiry, runtime pins, concurrency and rollback — 2026-10-30 00:48 ET: 21 MySQL cases pass, including long exact keys/indexed reads, both duties on one login refusing self-verification, changed worker/verifier runtimes and completion delayed past expiry; retained PostgreSQL cohort passed 78 cases in 85.49 seconds.
- [x] Qualify ordered/resource checkpoints, generated children, unchanged retries and populated migration recovery — 2026-10-30 00:48 ET: real normal callers and owner interruption/restore preserve committed work, cursor precision, roles and intent; missing tables are refused without recreation. Independent committed-install check remains separately open below.
- [ ] Qualify independent installed control CLI/workers, package independence and normal recovery with Change Journal.
- [ ] Review Standards, Spec and GoF; publish implementation and final CI evidence in a PR before closeout.
- [ ] ~~SQL Server normal lifecycle~~ deferred until the PostgreSQL/MySQL gate; retain current adapter tests.
- [ ] Learning → skill: separate reusable procedural corrections or record none.

## Scope and initial GoF consult

The operator requested Rules/Bookkeeping portability and Change Journal, with
PostgreSQL/MySQL first. Rules has its own bounded implementation branch. Journal
already has its normal selected-engine implementation; reuse it. Keep one
Bookkeeping facade and its fixed external worker/verifier protocol. Shared
Python/Rust prepares frozen work, specifications and deterministic results;
the database owns durable state, exact identities, authorization, leases/fences,
current-state comparisons and atomic commits. No domain callbacks, new execution
engine, source interpretation, provider request or production store change.

The existing history (f001c3c4, e44e5daa) establishes typed selected-engine reads
and native prepared run completion/resumption behind the existing facade. Reuse
those boundaries; SQL dialect variation belongs to the storage adapter. A new
class hierarchy has no demonstrated benefit. Preserve historical migrations.
Tests use isolated databases on the existing test servers and private credentials;
no shared operational store is modified.

## Qualified implementation boundary

The existing facade now names control actions; the small lifecycle adapter owns
PostgreSQL call syntax and the MySQL storage capability. Frozen configuration,
work preparation, dependency reconstruction and verifier-report checking remain
in shared Python/Rust. MySQL uses database-owned transactions to recheck physical
profile memberships, current leases/fences and receipt comparisons before commit.
It preserves opaque documents/cursors as exact text; internal hashes index long
identities while predicates retain their original values.

MySQL owner installation is checksummed and rejects untracked metadata. A pending
marker refuses normal mutation, even for cached callers. Interrupted guard rebuild
revokes old callers first; run migration for each configured runtime principal to
restore its SELECT/EXECUTE grants after repair. Completed table/index/procedure or
untracked-trigger drift refuses access. No caller receives direct control writes
or capability administration. The new MySQL v1 payload is frozen when published;
prior PostgreSQL migrations remain unchanged.

Change Journal storage is retained. Its API already supported an explicit isolated
database name, but its normal CLI did not expose that choice. The small CLI flag
addition is tested through real init/migrate commands; all ten current normal
Journal cases pass on each selected engine. No Journal storage rewrite was needed.

The legacy guard for a caller-held destination transaction remains PostgreSQL-only.
Both unsupported MySQL entry points now refuse before SQL, with the exact boundary
named; no deferred-commit emulation was invented. Normal writers use their owning
destination's atomic capability. Existing PostgreSQL guard tests remain intact.

The recovery pass also found an acknowledgement bug in the first MySQL prototype:
the literal error name `null` was confused with JSON null and acknowledged a failed
Journal verification. The red case now passes: intent remains pending, the same
durable event is reconciled and no duplicate event appears on retry.

No source run, provider request, production installation, activation or cutover
was performed. SQL Server's normal control lifecycle remains a later gate.
