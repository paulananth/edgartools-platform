# Warehouse S3 Duplicate-Storage Reclaim

Label: `wayfinder:map`

## Destination

A decided, buildable plan for the remaining warehouse duplicate-storage
reclaim after GSD Leak-seal is locked. Hands off to `/to-spec` then
`/to-tickets` (Ask Matt main flow) once CloudWatch retention, gold
keep-latest completeness, in-flight identity skip, leftover inventory, and
the reclaim contract beyond `_staging/` are settled. This map decides; it
does not apply Terraform or delete objects.

## Notes

- Domain: prod warehouse bucket `edgartools-prod-warehouse-690839588395`,
  account `690839588395`, `us-east-1`. Consult root `CONTEXT.md` (Canonical
  Silver, Joined Live Key, VersionId Reclaim, Staged Warehouse Object,
  Identity Refresh Run). Flag conflicts via `/domain-modeling`.
- GSD workstream `s3-silverstage-lifecycle` Phase 1 Leak-seal is **already
  decided** in
  [01-CONTEXT.md](../../.planning/workstreams/s3-silverstage-lifecycle/phases/01-leak-seal/01-CONTEXT.md)
  (D-01–D-17). Do not re-litigate it here. Leak-seal implementation happens
  after this map clears, via `/to-spec`.
- Standing: never expire current Canonical Silver; never use
  `cleanup-s3-staging.sh` as-is (it deletes `IsLatest=true`); copy its
  dry-run TSV / confirm / VersionId contract from
  [ADR 0004](../../docs/adr/0004-one-time-version-aware-staging-cleanup.md).
- [Production Observability and Image Cost Control](../ops-cost-control/map.md)
  locked a **seven-day** CloudWatch floor and listed “reducing log
  retention below seven days” as out of scope. GSD CW-01 asked for three
  days — that conflict is a ticket, not a silent override.
- Skills every session: `/grilling`, `/domain-modeling`. After the map
  clears: `/to-spec` then `/to-tickets` under this directory. Do not
  `/implement` from GSD `PLAN.md`.
- **This map does not carry execution.** Research tickets may measure live
  AWS read-only.

## Decisions so far

- [What leftover billed bytes remain on the warehouse bucket after silverstage delete?](issues/04-measure-live-warehouse-leftover-inventory.md) — Silverstage versions are gone (0 versions/DMs; 156 empty MPUs, 0 part bytes). Remaining billed: 315.45 GiB noncurrent shards (830 versions), 1.48 GiB noncurrent `silver.duckdb`, 19.09 GiB identity_refresh (614 current keys, 16 run dirs), 3.43 GiB current + 0.89 GiB noncurrent gold `run_id=` copies (28 tables × 7 runs). Canonical current silver.duckdb + 4 shards still present (3.03 GiB). [research/04-live-warehouse-leftover-inventory.md](research/04-live-warehouse-leftover-inventory.md).
- [Does bronze have billed duplicate or noncurrent waste, or only immutable current objects?](issues/05-inventory-bronze-duplicate-versions.md) — Almost all 69.64 GiB is current StandardStorage; listed noncurrent ~0.36 GiB; no current-key duplicates. Bronze reclaim of current SEC objects is out of this map. [research/05-bronze-duplicate-inventory.md](research/05-bronze-duplicate-inventory.md).
- [Keep, drop, or rewrite the three-day CloudWatch retention requirement?](issues/01-decide-cloudwatch-retention-vs-seven-day-floor.md) — Drop CW-01. Prod stays at seven-day Operational Forensics Window; GSD Phase 5 is out of this map. Live groups still 7 days (read-only, 2026-08-21).


## Not yet specified

- How `/to-spec` should slice Leak-seal vs reclaim vs bronze vs CloudWatch
  once the tickets below close.
- Whether the standing 7-day noncurrent rule on `warehouse/silver/` is
  enough after a one-shot shard VersionId reclaim, or a shorter window is
  required.
- Where reclaim dry-run TSVs and byte-evidence live
  (`warehouse/release-evidence/` vs operator scratch).

## Out of scope

- Re-opening GSD Phase 1 Leak-seal decisions D-01–D-17.
- Deleting current Canonical Silver keys.
- Executing VersionId deletes or Terraform apply from this map.
- ECR rollback-tag prune and empty `edgartools-dev-images`.
- [S3 Request-Churn Elimination](../s3-request-churn/map.md) (request
  volume, not duplicate object bytes).
- Blind bronze content delete without an inventory that proves billed waste.
- Reclaim of **current** bronze SEC filing keys (inventory shows they are not duplicates; noncurrent waste is ~0.36 GiB and not material next to warehouse shards).
- GSD CW-01 / Phase 5 three-day CloudWatch retention (seven-day floor stands).
