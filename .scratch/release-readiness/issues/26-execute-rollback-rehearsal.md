# Execute the Rollback Rehearsal

Type: task
Status: resolved
Blocked by: 05, 11

## Question

Ticket 05 (Define the Rollback Rehearsal Contract) specified the proof, not the proof itself.
This ticket performs it: (1) confirm/attest the digest-restoration mechanism
(`deploy-aws-application.sh --image-ref`/`--mdm-image-ref`, no Terraform change) completes
within the 1-hour RTO — evidenced by the most recent qualifying prod deploy, or a fresh one if
none exists yet; (2) execute a live BatchSilver re-run that deliberately exercises the
old-task/new-task overlap during a rollback transition, proving ticket 11's contention-safe
publication boundary holds and the silver layer is not clobbered by multiple loaders. Produces
`docs/release-readiness/rollback-rehearsal.json` (sanitized, AWS-Operator-attested), the
standing evidence file ticket 06's stage 2 fail-fast check reads before any pipeline work
starts.

## Answer

Both proofs executed live in prod on 2026-07-29 and PASS. Evidence:
`docs/release-readiness/rollback-rehearsal.json` (top-level record) plus
`docs/release-readiness/rollback-rehearsal-batchsilver-overlap-evidence.json`
(the `batchsilver_transition_overlap_proof.evidence_ref`). AWS Operator attested.

**Proof 1 — digest restoration, ordinary use, 1h RTO.** A real prod rollback via
`deploy-aws-application.sh --image-ref/--mdm-image-ref --skip-build` (no Terraform touched):
6 ECS task definitions re-registered, 26 Step Functions state machines updated to reference
them. Verified consistent across every task definition and a spot-check of all 26 state
machines. **Duration: 5m37s**, well inside the 1-hour bound.

**Proof 2 — BatchSilver contention-safe publication under a genuine rollback-transition
overlap.** Rather than orchestrating a full Step Functions BatchSilver Map (which in this
repo's `bronze_seed_silver_gold`/`silver_mdm_gold` state machines seeds from the *entire*
bronze/silver inventory, not a scoped CIK set), the overlap was exercised directly at the ECS
level — the actual unit ticket 11's publication boundary protects. Two `bootstrap-batch
--cik-list 320193` (Apple, the repo's locked pilot CIK) tasks were launched back-to-back:
one on `edgartools-prod-medium:89` (digest `sha-19e7ad9f6e50`, the currently-live rolled-back
image), one on `edgartools-prod-medium:86` (digest `sha-48d761abe60d`, the prior forward
image) — the exact two digests this session's Proof 1 transitioned between.

Log evidence confirms a genuine overlap, not a sequential no-op: both tasks hydrated the
canonical `silver.duckdb` from the **same** base version 0.7s apart, then their publish
windows overlapped for **~70 seconds** before either completed. Neither publish was lost —
two distinct sequential canonical versions were recorded (not one overwriting the other
silently), and a before/after semantic reconciliation (SHA-256 of canonical rows) across all
6 CIK-scoped `sec_company*` tables for CIK 320193 was **byte-identical**, zero duplicate
primary keys introduced. Both tasks exited 0. **Result: PASS** — ticket 11's contention-safe
publication boundary held under a real old-task/new-task overlap during a rollback-style
transition. Judged on correctness, not against a clock, per ticket 05.

This is a lighter-weight, CIK-scoped correctness check — not the full formal
`maxconcurrency4-data-integrity.json` gate (ticket 03), which is the steady-state,
whole-universe release gate and out of scope for a standing rollback-mechanism proof per
ticket 05's own framing.

**Deferred, not part of this ticket:** the user separately asked mid-session to build a new
prod warehouse image from PR #298 and redeploy it. That build hit two unrelated environment
issues — this workstation's Colima daemon (containerd-snapshotter misconfiguration, then a
`--memory 8` request against an 8GB-total-RAM host that got the VM OOM-killed) and a
pre-existing, unrelated CI OIDC trust failure blocking `deploy.yml` on the last 3 runs
regardless of commit. Neither blocks this ticket — Proof 2 only needed two *distinct* already-
published digests, both of which already existed in ECR from earlier in this session. The
PR #298 image build/redeploy is tracked separately, not folded into this evidence.
