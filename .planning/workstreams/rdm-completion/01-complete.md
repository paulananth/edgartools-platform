# Complete RDM on PostgreSQL and MySQL

Operator via Lavish, 2026-10-23: “close this gap first do not over engineer” on the RDM section.

- [x] Inspect current main, branch ownership and search design/history; create fresh isolated branch — origin/main 8ca8bb85, no open PRs, clean own worktree, initial overlap guard passed; 2026-10-23 07:15 ET.
- [x] Reproduce short/stop-word, negative-only and punctuation/compound search gaps through the normal caller on both engines — 11 PostgreSQL edge cases passed; MySQL failed short-word retrieval classification before the fix; 2026-10-23 07:31 ET.
- [x] Fix demonstrated gaps using existing storage/native boundaries; preserve approved PostgreSQL behavior — 104 MySQL storage/recovery/computation cases passed in 72.67 seconds and 105 PostgreSQL caller/context/computation cases passed in 29.45 seconds, plus two Rust reference cases; 2026-10-23 07:40 ET.
- [ ] Qualify lifecycle, approval/publication, history/context, populated migration, rights, concurrency, artifact pinning and installed normal callers on PostgreSQL/MySQL.
- [ ] Review Standards, Spec and GoF; publish the bounded completion with CI evidence.
- [ ] Reconcile the canonical plan and Lavish status with verified outcomes.
- [ ] Learning → skill: name the changed skill line, or none.

## Design consult

Existing search boundary: `rdm/storage.py` retrieves candidates through per-engine indexes; `control-contract/src/reference.rs` ranks/deduplicates/orders results; `CodeContext` remains the normal facade. History shows the context addition and #1121 portable implementation. Keep this boundary; no new hierarchy or general search framework. Verify candidate completeness before changing ranking or broadening reads. SQL Server stays deferred.

## Implementation and qualification evidence

MySQL stores native SHA-256 word tokens in a derived full-text column, avoiding the default index's short/stop-word omissions. Native membership checks preserve phrases/exclusions and reject candidate hash collisions. Negative-only alternatives read the requested indexed version scope. Existing PostgreSQL candidate semantics remain unchanged; common native density handling now retains compound components and dotted/email/path boundaries.

A new frozen `mysql-search-v2.sql` adds derived columns/indexes. The owner backfills in pages with runtime writes revoked, including already-connected sessions. Incomplete markers block normal callers; interrupted populated backfill resumes with the same checksum. Existing published content, approval/publish times, canonical file bytes and pin remain unchanged. Approval locks the draft version and refreshes derived tokens from authoritative labels before freezing it, including direct draft edits.

Existing lifecycle, concurrent publication/content-edit, runtime rights, indexed word/code/child reads, multilingual order, exact JSON/key, rollback, history and artifact tests are retained. A legacy describe test depended on another test's publication; its own published fixture now makes it order independent. Earlier retained PostgreSQL and MySQL endpoints refused connections; final verification used the existing disposable fixtures and cleaned up their servers.

## Standards

Fresh isolated branch; source-neutral changes; additive frozen migration; no historical SQL changed. Affected testmon invocations are bounded below five minutes and use separate caches. No provider request or operational source record is involved. Real isolated stores and restricted runtime roles are retained.

## Spec

RDM first, PostgreSQL/MySQL only. Reuse current facade, native computation and typed storage; no new search framework, entity constants, activation or hosted cutover. SQL Server remains deferred. Installed normal-caller proof is the next gate; passing helper checks alone does not close the parent.

## GoF

Existing Facade/Adapter boundaries already localize the change. A derived index and three native operations extend the current interface; no class hierarchy or alternate lifecycle is warranted. Cost: MySQL needs the additive owner migration, token backfill and matching native wheel. Immutable content and pins remain authoritative; source/field policy is not embedded in storage.
