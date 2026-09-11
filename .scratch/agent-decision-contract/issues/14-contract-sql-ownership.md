# Decide who owns Snowflake Decision Contract objects

Type: grilling
Status: resolved
Blocked by: 06, 07

## Question

Long-term, who owns `EDGARTOOLS_DECISION` views and the publication table:
dbt, bootstrap SQL, or Python-generated SQL?

Python serving modules are the unit-tested semantics. Gold `FINANCIAL_FACTORS`
is already a dbt dynamic table. READY publication is written by the watermark
aggregator, not by dbt run.

## Answer

Bootstrap SQL owns `EDGARTOOLS_DECISION` (views and publication table).
dbt owns gold/silver dynamic tables, including `FINANCIAL_FACTORS`.
Python serving modules own contract semantics. The watermark aggregator
writes READY rows; `dbt run` does not.

## Comments

- Follow-on (2026-09-11): first implementation slice is **missing input
  data**, not contract SQL/READY writer. Scope of that data is the next
  question.
