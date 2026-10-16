# Automatic local test baseline promotion

Status: skill-policy update; environment automation is not implemented by this ticket.

Operator decision: “B, why do i need to approve, can we add rules to the skills because everything is agent driven”. B selects automatic promotion after verification, without a separate operator approval for each local test baseline.

## Parts

- [x] Record the automatic-promotion policy in the data-platform skill and add a setup pointer (canonical policy and setup pointer verified; 2026-10-16 16:13 ET).
- [x] Check the policy against the decision, existing approval rules and executable capability; validate links and Markdown (seven gates, scope, packaging, no invented CLI, links and fences passed; 2026-10-16 16:13 ET).
- [ ] Review Standards, Spec and GoF and publish a separate skill-policy PR with CI tracking its current head.
- [x] Learning → skill: data-platform/LOCAL-TESTING.md owns the local baseline policy; the environment implementation must enforce its gates (new policy and trigger verified; 2026-10-16 16:13 ET).

## Review

### Standards

Dedicated branch/worktree, public guidance only, one canonical policy with a setup pointer. No provider calls, data values, store writes or runtime code changes.

### Spec

Automatic promotion of verified local test baselines replaces the proposed per-baseline manual approval. The future implementation must enforce the policy; this documentation does not claim it exists.

### GoF

Documentation only; no production code or pattern refactor.
