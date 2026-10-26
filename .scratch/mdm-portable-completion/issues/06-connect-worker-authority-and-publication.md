# Connect worker authority and publication recovery

Type: task
Status: claimed
Assignee: Codex
Claimed: 2026-10-25 15:21 ET
Parent: [Complete portable MDM and retire PostgreSQL business logic](../map.md)
Blocked by: none; 04, 05 and their skill prerequisites are merged

## Question

Can the normal worker preserve authority through commit and recover publication safely on both engines?

## Parts

- [x] Integrate the demonstrated destination-local fence/expiry capability with the normal worker; do not expand into unrelated Bookkeeping conversion. — 2026-10-25 21:22 ET; normal worker authority passes for two configured kinds on PostgreSQL/MySQL; independent installed checkpoint 7708cb5b also passes.
- [x] Refuse expired, superseded and same-token/different-attempt proofs through commit, including duplicate and caller-held transaction cases; test malformed direct database requests as well as Python validation. — 2026-10-25 21:22 ET; normal authority and direct protocol-6 fault cases pass on both engines, with unchanged retained rows after refusal.
- [x] Preserve publication-on-input, index-only no-publication, per-consumer delivery, retry receipts and root-run observations; recover after interrupted commit/delivery. — 2026-10-25 21:27 ET; both kinds pass recovery on each engine. Input/index boundary cases pass; held-review cases retain set-aside records and prevent false completion after delivery (two cases per engine).
- [x] Freeze and verify protocol 1–3 migration fingerprints; review and qualify the minimal new protocol independently of onboarding. — 2026-10-25 21:22 ET; all 13 historical engine/protocol sets remain fixed; PostgreSQL/MySQL protocol 6 adds two fixed sets. An intentionally wrong answer fails before restoration and the positive rerun.
- [x] Connect immutable root-run scope, attempts, mapping pins, receipts and reconciliation through indexed portable storage; no fake business batches. — 2026-10-25 21:22 ET; mapping interruption/resume retains the original version on both kinds/engines; a later root uses the corrected version. Observing roots retain producer attribution and add no business generation.
- [x] Connect actual merge/publish workers, normal manifest execution, Journal delivery and supported forced-publication commands to that storage. — 2026-10-25 21:22 ET; both kinds pass actual worker execution, immutable Journal retry and forced CLI page delivery on each engine; four independent installed cases pass at 7708cb5b.
- [x] Qualify two configured kinds/sources on each engine through an independently installed five-wheel bundle; include lost acknowledgement and zero-work replay — 2026-10-25 20:39 ET; committed runtime 7708cb5b passes four isolated installed cases with two sources, separate worker/verifier processes and a SELECT-only verifier login. Journal interruption/replacement-run recovery, forced CLI pages and no-new-merge retry pass. MySQL verifier-grant fixture uses SQLAlchemy text compilation for its literal host wildcard. Original installed-save first-kind regressions also pass on both engines; final-head installed qualification and CI remain pending.
- [ ] Finish Standards/Spec/GoF review and final CI, publish the implementation PR, and update Lavish with verified outcomes.
- [x] Qualify the initial opaque run-metadata boundary — 2026-10-25 15:52 ET; four storage cases per engine pass for immutability, CAS conflicts, expired proof and denied direct writes.
- [x] Qualify the initial fenced/outbox ordering and release boundary — 2026-10-25 15:52 ET; four storage cases per engine pass, including expired acknowledgement and stale-owner refusal after release/reclaim.
- [x] Qualify normal merge authority and actual contract publication worker/verifier — 2026-10-25 15:52 ET; four normal cases per engine pass across two configured kinds; expired first/duplicate writes and expired delivered-row retries refuse.
- [x] Qualify initial normal merge-worker lost-acknowledgement recovery — 2026-10-25 15:52 ET; two kinds per engine pass with two configured sources: exactly two commits, retry invokes no merge, independent receipt verification and completion only after both deliveries.
- [x] Freeze protocols 1–5 before extension and compare their 13 supported engine/protocol fingerprint sets — 2026-10-25 15:52 ET; the public fixed-answer compilation test passes after the new protocol-6 changes.
- [x] Qualify interrupted normal Journal delivery with a replacement producing run — 2026-10-25 16:26 ET; two configured kinds pass on PostgreSQL and MySQL, preserving one original event/context after delivery interruption, refusing the superseded worker and advancing no business generation on retry.
- [x] Qualify the normal forced-publication CLI and page delivery — 2026-10-25 16:44 ET; two configured kinds pass on both engines, retaining identical retry manifests, refusing changed page scope and unsupported consumers, and preserving current/history/lookup bytes.
- [x] Qualify populated protocol-5 owner upgrades and interruption recovery — 2026-10-25 16:44 ET; both engines preserve original business bytes and generations, rebuild waiting references, replay original protocol-5 batches and reject fresh protocol-5 writers after upgrade. Explicitly install the added observer index on existing tables. Keep unchanged mastering vocabulary on its existing catalog version.
- [x] Qualify protocol-6 rollback and direct-call fencing — 2026-10-25 20:30 ET; late expiry, caller-held transactions and malformed SQL authority requests pass on both engines without retained-row changes on refusal.
- [x] Reproduce the draft CI failures and correct affected fixture contracts — 2026-10-25 20:30 ET; quality-report file passes 72 tests, owner registry passes 7 PostgreSQL/6 MySQL cases, and both kinds pass search-maintenance checks on both engines. Installed-package cases and final CI remain unchecked.
- [x] Diagnose cumulative CI timeout and retain every qualification folder in independent required jobs — 2026-10-25 21:22 ET; old PostgreSQL CI passed 351 tests in 13:28 before the shared 15-minute budget expired. New MDM/RDM/Silver matrices and merge-gate coverage regression are pushed at 864f755c; three architecture checks pass. Final CI is pending.
- [x] Complete local held-review qualification — 2026-10-25 21:27 ET; two cases per engine pass in 46.76 seconds (PostgreSQL) and 58.66 seconds (MySQL), preserving held records and blocking false completion. Lint F821 and whitespace checks pass.
- [x] Learning → skill — 2026-10-25 21:22 ET; separate PR #1173 updates `skills/mdm-engineering/references/storage-adapters.md` for added-index installation, unchanged catalog authority, durable delivery origins, complete consumer accounting and independent installed verification; eight affected source-neutrality checks pass. Skill PR remains draft pending its own CI.

## Acceptance evidence

Normal configured worker and publication recovery pass on each real engine with restricted roles, late expiry, overtaking, rollback and zero-work replay.

## Comments

Charted from the operator’s existing implementation direction and Lavish request on 2026-10-23; no part is claimed complete by creating this ticket.


## Pickup and initial design consult — 2026-10-25 15:21 ET

Fresh branch/worktree from origin/main 69f1501c. Prerequisites #1164/#1165
merged. User feedback on the worker/publication node asks to complete ticket
06 in one continuous implementation. No source requests or activation.

The existing protocol-5 adapter already proves commit-local worker fences
and exact per-consumer publication bytes, but the normal worker refuses
authority. RunCoordinator and worker receipts still read native PostgreSQL
run tables. Existing outbox claims also lack normal worker authority and
consumer generation ordering. These are demonstrated execution/storage gaps.

GoF review: preserve Store, RunCoordinator and the existing worker interfaces.
Their histories show transport/authority additions, not growing domain-policy
variants; no new Strategy hierarchy is justified. Use the adapter boundary
for indexed bytes and durable CAS/immutable run metadata. Introduce any
necessary capability in a new protocol, keeping all earlier fingerprints
unchanged. Shared computation prepares values; the destination enforces
current leases, versions, immutability and commit expiry.


## Initial execution checkpoint — 2026-10-25 15:52 ET

The normal owner command now installs protocol 6 on PostgreSQL/MySQL,
withholds runtime execution while rebuilding the waiting-review index and
then enables the restricted caller. Opaque CAS/immutable execution metadata
has server recording time without advancing business generations. Existing
external resource-proof validation is shared by normal merges, metadata and
publication claims/acknowledgements. Earlier-consumer generations block later
publication, and failed deliveries can release a still-owned claim.

Normal run scope/attempt/report and merge-worker receipts now use indexed
selected-store reads. A lost worker acknowledgement retries the same frozen
manifest with no new Merge Stage invocation. Reconciliation retains original
producing-run quality profiles and waits for required deliveries. Current
normal proofs pass for both configured kinds and both sources on each engine.
The new Rust waiting-reference test passes, and all 13 earlier migration
fingerprint sets remain unchanged.

Still incomplete: Journal delivery/original delivery context; full expiry and
concurrency/direct-wire cases; populated interrupted upgrade; independently
installed workers and read-only verifier; forced publication; final regressions,
CI and separate skill learning. No full workflow support or retirement is
claimed. No provider requests, source activation or shared-store mutation.

## Review checkpoint — 2026-10-25 21:22 ET

### Standards

Dedicated Codex branch/worktree; clean rebase onto main 6b5c46a3 and overlap guard pass. Historical fingerprints remain unchanged. Commit-time authority, restricted roles and immutable evidence remain destination guarantees. No provider access or shared-store activation.

### Spec

Worker recovery, mapping freeze, Journal origin retention, forced publication and populated upgrades are implemented and qualified locally on both selected engines. Held-review completion passes for both kinds on each engine; final-head CI remains open. Full 18-family workflow qualification and retirement stay in tickets 07 and 08.

### GoF

Reviewed the changed Store/worker/adapter modules and their recent history with the available gof-refactor-reviewer skill. Preserve the existing facade and adapter seam. Shared orchestration and engine-specific enforcement remain separate; no repeated variation justifies a new Strategy hierarchy. CI uses explicit independent jobs to give existing qualification families separate budgets.
