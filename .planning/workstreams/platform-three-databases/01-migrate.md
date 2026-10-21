# Complete platform database portability before master configuration

Operator, 2026-10-20: "yes take ownership but work on that last after migrating everything to work with all three databases".

Scope: one common implementation across PostgreSQL, MySQL and SQL Server for
Rules, Change Journal, Bookkeeping, MDM, RDM, Silver and their installed callers,
workers and health checks. Preserve the existing migration worktrees and retained
data. Configuration of Company, Person, Security and their relationships follows
completion of database portability. Hosted targets remain Snowflake Postgres and
Databricks Postgres; AWS Postgres and new provider requests are outside scope.
Approval, activation and merge remain separate operator gates.

## Current priority (operator, 2026-10-21)

"complete mdm, rdm and silver no entity names or any hard coding everything
must be decoupled and config driven focus on postgress and mysql first park
mssql for last"

The immediate completion gate is the normal MDM, RDM and Silver callers on
PostgreSQL and MySQL. Entity names, identifiers, fields, profiles, source
priorities, relationships and matching/selection policy belong in configuration;
shared engine code implements generic operations. Database selection comes from
the connection configuration. SQL dialect syntax and database integrity checks
remain storage concerns, with one shared business implementation. Existing
approved behavior and ticket 120's detail/history/compaction changes must survive.

SQL Server qualification follows this two-engine gate. Remaining Rules and
Bookkeeping work is deferred unless a demonstrated dependency blocks one of
these three stores. Masters' onboarding and activation remain later gates.

- [x] Preserve unfinished Bookkeeping corruption-blocking work separately — named Git stash, including untracked migration and tests; 2026-10-21 18:17 ET.
- [ ] Audit entity-specific engine branches and cross-store dependencies; move policy into configuration without changing approved outcomes.
- [ ] Complete RDM's normal version, approval, publication, history and context paths on PostgreSQL and MySQL; qualify populated migrations, runtime rights, concurrent changes and pinned artifacts.
- [x] Implement the shared RDM version caller, native canonical/hierarchy/summary/order preparation and MySQL owner migration — 34 shared cases passed on PostgreSQL and MySQL, plus seven MySQL metadata/recovery cases (41 total on MySQL); 16 legacy PostgreSQL RDM cases, including a populated upgrade, also passed after the latest search extension (8.20 seconds); 2026-10-21 19:01 ET.
- [x] Remove RDM's imports of MDM's entity catalog; use the existing configured context definitions and neutral connection/type modules — normal CLI and read-only context cases passed on both engines, including non-default session timezone; 2026-10-21 18:57 ET.
- [x] Correct the reviewed migration-authority and interruption gaps — table/column metadata rights refused, exact-checksum empty-marker recovery, runtime writes revoked before trigger replacement, and populated failure/retry with an already-open runtime connection passed on MySQL; PostgreSQL/MySQL approval waits for an admitted draft edit; 2026-10-21 18:57 ET.
- [ ] Finish RDM search parity beyond the common-query checkpoint: short/stop words, negative-only queries, punctuation/compound tokens, multilingual synonym order and actual candidate index plans. Common search cases and eight native scoring cases passed per engine; this is not complete search parity.
- [x] Verify the RDM checkpoint outside the checkout through the installed five-wheel bundle — committed head e6c09467 installed all five wheels with no duplicate files and imported both neutral modules and the RDM modules; one affected installed test passed in 168.26 seconds; 2026-10-21 19:07 ET.
- [x] Silver: replace PostgreSQL-only delivery SQL with one typed sink and retain atomic modes, changed counts, source timestamps and derived updates — 21 shared cases on PostgreSQL and MySQL, plus eight MySQL recovery/permission cases (29 total); 143 affected legacy/unit/architecture cases and 11 Rust cases passed; 2026-10-21 19:20 ET.
- [ ] Silver: finish owner-only MySQL installation, interrupted registration recovery, all configured types/indexes and runtime-rights qualification.
- [x] Silver: qualify the current owner migration/registration checkpoint — empty-marker and interrupted CREATE recovery, denied temporary registry shadowing, table/column metadata grants, strict conversion, structural JSON numbers, raw high-precision JSON, signed-zero and binary keys, long exact keys and ID refresh; the 29-case MySQL suite passed; 2026-10-21 19:20 ET.
- [ ] Silver: qualify MySQL calendar-interval text, configured partition indexes, remaining type/transport edges and full native preparation; current duration proof covers exact Python timedelta values, with legacy PostgreSQL interval text separately preserved.
- [ ] Silver: qualify normal CLI, context, configured master links, concurrent writers and populated replay on both engines, including the installed bundle.
- [ ] Complete Silver's normal registration, append/upsert/snapshot, quality and master-link refresh paths on PostgreSQL and MySQL; qualify exact types, rollback, replay and populated upgrades.
- [ ] Complete MDM's normal configuration, indexed scope/matching, atomic merge, history, relationships, detail lists and publication paths on PostgreSQL and MySQL; qualify competing writers, stale work, recovery and unchanged replay.
- [ ] Qualify the installed configured callers on both engines with invented kinds and source names, demonstrating that new entity configuration needs no engine edits.
- [ ] SQL Server last: run the same normal callers and qualification after the PostgreSQL/MySQL completion gate.

## Full work checklist

- [x] Inspect live branches, existing migration tickets and current main; create a fresh isolated branch/worktree — git state and worktree inventory, origin/main 275a9d22; 2026-10-20 19:53 ET.
- [x] Preserve and inventory both migration drafts — 77 files fingerprinted privately, originals preserved; 50 MDM/skill paths held as pending imports so the Journal/Bookkeeping slice has no overlap — 2026-10-20 20:19 ET.
- [x] Replace Bookkeeping inspection SQL with selected-engine typed reads and move run-check/capture decisions into shared Rust — six real-engine read cases passed on each selected engine, seven Rust cases, 65 normal PostgreSQL control cases; 2026-10-20 20:19 ET.
- [x] Qualify the populated metadata-index upgrade and repeated migration — old frozen run preserved exactly through the normal typed caller; one affected integration case passed; 2026-10-20 20:19 ET.
- [x] Qualify native-prepared completion storage on all three engines — 15 completion cases per engine, including forged state/metadata, changed observations, concurrent retries, and rollback after a destination trigger fails; 2026-10-21 06:19 ET.
- [x] Resolve the bounded slice's Standards, Spec and GoF findings — exact resource/work lookups retain actual index seeks, capture selection/output and frozen run/work share consistent observations, both prepared-state directions are checked, migration 009 contains frozen SQL; reviewers found no remaining material correction issue and 31 combined cases passed per engine; 2026-10-21 06:19 ET.
- [x] Requalify the normal PostgreSQL caller and populated upgrade after the review corrections — 66 affected integration cases passed in 69.46 seconds; 2026-10-21 06:19 ET.
- [x] Inventory normal caller operations, existing drafts and remaining capability gaps across all six stores — source inspection recorded in OPERATIONS.md, with unsupported normal migration/caller paths distinguished from helper qualification; 2026-10-21 06:27 ET.
- [x] Record operation placement and GoF evidence; retain one Rust computation and database-authoritative writes — OPERATIONS.md and independent Standards/Spec/GoF reviews; existing facades retained, no new hierarchy; 2026-10-21 06:27 ET.
- [ ] Complete and qualify Rules on all three engines, including immutable versions, evidence, approval and activation authorization.
- [x] Integrate and qualify Change Journal on all three engines, preserving its independent package and existing evidence — nine selected-engine cases per engine (SQL Server's authorization case covers six elevation grants), 14 PostgreSQL normal/independent-package cases, and final installed proof on all three retained targets with one event before/after and identical retry receipt; Standards/Spec/GoF corrections resolved; 2026-10-21 06:30 ET.
- [ ] Complete and qualify Bookkeeping on all three engines, including leases, fences, transitions, recovery and destination guards.
- [x] Migrate run resumption through a native-prepared, destination-checked capability, preserving compaction refusal, stale-observation checks and unchanged retries — 14 resume cases passed per engine, exact checks/completion tokens reject changed checks and a later completion, including SQL Server 100-nanosecond precision; 66 normal PostgreSQL caller/upgrade cases passed, frozen migration 010 shipped by the independent wheel; 2026-10-21 07:03 ET.
- [x] Remove the selected-engine test-order dependency by giving Journal its own disposable database; preserve its refusal of business tables and qualify the whole affected adapter folder — 74 cases passed per engine; PostgreSQL historical upgrade also reproduced failing alone and then passed alone after fixture correction; 2026-10-21 07:03 ET.
- [ ] Complete and qualify the normal MDM caller on all three engines, including identity, history, indexed reads, publication and unchanged replay.
- [ ] Complete and qualify RDM on all three engines, including immutable code versions and current activation.
- [ ] Complete and qualify Silver on all three engines, including registration, idempotent deliveries and reference refresh.
- [ ] Qualify installation, configured workers, migration commands, health checks and retained-data upgrades on the selected engines.
- [x] Qualify the committed five-wheel bundle installation at its Git revision — five selected package/import/independence cases passed in 177.72 seconds, all sources pinned to the same ref with no duplicate shipped files; separate installation skill PR #1120; 2026-10-21 06:47 ET.
- [x] Inspect checkpoint CI for draft PR #1121 and skill PR #1120 — #1120 all checks green; #1121 reached terminal failure with one engine regression and 1,083 engine cases passed, all other job groups green; initial monitoring stopped on the terminal result before its deadline; 2026-10-21 07:03 ET.
- [x] Fix the reproduced CI combination regression for escaped lone-surrogate metadata; retain native equality, exact Python code-point behavior and strict durable UTF-8 publication — exact failing case reproduced locally; 13 combination/Unicode checks and 65 affected contract/image/Unicode checks passed after the fix; independent Standards/Spec/GoF review found no remaining issue; 2026-10-21 07:03 ET.
- [ ] Inspect the next revision's complete CI for #1121; monitor for at most 20 minutes from push, stop on any terminal result or PR closure, and record pending checks at the deadline.
- [ ] Audit opaque JSON value fidelity and exact-key index plans in the remaining stores; preserve large integers, Unicode, nulls and original key distinctions.
- [ ] Review Standards, Spec and GoF; record active and historical database code separately.
- [ ] Build and freeze complete Company, Person, Security and relationship configuration using existing approved captured-input findings.
- [ ] Run each onboarding part's required test and one proving run after configuration freeze; verify uniqueness, held-back records, links, holdings and unchanged replay.
- [ ] Qualify documented Snowflake Postgres and Databricks Postgres procedures, or record exact unsupported capabilities.
- [ ] Obtain any required approvals and activation instructions for the qualified configuration.
- [ ] Learning → skill: record reusable guidance in its owning skill on a separate branch/PR, or none.

## Existing work

Journal and Bookkeeping drafts remain in `control-journal-portability-20261020`;
shared MDM Rust extraction and adapter drafts remain in
`mysql-mastering-merging-20261019`. Journal's ticket reports selected-engine
installed-caller qualification; Bookkeeping and full MDM caller qualification
are incomplete. Their reported results are evidence to inspect, not proof
that this consolidated branch contains or has qualified the implementation.


## Bounded operation: control reads and run observations

Standards: fresh dedicated branch; original worktrees and test contents preserved.
The guard passes after keeping the unrelated MDM and shared-skill imports in
private pending copies. Tests use separate testmon files and bounded invocations;
fixture-created databases and principals are cleaned up. No provider request,
source onboarding test, source execution, approval or activation occurred.

Spec: the normal Bookkeeping inspection caller uses SQLAlchemy statements on
all engines. Rust owns run-check decisions, newest-capture grouping and verified
output deduplication. A later rerun of an older capture never makes it newest;
unfinished or compacted newest runs are refused. This proves read operations and
shared decisions only. Non-PostgreSQL migration, profile grants, work transitions
and destination guards remain missing and their existing refusals remain.

GoF: recent changes to frozen reads and latest-capture behavior (275a9d22,
68baf111 and 0bb78d53) justify collecting storage syntax behind the existing
Bookkeeping facade. Reuse SQLAlchemy and the shared control Rust library; no
new class hierarchy. The concrete adapter liability is value fidelity and the
write-interface gap. Real-engine checks exposed MySQL numeric rounding,
SQL Server scalar JSON projection and default collation comparisons; tests
now cover exact large integers, null/empty distinctions, Unicode, long scalar
values, case, accents and trailing spaces.

Seven-waste review: transport stays scoped to one run or configured document;
only selected verified-unit identities are read after capture selection. Native
deduplication transfers duplicate identities before folding them; no speed claim
is made. The new document index prevents metadata table scans. One native
implementation replaces the old Python checks and SQL capture-selection logic;
SQL retains indexed retrieval and lookup addressing. Existing write authority
is preserved. Private pending drafts avoid competing edits; disposable proofs
leave no control rows in retained targets.

The first setup/read integration step took about 18 minutes. The longest
normal-caller test invocation was 53.80 seconds. Cross-engine read/Journal
cohorts completed in 3.75 seconds (MySQL) and 9.53 seconds (SQL Server);
PostgreSQL's final six read cases completed in 2.27 seconds. Journal's eight
selected cases also passed on PostgreSQL. Independent installed Journal
qualification subsequently passed on each retained selected test instance:
one invented event before and after, the same receipt on retry, and no domain
package installed. No source execution was performed.

## Completion storage and consistent observations

The destination locks the run and rechecks actual work, verified work, pending
delivery and unsealed expansion counts before saving Rust-prepared state,
checks and summary. A forged completion or waiting state, duplicate/type-invalid
metadata, changed counters, compacted run or ungranted principal is refused.
Identical retries preserve the original completion time; a late destination
failure rolls back the update and the same intent can succeed after repair.
SQL Server counters use COUNT_BIG. Normal claims and other writes still use the
existing PostgreSQL capabilities; MySQL/SQL Server initialization is still
explicitly refused until the full workflow and grants are qualified.

Standards: migration 009 is frozen SQL rather than generated again from mutable
runtime/native code. Its populated-upgrade test changes the generator after
installation and verifies migration replay is unchanged. Exact binary residual
comparisons preserve original keys while indexed equality retains seeks.
Real query plans cover capture metadata, resource checkpoints and work identity.

Spec: capture metadata, Rust selection and chunked output reads use one
consistent observation set. Frozen run/work reads do likewise. PostgreSQL and
MySQL use repeatable-read snapshots; SQL Server uses a serializable read set.
A concurrent compaction test returns the original coherent output and the next
call refuses the compacted run. Readers never return partial compacted output.

GoF: independent review recommends retaining the facade and typed boundary;
the corrections require no additional class hierarchy. Both review axes found
their original findings resolved on reinspection.

Latest selected-engine cohort: 31 passed on each engine (eight read cases,
15 completion cases, eight Journal cases), in 2.40, 5.01 and 6.04 seconds for
PostgreSQL, MySQL and SQL Server respectively. The 66-case normal PostgreSQL
caller/upgrade cohort passed in 69.46 seconds. Installed Bookkeeping and
independent Journal checks passed six cases before the final frozen-SQL change;
the final installed cohort also passed six cases in 71.93 seconds. All artifacts contain invented
fixtures or counts and outcomes only.

Live origin/main advanced to 52f7919b with Security skill/evidence changes;
those four changed paths do not overlap this control slice. Master configuration
remains last, and the new Security evidence will be reread before that work.

## Independent Journal closeout

Frozen native SQL payloads now live under `change_journal/migrations/native/`.
Their exact statement bytes preserve the already-applied native checksums;
later code changes cannot regenerate historical payloads. The independent wheel
ships all three payloads, verified by the installed-package manifest test.
Shared native read preparation normalizes accepted UUID filter spellings before
storage lookup; uppercase and undashed identifiers find the same saved event.

SQL Server owner migration inspects the runtime login's effective server,
database, principal, role, schema and object permissions before writing. Tests
grant direct CONTROL SERVER, impersonation of dbo, db_ddladmin membership,
schema ALTER, procedure ALTER and readback-view ALTER one at a time; each is
refused, its grant is repaired, and the original durable receipt still verifies.
The inspection requires permission to impersonate the selected runtime login;
it does not silently substitute a weaker database-only check.

The final independent build qualified all retained selected test targets with
exactly one invented event before and after, no domain/source packages, and
the same receipt on retry. The original retained proof event and credentials
were reused. No source records, provider requests or source executions were
added. The review/qualification continuation took approximately 18 minutes;
every individual local test invocation remained below five minutes.

## Run resumption and CI correction

Resumption now uses a shared native preparation and one destination enforcement
sequence for every selected engine. It clears checks/completion only after a
locked comparison of state and exact stored values. Opaque timestamp tokens
retain the destination's full precision, including SQL Server's 100-nanosecond
values that Python datetime cannot represent. The desired state already present
is a harmless unchanged retry; a changed check or newer completion is stale.
Work items, receipts, summaries, leases and checkpoints are preserved.
Migration 010 is frozen SQL; the old PostgreSQL resume function is retired.

The whole affected adapter folder exposed Journal's shared-database test-order
dependency. The test factory now provisions a separate disposable Journal store
and principal with the same cleanup; production refusal of non-Journal tables
remains intact. All 74 cases passed on PostgreSQL and MySQL in 27.67/38.55 seconds
and on SQL Server in a final isolated-log run in 92.26 seconds. Its historical
PostgreSQL upgrade case also passes alone. The six-case independent control
wheel/architecture cohort passed after the resume change in 95.13 seconds.

Checkpoint CI found one source combination regression (1,083 other engine cases
passed): an escaped lone-surrogate metadata value reached the new UTF-8-only
native boundary before an unused column was dropped. The exact case reproduced
locally. A native opaque-value encoder now retains Python string code points for
equality, while normal UTF-8 canonicalization remains unchanged and hashing or
publication of invalid UTF-8 remains refused. Thirteen combination/Unicode cases,
65 affected contract/image/Unicode cases and nine native cases pass. Source
combination history (3a75cfd1, 610a35e8) already uses the same surrogatepass
transport for opaque metadata. Independent reviews found the correction sound;
the existing serialization boundary is retained without a new hierarchy.

This resumption/review/CI correction pass took approximately 30 minutes. The
longest local invocation remained the five-wheel installation at 177.72 seconds.
The PRs remain draft; skill PR #1120 has green CI. The next #1121 revision must
pass full CI before readiness is claimed. No merge or activation is authorized.
