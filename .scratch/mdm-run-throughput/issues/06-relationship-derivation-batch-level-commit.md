Type: task
Status: resolved

## Question

`derive_relationships`'s per-type worker (`_derive_one`, `edgar_warehouse/mdm/pipeline.py:1324-1343`) commits exactly once at the end of an entire relationship type's derivation. Should types with an existing internal batch structure (`INSTITUTIONAL_HOLDS`, `MANAGES_FUND`) commit periodically at their batch boundary instead, the way Ticket 04 fixed `_run_grouped_concurrent`?

## Context

Found live while watching a `daily_incremental` execution (`daily-incremental-1788831083`, 2026-09-07/08) progress through its `RunMdmChain` → `Mastering` step. Direct `pg_stat_activity` inspection (distinguishing true transaction age via `xact_start` from last-statement age via `query_start` — an earlier confusion in this same investigation, since all-but-2 sessions showed `idle` with a stale `query_start` while genuinely still mid-transaction) found session `583257` had one open transaction for **3h24min+ and growing**, actively executing real INSERT/UPDATE statements (new `mdm_security` stub entities, `mdm_change_log` rows, `mdm_relationship_instance` rows) the entire time, with **zero commits**.

Root cause, confirmed by a full audit of every `_derive_*` method (`_derive_is_insider` through `_derive_institutional_holds_batch`, `pipeline.py:1465-4260`): **zero `commit()` calls exist inside any of the 11 relationship-type derivation methods.** The only commit in the whole `derive_relationships` call path is `_derive_one`'s single `worker_session.commit()` after `_derive_relationship_type` fully returns (`pipeline.py:1340`).

For most types this is harmless — confirmed live the same night: `ISSUED_BY`/`IS_ENTITY_OF`/`IS_INSIDER`/`HAS_PARENT_COMPANY`/`IS_PERSON_OF` all completed in under 1 second each. But `INSTITUTIONAL_HOLDS` derives from `sec_thirteenf_holding` — 6.8M rows in prod, the largest table in the system — and was the type actively running during the 3h24min+ uncommitted-transaction observation (confirmed via log evidence: `put_call`/`discretion_type`/`shares_held` property keys are 13F-specific).

This is the exact same "commit once per unit of work, but the unit of work turns out unbounded" shape [Ticket 04](04-run-grouped-concurrent-single-end-of-group-commit.md) already fixed for `_run_grouped_concurrent`'s oversized security groups — just in a sibling code path (relationship derivation, not entity resolution) this session hadn't touched until now.

**Structural difference across the 11 methods, confirmed before scoping the fix:**
- `_derive_institutional_holds` (CIK-range batching, `_INSTITUTIONAL_HOLDS_CIK_BATCH_SIZE`) and `_derive_manages_fund` (CRD-range batching, `_MANAGES_FUND_CRD_BATCH_SIZE`) already have an existing batch-loop structure from an earlier, unrelated OOM-guard fix (bounds a single `silver.fetch()` from reading too much into memory at once). Each batch call (`_derive_institutional_holds_batch`/`_derive_manages_fund_batch`) already `flush_pending()`s and `unprime_relationship_type()`s internally in a `finally` block before returning — a clean, already-existing checkpoint boundary with nothing left half-written and no stale cache for the next batch to trip over.
- `_derive_holds`/`_derive_company_holds` fetch the entire ownership-transaction universe unbounded in one `self.silver.fetch()` call with no batch structure at all — a different, larger gap (OOM risk, not yet a periodic-commit gap, since there's no natural boundary to commit at). Deliberately out of scope for this ticket.
- The other 7 methods have zero evidence of costing anything (confirmed live, sub-second each) — building a shared commit mechanism for them now would be premature generalization against zero real cases.

`/gof-refactor-reviewer` consulted before implementing (CLAUDE.md hard rule): confirmed the batch-boundary insertion point is safe (each batch already flushes/unprimes before returning, so a commit there has nothing stale to interact with), confirmed the narrow two-method scope is correct (Rule 0: leave the 7 unproblematic methods alone), and confirmed `_derive_holds`/`_derive_company_holds`'s unbounded-fetch shape is a separate, larger decision not to fold into this fix.

## Answer

**Fix (implemented and live-tested against the incident's own live-observed shape, matching the "real measurements" standing preference):** added `self.session.commit()` immediately after each batch call returns, in both `_derive_institutional_holds`'s CIK-range `while` loop (`pipeline.py:4111-4131`) and `_derive_manages_fund`'s CRD-range `for` loop (`pipeline.py:2298-2311`) — right after the batch's own `flush_pending()`/`unprime_relationship_type()` has already run, before the loop's own early-exit `break` check (so even the last, break-triggering batch still gets committed). `_derive_one`'s existing final `worker_session.commit()` is unchanged — this adds periodic checkpoints in addition to, not instead of, that final commit.

Tests: 2 new in `tests/mdm/test_pipeline_relationships.py` —
`TestInstitutionalHoldsBatching::test_commits_periodically_at_each_cik_batch_boundary`
(3 distinct CIKs, batch_size=1 → 3 batches → asserts `commit_count >= 3`) and
`TestRunRelationships::test_manages_fund_commits_periodically_at_each_crd_batch_boundary`
(5 advisers, batch_size=2 → 3 batches → asserts `commit_count >= 3`), both using an
`event.listen(session.get_bind(), "commit", ...)` counter (same pattern Ticket 04's
tests used). Both confirmed to fail (`commit_count == 1`) against the pre-fix code via
a `git stash` round-trip, then pass after. Full `tests/mdm/` suite green: 689 passed.

**Deployed and live-verified 2026-09-08.** Built and deployed a fresh MDM prod image
(`edgartools-prod-images:mdm-sha-3af348b5d0b7`/`mdm-prod`, digest
`sha256:8a7bd53...`) via `deploy-aws-application.sh --env prod --skip-build --enable-mdm`
(PR #572, containing both this ticket and Ticket 07, merged and deployed together).

Deploying surfaced the exact incident this ticket documents, still live: session `583257`
(`daily-incremental-1788831083`'s `Mastering` step, still on the *old* pre-fix image, running
7h15min+ on `RunMdmChain`) was still open, idle-in-transaction, and now blocking a fresh
scoped verification task (`mdm derive-relationships --relationship-type INSTITUTIONAL_HOLDS
--target-per-type 10000`) via a Postgres `transactionid` lock. Stopped the stale execution
(`aws stepfunctions stop-execution`), confirmed the nested MDM execution and its lock both
cleared, then started a fresh unscoped `daily_incremental` execution on the fixed image.

Direct evidence the fix works: querying `mdm_relationship_instance` for the scoped test's
`run_id` while its ECS task was still `RUNNING` (not yet finished) showed row count go
`0 → 384` — durable, externally-visible progress landing mid-derivation, not withheld until
a single end-of-type commit. This is the same live technique Ticket 04 used for its own
mid-group commit proof, applied here to the sibling relationship-derivation path.

**Full-run confirmation (execution ran 07:00:47–07:36:18 ET, ~35.5 min, 9,900 rows against
a 10,000 target-per-type):** grouping committed rows by minute for this `run_id` shows six
distinct landing bursts spread across the whole run — 11:01 (384), 11:07 (2,271), 11:15
(459), 11:16 (1,417), 11:20 (898), 11:23 (4,471) UTC — not one commit at 11:36 when the
execution actually finished. This is exactly the periodic-checkpoint behavior the fix was
built for, at real production scale, not just a small window.
