# 21 — Apply DuckDB file lifecycle disposition (S3 archive/delete)

**What to build:** Apply DuckDB file disposition for the canonical `silver.duckdb`/shard
objects still in S3, per DuckDB Retirement's Ticket 01 answer: extend the existing
`expire-noncurrent-silver-canonical-versions` lifecycle-rule precedent -- bounded
retention on the final current version, then archive/delete.

Split out of Ticket 12 because it is irreversible against shared production data and
gated on a different, currently-open dependency: [Ticket 19](
19-sec-company-ticker-cross-store-divergence.md)'s own Done-when criterion requires "a
repeat `table-reconcile --tables sec_company_ticker` run passes clean afterward" -- which
needs both the DuckDB side of that comparison and the live 1.79GB canonical object to
still exist. Applying disposition before Ticket 19 resolves would remove the evidence
needed to close it.

**Blocked by:** nothing since 2026-09-14 ([Ticket 19](19-sec-company-ticker-cross-store-divergence.md)
closed as explained, its evidence recorded in the ticket, so the DuckDB file is no longer needed
to close it). Still requires explicit operator go-ahead separately (destructive action on shared
prod infrastructure, not something to execute on an inferred approval).

**Status:** resolved 2026-09-14 (applied to prod 20:29 ET with operator go-ahead)

- [x] Ticket 19 resolved (closed 2026-09-14 as explained)
- [x] Explicit operator go-ahead obtained for this specific disposition action ("7 days",
      2026-09-14, after the inventory and plan below were presented)
- [x] Bounded retention + archive/delete applied to the canonical `silver.duckdb`/shard S3
      objects, following the `expire-noncurrent-silver-canonical-versions` precedent

## Answer

**Inventory before the change** (`edgartools-prod-warehouse-690839588395`, `warehouse/silver/sec/`):

| Object | Size | Last written |
|---|---|---|
| `silver.duckdb` | 1.79 GB | 2026-09-06 10:42 ET |
| `shards/shard-0..3.duckdb` | 0.82 / 0.43 / 0.27 / 0.14 GB | 2026-08-20 |
| `runs/*/manifest.json` (7,621 files) | 0.03 GB | ongoing bootstrap-batch run manifests |

Noncurrent DuckDB versions: 0 (the 7-day noncurrent rule had already cleared them). No command
has written a DuckDB file since cutover Ticket 10 (2026-09-12). Remaining readers: `table-reconcile`
(hydrates `silver.duckdb`; leaves with the engine in silver-merge-engine-migration Ticket 09) and
`reclaim-warehouse-duplicates`, which only protects these keys and never reads them.

**Disposition chosen:** expire the final current version, no Glacier step. At 3.45 GB the
objects cost about $0.08/month, so archive adds nothing. The operator chose a 7-day window
(30 days was offered as the default).

**Change:** two rules added to `aws_s3_bucket_lifecycle_configuration.warehouse` in
`infra/terraform/modules/storage_buckets/main.tf`:
- `expire-retired-silver-canonical`, prefix `warehouse/silver/sec/silver.duckdb`, `expiration { days = 7 }`
- `expire-retired-silver-shards`, prefix `warehouse/silver/sec/shards/`, `expiration { days = 7 }`

Scoped to the exact keys so the `runs/` manifests are untouched, and the existing
`expire-noncurrent-silver-canonical-versions` rule keeps its no-`expiration` contract (its comment
forbids adding one). `terraform plan` on `infra/terraform/accounts/prod` showed exactly "0 to add,
1 to change, 0 to destroy": the one resource updated in place, two `+ rule` blocks, "3 unchanged
blocks hidden" (the known replace-the-whole-rule-set pitfall did not fire). Applied from the saved
plan at 20:29 ET; `Apply complete! Resources: 0 added, 1 changed, 0 destroyed`. Live
`get-bucket-lifecycle-configuration` read back: five rules, the three old ones byte-for-byte as
before. A post-apply `plan -detailed-exitcode` returned 0 (no drift).

**Timing caveat, found after apply and reported to the operator:** S3 measures `expiration days`
from each object's last-modified time, not from the rule's creation. All five objects are already
older than 7 days, so S3 places delete markers on them at its next daily lifecycle pass (within
about 24–48 hours of 20:29 ET), not on 2026-09-21. Recovery window after that: each object remains a
noncurrent version for 7 days under the existing rule, restorable by deleting the delete marker
(`aws s3api delete-object --bucket ... --key ... --version-id <delete-marker-id>`). The operator was
offered a later `days` value to get a full week of visibility.

**Effects downstream:**
- `table-reconcile` will fail to hydrate once the delete markers land; it is deleted by Ticket 09.
- Ticket 09 (silver-merge-engine-migration) loses this blocker. Its remaining one is its own
  [Ticket 12](../../silver-merge-engine-migration/issues/12-fundamentals-markers-landing-only.md),
  resolved in code (PR #633 open at the time of writing).
- The two rules should be deleted with the engine once the objects are gone (comment in the module
  says so).
