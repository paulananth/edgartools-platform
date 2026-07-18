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

### Parser completeness (2026-07-18)

| PR | Capability |
| --- | --- |
| #146 | Scope ambiguity to Item 5.02 section only |
| #154 | Active-voice appointments/terminations |
| #155 | spaCy dependency parse + NER (PARSER_VERSION 2) |
| #157 | Possessive resignations; newly-appointed modifiers |
| #159 | Board without `as`, step-down, join-as, date fallback (PARSER_VERSION **3**) |

Silver re-parse after image rollout requires **parser_version 3** bump awareness (`force` or version-aware re-run). Residual true-hard NLP cases may still classify `unresolved` under release mode — use explicit repair manifests; do not treat ordinary full-chain skip-policy as Ticket 20 proof.
