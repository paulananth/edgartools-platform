# Decide a Single Prod Workload-to-Profile Contract

Type: grilling
Status: open
Blocked by: 03, 05

## Question

How should canonical workload classes select warehouse `small`, `medium`, or
`large`, and MDM `mdm-small`, `mdm-medium`, or `mdm-large` through one durable
contract? Represent bounded MDM, ordinary full MDM,
residual-holds/security work, BatchSilver, gold, daily incremental, bootstrap,
and validation-only commands without duplicating the selection decision across
shell functions and state-machine generators. Preserve the sizing safety bands
and documented OOM floors decided earlier.
