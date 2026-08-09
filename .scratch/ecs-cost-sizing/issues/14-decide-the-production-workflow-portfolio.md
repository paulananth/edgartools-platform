# Decide the Production Workflow Portfolio

Type: grilling
Status: open
Blocked by: 10, 11, 13

## Question

Which production state machines should be kept as-is, reshaped, merged into a
canonical pipeline, split for isolation, made operator-only, rescheduled, or
retired?

Apply the agreed workflow value test to every inventoried state machine. Keep
distinct workflows where they provide a unique output, bounded repair path,
failure-isolation boundary, release gate, or materially better economics.
Consolidate wrappers and repeated MDM/gold chains only when immutable inputs,
resume semantics, observability, IAM, and rollback remain unambiguous. Require
a downstream-consumer and schedule audit before retirement.
