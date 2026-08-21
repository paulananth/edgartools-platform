# Does ADR 0004’s staging cleanup contract extend, or do we need a sibling reclaim contract?

Type: grilling
Status: resolved
Blocked by: none

## Question

[ADR 0004](../../../docs/adr/0004-one-time-version-aware-staging-cleanup.md)
and `cleanup-s3-staging.sh` define a one-time, default-dry-run,
VersionId, confirm-flag cleanup **only** for `warehouse/_staging/` (later
`warehouse/silverstage/`). That script selects `IsLatest=true` under an
ephemeral prefix — fatal if pointed at Canonical Silver shards.

GSD SAFE-01/SAFE-02 want a shared VersionId primitive for:

- noncurrent `shard-*.duckdb` (`IsLatest=false` only)
- unique current identity-refresh run keys
- historical gold `run_id=` copies with a keep-set

Decide:

1. Extend ADR 0004 / one script with prefix-specific selectors and a hard
   deny-list of Canonical Silver current keys.
2. New sibling ADR + `reclaim-warehouse-duplicates.sh`; ADR 0004 stays
   staging-only.
3. Three separate scripts, no shared primitive.

Name the deny-list keys and the confirm flags. Do not implement the script
in this ticket.

## Answer

**Option 2.** ADR 0004 stays staging-only. Warehouse duplicates use a
**sibling** VersionId Reclaim contract, not an extension of the staging
cleanup.

Staging cleanup keeps `IsLatest=true` under the ephemeral prefix and
requires `--confirm-delete-staging` with `--apply`. Do not add a Canonical
Silver deny-list or gold keep-set to that script.

Sibling reclaim:

- Confirm flag: `--confirm-delete-duplicates` (distinct from staging).
- Deny-list: current (`IsLatest=true`) Canonical Silver
  `warehouse/silver/sec/silver.duckdb` and
  `warehouse/silver/sec/shards/shard-{0,1,2,3}.duckdb`. A reviewed manifest
  that includes those VersionIds is a hard fail.
- Eligible: noncurrent Canonical Silver versions; Identity Refresh Run
  snapshots older than 24 hours; gold `run_id=` copies outside the keep-set.

Not option 1: `IsLatest=true` on staging would be fatal on shards.
Not option 3: one sibling primitive, not three scripts.

Shipped. Covered by
`test_adr0004_staging_cleanup_script_is_unchanged_islatest_contract`.
