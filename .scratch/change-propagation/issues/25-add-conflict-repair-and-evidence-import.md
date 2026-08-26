# 25 — Add conflict, repair, exclusion, and evidence-import workflows

**What to build:** Give operators safe, auditable workflows for conflicting
immutable evidence, explicit exclusions, corrective child revisions, and
checksum-verified evidence imported from another environment or account.

**Blocked by:** 17 — Make Bronze capture retry-safe and recoverable; 18 —
Materialize ordered logical source revisions

**Status:** resolved (partially — bullets 3/4 explicitly split out to a
follow-up ticket, see Answer)

- [x] Different bytes under one immutable SEC identity are both retained and
  quarantined; neither arrival order nor a mutable latest pointer chooses one.
- [x] A repair creates an immutable child revision naming accepted and rejected
  evidence, its operator authorization, and reason without rewriting history.
- [ ] An exclusion is authorized, reasoned, scoped, visible in Source Change
  Status, and cannot masquerade as a source deletion or no-impact result.
- [ ] Cross-environment evidence becomes processable only after explicit local
  authorization, checksum verification, and preserved source lineage.
- [x] Database roles keep coordinator, acquisition worker, processor, Silver
  finalizer, and operator transition ownership separate.

## Answer

**Scope split, agreed before implementation (advisor consult):** this ticket
bundles four largely-independent mechanisms plus a role-separation audit.
Bullets 1+2 share one schema decision (conflict quarantine and repair are the
same `RevisionRelationship.REPAIR` foothold Ticket 18 already reserved but
never built); bullet 5 turned out to already be built (013's role graph) and
only needed a real-Postgres proof. Bullets 3 (exclusion) and 4
(evidence-import) are genuinely independent mechanisms with no dependency on
the conflict/repair schema — explicitly **not attempted** this session, not
partially done. A follow-up ticket owns them.

**Bullet 1 — conflict quarantine.** Traced to its real trigger: `object_storage.
write_immutable_bytes` already detects a content mismatch at an existing
immutable Bronze key, but previously just raised a bare `WarehouseRuntimeError`
and discarded the new payload — a crash, not a quarantine. Confirmed this can
only happen for an *identity-keyed* Bronze path (one accession/document); the
new Ticket 14/15 Facade's own capture path (`facade._capture_bronze_evidence`)
is content-hash-keyed, so different bytes always land at a different key there
by construction — this bullet's real target is the legacy identity-keyed
writers (filing artifacts, ADV documents, etc.), not the new Facade.

Fix: `write_immutable_bytes` now writes the conflicting payload to a
content-addressed quarantine sibling (`{relative}.conflict/{new_hash}`, reused
via the same method so it's collision-proof and replay-idempotent) and raises
a new `ImmutableContentConflictError` (a `WarehouseRuntimeError` subclass, so
existing broad catches still work) carrying both hashes and the quarantine
path — instead of discarding the new bytes. Neither payload is ever silently
picked; both are durably retained. Caught a real bug fixing this: the first
draft re-read the existing object via `read_bytes()` to compute its hash,
which for a remote (S3) conflict used `fsspec`, a code path the existing
test's mock didn't cover — hit a real `PermissionError: Forbidden` network
call under test. Fixed by computing the existing-content hash inline during
the byte-for-byte compare already being done (incremental hashing in the
remote branch, direct bytes-in-hand in the local branch), never re-reading.

**Bullet 2 — repair.** New `SourceRevisionLedger.materialize_repair` (mirrors
`materialize_reinterpretation`'s shape closely, but genuinely different bytes,
not a new interpretation of the same bytes — raw evidence, canonical-source
hash, and Bronze reference are all fresh; contract/parser/schema/configuration
version are inherited from the parent unchanged). Idempotent per parent by
reusing the existing `uq_source_revision_reinterpretation` index rather than
adding a new one (a repair's version tuple is always identical to its
parent's, since interpretation didn't change — that index already enforces
"at most one repair per parent" for free).

New `ConflictLedger` (`acquisition/conflict.py`) owns the operator-facing
repair action: `record_evidence_conflict` (idempotent per quarantine
reference) and `resolve_conflict` (`accept="existing"` closes the conflict
with zero new revisions — "without rewriting history" literally, nothing in
`source_revision` changes; `accept="conflicting"` materializes the REPAIR
child and points the closed conflict at it). Race-safe via a conditional
`UPDATE ... WHERE status = 'PENDING'` (not read-then-write) so two concurrent
resolves can't both "win." Requires non-empty `operator_authorization_reference`
and `reason` — enforced as data (`InvalidResolutionEvidence`), not a new DB
role, matching how `SourceRegistryLedger.open_draft`/`activate` already treat
operator authorization as audit evidence rather than a role gate.

New migration `015_source_evidence_conflict.sql`: caught a real bug building
it. First draft transferred `source_evidence_conflict`'s ownership to
`edgartools_acquisition_processor` (reasoning: recording/resolving a conflict
is a processing-lifecycle action, same role as revision materialization) and
gated the self-managing migration wrapper on that role's membership. Reproduced
live against real Postgres: `permission denied for schema public` on `CREATE
TABLE`, running as `application` — `CREATE` on schema `public` was only ever
granted to `edgartools_acquisition_owner` in 013, never to any of the five
*operational* roles (`application` is a member of those five, never of the
owner role — confirmed by re-reading 013's own DO block, not assumed). Fixed
by following 013's own established shape exactly: the table is owned by
`edgartools_acquisition_owner` (same as `source_revision`), with scoped
GRANTs (not ownership) to `edgartools_acquisition_processor`/coordinator/
worker/operator/silver_finalizer. The self-managing wrapper
(`_apply_source_evidence_conflict_migration`) now mirrors
`_apply_acquisition_ledger_migration`'s gate exactly. `bootstrap-prod-mdm.sh`
and `mdm_post_restore.sql` both updated to match (the new table folded into
the existing `edgartools_acquisition_owner`-scoped REVOKE/restore blocks, not
a separate one under the wrong role — caught and fixed before this was
committed, not left as a latent prod gap).

**Bullet 5 — role separation.** Found already built: 013's migration already
creates and grants five separate Postgres roles (coordinator/worker/
operator/processor/silver_finalizer) with real GRANT-level separation, not
just Python-side `require_*_role` checks. What was missing was proof at the
GRANT level, not just the happy path — added
`test_processor_and_silver_finalizer_boundaries_are_grant_enforced_not_just_
python_checked` (real Postgres, not SQLite — a SQLite session would
short-circuit `set_postgres_role` entirely and prove nothing, per this
codebase's own prior Ticket-20 lesson): worker/coordinator cannot `INSERT`
into `source_revision` (processor-only), and processor cannot `UPDATE` the
finalizer-only columns on `source_processing_decision`/
`source_expected_producer`. All four attempts correctly rejected with
`permission denied for table ...`, proving the boundary lives in the GRANT
graph, not just application code that a direct-SQL caller could bypass.

**Post-implementation code review (Standards + Spec axes) caught a third real
bug, fixed before commit.** The Spec-axis reviewer found that
`resolve_conflict`'s original race-safety design — read the conflict,
materialize a REPAIR revision for `accept="conflicting"` (its own, separate
transaction), *then* attempt a conditional `UPDATE ... WHERE status =
'PENDING'` — had a gap the "conditional UPDATE, not read-then-write" framing
didn't cover: under a genuine race against a concurrent `accept="existing"`
resolve, the loser's already-materialized REPAIR revision had no way to be
un-created once the UPDATE told it the row was already settled differently.
That left a permanent, audit-orphaned `source_revision` row — created, but
referenced by nothing (the closed conflict's `repair_revision_id` points at
the parent, not it) — directly undermining bullet 2's "without rewriting
history" audit-completeness guarantee. Fixed by switching from the
CAS/recursion pattern to a `SELECT ... FOR UPDATE` row lock on the conflict
before either branch runs: the second concurrent caller blocks on the lock,
then finds the row already `REPAIRED` and never calls `materialize_repair`
at all — actually simpler code than what it replaced, not just safer.
Reproduced empirically both ways: the new
`test_resolve_conflict_concurrent_opposing_outcomes_never_orphan_a_revision`
(real Postgres, two threads racing opposite outcomes on the same conflict)
fails 5/5 runs against the pre-fix code (an orphaned REPAIR revision
detected) and passes 5/5 against the fix. Also fixed two review-flagged
nits: a stale comment in `mdm_post_restore.sql` that said
`source_evidence_conflict` reuses `edgartools_acquisition_processor` as
owner (the code beside it was already correct —
`edgartools_acquisition_owner` — only the comment was wrong), and an
inline-`import pytest`-per-test-function inconsistency in
`test_conflict.py` versus its sibling files' module-top-import convention.

**Tests:** 3 new `materialize_repair` unit tests, 9 new `ConflictLedger` unit
tests, 4 new migration static-assertion tests, 1 new cross-role GRANT proof
(real Postgres), 4 new conflict-specific real-Postgres integration tests
(migration rerun-safety, ownership/fencing, full round-trip, and the
concurrent-opposing-outcomes race proof added after review) — 54 tests total
across the affected files, all green including four separate real-Postgres
runs (not mocked). `tests/unit/test_object_storage_conditional_promotion.py`
gained 2 new local-conflict tests plus an updated remote-conflict test
(now asserts quarantine behavior, not just rejection).
