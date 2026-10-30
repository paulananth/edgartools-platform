# Complete Rules, Bookkeeping and Change Journal portability

Status: Rules and its guidance merged; Bookkeeping/Journal normal PostgreSQL/MySQL implementation and local qualification complete on its follow-up branch; final CI/release and deferred SQL Server remain open.
Base: current origin/main after Silver closeout; branch `codex/control-store-portability-20261029`.
Parent: [Platform portability](../platform-three-databases/01-migrate.md).

## Parts

- [x] Reconcile actual normal callers, existing selected-engine helpers, retained drafts and qualification evidence; preserve unrelated work — 2026-10-29 23:25 ET: live source/history and worktree inventory; Journal already has selected-engine storage, Rules and Bookkeeping still have normal-call gaps. Archived work and unrelated main changes preserved.
- [x] Complete Rules owner migration and restricted agent/approval duties on PostgreSQL/MySQL with immutable historical migrations and populated recovery — 2026-10-29 23:43 ET: selected-engine tests and installed init/migrate passed on both engines; drift and interrupted-DDL cases refuse unsafe access.
- [x] Complete Rules normal save/version/proof/approval/activation/export on both engines; preserve immutable content, exact evidence and authorization against direct bypass and concurrency — 2026-10-29 23:43 ET: normal/negative/concurrent tests, actual governed MDM handoff and installed CLI lifecycle passed.
- [ ] Complete Bookkeeping normal initialization and worker/verifier grants on both engines.
- [ ] Complete Bookkeeping normal start/claim/heartbeat/report/verify/completion/checkpoint/generated-work/resume/finalize and destination authority/recovery on both engines; keep durable state enforcement authoritative at its destination.
- [x] Verify and retain existing Change Journal selected-engine support and independent package; implement only demonstrated gaps in normal append/replay/read/receipt/delivery/migration/rights behavior — 2026-10-29 23:43 ET: nine retained normal cases passed on each selected engine; existing independent-package and SQL Server evidence unchanged; no Journal gap found.
- [ ] Qualify normal configured callers and installed workers/verifiers, migration/health commands, rollback/recovery, unchanged replay and populated upgrades; reuse applicable existing proofs.
- [ ] Review Standards, Spec and GoF; publish bounded implementation PRs and qualify final heads before merge.
- [ ] ~~Full SQL Server qualification~~ deferred until the PostgreSQL/MySQL gate; retain existing SQL Server adapter checks and Journal qualification.
- [x] Resolve Rules CLI overlap before editing that file — 2026-10-29 22:26 ET: operator explicitly assigned edgar_warehouse/rules/cli.py to Codex in this session; archived Claude work is preserved. The real guard continues to report that known overlap; no other overlap is authorized.
- [x] Learning → skill: publish demonstrated reusable learning separately or record none — 2026-10-30 00:12 ET: PR #1236 updates mdm-engineering/references/storage-adapters.md with normal Rules handoff, approval-evidence and guard/index readback qualification; 87 genericity cases and independent review passed. Its CI remains a separate gate.

## Settled scope and seams

The operator explicitly invoked implement for these three stores. Existing
platform scope requires one configuration-driven implementation, PostgreSQL/MySQL
first, SQL Server last. Test the already-agreed normal public CLI/store and
worker/verifier boundaries, not adapter helpers as a substitute. Use focused
red/green cases there and keep local invocations below five minutes; CI runs the
full suite. Current Change Journal qualification already covers three engines;
verify its current ordinary caller and preserve the proof instead of rewriting it.

Shared Rust/Python owns deterministic preparation; each database retains durable
storage, indexed reads, uniqueness, permissions, leases/fencing, current-state
validation and atomic transitions. Keep existing package/facade seams, configuration
pins and caller signatures. Database dialect details are storage concerns.
No source onboarding/activation, provider requests, hosted cutover or production
schema changes are authorized by this implementation task. Disruptive tests use
isolated test databases/roles, never the shared operational stores.

## Rules checkpoint (2026-10-29 23:25 ET)

The first bounded PR implements Rules only. Bookkeeping and the final cross-store
gate stay open below; this checkpoint does not claim the parent effort complete.

- [x] Normal lifecycle, CLI status, populated migration and actual selected-engine MDM reading reuse — PostgreSQL/MySQL normal-caller tests passed, 2026-10-29 23:25 ET.
- [x] Direct acquisition-proof bypass, immutable history/proof, stale approval evidence and concurrent activation — retained PostgreSQL approval tests plus new selected-engine negative tests passed, 2026-10-29 23:25 ET.
- [x] MySQL empty/populated interrupted migration recovery, cached runtime revocation, unknown migration version and invalid completion flag — ten MySQL cases passed; five PostgreSQL normal cases passed and five MySQL-only cases skipped explicitly, 2026-10-29 23:25 ET.
- [x] Retain current Journal qualification — nine normal Journal cases passed on each engine in combined runs (MySQL 18 passed; PostgreSQL 38 passed, five MySQL-only skips), 2026-10-29 23:25 ET. No Journal implementation change needed at this checkpoint.
- [x] Qualify committed Rules CLI from the independently installed five-wheel bundle on both engines — 2026-10-30 00:12 ET: final source head 2cd63adb passed installed init/save/record-proof/pending/approve/activate/status/export/populated migrate with bare backend URLs on both engines (113.70/115.96 seconds). Earlier source head b4829224 and the first MySQL installation also passed.
- [x] Review Standards, Spec and GoF — 2026-10-29 23:43 ET: two independent Luna low reviewers; missing-guard/index drift finding reproduced and corrected, then re-reviewed with no remaining blocking finding. Existing facade/storage seam retained.
- [x] Publish the bounded Rules PR — 2026-10-30 00:12 ET: PR #1235 publishes the implementation and local evidence; retained as draft until its final head passes CI.
- [x] Qualify final CI before readiness and merge — 2026-10-30 06:51 ET: all 20 checks passed at Rules head 756ccfef; PR #1235 merged as 6423a4169. Guidance PR #1236 passed all 20 checks at 6d282783 and merged as b05d27513.
- [x] Learning → skill: document only demonstrated reusable installation/qualification changes, on a separate skill branch/PR — 2026-10-30 00:12 ET: PR #1236, separate branch, 87 genericity checks and independent review passed.

## Final local evidence and review

At the earlier source head b4829224, the complete named PostgreSQL Rules/CLI regression cohort
passed 31 cases with seven explicitly MySQL-only cases skipped. MySQL passed 12
normal/storage cases with the PostgreSQL-only principal case skipped. Both
independently installed CLI cohorts passed. Every local invocation stayed below
five minutes. Compile/import and whitespace checks pass; no repository Python
typechecker is configured for this area. CI runs the full repository cohorts.

Bookkeeping's normal CLI test exposed a shared connection-construction gap:
bare MySQL URLs selected an unshipped default driver. The same Rules path failed
before correction. Its existing factory now preserves explicit drivers and maps
bare PostgreSQL/MySQL URLs to the shipped drivers; migration and MDM handoff
connections use that factory too. The actual default-driver owner/init/runtime
case passed on both engines, and two independent reviewers found no issue.
The final committed independent installs at 2cd63adb cover that correction.

### Standards

Independent review found no documented violation. Both configured PostgreSQL
principals must be restricted and separate from the owner. Agent recording of an
operator's approval preserves the existing operator ruling and exact words; the
optional separate approval principal retains its narrower column grants.

### Spec

The normal caller uses typed selected-engine storage and the existing governed
MDM reading API. Guard/index drift now revokes MySQL callers and refuses migration;
cached callers are also denied during incomplete guard rebuilding. Approved proof
mutation is refused by both databases. Bookkeeping is a separate unfinished slice,
not included in the bounded Rules implementation claim.

### GoF

Leave the existing Rules facade and small storage adapter seam in place. History
does not justify a new registry, class hierarchy or generic mutation protocol.
The MySQL fingerprint intentionally refuses changed rendered metadata; a server
upgrade that changes those definitions needs owner diagnosis and qualification.
No hosted installation or cutover is qualified here.

## Initial GoF consult

Current Rules combines its normal facade with PostgreSQL text SQL. Bookkeeping
already has typed inspection/run-check/resume storage helpers, but its normal
owner install, grants and lifecycle still call PostgreSQL routines. Journal
already selects its normal storage adapter. Reuse those interfaces and native
control preparation rather than a parallel control engine, policy registry or
store hierarchy. Inspect each actual transition and race before changing it.
