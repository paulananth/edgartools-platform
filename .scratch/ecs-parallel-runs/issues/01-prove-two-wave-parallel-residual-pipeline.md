# Prove the Two-Wave Parallel Residual Pipeline with a Controlled Canary

Labels: `wayfinder:task`, `ready-for-agent`

Type: task

Status: open

GitHub mirror: [Prove the Two-Wave Parallel Residual Pipeline with a Controlled Canary](https://github.com/paulananth/edgartools-platform/issues/511)

## Question

Can a disposable two-wave Standard Step Functions state machine run the
complete residual-security workload with exact output parity, no workload
retries or OOMs, safe partial-failure recovery, no material compute-cost
regression, and at least 5% end-to-end improvement over the accepted
sequential control?

## Task

- Wait until the machine-profile sizing cohort is terminal and its accepted
  immutable profile is frozen.
- Reuse the accepted image, task revisions, commands, limits, input, and data
  population; change only orchestration topology.
- Build a disposable canary definition with Wave A (`MdmSecurities` and
  `MdmPersons`), Wave B (`MdmIsInsider`, `MdmHolds`, `MdmCompanyHolds`, and
  `MdmInstitutionalHolds`), and the strict `MdmExport` -> `MdmSync` ->
  `MdmVerify` tail.
- Keep Retry and Catch policies on each ECS task. Do not apply Retry to either
  Parallel state.
- Run the complete success canary and compare it with the sequential control.
- Rehearse one controlled branch failure and prove sibling disposition,
  partial-write detection, and safe rerun behavior.
- Record durable, secret-safe evidence: canary definition digest, execution
  ARNs, task revisions, timing, utilization, costs, task exits, retries,
  entity/relationship/export counts, graph counts, and Per-Type Exact
  Relationship Parity.

## Pass gate

Pass only with exact validated-output parity, zero OOMs, zero workload
retries, zero unresolved or duplicated entities/relationships, at least 5%
end-to-end improvement, no material billed-task-second or Fargate-cost
regression, and a demonstrated safe rerun after branch failure.

Otherwise resolve this ticket as rejected and do not unblock implementation.
