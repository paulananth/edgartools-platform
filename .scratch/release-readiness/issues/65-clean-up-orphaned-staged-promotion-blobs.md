# Clean up orphaned staged-promotion blobs in S3 `silverstage/`

Type: task
Status: open

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
