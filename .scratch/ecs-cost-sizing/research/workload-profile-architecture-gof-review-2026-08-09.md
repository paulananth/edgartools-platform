# Workload Profile and Step Functions Architecture: GoF Review

Reviewed 2026-08-09 at `d1ca9ca7746244316884fc403fb832538bd7b5ee`.
Scope is the AWS application deployment boundary: ECS task-profile authority,
Amazon States Language generation, deployment transactionality, rollback, and
drift. Parser, Snowflake, dbt, dashboard, and passive Terraform architecture are
outside this review.

Portability is a hard boundary: source artifacts use repository-relative paths
and do not embed usernames, home directories, account IDs, regions, ARNs, image
digests, secret identifiers, or environment-specific resource names. Exact
deployment identities belong only in generated manifests and evidence.

**Overall:** The AWS deployment architecture is operationally coherent, but
three seams now cost more than they would cost to extract: workload-profile
selection, ECS task-state construction, and deployment rollback. The evidence
supports focused, data-oriented refactoring; it does not support rewriting the
4,899-line operator script into an object hierarchy.

The evidence bar is repeated change, not appearance. Profile and memory wiring
changed repeatedly in response to production behavior, including commits
`eaeee4b4`, `37c3171f`, `9bac02d8`, `4760be81`, `37918c91`, `8d6d3212`, and
`995856c7`. The characterization baseline is green: 101 tests passed across
gold-affecting sizing, residual-holds, daily identity refresh, and load-history
architecture tests.

---

## 1. Workload selection is a repeated Strategy decision with three authorities

`infra/scripts/deploy-aws-application.sh:1193-1236`,
`infra/scripts/deploy-aws-application.sh:2814-2907`,
`tests/architecture/test_gold_affecting_commands_task_sizing.py:7-38`,
`tests/architecture/test_gold_affecting_commands_task_sizing.py:62-95`,
`tests/architecture/test_gold_affecting_commands_task_sizing.py:120-218`

Warehouse workflow names select profiles through `workflow_profile()`, MDM
workflow names select task ARNs through `task_definition_for_mdm_workflow()`,
and multi-stage generators receive concrete profile ARNs positionally. The
script itself records that the `bootstrap` and `daily_incremental` cases in the
first selector are dead while their real states select `large` directly. The
architecture test must execute shell fragments, generate ASL with fake ARNs,
and maintain a special-case allowlist to reconstruct the effective decision.

**Cost today:** A profile change can require coordinated edits to selector
cases, generator arguments, direct ARN choices, explanatory comments, and
tests that emulate each dispatch route. A missed route has already produced
repeated OOM remediation rather than a compile- or validation-time failure.

**Fix:** **Strategy**, implemented with the language's data facilities rather
than strategy classes. Make `infra/config/aws-workload-profiles.json` the
versioned registry of Workload Class to `{runtime, operational_tier,
safety_floor, risk_class, evidence}`. A single resolver converts that binding
to an exact deployment task ARN; workflow builders name Workload Classes and
never choose ARNs.

**Cost of the fix:** The registry and resolver add an indirection that makes
plain grep less direct. Builders become clients of a stable Workload Class
interface, so careless naming can leak implementation concerns outward. The
schema becomes a governed public contract and must be migrated deliberately.

**Green steps:**

1. Preserve normalized generated-ASL and task-assignment characterization for
   all 26 production definitions.
2. Add the schema, validator, and resolver unused; validate the accepted
   initial matrix against fixed test ARNs.
3. Migrate one generator at a time internally and require normalized old/new
   graph and profile-assignment parity after each commit.
4. Make one production cutover that switches every ECS task state to the new
   authority and removes the two shell selectors, direct ARN choices, dead
   cases, and test allowlists. Incremental development is safe; dual production
   authority is not.
5. Fail before any AWS mutation when a workload, runtime, tier, floor,
   evidence identity, contract revision, or contract hash is invalid.

---

## 2. ECS Task-state construction is copied instead of adapted once

`infra/scripts/deploy-aws-application.sh:1887-1905`,
`infra/scripts/deploy-aws-application.sh:2848-2866`,
`infra/scripts/deploy-aws-application.sh:4481-4503`,
`infra/scripts/deploy-aws-application.sh:4531-4554`,
`infra/scripts/deploy-aws-application.sh:4613-4636`

The script contains eight embedded `ecs_state` functions. They repeat the AWS
integration, cluster/network configuration, container override, retry shape,
and transition mechanics, while differing in details such as two versus three
retry attempts. Concrete task-definition ARNs are threaded into each copy,
coupling AWS representation to workload selection.

**Cost today:** Every cross-cutting requirement—profile resolution, task-bound
telemetry, tags, retry classification, canary metadata, or drift identity—must
be implemented and reviewed across eight construction sites. Divergence can be
accidental, and current source-substring tests protect text shape more than the
one intended task-state contract.

**Fix:** **Factory Method plus Adapter**, expressed as a small pure Python
factory rather than a class hierarchy. One AWS task-state adapter should accept
the Workload Class, command expression, transition, and an explicit retry
policy; it should obtain the concrete task ARN only through the profile
resolver. Keep each workflow's graph explicit.

**Cost of the fix:** This adds one debugging hop and can become a god helper if
workflow-specific graph logic is allowed into it. Normalizing retries can also
change behavior accidentally, so existing differences must remain explicit
policy inputs until a separate decision changes them.

**Green steps:**

1. Snapshot normalized task-state JSON for every current builder, including
   Catch, Retry, Map nesting, and transition behavior.
2. Add one pure task-state factory with the current AWS representation and no
   behavior change.
3. Migrate one builder and compare generated JSON structurally, then migrate
   the remaining builders one at a time.
4. Delete the eight local copies only after full generated-definition parity.
5. Add profile identity, telemetry, and drift fields at the single adapter seam
   in later tickets, without moving workflow topology into the factory.

---

## 3. Sequential live updates need an explicit deployment plan and before-state

`infra/scripts/deploy-aws-application.sh:4333-4361`,
`infra/scripts/deploy-aws-application.sh:4378-4407`,
`infra/scripts/deploy-aws-application.sh:4786-4897`,
`.scratch/ecs-cost-sizing/research/task-definition-reference-reconciliation-2026-08-09.md:65-89`,
`.scratch/ecs-cost-sizing/research/task-definition-reference-reconciliation-2026-08-09.md:140-150`

The deploy script registers a new task-definition cohort, generates and updates
state machines sequentially, and writes its summary only after the updates. An
interruption can therefore leave a mixed live cohort with a stale or absent
manifest. This directly conflicts with the accepted requirement to restore an
exact pre-change configuration within 15 minutes.

**Cost today:** Operators cannot prove the intended 26-workflow update set
before mutation, identify exactly how far a failed deployment progressed from
the final manifest, or deterministically restore every pre-change definition
without separately reconstructing state.

**Fix:** **Command plus Memento**, implemented as immutable deployment-operation
records and exact before-state snapshots rather than one class per AWS call.
Build and validate a complete Deployment Plan first; snapshot every affected
definition and hash; journal each applied operation; post-audit the full set;
and use the snapshots as the Configuration Rollback input on failure.

**Cost of the fix:** This is the highest-cost recommendation. AWS updates are
still not atomic, rollback itself can fail or race another operator, and exact
snapshots require retention and access controls. Command-style records add
more artifacts and Memento storage even though the live state may be modest.

**Green steps:**

1. Extract a read-only Deployment Plan that lists all registrations,
   definitions, expected hashes, and update operations without calling AWS.
2. Capture and validate exact before-state definitions and contract/profile
   identities; abort on incomplete inventory or running-work conflicts.
3. Add a dry-run and failure-injection test around one journaled update and its
   exact restoration.
4. Extend apply/rollback to the complete set, then require recursive post-audit
   before writing the Resolved Profile Manifest or declaring success.
5. Keep task-definition retirement in a later, separately reviewed window.

---

## Noted, not recommending

- **Bridge classes for warehouse/MDM x small/medium/large:** Runtime Variant
  and Resource Tier are independent dimensions, but the matrix is small and
  closed. Data composition captures the useful separation without Bridge's
  hierarchy and up-front complexity.
- **Template Method for complete workflows:** Similar task states do not make
  the graphs interchangeable. Their Catch, Retry, Map, sequencing, and output
  gates are meaningful and should remain visible.
- **State, Visitor, Composite, or a Mediator rewrite of ASL:** Amazon States
  Language already represents workflow state and composition. Another object
  model would obscure the deployable JSON.
- **Rewrite the whole shell composition root:** Length alone is not a smell.
  Keep the linear operator flow and extract only the three volatile seams
  above.

## Wayfinder conclusion

The accepted **Decide a Single Prod Workload-to-Profile Contract** direction is
the right first refactor. It addresses the demonstrated Strategy duplication
and creates the seam needed by later concurrency, telemetry, stage-sizing, and
drift decisions. The task-state factory and deployment plan should be included
in the implementation handoff, but they do not justify expanding this planning
ticket into an architecture rewrite.
