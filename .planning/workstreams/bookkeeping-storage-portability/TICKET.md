# Complete the normal Bookkeeping storage lifecycle on PostgreSQL and MySQL

Status: PostgreSQL/MySQL implementation, committed-install qualification and review complete; publication/final CI remain the release gate. SQL Server normal lifecycle remains deferred.
Base: b05d27513; branch codex/bookkeeping-storage-portability-20261029.
Parent: control-store-portability and platform-three-databases.

## Parts

- [x] Reconcile live ownership and normal control callers; retain existing PostgreSQL guarantees and all selected-engine read/completion/resume evidence — 2026-10-30 00:48 ET: live code/history and overlap checks; source workers use destination-owned capabilities, with no import/call of the legacy caller-held guard. Historical migrations unchanged.
- [x] Demonstrate the normal configured initialization/start failure on MySQL, using isolated databases and restricted worker/verifier logins — 2026-10-30 00:48 ET: normal owner initialization first failed on the missing configured-database argument; subsequent real default-driver, missing lifecycle capability, timestamp and migration/read boundaries were reproduced before fixes.
- [x] Implement owner migration, independent package contents, restricted runtime grants and profile duties on both engines — 2026-10-30 06:51 ET: committed independent control-only installation passed on both engines at source head 6b057fc8; real restricted worker/verifier duties and host-restricted MySQL account qualification passed.
- [x] Complete ordinary start/claim/renew/report/verify/admit, delivery and finalization with actual normal callers — 2026-10-30 00:48 ET: selected-engine normal API flows pass; initial independent control-only CLI proofs passed from empty stores on both engines with two external workload profiles and separate logins (48.41/51.17 seconds, PostgreSQL run also included eight architecture cases).
- [x] Qualify immutable frozen work, exact large integers/Unicode, issuer duties, stale/missing fences, expiry, runtime pins, concurrency and rollback — 2026-10-30 00:48 ET: 21 MySQL cases pass, including long exact keys/indexed reads, both duties on one login refusing self-verification, changed worker/verifier runtimes and completion delayed past expiry; retained PostgreSQL cohort passed 78 cases in 85.49 seconds.
- [x] Qualify ordered/resource checkpoints, generated children, unchanged retries and populated migration recovery — 2026-10-30 00:48 ET: real normal callers and owner interruption/restore preserve committed work, cursor precision, roles and intent; missing tables are refused without recreation. Independent committed-install check remains separately open below.
- [x] Qualify independent installed control CLI/workers, package independence and normal recovery with Change Journal — 2026-10-30 06:51 ET: final committed control-only CLI runs from empty stores, uses two external workload profiles/separate logins, finalizes/resumes/retries unchanged, and refuses missing Journal history; PostgreSQL 130.39 seconds, MySQL 69.73 seconds. No domain distribution in the controller installation.
- [x] Complete Standards, Spec and GoF review — 2026-10-30 06:51 ET: two independent Luna low reviewers, including host/account and Journal safeguard increments, found no remaining blocking issue; keep the existing facade/storage seam.
- [x] Publish reviewed implementation in PR #1237 — 2026-10-30 07:11 ET: production source 6b057fc8 and initial record head 07909421 are published; final-head CI remains a separate gate.
- [x] Qualify the coupled installed Rules → Bookkeeping → real workers/verifier → Journal pipeline — 2026-10-30 07:11 ET: five-wheel installed source 07909421 passed on MySQL (132.29 seconds) and PostgreSQL (43.72 seconds); two verified steps, two Journal events, unchanged resume. Two independent reviewers found no Standards, Spec or GoF issue in the added test.
- [ ] Qualify final published head in full CI before readiness and merge.
- [ ] ~~SQL Server normal lifecycle~~ deferred until the PostgreSQL/MySQL gate; retain current adapter tests.
- [x] Learning → skill: bookkeeping and change-journal — 2026-10-30 07:11 ET: separate PR #1239 records configured initialization, role membership, host restrictions, interrupted install and lost-history recovery; 95 affected checks and independent review passed. Merge follows #1237.

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
addition is tested through real init/migrate commands. A new populated-recovery
case also proved that completed MySQL Journal migration recreated a missing event
table; the owner now refuses that condition before DDL. All eleven current normal
Journal cases pass on PostgreSQL/MySQL, and the installed proof includes the same
refusal. The existing append/receipt protocol and historical SQL remain unchanged.

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

## Final source qualification and review

Source head 6b057fc8 is the committed installation proof. The MySQL cohort has 22
normal/security/recovery cases, including the final host-restricted account case;
ambiguous account names refuse both migration and cached profile execution. The
PostgreSQL selected read/completion/resume/control cohort passed 48 cases with ten
explicit MySQL-only skips before that additional MySQL-only case. The retained
78-case PostgreSQL regression cohort also passed. Eleven Journal cases pass on
each selected engine. Every local invocation stayed below five minutes; source
compile/import and whitespace checks pass. No Python typechecker is configured
for these modules; CI runs the full repository cohorts.

### Standards

Independent review found no documented violation. Counters/positions use BIGINT;
opaque document/cursor precision remains intact. Historical PostgreSQL migrations
are immutable. Effective privileges, authenticated profile duties and installed
definition readback remain storage responsibilities. Rendered MySQL metadata
changes can require owner diagnosis after a server upgrade.

### Spec

Normal configured owner/runtime/CLI paths pass on both engines. An early review
question about adding SQL privileges to profile groups was withdrawn after tracing
the authenticated membership checks; only the runtime principal receives control
capabilities. No extra group privileges were added. Missing initialized Journal
history now refuses recovery rather than becoming empty replacement history.

### GoF

Keep the existing facade, typed observations, native run preparation and small
storage adapter. A new registry, controller hierarchy or worker callback system
has no demonstrated benefit. The unsupported legacy caller-held guard remains
explicit rather than receiving a simulated commit boundary.
