---
name: data-operations
description: Manages recurring loads from completed local deliveries, detects changed or renamed files, sizes work to available resources, and coordinates Bookkeeping, verification and Change Journal recovery. Use when operating daily loads, checking source readiness, managing a backlog, monitoring a run or maintaining its operational runbook.
---

# Data Operations

Operate existing sources repeatedly using their configured engines. Maintain the
source's operational runbook and report verified progress with counts and reasons.
This skill guides an invoked agent; it does not install a scheduler or stay running
between invocations. AWS acquisition supplies completed deliveries independently.

## Start with live state

Resolve the requested environment, source and retained delivery from existing
configuration and evidence. Reuse the current authorization for that scope.
Read the source's runbook and live Bookkeeping runs/leases before starting work;
another agent's in-flight work is a dependency, not a cleanup target.

Use [RUNBOOK.md](RUNBOOK.md) for delivery, file-change, capacity and recovery
decisions. Discover actual command capabilities with `edgar-warehouse doctor` and
CLI help. Report missing enforcement or unsupported stages as runtime gaps;
instructions cannot make them available. An offline sequence check is not a
runtime readiness certificate. Recover retained progress before making a new run.

When deploying tested configuration to an environment, follow **Configuration
promotion** in RUNBOOK.md. Reuse the existing Rules approval procedure and exact
release evidence; distinguish an approved release from its active deployment.

## Operate the recurring loop

1. **Inventory and readiness.** Account for the entire declared delivery and its
   acquisition completion evidence, expected/available file counts and receipt
   hashes. Check approved processing versions and required references. An existing
   folder or timestamp alone cannot establish downloaded-and-ready status. Let
   independent ready sources proceed when another source is delayed; hold only
   genuinely dependent work. Never start acquisition to resolve a missing delivery.
2. **Changes.** Compare with the last verified inventory and consult the Change
   Journal under the actual processing identity. Distinguish new bytes, changed
   rules/shared inputs, suspected renames and schema drift using RUNBOOK.md. Route
   new feeds to [data-onboarding](../data-onboarding/SKILL.md), shape/meaning changes
   to [data-profiling](../data-profiling/SKILL.md), and existing rule changes to
   [refining-rules](../refining-rules/SKILL.md). Routine deliveries reuse applicable
   qualification and approval; missing version evidence is reconciled, not invented.
3. **Size the work.** Measure usable CPU, memory, disk, database connection budget
   and competing work at the actual execution host/container. Use prior verified
   measurements and current supported bounds to choose concurrency and bundle size.
   Account for verifier costs too. Unknown estimates start conservatively; exhausted
   resources wait. Size divides the whole backlog into work, never drops records.
4. **Submit or resume.** Use [Bookkeeping run](../bookkeeping/RUN.md) and
   [recovery](../bookkeeping/RECOVERY.md) for the existing task protocol. Keep the
   source-owned steps, original input/rule/reference/runtime pins and authoritative
   leases. Run declared local prerequisites only through supported approved paths;
   a preferred source order is not a dependency. Missing common-command support
   remains a blocker, not permission to invent source-specific orchestration.
5. **Work and verify.** Use separate worker and verifier duties. Adjust dispatch
   between invocations within supported limits as capacity changes. Changing a
   frozen contract or input requires new work; preserve the existing run. Inspect
   progress, contention, failures and pending events with bounded queries. Use
   [Change Journal](../change-journal/SKILL.md) for receipts/delivery recovery through
   the producer that owns the outbox, never direct edits to journal or run state.
6. **Close or hand off.** Finalize only after declared work is independently verified,
   source outcomes reconcile and required Journal deliveries are acknowledged. An
   unchanged repeat should select zero files and start no mastering work. Report a
   partial run honestly. Save the run ID, frozen evidence references, resource
   measurements, blocker and next action in the source runbook for the next agent.

For a monitoring request, set an explicit deadline and exit on completion,
blockage, cancellation or the deadline. At expiry retain resumable state and
report the next action. Scheduling a future invocation is separate deployment work.

## Durable owners

| Owner | Authority |
| --- | --- |
| Rules | Versioned, tested and approved processing configuration |
| Bookkeeping | Runs, worklists, dependencies, leases, checkpoints and verified progress |
| Change Journal | Durable events and verified processing/delivery receipts |
| Destination | Atomic writes, identity, constraints and commit evidence |
| Operational runbook | References, measurements, observations and next actions; never authority to mark work complete |

Use the existing shared stores and private role connections. Preserve captured
data, source identities and exact integer precision. Public reports contain counts
and invented examples; keep credentials and row-level evidence private.
