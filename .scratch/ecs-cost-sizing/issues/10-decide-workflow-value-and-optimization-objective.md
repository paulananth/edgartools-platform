# Decide the Workflow Value Test and Optimization Objective

Type: grilling
Status: resolved

## Question

What makes a production workflow worth retaining, and in what order should
correctness, recoverability, freshness, throughput, runtime, and AWS cost be
optimized?

Decide the scorecard used for all 26 currently observed `edgartools-prod-*`
state machines. The recommended default is: preserve correctness and required
recovery gates first; require a named output or operator capability and a
known consumer; then optimize cost per successful execution and cost per 1,000
committed records without worsening freshness or completion time beyond an
agreed tolerance. A workflow with no unique output, consumer, safety role, or
economic advantage becomes a merge or retirement candidate.

## Answer

The optimization priorities are:

1. **Co-primary:** preserve correctness, complete outputs, integrity gates,
   bounded replay, rollback, and required recovery capabilities; and minimize
   end-to-end time from trigger to a durable, validated, consumer-usable
   output.
2. Improve throughput and remove critical-path waits where measured
   parallelism, batching, or a larger profile shortens completion without
   increasing correctness, quota, contention, retry, or recovery risk.
3. Reduce AWS cost on the cost-versus-completion-time frontier. A cheaper
   configuration is not preferred when it materially slows a correct complete
   workflow unless the later policy explicitly accepts that trade-off.

A workflow is valuable only when it has at least one evidenced reason to
exist: a named downstream consumer and required output; a unique integrity or
release gate; a bounded repair/recovery capability; an operator control; or a
measurably safer or cheaper execution path than composing retained workflows.
Absent one of those reasons, it is a consolidation or retirement candidate.

Do not assign a blanket savings percentage before measurement. First establish
the per-workflow baseline: successful executions, complete outputs, end-to-end
and stage duration, critical-path waits, freshness contribution, records per
second, attempted/committed/exported record funnels, retries, Fargate
resource-seconds, and Step Functions cost. Then set speed and cost targets for
that workflow. Use cost per successful execution for verification and operator
utilities where a records-based denominator is not meaningful; otherwise also
use cost per 1,000 committed and per 1,000 exported records.

No optimization passes if it lowers output completeness, changes record
semantics, removes a required recovery path, or exceeds the later-agreed
freshness, duration, OOM, failure, or retry gates.

Amended by the operator after resolution: speed to complete, validated output
is a number-one priority alongside correctness and recoverability.
