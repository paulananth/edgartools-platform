# Decide the test-case and batch-gate format

Type: grilling
Status: open
Blocked by: 01, 03

## Question

Decide how the `tests` section is written:

- parse cases: fixture reference, expected silver rows, how partial
  expectations and ordering work;
- mapping cases: expected assertions (kind, identifiers, fields,
  evidence-only fields);
- mastering cases: declared existing identities, expected bind / create /
  defer outcome and surviving fields;
- the batch gate: which metrics (coverage, deferral rate, row counts …),
  thresholds, and how a result is recorded as proof for go-live;
- the failure output format (check 9).

Carried in from ticket 04: **custom checks** (Q6 allowed them per source) —
their shape and rules; and the gate on custom-step `reject(reason)` counts.
