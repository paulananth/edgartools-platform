# Phase 2: Status Completeness - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-16
**Phase:** 02-status-completeness
**Areas discussed:** Stage list maintenance, Map state active-stage granularity

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

## Claude's Discretion

- **Retry state visualization** — not selected for discussion. Current behavior (✗ icon for
  failing-then-retrying stages) is acceptable for v1. Claude may improve this if trivial,
  but it is not required for OBS-04.

## Deferred Ideas

None — discussion stayed within phase scope.
