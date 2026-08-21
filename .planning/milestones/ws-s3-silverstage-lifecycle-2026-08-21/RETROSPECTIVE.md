# Retrospective

## Milestone: v1.0 — Warehouse S3 duplicate-storage reclaim

**Shipped:** 2026-08-21
**Phases:** 5 (4 complete, 1 dropped) | **Plans:** 4 wayfinder tickets

### What Was Built

Leak-seal on Joined Live Keys, a sibling VersionId reclaim tool, and a one-shot apply that removed ~2 TiB of billed warehouse duplicates. Current Canonical Silver stayed. Bronze was inventoried, not deleted.

### What Worked

- Discuss-phase locked D-01–D-17 so Terraform apply could not restore `silverstage/`
- Converting remaining GSD fog to a wayfinder map then `/to-spec` / `/to-tickets` got leak-seal and reclaim into prod the same day
- Deny-list of current Canonical Silver in the reclaim tool; apply counted from the reviewed TSV, not a live re-select

### What Was Inefficient

- GSD ROADMAP stayed at 0% while prod work shipped; closeout is retroactive
- Gold keep-set was implemented before asking whether warehouse `gold/` is even serving (it is not; Snowflake gold is)
- Grilling tickets 03 and 06 were never closed even though spec defaults shipped

### Patterns Established

- Lifecycle filters must be prefixes of `StorageLocation.join()` keys, not relative write paths
- Terraform owns standing expire; operator script owns existing VersionIds
- Staging cleanup (`IsLatest=true`) must not be reused on Canonical Silver shards

### Key Lessons

- A lifecycle rule that matches nothing is a silent leak, not a no-op you can spot in `terraform plan` without live listing
- Dual-write leftovers (warehouse gold parquet) keep refilling after reclaim until the writer is removed
- Do not close a cost cleanup until you know which layer the bytes actually serve

### Cost Observations

- Silverstage leak: 1.71 TiB deleted
- Leftover reclaim: 339.8 GiB deleted
- Remaining keep-set gold ~0.5 GiB until dual-write stops

## Cross-Milestone Trends

First milestone in this workstream. No prior trend table.
