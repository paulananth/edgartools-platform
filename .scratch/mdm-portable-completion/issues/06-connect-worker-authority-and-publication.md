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

- [ ] Integrate the demonstrated destination-local fence/expiry capability with the normal worker; do not expand into unrelated Bookkeeping conversion.
- [ ] Refuse expired, superseded and same-token/different-attempt proofs through commit, including duplicate and caller-held transaction cases; test malformed direct database requests as well as Python validation.
- [ ] Preserve publication-on-input, index-only no-publication, per-consumer delivery, retry receipts and root-run observations; recover after interrupted commit/delivery.
- [ ] Freeze and verify protocol 1–3 migration fingerprints; review and qualify the minimal new protocol independently of onboarding.
- [ ] Connect immutable root-run scope, attempts, mapping pins, receipts and reconciliation through indexed portable storage; no fake business batches.
- [ ] Connect actual merge/publish workers, normal manifest execution, Journal delivery and supported forced-publication commands to that storage.
- [ ] Qualify two configured kinds/sources on each engine through an independently installed five-wheel bundle; include lost acknowledgement and zero-work replay.
- [ ] Finish Standards/Spec/GoF review and final CI, publish the implementation PR, and update Lavish with verified outcomes.
- [x] Qualify the initial opaque run-metadata boundary — 2026-10-25 15:52 ET; four storage cases per engine pass for immutability, CAS conflicts, expired proof and denied direct writes.
- [x] Qualify the initial fenced/outbox ordering and release boundary — 2026-10-25 15:52 ET; four storage cases per engine pass, including expired acknowledgement and stale-owner refusal after release/reclaim.
- [x] Qualify normal merge authority and actual contract publication worker/verifier — 2026-10-25 15:52 ET; four normal cases per engine pass across two configured kinds; expired first/duplicate writes and expired delivered-row retries refuse.
- [x] Qualify initial normal merge-worker lost-acknowledgement recovery — 2026-10-25 15:52 ET; two kinds per engine pass with two configured sources: exactly two commits, retry invokes no merge, independent receipt verification and completion only after both deliveries.
- [x] Freeze protocols 1–5 before extension and compare their 13 supported engine/protocol fingerprint sets — 2026-10-25 15:52 ET; the public fixed-answer compilation test passes after the new protocol-6 changes.
- [ ] Learning → skill: update its owning skill on a separate branch/PR, or record none.

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
