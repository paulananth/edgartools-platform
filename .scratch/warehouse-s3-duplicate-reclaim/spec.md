# Spec: Warehouse S3 Duplicate-Storage Reclaim

**Status:** ready-for-agent
**Type:** spec
**Label:** ready-for-agent
**Date:** 2026-08-21
**Repo:** edgartools-platform
**Map:** [Warehouse S3 Duplicate-Storage Reclaim](map.md)

## Problem Statement

From the operator's perspective: the prod warehouse bucket is billing hundreds of
gigabytes of duplicate DuckDB and parquet copies that are not Canonical Silver.
A lifecycle filter on the relative path `silverstage/` matched nothing (Joined Live
Keys are `warehouse/silverstage/...`), so Staged Warehouse Objects piled up until a
one-shot VersionId Reclaim removed 1.71 TiB. That leak is patched live but not
sealed in Terraform, identity-refresh unique keys still have no standing expire, and
leftover billed bytes remain: ~315 GiB noncurrent shards, ~1.5 GiB noncurrent
Canonical Silver file, ~19 GiB Identity Refresh Run snapshots, ~4 GiB gold `run_id=`
copies. A later Terraform apply from the old prefix would reopen the leak. Recursive
`s3 rm` would not free the bytes.

## Solution

Seal standing lifecycle on Joined Live Keys (staging 3-day current+noncurrent,
identity-refresh 7-day current+noncurrent, Canonical Silver noncurrent-only 7-day
with no current expiration). Prove the prefixes with an architecture test against
production `join()`. Then give operators a sibling VersionId Reclaim tool (ADR 0004
contract, not the staging script) that dry-runs a reviewed TSV, deletes only listed
VersionIds after a distinct confirm flag, never touches current Canonical Silver,
skips in-flight Identity Refresh Run directories younger than 24 hours, and keeps
the union of per-table newest gold `run_id=` prefixes. Report bytes reclaimed.
Do not change CloudWatch retention (seven-day Operational Forensics Window stands).
Do not delete current bronze SEC objects.

## User Stories

1. As a platform operator, I want staging objects to expire under the Joined Live Key prefix, so that Staged Warehouse Objects cannot accumulate forever after a failed promotion.
2. As a platform operator, I want a Terraform apply that cannot restore the relative prefix `silverstage/`, so that the 1.71 TiB leak cannot recur on the next infrastructure apply.
3. As a platform operator, I want to apply only the warehouse lifecycle resource after a reviewed plan, so that unrelated prod-root drift does not go live with leak-seal.
4. As a platform operator, I want that plan/apply to run as the AWS admin prod profile, so that passive infrastructure stays off the deployer role.
5. As a platform operator, I want the apply aborted if the plan shows extra warehouse-bucket changes, so that leak-seal cannot ride along other storage drift.
6. As a platform operator, I want the prefix regression green before apply, so that applied HCL cannot be the silent no-op prefix.
7. As a platform operator, I want Identity Refresh Run snapshots to expire after 7 days current and noncurrent, so that unique run keys (which never become noncurrent by overwrite) do not live forever.
8. As a platform operator, I want that 7-day identity rule in the same lifecycle document as the staging prefix, so that a split apply cannot revert the other rule.
9. As a platform operator, I want identity-refresh leases outside that prefix left alone, so that Identity Refresh Slot bookkeeping is not expired with snapshots.
10. As a platform operator, I want the standing identity expire to be a hard 7 days, so that lifecycle does not try to detect RUNNING maps.
11. As a platform operator, I want Canonical Silver current objects never expired by lifecycle, so that the live typed store cannot vanish on a quiet day.
12. As a platform operator, I want Canonical Silver *noncurrent* versions expired after 7 days, so that shard overwrite storms stop billing forever.
13. As a platform operator, I want lifecycle prefixes to use trailing slashes, so that `warehouse/silver` cannot match `warehouse/silverstage`.
14. As a developer, I want an architecture test that parses warehouse lifecycle HCL and calls production `join()`, so that a prefix/root contract change fails CI without AWS credentials.
15. As a developer, I want that test to fail if the filter is `silverstage/`, so that a revert of the 1.71 TiB incident cannot merge.
16. As a developer, I want the same test to lock staging, identity-refresh, and Canonical Silver prefixes, so that one test owns the three-string contract.
17. As a developer, I want `join()` asserted on a storage root that ends in `/warehouse`, so that hand-concatenated keys cannot fake the live contract.
18. As a developer, I want the test to fail if `join("silverstage", ...)` does not start with the Terraform staging prefix, so that a storage-root rename cannot ship without a matching HCL change.
19. As a platform operator, I want only the prod storage-buckets lifecycle edited for this work, so that decommissioned destroyable/dev modules are not churned unless they still carry the old prefix.
20. As a platform operator, I want a dry-run VersionId Reclaim that writes a reviewed TSV of key, version id, last modified, size, and is-latest, so that I can inspect candidates before any delete.
21. As a platform operator, I want `--apply` to require a distinct confirm flag, so that a typo cannot delete.
22. As a platform operator, I want deletes in batches of at most 100 VersionIds, so that a partial failure is bounded.
23. As a platform operator, I want a post-list proof that selected VersionIds are gone, so that I do not trust delete-markers as success.
24. As a platform operator, I want count and GiB reclaimed per prefix, so that I can see whether the bill should move.
25. As a platform operator, I want a second empty apply to succeed, so that the tool is idempotent.
26. As a platform operator, I want current Canonical Silver keys on a deny-list, so that shard reclaim cannot use `IsLatest=true`.
27. As a platform operator, I want noncurrent shard versions deleted by VersionId, so that the measured 315 GiB is actually freed.
28. As a platform operator, I want the one noncurrent Canonical Silver duckdb version eligible for reclaim, so that 1.48 GiB of superseded canonical is not billed, while the current object stays.
29. As a platform operator, I want historical Identity Refresh Run directories reclaimed, so that 19 GiB of unique current keys go away without waiting for the new 7-day rule to age them.
30. As a platform operator, I want Identity Refresh Run directories whose newest object is younger than 24 hours skipped on the one-shot, so that an in-flight reducer is not deleted mid-run.
31. As a platform operator, I want gold parquet `run_id=` copies reclaimed except the keep-set, so that seven copies of each table are not billed.
32. As a platform operator, I want the gold keep-set to be the union of per-table newest `LastModified` `run_id=` prefixes, so that UUID sort cannot keep a stale run and a partial newer run cannot orphan another table's latest complete file.
33. As a platform operator, I want gold noncurrent versions of deleted historical `run_id=` keys reclaimed too, so that 0.89 GiB of leftover versions is not left billed.
34. As a platform operator, I want staging VersionId Reclaim out of this work (already done), so that the tool does not re-scan an empty prefix unless proving emptiness.
35. As a platform operator, I want incomplete multipart uploads with zero parts ignored as zero-bill, so that I do not confuse MPU abort with VersionId Reclaim.
36. As a platform operator, I want bronze current SEC objects left untouched, so that immutable capture is not "cleaned up."
37. As a platform operator, I want CloudWatch log retention left at seven days, so that the Operational Forensics Window is not shortened under a storage-reclaim spec.
38. As a reviewer, I want no MDM WIP mixed into this change, so that credential-isolation work does not land in the lifecycle PR.
39. As a future operator, I want ADR 0004 to remain staging-only, so that the `IsLatest=true` staging selector cannot be copy-pasted onto shards.
40. As a future operator, I want a sibling reclaim contract for warehouse duplicates, so that deny-list and keep-set are explicit.
41. As a CI system, I want architecture tests to run with `uv` and no AWS credentials, so that prefix regressions fail on every PR.
42. As a platform operator, I want live lifecycle readback after apply (staging prefix, identity 7/7, silver noncurrent-only 7, no current expire on silver), so that Terraform and the bucket agree.
43. As a platform operator, I want reclaim evidence under a dedicated release-evidence prefix, so that dry-run TSVs are auditable without living only on a laptop.
44. As a developer, I want fixture-based reclaim tests (synthetic version listings), so that deny-list and keep-set are proven without prod S3.
45. As a platform operator, I want the tool to refuse a manifest that includes a deny-listed current Canonical Silver VersionId, so that a hand-edited TSV cannot delete the live store.

## Implementation Decisions

- Two control planes, one each: Terraform owns *standing* lifecycle on the existing warehouse lifecycle resource (apply replaces the whole document). An operator tool owns *existing* billed leftovers via VersionId Reclaim. Terraform never lists or deletes object versions.
- Lifecycle prefixes (trailing slashes required): `warehouse/silverstage/` (current+noncurrent 3 days, already live), `warehouse/identity_refresh/` (current+noncurrent 7/7, new), `warehouse/silver/` (noncurrent 7 days, no current expiration). Identity-refresh leases stay under `warehouse/reference/identity_refresh_lease/` and are not in the 7-day rule.
- Staging and identity rules ship in the same targeted apply of that one lifecycle resource. Profile: AWS admin prod. Abort if the plan mutates other warehouse-bucket resources. Architecture tests must pass first.
- Edit only the prod storage-buckets lifecycle unless a second module still contains the no-op `silverstage/` prefix.
- Architecture test: read lifecycle HCL as text (same style as ECR lifecycle and CloudWatch retention architecture tests) *and* call production object-storage `join()` on a root ending in `/warehouse`. Negative case: `silverstage/` is not a prefix of joined staging keys. Fail if join output and HCL staging prefix diverge.
- Reclaim tool is a **sibling** of the ADR 0004 staging cleanup, not an extension of that script. Staging cleanup keeps `IsLatest=true` under the ephemeral prefix. Reclaim selectors: (1) `IsLatest=false` on Canonical Silver shard keys and the single noncurrent canonical duckdb version; (2) current unique keys under `warehouse/identity_refresh/` whose run directory newest object is older than 24 hours; (3) gold `run_id=` objects not in the keep-set, including their noncurrent versions.
- Deny-list: current (`IsLatest=true`) Canonical Silver duckdb and shard-0..3. Any apply manifest containing those VersionIds is a hard fail.
- Gold keep-set: for each table prefix, take the `run_id=` with the newest current-object `LastModified`; union those `run_id=` values across tables; keep every current object whose `run_id=` is in that union. Do not sort UUIDs. This is the synthesis of GSD GOLD-01 and the incomplete-run warning; wayfinder grilling on "complete run" was still open and this is the locked default.
- One-shot identity skip: 24-hour newest-object age on the run directory. Standing 7-day lifecycle does not skip RUNNING maps (already locked).
- Default is dry-run. Apply requires a distinct confirm flag and a reviewed manifest. Batches of 100. Post-list must show listed VersionIds absent. Empty candidate set is success. Report count + GiB per prefix.
- Evidence lands under warehouse release-evidence for this reclaim, analogous to staging-cleanup evidence, not only a local temp dir.
- CloudWatch: do not change retention in this spec. The seven-day Operational Forensics Window from the observability cost map stands. GSD's 3-day story is dropped here.
- Bronze: no delete of current SEC objects. Noncurrent bronze (~0.36 GiB) is not in this spec.
- Do not mix MDM credential-isolation working-tree files into this implementation.

## Testing Decisions

- Good tests assert observable contracts: HCL prefix strings, `join()` key prefixes, dry-run TSV columns, deny-list refusal, keep-set membership, empty-run success. They do not assert internal helper names or live AWS.
- Architecture tests (no credentials): warehouse lifecycle prefixes vs production `join()`. Prior art: ECR image lifecycle architecture test; CloudWatch seven-day retention architecture test.
- Reclaim unit/contract tests: feed a synthetic version listing (in-memory or fixture JSON) and assert the TSV keep/drop set. Must cover: noncurrent shard kept vs current shard denied; identity run younger than 24h skipped; gold keep-set union; manifest that includes deny-listed VersionId rejected; second run on empty set succeeds.
- Do not require a prod apply in CI. Operator apply remains a human-gated step after tests pass.
- Do not use integration tests that call `delete-objects` against prod.

## Out of Scope

- Re-litigating GSD Leak-seal decisions D-01–D-17 except as restated above.
- Changing CloudWatch log retention (including GSD CW-01 three-day).
- Deleting current Canonical Silver objects.
- Deleting current bronze SEC filing objects; bronze VersionId reclaim of the 0.36 GiB noncurrent pile.
- ECR rollback tags and the empty dev images repository.
- S3 request-churn (listing/HEAD volume), as opposed to billed duplicate bytes.
- Executing Terraform apply or VersionId delete from the wayfinder map itself (implementation after this spec).
- Shortening the 7-day Canonical Silver *noncurrent* standing rule (one-shot reclaim of already-superseded shard versions is in scope; changing the standing window is not).
- Recurring lifecycle on gold `run_id=` prefixes (cannot express keep-latest).
- New buckets, new warehouse roots, ECS reclaim tasks, boto3 CLIs, Glacier.

## Further Notes

- Live inventory 2026-08-21 (read-only): see [04-live-warehouse-leftover-inventory.md](research/04-live-warehouse-leftover-inventory.md) and [05-bronze-duplicate-inventory.md](research/05-bronze-duplicate-inventory.md).
- Wayfinder [Keep, drop, or rewrite the three-day CloudWatch retention requirement?](issues/01-decide-cloudwatch-retention-vs-seven-day-floor.md) is resolved: drop CW-01, keep seven days. [How do we detect an in-flight Identity Refresh Run for one-shot skip?](issues/03-decide-in-flight-identity-refresh-skip.md) is resolved: 24-hour newest LastModified on the run directory. [Does ADR 0004’s staging cleanup contract extend, or do we need a sibling reclaim contract?](issues/06-decide-reclaim-contract-beyond-staging.md) is resolved: ADR 0004 stays staging-only; sibling VersionId Reclaim for warehouse duplicates. [Is the 7-day Canonical Silver noncurrent rule enough after the one-shot?](issues/11-keep-seven-day-silver-noncurrent-window.md) is resolved: keep 7-day noncurrent-only; do not shorten.
- `/to-tickets` already sliced leak-seal vs reclaim as (1) architecture test + lifecycle HCL, (2) targeted apply runbook, (3) reclaim tool + fixtures, (4) operator dry-run then apply against shards / identity / gold. One-shot evidence lives under the warehouse release-evidence prefix.
- Vocabulary: Canonical Silver, Joined Live Key, VersionId Reclaim, Staged Warehouse Object, Identity Refresh Run — root `CONTEXT.md`.
