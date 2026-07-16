# Implement Item 5.02 Employment Events

Type: task
Status: resolved
Blocked by: 16
Blocks: 20

## Task

Parse Form 8-K Item 5.02 appointment, departure, role-change, and covered compensation events and apply their temporal effects to Reported Executive Employment.

## Done when

- Item 5.02 candidates produce typed events or stable not-applicable outcomes.
- Appointments open and departures close versioned `EMPLOYED_BY` relationships.
- Proxy baselines and later 8-K events reconcile without duplicate identities.
- Ambiguous names, companies, dates, and contradictory events remain unresolved and block release.
- Current-at-watermark and historical tests cover appointment/departure sequences.

## Resolution

Implemented by commit `1841e2f`: Item 5.02 appointments, departures, role changes, and covered salary changes persist as typed silver events and apply temporal effects during `EMPLOYED_BY` derivation. Conservative ambiguous outcomes remain unresolved.
