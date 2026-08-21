# Phase 1: Leak-seal - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-20
**Phase:** 1-Leak-seal
**Areas discussed:** Terraform apply gate, Identity-refresh expire shape, Regression test shape, Prefix / path exactness

---

## Terraform apply gate

| Option | Description | Selected |
|--------|-------------|----------|
| Targeted lifecycle resource after plan review | Plan, abort on extra warehouse-bucket drift, apply only the warehouse lifecycle resource | ✓ |
| Full prod root apply | Apply entire accounts/prod | |
| You decide | Planner picks safest apply | |

**User's choice:** Targeted lifecycle resource after plan review; profile `aws-admin-prod`; abort extra warehouse-bucket changes; regression green before apply.

**Notes:** Four questions in this area. Next-area after the first four.

---

## Identity-refresh expire shape

| Option | Description | Selected |
|--------|-------------|----------|
| Current + noncurrent at 7 days | Unique run keys never become noncurrent by overwrite | ✓ |
| Noncurrent-only at 7 days | Would not expire unique current keys | |
| warehouse/identity_refresh/ | Trailing slash; leases live elsewhere | (Claude discretion — user said You decide) |
| Only warehouse/identity_refresh/runs/ | Narrower | |
| 7 days is hard | Standing rule does not skip RUNNING Maps | ✓ |
| Both 7 days | expiration and noncurrent 7 | ✓ |
| Same apply as silverstage prefix | One lifecycle document | ✓ |

**User's choice:** Current+noncurrent 7/7, hard expire, same apply. Prefix left as You decide → locked to `warehouse/identity_refresh/`.

**Notes:** Lease path is `reference/identity_refresh_lease/` per warehouse_paths.properties.

---

## Regression test shape

| Option | Description | Selected |
|--------|-------------|----------|
| HCL parse + StorageLocation.join() | Analog test_ecr_image_retention.py plus production join() | ✓ |
| HCL string only | Faster, misses join() drift | |
| silverstage/ must not match joined keys | Negative case for the 1.71 TiB incident | ✓ |
| All three prefixes | silverstage, identity_refresh, silver with trailing slashes | ✓ |
| tests/architecture/ | No AWS credentials | ✓ |

**User's choice:** Architecture test, HCL+join(), negative `silverstage/`, all three prefixes, `tests/architecture/`.

---

## Prefix / path exactness

| Option | Description | Selected |
|--------|-------------|----------|
| These three strings | warehouse/silverstage/, warehouse/identity_refresh/, warehouse/silver/ | ✓ |
| Real StorageLocation with /warehouse root | Production join() contract | (Claude discretion — user said You decide) |
| Prod module only | storage_buckets/main.tf; skip destroyable/dev | ✓ |
| Fail the test if join() and HCL diverge | Including root no longer ending in /warehouse | ✓ |

**User's choice:** Exact three trailing-slash prefixes; prod module only; fail if join() and HCL diverge. Join() fixture construction left as You decide → real StorageLocation on a `/warehouse` root.

---

## Claude's Discretion

- Identity-refresh Terraform rule `id`
- Pytest filename
- HCL parse technique
- `-target` CLI details
- StorageLocation constructor in the test
- Prefix `warehouse/identity_refresh/` (user picked You decide)
- Real StorageLocation join() fixture (user picked You decide)

## Deferred Ideas

None — discussion stayed within phase scope.
