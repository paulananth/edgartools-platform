# Define the Rollback Rehearsal Contract

Type: grilling
Status: resolved
Blocked by:
Blocks: 26

## Question

What exact pre-GO rehearsal must prove that named operators can restore the prior approved image digests and safe BatchSilver concurrency, within bounded recovery time, without changing passive Terraform infrastructure or exposing secrets?

## Answer

Resolved via grilling (2026-07-28). The rehearsal splits into two proofs with different shapes,
both attested by the **AWS Operator** role.

**1. Digest restoration — proven by ordinary use, not a dedicated drill.**
`deploy-aws-application.sh`'s `--image-ref`/`--mdm-image-ref`/`--skip-build` path is the exact
same code path used for every routine prod image promotion — forward-deploying a new digest is
mechanically identical to restoring a prior one (the script takes a target digest, not a
direction). So the mechanism is continuously re-proven by ordinary operations; no dedicated
"break prod on purpose" live-fire event is required, and there is **no staleness/expiration
concept** to define — the standing precondition ticket 06 names is satisfied as long as prod
deploys keep going through this documented, Terraform-untouched path (not an undocumented
shortcut), not by a freshness timer. **Bound:** restoring prior warehouse + MDM image digests
(task-definition register, ECS service update, health settle) must complete within **1 hour**.

**2. BatchSilver concurrency restoration — requires a live re-run, not a parameter check.**
Confirming the rollback command carries the correct `--bootstrap-batch-concurrency` value isn't
enough: the real risk is silver-layer write contention during the rollback *transition* itself —
old tasks still finishing while rolled-back tasks start, a scenario ticket 03's steady-state
MaxConcurrency=4 proof never exercises. This proof requires an actual BatchSilver re-run that
deliberately exercises that old-task/new-task overlap, confirming ticket 11's contention-safe
publication boundary (semantic rehydrate-and-merge + atomic S3 conditional write) holds under a
rollback transition specifically. **Separate from the 1-hour digest-restore bound** — judged
pass/fail on correctness (no silver clobbering), not against a clock.

**Standing, not per-candidate.** Per ticket 06's framing, this isn't bound to any one Release
Candidate's specific digests — it's a standing capability proof for the current deploy mechanism.
Evidence lives outside any single `releases/rc-<YYYYMMDD>-<commit>/` directory, at
`docs/release-readiness/rollback-rehearsal.json` (or equivalent fixed, non-RC-scoped path),
regenerated when the deploy mechanism itself changes (`deploy-aws-application.sh`'s
`--image-ref` path, ECS task-definition shape, or ticket 11's contention-safety mechanism) — not
on a calendar. Ticket 06's stage 2 fail-fast check reads this file's existence and that it
references the current mechanism, before any pipeline work starts.

**Evidence artifact**, following the pattern ticket 01 established for every other gate: a
sanitized JSON record with `{status, deploy_path_verified, digest_restore_duration, batchsilver_
transition_overlap_proof: {status, evidence_ref}, attested_by: "aws_operator", attested_at}`. Per
ticket 01's secret-safe doctrine, raw CloudWatch logs, generated AWS application JSON, ARNs,
account identifiers, and connector traces stay outside Git — only sanitized digests (no
registry/account prefix), task-definition revision numbers, durations, and pass/fail outcomes are
captured.
