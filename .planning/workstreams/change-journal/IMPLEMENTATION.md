# Fresh Change Journal implementation

Branch: `codex/fresh-change-journal`, based on refreshed `origin/main` at
`94b5633d`. Shared checkout and other worktrees are protected.

- [ ] Inventory legacy tables, active callers, privileges and invariants; assign replacements and qualifying tests.
- [x] Implement empty PostgreSQL 16 journal, checksummed migration, separate owner and restricted append/read functions. (2026-09-27 13:50 ET)
- [x] Implement versioned append/get/bounded list/verify interface and operator CLI. (2026-09-27 13:50 ET)
- [x] Replace fresh Bookkeeping and Clean MDM mirror delivery; retain owner-local outboxes and MDM commit evidence. (2026-09-27 13:50 ET)
- [x] Extend generic checkpoints with resource scopes, lease checks and compare-and-swap across runs; preserve ordered progress. (2026-09-27 13:50 ET)
- [x] Record Rules acquisition integration contract for Claude. (2026-09-27 13:50 ET)
- [x] Implement acquisition authority in Rules and Rules-backed dataset registration without losing historical registration evidence. (2026-09-27 13:50 ET)
- [ ] Replace every acquisition family caller and legacy processing, producer, revision, conflict and import use.
- [x] Require committed authorization and verified journal acknowledgement before provider requests; reconcile committed effects. (2026-09-27 13:50 ET)
- [x] Add source/feed Change Journal skill, shared installation and real mode validation. (2026-09-27 13:50 ET)
- [x] Qualify isolated PostgreSQL 16 failure/recovery/concurrency acceptance without skips. (2026-09-27 14:04 ET; fresh core, not every legacy caller)
- [ ] Exercise bounded acquisition families and unseen configured feed, preserving conditional fetch and completeness.
- [x] Remove legacy tables from fresh provisioning; retain legacy archives and runs until feed cutover qualifies. (2026-09-27 13:50 ET)
- [x] Update current Change Propagation terminology and retain historical artifact names. (2026-09-27 13:50 ET)
- [ ] Qualify AWS rollout, drain legacy deliveries on legacy stack, verify each feed before promotion.

Unchecked work is incomplete, including deployment; no generic control fixture
alone qualifies a production acquisition feed.

## Design review

Reviewed current code and history with `gof-refactor-reviewer`: the configured
Bookkeeping and stage worklist commits (#732/#734) added a second mirror beside
Clean MDM's mirror. `bookkeeping/clean/destinations.py:53` and
`mdm/clean/publication.py:91` duplicate sink delivery contracts. A thin Adapter
to one journal avoids maintaining two sinks; its liability is one conversion
boundary per existing envelope. Keep capability functions and local outboxes;
no Strategy hierarchy or new orchestrator is justified.

## Verified scope and remaining work

The fresh implementation is locally qualified; the entire replacement/cutover
plan is **incomplete**. The table/caller inventory is published in
[LEGACY-INVENTORY.md](LEGACY-INVENTORY.md), including pending original-stack
entrypoints. All three fresh stores can be provisioned without legacy tables.
Historical roots are rejected without altering their state or pending intent.

Draft Rules source/feed policies cover SEC filings, submissions, company facts,
reference catalogs, ADV filing/bulk/roster and GLEIF member feeds. Bounded
provider bytes and an unseen fixture feed exercise shared capture; this is not
complete parser/Silver/native publication or production feed qualification.
Skill planning supports shared artifact/capture/source-evidence and configured
MDM operations without opening their databases; unsupported operations block. No live Rules
version was approved, no AWS rollout was run, and no database was retired.

The remaining local work is full replacement/qualification of legacy discovery,
revision/processing/Silver producer/finalizer and native publication callers,
plus complete family fixtures and live privilege inventory. The remaining live
work requires exact approved Rules/baseline scopes, isolated hosted owner and
runtime connections, reviewed runtime secret ARN access, original-stack drain,
feed-by-feed promotion and recovery verification. Preserve archives indefinitely.

## Verification record

- Isolated PostgreSQL 16 acceptance: 83 passed in the first combined run;
  added real-policy, canonical Unicode/timezone, archive-preservation, CLI
  recovery and direct Rules proof tests subsequently passed. Final counts are
  Final combined acceptance: 98 passed in 206.09 seconds, with no
  prerequisite skips (42 Bookkeeping; 56 journal/acquisition/MDM/
  source-evidence/skill, including four malformed SQL-boundary cases). Latest authority/proof/outcome
  checks: 42 passed; MDM planning and skill modes: two passed; CLI recovery: one
  passed.
- Broad unit/architecture/MDM/acquisition regression: 3,467 passed, 27 subtests
  passed, nine existing prerequisite/optional skips; six existing SQLAlchemy
  transaction warnings and 119 existing datetime deprecation warnings.
- Actual HTTP transport/architecture checks: 16 passed; latest transport,
  fresh-runtime connection guard and AWS container wiring checks: 11 passed.
  After the legacy-connection guard, acquisition/architecture/CLI regressions
  passed 877 tests.
- Shared skill validates and installs via two verified symlinks; all mode
  operations use real interfaces and isolated PostgreSQL qualification.
- Wheel build succeeds and includes the journal, resource checkpoint,
  authorization and Rules migration SQL. Bash syntax and `git diff --check`
  pass. No tests make a live provider request or perform an AWS deployment.

Independent GoF review is available and was applied: one narrow publication
Adapter is justified by the two pre-existing mirrors. Fenced transactions,
mandatory reconciliation and source-independent capability selection remain
functions, without a new inheritance tree.

- Final review fix (2026-09-27 14:10 ET): producer timestamps normalize to UTC
  before hashing. Real Bookkeeping and MDM sessions in America/New_York pass
  duplicate/lost-ack tests; two PostgreSQL tests passed. Fresh CLI dispatch and
  SEC transport refuse old ungated work when the journal runtime is configured.
  This means fresh connection wiring must not replace legacy scheduled task
  revisions before their configured replacement qualifies.

- Fresh CLI/transport safeguards and existing SEC/architecture/CLI coverage: 36
  passed (2026-09-27 14:10 ET). Refreshed main advanced only two Rules research
  documents; rebase changed no tested source, configuration or test files.

- Follow-up review: deployment reads committed validation runs and exact journal
  receipts before executing; missing/unfinished roots, invented checks, changed
  receipts and incomplete validation connection pairs fail before provider
  requests. The real PostgreSQL skill-mode test passes. Provider URL coverage
  rejects encoded traversal, nested escapes, backslashes and control characters;
  unit/Rules skill compatibility checks pass 19 tests. Boolean capture envelope
  versions are refused. Main's Rules skill PR #737 is preserved, including its
  SEC policy comments; no mapping or bookkeeping digest was changed by that sync.

- AWS review correction: fresh connections are restricted to separate
  `journal-large` / `mdm-journal-large` task families with a read-only status
  default. Original task families ignore fresh connection flags and retain
  the original Bookkeeping DSN and commands, so configured connection wiring
  cannot break historical workflows. No workload sizing reference changes.

- Final combined PostgreSQL 16 acceptance after validation read-back and URL
  coverage fixes: **99 passed in 176.20 seconds, no skips**. Fresh/legacy AWS
  task isolation, transport and current Rules skill compatibility: **27 passed**.
  Final wheel contains byte-identical copies of all four new migrations;
  the installed shared skill validates, Bash syntax and diff checks pass.

- Physical empty local stores (2026-09-27 14:45 ET): PostgreSQL 16.15 container
  `edgartools-change-journal-local-235e8eec`, endpoint `127.0.0.1:33613`.
  [LOCAL-EMPTY-STORES.json](LOCAL-EMPTY-STORES.json) records all checksums, zero
  rows in every fresh control table, zero legacy tables, and runtime roles with
  no table mutation/schema creation/migration-owner membership. Journal init is
  idempotent; restricted status reports zero events and bounded inspection is
  empty. No Rules version or history was installed. Private connections are in
  the recorded mode-0600 file outside the repository. This is local evidence,
  not hosted qualification or cutover.

- User scope (2026-09-27): local qualification only. AWS rollout and feed
  promotion remain outside this execution; no live changes are authorized by
  local acceptance results.
- Source completeness review: `source-manifest-v2` verifies typed scope
  inventories, actual artifact/row counts, ordered business key hashes and
  duplicate identities. Opaque proof, wrong feed, forged counts/digests and
  invalid business keys fail closed. The source-evidence PostgreSQL suite
  passed **30 tests**; updated SEC/GLEIF artifact fixture authority passed
  **four tests**. Destination effect verification remains owner-specific and
  is not inferred from record inventories.
- Revision lineage additionally requires an actual committed predecessor
  receipt, acknowledged journal intent, exact resource/checkpoint comparison
  and no unsettled declared same-scope work. Real PostgreSQL tests reject
  invented predecessors, missing acknowledgements and incomplete barriers.
- Latest unit/architecture/Bookkeeping regression: **2,163 passed, 27 subtests
  passed, eight existing optional skips**, with six existing SQLAlchemy
  transaction warnings. New journal modules pass Ruff; skill validation,
  Bash syntax and wheel build pass.
