# Decide the Optimization Rollout and Acceptance Gates

Type: grilling
Status: resolved
Blocked by: 04, 13, 14, 15, 16, 17, 18

## Question

In what waves should workflow portfolio, loop, concurrency, telemetry, and
machine-profile changes be implemented and validated, and what evidence blocks
promotion or triggers rollback?

Define an immutable baseline and candidate, one-variable-at-a-time canaries
where practical, representative bounded and full-volume executions, record-
funnel equality, output and integrity checks, OOM/failure/retry thresholds,
duration and freshness tolerances, cost-per-output targets, state-machine
reference audits, and protected rollback revisions. Require a new post-change
execution; never use a redrive of pre-change work as acceptance evidence.
Make end-to-end completion speed a promotion gate alongside correctness: each
candidate must report critical-path and total duration against the immutable
baseline, with an explicit operator-approved exception for any material
slowdown even if AWS cost falls.

## Answer

Ticket 04 already built a comprehensive canary/rollback policy — but scoped
specifically to task-*profile* changes. This ticket sequences the other
four change types this map decided and defines acceptance gates for the
ones Ticket 04 doesn't cover.

**Gap surfaced, folded in as a hard prerequisite rather than assumed:**
this ticket isn't formally blocked by
[Decide and Capture the Protected Rollback Cohort](23-decide-and-capture-protected-rollback-cohort.md),
and Ticket 04 explicitly deferred rollback-cohort designation to it — but
it's still unresolved, offering two real, undecided options. **No wave
below may promote anything without a designated Configuration/Code
Rollback target existing.** This becomes **Wave 0**, a hard precondition,
not itself one of the five change-type waves — matching how Ticket 04
treated the same gap (deferred, not ignored).

### Wave order

1. **Wave 1 — Telemetry** (Ticket 17). Foundational and additive; needed to
   measure every later wave's acceptance evidence (record-funnel equality,
   durable manifests, `triggered_via`, Map child traceability).
2. **Wave 2 — Portfolio retirement + reshape** (Ticket 14). Shrinks the
   surface before Wave 5's templating touches it; wires the `verify_status`
   marker onto Wave 1's manifest schema; adds `residual_holds_graph`'s
   missing `Catch`.
3. **Wave 3 — Loop/concurrency** (Ticket 15). CIK-window resume (opt-in,
   low blast radius) and the unbounded `sync-graph` canary (already
   scheduled as Ticket 25).
4. **Wave 4 — Machine profile** (Ticket 16). Fully governed by Ticket 04's
   existing policy already; no new gate design needed here.
5. **Wave 5 — Structural simplification** (Ticket 18). Last, deliberately:
   touches every remaining machine's ASL generation, benefits from Wave 2's
   already-shrunk portfolio, and per Ticket 04's own finding needs
   infrastructure ("the current sequential all-workflow deploy path is not
   a valid canary mechanism") that doesn't exist yet — see the new
   prerequisite ticket below.

### Acceptance gates for non-profile changes

Ticket 04's gates (memory bands, ≥10% cost improvement, etc.) are
profile-specific and don't fit portfolio retirement or a `Catch`-policy
reshape. **New: a Structural/Behavior Canary** — reuses Ticket 04's
isolation *mechanism* (temporary, unscheduled, no live triggers, immutable
candidate definition, one frozen update-set transaction before any live
reference changes) but swaps the gate criteria to correctness/output-
parity/record-funnel-equality instead of memory/CPU/cost thresholds.
Applies to Waves 1, 2, 3, and 5.

### Standing rules across every wave

- **Never use a redrive as acceptance evidence.** Every wave requires a
  genuinely new post-change execution — stated once here, not re-litigated
  per wave.
- **End-to-end completion speed is a co-equal promotion gate alongside
  correctness**, reusing Ticket 10's already-decided value ordering. A
  material slowdown requires explicit operator sign-off even if cost falls.
- **Configuration Rollback vs. Code Rollback stay distinct**, per Ticket
  04's already-established definitions — this ticket reuses that
  distinction rather than re-deriving it, for both profile and non-profile
  waves.

### Wave 5's missing infrastructure

Staged-transaction deploy support is an **explicit prerequisite task**
blocking Wave 5 specifically (not the whole rollout), named and tracked
rather than left implicit — see the new ticket below, matching this map's
own pattern (Tickets 23-27) of surfacing a real gap as a tracked task
instead of letting it hide inside a larger decision.
