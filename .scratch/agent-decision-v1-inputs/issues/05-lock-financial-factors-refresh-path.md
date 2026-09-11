# Lock the financial-factors refresh path

Type: grilling
Status: open
Blocked by: 01

## Question

Given the live FINANCIAL_FACTORS bind gap, how should the 19-key vector
land in prod gold?

At minimum decide:

1. One-shot operator `dbt run --select financial_factors --full-refresh
   --target prod` versus waiting for an ordinary gold-refresh /
   `REFRESH_AFTER_LOAD` cycle versus a new pipeline state.
2. Whether `FINANCIAL_DERIVED` (or facts) must refresh first, or factors
   passthrough alone is enough.
3. Whether this map's plan stops at "operator runs this command" or
   requires a verified live column list after the refresh (a later task
   ticket).

Predecessor: [Bind v1 feature keys to gold FINANCIAL_FACTORS](../../agent-decision-contract/issues/12-bind-v1-feature-keys-to-gold-financial-factors.md)
already implemented the model on this branch; prod still needs the
columns. Dynamic tables do not pick up SQL-body changes without
`--full-refresh` (CLAUDE.md dbt convention).

## Comments

- 2026-09-11 [Explain why FINANCIAL_FACTORS has only 21 CIKs](07-why-financial-factors-only-21-ciks.md):
  `--full-refresh` adds the three missing columns only. It does not add
  CIKs. Coverage is ticket 08, not this ticket.
