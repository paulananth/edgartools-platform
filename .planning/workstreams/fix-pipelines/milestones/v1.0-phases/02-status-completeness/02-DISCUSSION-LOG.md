# Phase 2: Status Completeness - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-16
**Phase:** 02-status-completeness
**Areas discussed:** Stage list maintenance, Map state active-stage granularity, D-03 vs D-05 verification tension, Retry-state icon

---

## Stage list maintenance

### Q1 — How to prevent stage list drift

| Option | Description | Selected |
|--------|-------------|----------|
| Comment reference + convention | Add comment above MACHINES array pointing to deploy-aws-application.sh | ✓ |
| Inline smoke test | scripts/ops/check-stage-names.sh diffs live SM definition against MACHINES | |
| Dynamic generation at runtime | Query Step Functions at startup, build stage list dynamically | |

**User's choice:** Comment reference + convention
**Notes:** Lightweight; no runtime overhead; relies on reviewer discipline.

### Q2 — Where should the comment point

| Option | Description | Selected |
|--------|-------------|----------|
| Point to deploy-aws-application.sh functions | `# Stage order must match write_*_definition() in infra/scripts/deploy-aws-application.sh` | ✓ |
| Point to ROADMAP.md | Update both files together | |
| You decide | Claude picks most useful pointer | |

**User's choice:** Point to deploy-aws-application.sh functions

### Q3 — Live verification pass needed?

| Option | Description | Selected |
|--------|-------------|----------|
| No — code inspection is sufficient | Stage lists confirmed by reading deploy-aws-application.sh | ✓ |
| Yes — verify at least one machine live | Run gold-refresh and confirm STAGE PROGRESS renders | |
| Yes — spot-check all 5 machines | Trigger each machine; most thorough but expensive | |

**User's choice:** No — code inspection is sufficient

---

## Map state active-stage granularity

### Q1 — Two-section layout vs integrated batch count

| Option | Description | Selected |
|--------|-------------|----------|
| Sufficient as-is | ▶ BatchBootstrap + BATCH MAP RUN section is enough | ✓ |
| Integrate batch count into stage line | Show ▶ BatchBootstrap (45/100) on stage line | |

**User's choice:** Sufficient as-is
**Notes:** Existing layout already satisfies OBS-04.

### Q2 — Single-▶ invariant

| Option | Description | Selected |
|--------|-------------|----------|
| Exactly one ▶ is the right invariant | Multiple ▶ markers simultaneously is a bug | ✓ |
| Multiple ▶ could be valid in parallel branches | Don't hard-code single-▶ assumption | |
| You decide | Claude picks based on machine definitions | |

**User's choice:** Exactly one ▶ is the right invariant

---

---

## D-03 vs D-05 Verification Tension (update session — 2026-05-16)

### Q1 — What does 'verification step' mean for the one-▶ invariant?

| Option | Description | Selected |
|--------|-------------|----------|
| Code comment only | Comment in Python block explaining sequential-model guarantee. No assert, no live run. | |
| Python assert in code | `assert len(active) <= 1` after computing active set. Code-level enforcement, no live run. | ✓ |
| Live pipeline observation | Manual step: spin up pipeline, observe exactly one ▶. Contradicts D-03. | |

**User's choice:** Python assert in code
**Notes:** Resolves D-03/D-05 tension — structural enforcement without a live run.

### Q2 — Where should the assert live?

| Option | Description | Selected |
|--------|-------------|----------|
| After computing active, before rendering | `active = entered - exited - failed; assert len(active) <= 1, f'...'` | ✓ |
| Inside per-stage loop | Equivalent but harder to read. | |
| You decide | Leave to planner/executor. | |

**User's choice:** After computing active, before rendering

---

## Retry-State Icon (update session — 2026-05-16)

### Q1 — What should retry-state icon behavior be?

| Option | Description | Selected |
|--------|-------------|----------|
| Keep ✗ on TaskFailed (current) | Stage shows ✗ on ECS task failure. Transient ✗ then ✓ if retry succeeds. | ✓ |
| Show ▶ during retries | Remove TaskFailed from failure detection; only terminal events mark ✗. | |
| Show ↻ with new icon | New icon for retry state. More informative but more complex. | |

**User's choice:** Keep ✗ on TaskFailed (current behavior)
**Notes:** Accepted as known limitation for v1, not a bug to fix.

### Q2 — Document as known limitation?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, document as known limitation | Add note preventing future agents from "fixing" this. | ✓ |
| No, leave as Claude's Discretion | Keep current "acceptable for v1" language. | |

**User's choice:** Yes, document it as known limitation

---

## Claude's Discretion

- **Retry state visualization** — resolved by D-06: keep current ✗ behavior; documented as
  known limitation. Explicitly NOT a bug to fix in Phase 2.

## Deferred Ideas

- **Retry-state icon upgrade (▶ or ↻):** Would require distinguishing `TaskFailed`
  (intermediate) from `MapStateFailed`/`ExecutionFailed` (terminal). Deferred to a future
  phase. D-06 marks this as a v1 known limitation.
