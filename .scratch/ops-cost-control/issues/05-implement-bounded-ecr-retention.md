# Implement Bounded ECR Retention with Rollback Safety

Type: task
Status: resolved
Blocked by: 04

## Question

How should deployment, cleanup, and ECR lifecycle configuration implement the
confirmed Rollback Image Set: current production, two verified successful
rollback images, and every digest referenced by a running ECS task?

Add explicit protected tags or registry state, retire stale task definitions as
required by the researched contract, preview lifecycle/cleanup candidates, and
refuse deletion when ECS or rollback reconciliation is incomplete. Cover the
warehouse and MDM repositories consistently without touching dependency images
that follow a different retention contract.

## Answer

Implemented 2026-08-11. Before implementing, consulted `advisor` given the
scale mismatch between the researched contract (multi-hour build) and current
actual cost exposure (~20 tagged images × ~300MB ≈ 6GB, well under $1/month,
and the existing script already never deletes a tagged image). Put the
scoping choice to the user directly rather than deciding it unilaterally
(three options: full fail-closed contract / detect-and-report only / close as
not-worth-it) — user chose the **full fail-closed contract**.

**Premise correction carried forward from [ticket 04](04-confirm-safe-ecr-rollback-protection-mechanism.md):**
the researched contract assumed the pre-consolidation two-repository split.
This platform now has one shared repo (`edgartools-<env>-images`) with role
encoded in the tag prefix. Adapted every part of the contract accordingly —
mirror tags are role-scoped (`retain-warehouse-current` /
`retain-mdm-current` / etc., not per-repository), and "cover the warehouse
and MDM repositories" became "cover both roles within the one repository."

**Architecture — three modules, pure-logic core + thin AWS shell (mirrors
this repo's own `release_evidence.py`/`release_evidence_cli.py` split):**

1. **`edgar_warehouse/application/ecr_rollback_registry.py`** (pure, no I/O,
   no clock) — the durable deployment-cohort registry schema from the
   research doc, adapted to the single-repo/tag-prefix world.
   `empty_registry()`, `advance_registry()` (promotes a new verified cohort
   to `current`, shifts `current`→`rollback-1`→`rollback-2`, drops anything
   older — enforces cohorts advance in **verification order**, not push
   order, rejecting a non-monotonic `verified_at`), `validate_registry()`,
   `protected_digests_from_registry()`, `mirror_tag_for()`/
   `expected_mirror_tags()`. 19 tests
   (`tests/application/test_ecr_rollback_registry.py`).
2. **`edgar_warehouse/application/ecr_rollback_audit.py`** (pure) —
   `compute_plan()` takes already-fetched AWS facts (ECR image inventory,
   resolved mirror-tag digests, every `ACTIVE` task-definition revision
   under the family prefix — not just latest per family, closing the exact
   gap `advisor` flagged in `cleanup-ecr-images.sh`'s existing "latest
   revision only" scan — Step Functions `TaskDefinition` references walked
   recursively through nested Map/Parallel branches, live ECS tasks, ECS
   services) and produces a canonical, SHA-256-hashed plan: per-image
   disposition (`protected`/`candidate`/`lifecycle_managed`/
   `deps_out_of_scope`) with full provenance, stale task-definition ARNs,
   candidate digests, and a `fail_closed_reasons` list that — if non-empty —
   forces `candidate_digests` to empty regardless of what individual images
   looked like. Every fail-closed condition from the research doc is a real
   check: identity/region mismatch, malformed/insufficient-history registry,
   mirror-tag/registry disagreement, any ECS service present (this platform
   has none — Step Functions `runTask` only — so any is an anomaly, not a
   silently-handled case), unresolvable live-task digest, tag-pinned (not
   digest-pinned) task-definition image reference, and images pushed after
   the audit started. A moving pointer tag (`warehouse-prod`/`mdm-prod`) and
   an unrecognized tag shape both retain by default rather than being
   guessed at. 22 tests (`tests/application/test_ecr_rollback_audit.py`) —
   these caught one real bug during development (see below).
3. **`edgar_warehouse/scripts/ecr_rollback_cli.py`** (thin, all AWS I/O and
   the wall clock) — `plan` (dry-run, prints/writes the hashed plan),
   `apply` (re-gathers every fact from scratch — never trusts an
   in-process `plan` object — recomputes, refuses unless the hash matches
   `--plan-hash` exactly and the plan is appliable, acquires an S3
   conditional-create lock reusing `object_storage.py`'s existing
   `write_immutable_bytes` primitive, deregisters stale task definitions,
   confirms `INACTIVE`, then `BatchDeleteImage`s exactly the candidate
   digests in batches of ≤100, aborting remaining batches on any partial
   failure), `record-cohort` (advances the registry after a **manually
   supplied** verification-evidence reference), `release-lock` (manual
   unblock for a crashed apply). Registry reads/writes reuse this repo's
   existing ETag-guarded staged/promote pattern
   (`read_object_version`/`write_staged_bytes`/`promote_staged` — the same
   mechanism silver publication uses) instead of inventing new optimistic
   concurrency. 6 tests (`tests/unit/test_ecr_rollback_cli.py`) covering the
   recursive ASL TaskDefinition walker and argument-parsing wiring — the
   AWS-calling functions themselves are intentionally thin and untested
   here, matching this repo's own `release_evidence_cli.py` convention.

**Real bug caught by the audit test suite, not just designed around:** the
first `compute_plan()` draft added every scanned task definition's own ARN
to the "referenced" set merely because it existed in the input list —
meaning every active task definition trivially "referenced itself" and
staleness detection could never fire. `test_stale_task_definitions_are_flagged_when_not_referenced_by_anything_live`
failed against that draft, exposing it. Fixed by seeding the referenced set
from the **registry's own recorded task-definition ARNs** (the actual
rollback anchors) plus Step Functions/live-task references only — never
from the task-definition list being audited for staleness.

**Deliberately not wired into `deploy-aws-application.sh`'s automatic
per-deploy cleanup call** (`infra/scripts/deploy-aws-application.sh:874`,
`cleanup-ecr-images.sh --apply`, non-fatal on failure) — confirmed by
reading `cleanup-ecr-images.sh` that this existing call only ever deletes
**untagged** images (`keep = bool(tags)`, unconditionally), so it can never
touch a tagged rollback anchor and the non-fatal swallow-failure behavior is
safe as-is for that narrow scope. The new tagged-image deletion capability
is a **separate, explicitly-invoked** tool — this was one of `advisor`'s
named traps ("adding tagged deletion under that call path silently makes
every deploy destructive") and the design avoids it entirely by construction
rather than by adding a guard.

**Deliberately not auto-recording a cohort after every deploy** — the
registry's `advance_registry()` requires `verification_evidence`, and a
deploy has no verification evidence at the moment it completes (that's a
separate, later step). `record-cohort` stays a manual/operator action.

**Lifecycle policy:** no change needed — already confirmed correct.
`aws_ecr_lifecycle_policy.images` (`infra/terraform/modules/warehouse_runtime/main.tf`)
already scopes to `tagStatus: untagged` only, already covered by
`tests/architecture/test_ecr_image_retention.py`'s existing regression
guard. The single-repo consolidation already collapsed what would have been
4 separate per-repository lifecycle policies (2 final + 2 deps, each
needing "explicit ownership... consistent with their separate contracts"
per the research doc) into this one correct policy.

**Not yet done, explicitly deferred:**
- No live registry has been bootstrapped in S3 yet (`empty_registry()` has
  never been called against real prod state) — `plan` against an empty/
  under-3-cohort registry will correctly report `insufficient_history` and
  retain everything, which is the intended fail-closed default, not a bug.
  Bootstrapping the first 1-3 cohorts from the current live deployment state
  is an operator action for whoever runs this tool for the first time.
- Never run live against AWS — no `plan`/`apply` invocation this session,
  by design (this ticket's job was to build the fail-closed mechanism, not
  to perform a live cleanup). First live `plan` run (dry-run, non-destructive)
  is a natural verification step for [ticket 06](06-verify-observability-and-image-cost-controls.md).
- Deep integration with the existing `release_evidence.py` gate/attestation
  system was out of scope — `verification_evidence` accepts an opaque
  string reference (e.g. a path into that system) rather than being
  cross-validated against it. That system is a much heavier, differently-
  scoped "release readiness" process; forcing ECR rollback tracking into it
  would have been overreach beyond this ticket.
- The lock is a simple S3 conditional-create with no TTL/auto-expiry — a
  crashed `apply` leaves a lock that needs `release-lock` run manually.
  Judged acceptable for an infrequent, operator-invoked, non-automated tool.

Full repo suite green: 2038 passed, 4 skipped (47 new tests added). Not yet
committed as of this entry.
