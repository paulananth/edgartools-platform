# Complete RDM on PostgreSQL and MySQL

Operator via Lavish, 2026-10-23: “close this gap first do not over engineer” on the RDM section.

- [x] Inspect current main, branch ownership and search design/history; create fresh isolated branch — origin/main 8ca8bb85, no open PRs, clean own worktree, initial overlap guard passed; 2026-10-23 07:15 ET.
- [x] Reproduce short/stop-word, negative-only and punctuation/compound search gaps through the normal caller on both engines — 11 PostgreSQL edge cases passed; MySQL failed short-word retrieval classification before the fix; 2026-10-23 07:31 ET.
- [x] Fix demonstrated gaps using existing storage/native boundaries; preserve approved PostgreSQL behavior — 104 MySQL storage/recovery/computation cases passed in 72.67 seconds and 105 PostgreSQL caller/context/computation cases passed in 29.45 seconds, plus two Rust reference cases; 2026-10-23 07:40 ET.
- [x] Qualify lifecycle, approval/publication, history/context, populated migration, rights, concurrency, artifact pinning and installed normal callers on PostgreSQL/MySQL — 104 MySQL / 105 PostgreSQL affected cases; the committed 12a8d744 five-wheel CLI proof passed outside the checkout on PostgreSQL in 223.59 seconds and MySQL in 28.30 seconds; indexed negative-only scopes additionally passed on both engines; 2026-10-23 07:46 ET.
- [x] Review Standards, Spec and GoF; publish the bounded completion with CI evidence — PR #1147, all nine checks passed on implementation head 12a8d744; reviews below, diff/overlap checks passed; final record/index-assertion head is checked separately before readiness; 2026-10-23 07:51 ET.
- [x] Reconcile the canonical plan and Lavish status with verified outcomes — parent two-engine RDM items checked with evidence, operations checkpoint and Lavish RDM card updated; SQL Server/MDM/Silver and activation remain separate gates; 2026-10-23 07:51 ET.
- [x] Learning → skill: mdm-engineering, Search candidate completeness — separate PR #1146, 79 skill/genericity cases and all nine CI checks passed on final 9a178b0b; 2026-10-23 07:46 ET.

## Design consult

Existing search boundary: `rdm/storage.py` retrieves candidates through per-engine indexes; `control-contract/src/reference.rs` ranks/deduplicates/orders results; `CodeContext` remains the normal facade. History shows the context addition and #1121 portable implementation. Keep this boundary; no new hierarchy or general search framework. Verify candidate completeness before changing ranking or broadening reads. SQL Server stays deferred.

## Implementation and qualification evidence

MySQL stores native SHA-256 word tokens in a derived full-text column, avoiding the default index's short/stop-word omissions. Native membership checks preserve phrases/exclusions and reject candidate hash collisions. Negative-only alternatives read the requested indexed version scope. Existing PostgreSQL candidate semantics remain unchanged; common native density handling now retains compound components and dotted/email/path boundaries.

A new frozen `mysql-search-v2.sql` adds derived columns/indexes. The owner backfills in pages with runtime writes revoked, including already-connected sessions. Incomplete markers block normal callers; interrupted populated backfill resumes with the same checksum. Existing published content, approval/publish times, canonical file bytes and pin remain unchanged. Approval locks the draft version and refreshes derived tokens from authoritative labels before freezing it, including direct draft edits.

Existing lifecycle, concurrent publication/content-edit, runtime rights, indexed word/code/child reads, multilingual order, exact JSON/key, rollback, history and artifact tests are retained. A legacy describe test depended on another test's publication; its own published fixture now makes it order independent. Earlier retained PostgreSQL and MySQL endpoints refused connections; final verification used the existing disposable fixtures and cleaned up their servers.

## Standards

Fresh isolated branch; source-neutral changes; additive frozen migration; no historical SQL changed. Affected testmon invocations are bounded below five minutes and use separate caches. No provider request or operational source record is involved. Real isolated stores and restricted runtime roles are retained.

## Spec

RDM first, PostgreSQL/MySQL only. Reuse current facade, native computation and typed storage; no new search framework, entity constants, activation or hosted cutover. SQL Server remains deferred. The independently installed normal CLI passed its complete lifecycle on each engine at 12a8d744; All nine PR #1147 checks passed on implementation head 12a8d744; the final record/index-assertion head must pass CI before readiness. No helper-only support claim is made.

## GoF

Existing Facade/Adapter boundaries already localize the change. A derived index and three native operations extend the current interface; no class hierarchy or alternate lifecycle is warranted. Cost: MySQL needs the additive owner migration, token backfill and matching native wheel. Immutable content and pins remain authoritative; source/field policy is not embedded in storage.

## Installed normal caller

The committed five-wheel bundle ran outside the checkout with isolated stores and restricted runtime roles. On each engine the real CLI initialized, drafted, recorded synthetic operator test approval, published, searched short/stop/compound/excluded terms and synonyms, superseded, read history at the first publication time, replayed migration, verified both pins and retired the replacement. No operational approval or activation occurred. The installed proof commits contain the implementation; the later additions are index-plan assertions and records only.

The final plan assertions also prove negative-only search reads the requested small version through version indexes beside a 5,001-code unrelated version. Ordinary and short-word searches retain their word indexes. The two affected index-plan cases passed independently after the installed implementation was frozen.

## CI and elapsed time

All nine checks passed on implementation head 12a8d744, including both selected-engine adapter callers, the retained SQL Server adapter checks, installed bundle/engine, PostgreSQL integration, MDM, unit and shell gates. Final-head CI is read back on the PR before marking it ready; this record is not a claim about an unrun final head.

Implementation and local qualification took approximately 30 minutes before CI closeout. Every local invocation remained below five minutes; the installed PostgreSQL proof was longest at 223.59 seconds. The source-head CI gate took about ten minutes. Own disposable servers were stopped; retained servers were preserved.
