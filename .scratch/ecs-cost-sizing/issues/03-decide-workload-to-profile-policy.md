# Decide Sizing Safety Floors and Utilization Bands

Type: grilling
Status: resolved
Blocked by: 01, 02

## Question

What peak and sustained CPU/memory bands, runtime tolerance, OOM history, and
minimum evidence define an under-sized, right-sized, or over-sized workload?
Decide the safety floors that remain because lower-memory runs failed,
including gold and residual-holds/security work. These bands govern later
profile assignment; the canonical selection mechanism belongs to the separate
profile-contract decision.

## Answer

Sizing is decided per **Workload Class**, **Representative Input Envelope**,
and immutable image digest—not globally by ECS family or task-definition
revision. Standalone gold and combined daily/gold are therefore distinct
classes even when they currently share `large`.

### Classification policy

- **Under-sized:** any representative OOM/exit 137, resource-exhaustion or
  correctness failure, or CPU saturation demonstrated to violate the
  completion-time guardrail.
- **Constrained:** memory peak at least 85%, memory p95 at least 75%, or CPU p95
  at least 90%. Constrained is a warning and can still be the right operational
  choice when correctness and speed pass and a larger profile does not improve
  the outcome safely.
- **Healthy/right-sized:** correctness, output parity, retry, recovery, and
  completion-time gates pass; memory remains below the constrained bands; and
  there is no proven adjacent profile with a better accepted result.
- **Downgrade candidate:** memory peak no more than 40% and p95 no more than
  35%, with CPU p95 no more than 50% or average no more than 45%. This only
  authorizes a lower-profile canary.
- **Proven over-sized:** the adjacent lower profile passes the same
  representative correctness, output, retry, resource, and completion-time
  gates. Low utilization alone never proves over-sizing.

Memory and CPU are deliberately asymmetric: memory exhaustion terminates the
task, while CPU saturation can be an efficient use of a profile if completion
time still passes. Sparse one-minute samples cannot override an OOM result or
authorize a downgrade.

### Completion-time and evidence gates

A cheaper profile may regress p95 end-to-end time by no more than 5%. No cost
saving may introduce a correctness, output-completeness, freshness, retry,
recovery, or idempotency regression.

A normal downgrade needs two consecutive representative canaries. A workload
with prior OOM, transient-memory risk, or incomplete source coverage needs
three, including the largest known normal-production input envelope. Any OOM
rejects the candidate.

Every accepted sizing result must preserve:

- command and workload class, Representative Input Envelope, immutable image
  digest, task-definition resources/revision, execution ARN, and task IDs;
- task-bound max, average, and p95 CPU/memory plus time above 70%, 80%, and 90%;
- image-pull-to-stop billable duration, end-to-end duration, exit/stop reason,
  retry ordinal, OOM/quota classification, and requested resource-hours;
- selected, attempted, committed, exported, skipped, rejected, retried, and
  deduplicated record counts where applicable; and
- output identity, correctness, parity, completeness, recovery, and
  idempotency results.

Incomplete or family-only telemetry leaves the workload unclassified or
provisional; it cannot approve a downgrade.

### Current safety floors and operational profiles

| Workload Class | Decision |
| --- | --- |
| Combined daily/full-universe warehouse | `large` remains the Sizing Safety Floor and Operational Profile because 4 GiB previously OOMed and a successful run reached 5,972 MiB. |
| Full-canonical seed-universe | `large` remains the Sizing Safety Floor and Operational Profile because a current 4-GiB production run OOMed; bounded seed and parsing utilities are a separate Workload Class. |
| Full-universe and bounded-heavy MDM | Retain `medium`; measured peaks exclude `small`, and a current-digest full run remains required before reconsideration. |
| Post-shard `BatchSilver` | Retain `medium` with concurrency 20; it completed 680/680 while `large`/16 exceeded the account vCPU quota. |
| Residual-holds/security | Historical 2 GiB is prohibited. Retain `large` operationally until three `medium` canaries process non-zero 13F data and pass all gates. |
| Standalone gold | Retain `large` operationally while running the normal two representative `medium` canaries. |
| MDM migration, counts, and verification | `small` remains valid for the measured lightweight commands. |

This ticket sets policy and safety floors only. The canonical workload-profile
selection mechanism, per-stage assignments, canary automation, and drift gates
remain with their existing downstream Wayfinder decisions.
