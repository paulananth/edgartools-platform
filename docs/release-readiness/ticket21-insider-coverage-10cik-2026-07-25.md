# Ticket 21 — 10-CIK insider coverage evidence (2026-07-25)

## Scope

Issuer CIKs:

`320193, 789019, 1652044, 1018724, 1045810, 1318605, 1326801, 1067983, 21344, 886982`

(Apple, Microsoft, Alphabet, Amazon, NVIDIA, Tesla, Meta, Berkshire, Coca-Cola, GS)

## Loader contract (fixed)

Ticket 21 is **person + IS_INSIDER only**. Companies are not re-resolved on the
insider path except for a **targeted issuer-shell seed** when verify reports
`unresolved_issuer`.

| Step | Command |
|------|---------|
| Ownership silver (2y Form 3/4/5 + Item 5.02) | `bootstrap-batch` (completed earlier) |
| Persons | `mdm run --entity-type person --cik …` |
| IS_INSIDER | `mdm derive-relationships --relationship-type IS_INSIDER --cik …` |
| Missing issuers only | `mdm run --entity-type company --cik 1318605 --cik 1326801` |
| Gate | `mdm verify-insider-coverage --cik … --output s3://…` |

PRs: **#262** (person/IS_INSIDER-only loader + SM), **#263** (CIK-scoped company shells).

## Result (PASS)

```json
{
  "insider_identified": 146,
  "insider_total": 146,
  "insider_unresolved": 0,
  "source": "sec_ownership_reporting_owner",
  "unresolved": []
}
```

Artifact:

`s3://edgartools-prod-warehouse-690839588395/warehouse/release-evidence/ticket21-insider-coverage/insider_coverage-10cik-20260725T220108Z.json`

## Notes

- First verify: 122/146 identified; 24 `unresolved_issuer` for Tesla (`1318605`)
  and Meta (`1326801`) only — not person resolution failures.
- Seeded **two** issuer shells, re-derived IS_INSIDER for those CIKs, re-verified → **0 unresolved**.
- Full-universe `mdm run --entity-type company|all` is **not** part of this path.
