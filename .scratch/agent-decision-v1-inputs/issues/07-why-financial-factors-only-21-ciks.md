# Explain why FINANCIAL_FACTORS has only 21 CIKs

Type: research
Status: resolved
Blocked by: 01

## Question

Ticket 01 found gold `FINANCIAL_FACTORS` (and `FINANCIAL_DERIVED`, and
silver `SEC_FINANCIAL_DERIVED`) all have 5,056 rows on only **21 CIKs**.
The missing `ebitda` / `eps_diluted` / `ebitda_margin` columns are a
separate bind. Why is the CIK set 21, not the Decision Subject Universe
(tens of thousands of MDM-active issuers)?

Determine the first layer that shrinks to 21 CIKs:

1. Gold factors vs gold derived vs silver derived vs silver/gold
   financial facts — distinct CIK counts at each layer.
2. Whether the dbt derived/factors models filter away CIKs that have
   facts, or merely pass through an already-small silver table.
3. What writer populates `sec_financial_fact` / derived (entity-facts /
   companyfacts / `bootstrap-fundamentals`), and whether prod has only
   ever run that writer on a 21-CIK slice (pilot, incomplete Stage 1B,
   daily_incremental not wired).
4. Whether 21 is a parser-success subset of a larger facts table, or the
   facts table itself is 21 CIKs.

Read-only. `snow sql --connection edgartools-prod`. Do not implement.

Save findings at
`.scratch/agent-decision-v1-inputs/research/07-why-financial-factors-21-ciks.md`.

## Answer

The 21 CIKs are Apple smoke (2026-07-29) plus Ticket 42's 20-CIK sample
(list matches live gold exactly). Facts, landing, silver, derived, and
factors are all 21 CIKs / 434,805 facts — dbt does not drop anyone.
`entity-facts` is not in `daily_incremental`. Full-universe
`load_history` Stage 1B OOM'd in silver publish (ecs-cost-sizing Ticket 20,
2026-08-14) and never landed. Last ingest 2026-08-04. A factors
`--full-refresh` adds columns only, not CIKs.
[research](../research/07-why-financial-factors-21-ciks.md)
