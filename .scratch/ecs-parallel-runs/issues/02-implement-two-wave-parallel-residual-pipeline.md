# Implement and Roll Out the Proven Two-Wave Parallel Residual Pipeline

Labels: `wayfinder:task`, `ready-for-agent`

Type: task

Status: open

Blocked by: 01

GitHub mirror: [Implement and Roll Out the Proven Two-Wave Parallel Residual Pipeline](https://github.com/paulananth/edgartools-platform/issues/512)

## Question

After the controlled canary passes every gate, can the proven two-wave
topology be incorporated into the source-controlled residual-security MDM
Pipeline Machine and rolled out without changing commands, profiles,
relationship limits, retry ownership, graph scope, or protected tail ordering?

## Entry gate

Do not edit implementation code, deploy a replacement production definition,
or reinterpret a failed or ambiguous canary as approval while the controlled
canary ticket is open or resolved as rejected.

## Task

- Rebase the dedicated Codex implementation branch on current `origin/main`
  before editing.
- Run the repository-required GoF refactor review against the generator and
  relevant history; preserve the current design unless evidence justifies a
  focused extraction.
- Implement exactly the canary-proven Wave A and Wave B topology in the
  residual-security MDM Pipeline Machine generator.
- Preserve per-state commands, relationship limits, task-profile bindings,
  generation identity, Retry/Catch behavior, and the strict Export -> Sync ->
  Verify tail.
- Add or update generated-ASL architecture tests for the parallel waves,
  prerequisites, per-state recovery ownership, and protected tail.
- Run focused tests and the repository's proportional full verification suite,
  distinguishing new failures from named baselines.
- Build an immutable Release Candidate, deploy through existing staged release
  and rollback controls, and verify the production definition matches the
  reviewed generated ASL.
- Run post-rollout structural and behavioral verification. If production
  evidence differs from the passing canary, roll back rather than widening
  acceptance criteria.

## Completion gate

Complete only when the source-controlled topology, tests, immutable release
evidence, deployed production definition, exact parity, and rollback readiness
are all verified. Implementation without deployed verification is not
completion.
