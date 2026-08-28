# Decide a Single Prod Workload-to-Profile Contract

Type: grilling
Status: resolved
Blocked by: 03, 05

## Question

How should canonical workload classes select warehouse `small`, `medium`, or
`large`, and MDM `mdm-small`, `mdm-medium`, or `mdm-large` through one durable
contract? Represent bounded MDM, ordinary full MDM,
residual-holds/security work, BatchSilver, gold, daily incremental, bootstrap,
and validation-only commands without duplicating the selection decision across
shell functions and state-machine generators. Preserve the sizing safety bands
and documented OOM floors decided earlier.

## Answer

Adopt one versioned, fail-closed **Workload Profile Contract** at the
repository-relative path `infra/config/aws-workload-profiles.json`. It is the
only repository authority for production Workload Class sizing. A workflow
builder names a stable Workload Class for each ECS Task state; it never selects
a profile, task family, revision, or ARN directly.

The decision is supported by the
[GoF architecture review](../research/workload-profile-architecture-gof-review-2026-08-09.md):
the current implementation has three profile-dispatch mechanisms, eight copies
of ECS task-state construction, dead selector cases, and repeated production
OOM-driven sizing edits. A data-backed Strategy registry is warranted; a broad
object-oriented rewrite is not.

### Contract structure and resolution

- `schema_version` changes only when the document structure changes.
- `contract_revision` changes on every tier-resource, workload binding, safety
  floor, risk, or evidence-metadata change.
- One shared `tiers` table defines `small` as `512/1024`, `medium` as
  `1024/4096`, and `large` as `2048/8192` CPU/memory. Warehouse and MDM do
  not redefine tier resources.
- Every `workload_classes` entry records `runtime`, `operational_tier`,
  `safety_floor`, `risk_class`, `representative_envelope_ref`, evidence and
  decision references, and rationale.
- `runtime` is `warehouse` or `mdm` and controls image, task family,
  dependency surface, roles, logs, and runtime settings. `tier` controls only
  CPU/memory.
- A single resolver combines the workload binding with the candidate
  deployment's runtime task registry. Exact task-definition ARNs, revisions,
  and image digests exist only in the generated **Resolved Profile Manifest**,
  never in the source contract.
- Source configuration never contains usernames, home-directory paths, account
  IDs, regions, secret identifiers, environment-specific resource names, or
  mutable image references. Repository paths are relative; environment
  identities come from explicit operator configuration or existing
  deployment-time discovery and are recorded only in generated manifests and
  evidence.
- Multi-stage workflows such as `bootstrap` and `daily_incremental` bind each
  ECS state independently. Workflow name, state name, and CLI command remain
  useful metadata but are not sizing authorities.

### Initial workload-class matrix

| Workload Class | Runtime | Operational Tier | Safety Floor | Risk |
| --- | --- | --- | --- | --- |
| `warehouse.index_utility` | warehouse | small | small | normal |
| `warehouse.seed_parse` | warehouse | medium | medium | normal |
| `warehouse.full_canonical_seed` | warehouse | large | large | high |
| `warehouse.batch_silver_shard` | warehouse | medium | medium | normal |
| `warehouse.gold_standalone` | warehouse | large | medium | normal |
| `warehouse.combined_full_pipeline` | warehouse | large | large | high |
| `mdm.control_validation` | mdm | small | small | normal |
| `mdm.bounded` | mdm | medium | medium | normal |
| `mdm.full` | mdm | medium | medium | high |
| `mdm.residual_security` | mdm | large | medium | high |

This is the initial vocabulary, not permission to collapse distinct stages.
**Decide the Machine Profile for Every Workflow Stage** may split a class when
record-funnel and input-envelope evidence demonstrates different execution or
risk behavior.

**Decide Warehouse Versus MDM Profile Families** narrows
`warehouse.seed_parse` to bounded seed and parsing utilities that do not
hydrate the full canonical store. Current production evidence showed the
full-canonical operation exhausting the 4-GiB configuration, so
`warehouse.full_canonical_seed` is a separate high-risk class with `large` as
both Operational Profile and Sizing Safety Floor. A dormant medium definition
without production execution evidence cannot authorize a lower binding.

### Overrides, canaries, and governance

- Workflow input, environment variables, generator parameters, command aliases,
  and shell case statements cannot override the base contract.
- A **Candidate Profile Overlay** is explicit, temporary, canary-only, and
  changes one Workload Class tier without modifying the base contract.
- A production **Emergency Sizing Override** may only upsize, requires operator
  attestation and rationale, expires within 24 hours, appears in the Resolved
  Profile Manifest, and raises drift visibility. It cannot approve a downsize.
- Any downsize requires a valid contract revision and the accepted Sizing
  Canary cohort from **Decide ECS Sizing Canary, Rollback, and Drift Gates**.
- Profile-only changes are reviewed separately from workflow-structure changes.
  Evidence references and normalized definition diffs accompany every change;
  accepted canary execution identities accompany every downsize.

### Fail-closed validation and migration

Before any AWS mutation, validate the complete logical contract, resolve every
ECS Task state in all generated ASL, and validate the complete deployment set.
Fail on an unknown or unmapped state, unknown runtime/tier, a tier below its
safety floor, direct task-ARN selection outside the resolver, conflicting
aliases, missing evidence metadata, schema/revision/hash mismatch, or
environment-specific identity embedded in source configuration. Never
partially deploy a set that only validates workflow by workflow.

Migration is incremental in development but atomic in production authority:

1. Generate all 26 current and candidate definitions with fixed synthetic test
   ARNs and require normalized state-graph and task-assignment parity.
2. Internally migrate one builder at a time while the characterization suite
   stays green.
3. In one production cutover, route every ECS Task state through the resolver
   and remove `workflow_profile()`,
   `task_definition_for_mdm_workflow()`, direct profile-ARN choices, special
   test allowlists, dead cases, and generator profile arguments.
4. Emit the contract schema version, contract revision, content hash, complete
   state-to-workload-to-task resolution, exact image/task identities, and any
   emergency override in the Resolved Profile Manifest.

No deployed revision may contain dual sizing authorities. The implementation
handoff must also add the staged Deployment Plan and exact before-state journal
recommended by the architecture review so validation, cutover, and
Configuration Rollback operate on the full 26-workflow set.
