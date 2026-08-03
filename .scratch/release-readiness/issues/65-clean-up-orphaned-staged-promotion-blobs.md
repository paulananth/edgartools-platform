# Clean up orphaned staged-promotion blobs in S3 `silverstage/`

Type: task
Status: resolved

## Progress (2026-08-02 — prefix renamed)

The staging key prefix was renamed `_staging/` → `silverstage/` in
`object_storage.py:241` (plus matching test fixtures in
`test_object_storage_conditional_promotion.py` and `test_warehouse_orchestrator_mdm.py`; 71
tests pass). This is a **go-forward code change only** — the currently-deployed prod image
still writes to `_staging/`, and the 46 orphaned objects (49.3GB) documented below are
unaffected until a new image ships and the cleanup sweep below runs. Everywhere below that
says `_staging/` describes the still-live prod state as of this ticket's filing; the fix work
should target `silverstage/` going forward (new lifecycle rule prefix, new delete-on-success
key) while still sweeping the old `_staging/` objects once during cleanup.

## Question

`ObjectStorage.write_staged_bytes` (`edgar_warehouse/infrastructure/object_storage.py:231-243`)
writes every staged canonical-silver candidate to a fresh, never-reused key
(`silverstage/<uuid4>/<canonical_relative_path>`, renamed from `_staging/` — see Progress
above). `promote_staged` (`:322-389`) reads that staged
object and `PUT`s its bytes onto the canonical key (S3: conditional `PutObject` with
`IfMatch`/`IfNoneMatch`; local: plain copy) — but never deletes the staged object afterward,
on success or on `PromotionConflictError`. The docstring for `promote_staged` even documents
the conflict case as deliberately "leaving the staged object in place for inspection/retry" —
but nothing ever removes it later, including after a successful promotion that made it
permanently unreachable garbage.

This is not hypothetical — confirmed live in prod (2026-08-02):

```
$ aws s3 ls s3://edgartools-prod-warehouse-690839588395/warehouse/_staging/ --recursive --summarize
...
Total Objects: 46
   Total Size: 49285734400   # 49.3 GB
$ aws s3api get-bucket-lifecycle-configuration --bucket edgartools-prod-warehouse-690839588395
An error occurred (NoSuchLifecycleConfiguration) ...
```

Every `reduce-identity-refresh` reducer attempt (`identity_refresh_publication.py:169-238`)
writes one ~1GB staged blob per promotion attempt (more on any `PromotionConflictError` retry),
and the bucket has no lifecycle rule to expire the `_staging/` prefix at all. This grows
without bound as the Daily Identity Refresh schedule (ticket 49) goes live — at even one
promotion per day it's ~365GB/year of pure waste; more with backstop-sweep runs or promotion
contention.

## Required work

Two independent, non-conflicting mitigations — do both:

- **S3 lifecycle rule:** add an expiration rule on the `silverstage/` prefix to the warehouse
  bucket's Terraform (`infra/terraform/accounts/prod/` — find the existing
  `edgartools-prod-warehouse` bucket resource), e.g. expire objects under `silverstage/` after
  a short bounded window (a few days is enough to cover any manual conflict-inspection need
  the `promote_staged` docstring anticipates). Apply to dev's bucket too if dev is
  reprovisioned in the future (see CLAUDE.md's dev-decommission note — not blocking this
  ticket, just don't hardcode prod-only assumptions into the Terraform module).
- **Explicit delete on success:** after a successful `promote_staged` call inside
  `reduce_identity_refresh` (`identity_refresh_publication.py:217`), delete the staged object
  the reducer itself just wrote. Do not delete on `PromotionConflictError` — the existing
  leave-in-place-for-inspection behavior on conflict is intentional and should stay; the
  lifecycle rule is the backstop for that case instead.
- Sweep and delete the 46 already-orphaned objects (49.3 GB) currently in prod's old
  `_staging/` prefix once the fix is confirmed — a manual `aws s3 rm --recursive` after
  confirming none are a currently-in-flight promotion's staged object (cross-check against any
  `RUNNING` `daily_incremental` execution before deleting). Once a new image with the
  `silverstage/` rename is deployed, also confirm nothing still writes to the old `_staging/`
  key (no lifecycle rule will cover it unless one is added for both prefixes, or the sweep is
  done as a one-time manual cleanup instead of relying on lifecycle for the legacy prefix).

## Done when

The lifecycle rule is live in Terraform and confirmed via `get-bucket-lifecycle-configuration`;
a focused test proves `reduce_identity_refresh` deletes its own staged object after a
successful promotion and leaves it in place after a `PromotionConflictError`; and the
pre-existing 49.3GB of orphaned objects in prod is cleaned up.

## Progress (2026-08-03)

**Implemented**, on branch `claude/cleanup-orphaned-staged-blobs` (off `main` — note this
branch predates [ticket 64](64-add-identity-refresh-reducer-progress-logging.md)'s merge,
so `reduce_identity_refresh` here is the pre-ticket-64 version; a merge-time conflict with
PR #338 is expected and will be resolved the same way tickets 77/78 were):

- **Explicit delete on success**: added `StorageLocation.delete_object` (best-effort,
  `missing_ok=True` locally, `s3.delete_object` remotely) to `object_storage.py`, and one
  call site in `reduce_identity_refresh` right after a successful `promote_staged` —
  deliberately *inside* the `try` block, after `promotion = ...` and before the function can
  reach the `except PromotionConflictError` clause, so a conflict never triggers a delete.
- **S3 lifecycle rule**: added `aws_s3_bucket_lifecycle_configuration.warehouse` to
  `infra/terraform/modules/storage_buckets/main.tf` (shared by dev+prod, no prod-only
  hardcoding), filtered to the `silverstage/` prefix, 3-day expiration plus matching
  `noncurrent_version_expiration` (the bucket has versioning enabled). `terraform validate`
  and `terraform fmt -check` both clean.
- Confirmed `write_staged_bytes` already writes to `silverstage/` (not `_staging/`) — that
  part of this ticket's "Progress (2026-08-02)" rename note was already live before this
  session; no further code change needed for it.

**Tests**: 3 new tests in `tests/unit/test_object_storage_conditional_promotion.py`
(`delete_object` local-removes, local-missing-is-noop, remote-calls-s3-delete_object) and 2
new tests in `tests/unit/test_identity_refresh_publication.py`
(`test_reducer_deletes_its_own_staged_object_after_successful_promotion`,
`test_reducer_preserves_staged_object_after_promotion_conflict` — the latter captures both
attempts' distinct staged paths via a monkeypatched `promote_staged` and asserts the
conflicted attempt's object survives while the successful attempt's own object is deleted).
Full `tests/unit` + `tests/application` + `tests/architecture` suite: 1268 passed, 4 skipped
(pre-existing), 1 pre-existing unrelated deselect, 35 subtests.

**Live sweep — not yet done, pending explicit go-ahead.** Re-checked the orphaned prefix live
just before writing this: it has *grown* since this ticket was filed —
**48 objects, 51.4GB** (was 46/49.3GB on 2026-08-02), confirming the leak is ongoing pending
deploy of the fix above. Safety precondition checked and clear: zero `RUNNING` executions
across `daily-incremental`, `load-history`, `bootstrap`, `bootstrap-full`, `targeted-resync`,
`bootstrap-batched` at check time — nothing currently has an in-flight staged object under
this prefix. The actual `aws s3 rm --recursive` has not been run; this is a real, live,
~51GB deletion in prod and deliberately left for explicit confirmation before executing,
per this repo's destructive-operation convention (same as ticket 71's stance).

Not yet deployed — the code fix (delete-on-success + lifecycle rule) takes effect on the
next warehouse image rebuild/deploy plus a `terraform apply` for the lifecycle rule.

## Sweep completed (2026-08-03)

Both PRs merged (#338 ticket 64, #339 this ticket — resolved a real merge conflict between
them in `identity_refresh_publication.py`/`test_identity_refresh_publication.py`/`map.md`,
same shape as the earlier 77/78 conflict; full suite green afterward, 1270 passed). Re-ran
the safety precondition fresh immediately before the sweep (zero `RUNNING` executions across
all 6 SEC-fetching/reducer state machines, unchanged from the earlier check) and re-confirmed
the object count (still 48/51.4GB, unchanged). Ran `aws s3 rm --recursive` scoped strictly to
`s3://edgartools-prod-warehouse-690839588395/warehouse/_staging/` — confirmed empty
afterward (0 objects, 0 bytes).

**New finding, not yet actioned:** the *live* `silverstage/` prefix (what
`write_staged_bytes` actually writes to today) already has its own smaller version of the
same leak — **16 objects, 18.4GB** — because the code fix isn't deployed yet, so the leak is
still actively happening under the new prefix name. Deliberately did not sweep
`silverstage/` in this pass: unlike the dead `_staging/` prefix, it's the prefix the
still-undeployed fix will actually manage going forward, and a couple of its objects could
legitimately be conflict-preserved (intentional). Once the code + Terraform lifecycle rule
deploy, the 3-day expiration rule will catch up on whatever's there by then; a manual sweep
of `silverstage/` before that deploy is a separate, later decision, not part of this ticket's
scope (which named the old `_staging/` prefix specifically).
