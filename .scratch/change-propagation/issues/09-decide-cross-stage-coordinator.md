# Decide the cross-stage coordinator and composite watermark contract

Type: grilling
Status: open
Blocked by: 05, 06, 07, 08

## Question

What coordination contract lets silver, MDM, gold, and graph publish
independently yet exposes a Change Propagation Run as agent-grade only when all
affected stages are complete and aligned?

Decide the stage state machine, ownership of expected-producer and outcome
records, event/outbox handoffs, monotonic source-key ordering, timeouts,
retry/DLQ/manual-repair states, stage-local rollback, and composite Decision
Watermark commit. The answer should determine whether the physical topology is
one coordinator or several independently triggered machines while preserving
the already-settled SNS/SQS and on-demand compute decisions.
