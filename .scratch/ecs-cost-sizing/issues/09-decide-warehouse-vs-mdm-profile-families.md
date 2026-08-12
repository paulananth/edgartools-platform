# Decide Warehouse Versus MDM Profile Families

Type: grilling
Status: resolved
Blocked by: 05, 06

## Question

Do production workloads need separate warehouse and MDM task-definition
families, or should both runtimes use one shared profile family with runtime-
specific image, command, and role data?

Evaluate the current evidence: warehouse and MDM use different immutable image
digests, dependency surfaces, commands, log-stream prefixes, and workload
failure modes, while their `small`/`medium`/`large` CPU-memory tiers currently
align. Decide whether to retain separate runtime families but standardize the
sizing-tier vocabulary, or collapse the families. The decision must preserve
image isolation, rollback clarity, IAM boundaries, workload-specific memory
floors, and an unambiguous Step Functions reference contract.

## Accepted operator direction

On 2026-08-09, the operator accepted these constraints pending completion of
the blocking utilization and canonical profile-contract decisions:

- Retain separate warehouse and MDM runtime images and task-definition
  families for dependency, deployment, observability, and rollback isolation.
- Standardize one `small` / `medium` / `large` resource-tier vocabulary and one
  workload-to-profile selection contract across both runtime variants.
- Retain `warehouse-large`; its full-universe gold workload has observed OOM
  failures below the current memory floor and near-saturation utilization.
- Treat `mdm-large` as a removal candidate. It may be retired only after a
  representative residual-holds/security canary on `mdm-medium` proves no OOM,
  retry, output/parity, or unacceptable end-to-end duration regression.

This direction is resolved below using the thresholds, evidence volume,
duration tolerance, and canonical selection mechanism established by the
blocking decisions.

## Answer

Retain two production **Runtime Variants**, `warehouse` and `mdm`, with
separate images, dependency surfaces, IAM roles, log identities, task-
definition families, and rollback identities. Standardize their CPU and memory
through one shared `small` / `medium` / `large` **Resource Tier** table. A
Workload Class selects the resolved pair only through the Workload Profile
Contract; neither a workflow name nor a runtime-wide default is a sizing
authority.

This preserves runtime isolation without duplicating the resource model. The
shared tier name means the same CPU and memory for both runtimes, while the
Runtime Variant continues to determine everything needed to execute the code
safely. Warehouse and MDM must not be collapsed into one task-definition
family merely because their current tier resources align.

### Production release identity

Warehouse and MDM images may be built and published independently, but every
production deployment records one exact **Release Runtime Cohort** containing
both immutable runtime identities. Changing either runtime creates a new
cohort and Resolved Profile Manifest revision and requires compatibility and
full-chain validation. Production generation and rollback must never assemble
a pair from mutable tags or independently selected latest revisions.

### Current workload consequences

- Retain `warehouse-large`. The full-canonical `seed-universe` operation is a
  distinct high-risk Workload Class, `warehouse.full_canonical_seed`, with
  `large` as both Operational Profile and Sizing Safety Floor after the live
  4-GiB configuration exhausted memory. Bounded seed or parsing utilities may
  remain `warehouse.seed_parse` on `medium`; they cannot be treated as evidence
  for the full-canonical class.
- The three active production workflows that execute the full-canonical seed
  stage now reference the warehouse large profile. A dormant batched workflow
  still referencing medium has no production execution evidence and is not a
  sizing counterexample.
- Ordinary and bounded MDM work remains on `mdm-medium`. Keep `mdm-large`
  operational for residual-holds/security work until three current-image,
  representative `mdm-medium` canaries process non-zero residual-security/13F
  data and pass the complete task-bound identity, output correctness, parity,
  completeness, recovery, idempotency, and zero workload-attributable failure
  or retry gates.
- Each MDM canary must keep memory peak below 85% and memory p95 below 75%,
  keep p95 end-to-end completion no more than 5% slower, and reduce cost per
  successful validated output by at least 10%. One OOM rejects the candidate.

After that MDM cohort passes, remove the normal `mdm-large` workload binding
and stop routine registration unless an exact large definition is referenced
by the current cohort, a protected rollback cohort, or an emergency override.
Protect the exact prior large configuration through the later of seven days
and three representative runs. The shared `large` tier and the ability to
register an MDM large definition remain available for rollback or an attested
emergency upsize; retirement does not make the tier impossible to restore.

### Registration and cleanup boundary

Register a runtime-tier task definition only when the current Workload Profile
Contract, an accepted canary overlay, a protected rollback cohort, or an
attested emergency override references it. Historical family existence is not
sizing authority. Revision cleanup remains a separate fail-closed operation
that must preserve every exact current, canary, rollback, and bake-window
reference.

The source contract remains portable: it contains no usernames, home paths,
account identities, regions, secret identifiers, environment-specific names,
task-definition ARNs, or mutable image references. Exact runtime and task
identities belong only in generated manifests and evidence.
