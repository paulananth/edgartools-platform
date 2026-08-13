# Run `mdm.residual_security` Medium Canaries and the Unbounded `sync-graph` Canary

Type: task
Status: claimed
Blocked by: none

## Question

Run and record the outcome of two related, currently-unscheduled MDM canary
cohorts, both raised by [Decide the Machine Profile for Every Workflow Stage](16-decide-machine-profile-per-workflow-stage.md):

1. **`mdm.residual_security`→`mdm-medium` downgrade canaries.** Per Ticket
   09's standing policy, `mdm-large` stays the operational profile for
   residual-holds/security work until three current-image, representative
   `mdm-medium` canaries process non-zero 13F/residual-security data and
   pass the full correctness/parity/completeness/recovery/idempotency/
   zero-failure gate set. Zero of the three have run as of this ticket.
2. **The first unbounded `mdm sync-graph` run** (`--mdm-graph-limit 0`),
   per [Decide the Loop, Batch, and Concurrency Policy](15-decide-loop-batch-and-concurrency-policy.md)'s
   decision to raise the default from 200 for production runs. No execution
   at real (~193K-node) scale exists yet. Ticket 16 decided this first
   canary should run on `mdm-large`, not `mdm-medium`, given the complete
   absence of duration/memory evidence at this scale.

Both are MDM-runtime canaries blocked on the same kind of missing evidence
(a representative, non-zero-data, current-image execution) — grouped here
rather than split, since resolving one is likely to inform scheduling the
other. Record execution ARNs, task-bound CPU/memory peaks, duration, and
pass/fail against each cohort's own gate criteria (Ticket 03/09 for #1,
Ticket 15 for #2) on resolution.

## In progress (2026-08-13) — execution identities, recorded live

Neither existing generic single-command state machine
(`edgartools-prod-mdm-run`, `edgartools-prod-mdm-sync-graph`) could be
used directly: both pinned to stale task-def revision `mdm-medium:149`
(not current `158`), `mdm-run` hardcodes `--entity-type all` with no
override for `security`, and neither references `mdm-large` at all. Per
Ticket 04's own canary policy ("a canary must exercise the same
orchestration... as the covered production stage"), registered two
temporary, unscheduled Standard state machines instead — exact copies of
the real production definitions with only the candidate task-profile ARNs
swapped, nothing else:

- `canary-mdm-sync-graph-large-t25` — copy of `edgartools-prod-mdm-sync-graph`,
  all `mdm-medium:149` → `mdm-large:92`.
- `canary-residual-holds-medium-t25` — copy of `edgartools-prod-residual-holds-graph`,
  all 8 `mdm-large:92` references → `mdm-medium:158` (the 1 `mdm-small:158`
  verify-graph reference left untouched — not part of the candidate).

**Executions launched:**
- Sync-graph canary (`{"limit": 0}`, unbounded): `canary-sync-graph-unbounded-1`,
  started 2026-08-13T06:57:27-04:00.
- Residual-security canary attempt 1/3: `canary-residual-security-medium-1`,
  started 2026-08-13T06:57:42-04:00.

Both monitored to completion; results and pass/fail against each cohort's
gate criteria recorded below once terminal. Attempts 2/3 of the
residual-security cohort launch after attempt 1 completes.
