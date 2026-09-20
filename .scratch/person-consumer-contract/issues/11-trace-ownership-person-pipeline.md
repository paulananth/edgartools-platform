# Trace the Form 3/4/5 reporting-owner Person pipeline from code

Type: research
Status: resolved
Blocked by: none

## Question

Scope: Form 3/4/5 reporting owners: `sec_ownership_reporting_owner` (+ the two transaction tables), `owner_cik`, `IS_INSIDER` and `HOLDS`.

Trace it from **primary source only** — the repo's code, migrations, dbt
models, and Step Functions definitions — citing every claim as
`path:line`. No data queries (Snowflake is gone). Write findings to
`research/11-ownership-person-pipeline.md` next to research 01, in the same shape: what was
read, findings numbered F1…, "what this settles for ticket 02/03/05/06", and
what could not be determined from code. Cover, in order:

1. **Source form and fetch** — which SEC form(s), which command/stage fetches
   them (`edgar_warehouse/application/`, `scripts/`, Step Functions builders),
   idempotency key.
2. **Parser** — module, entry function, the exact fields it emits for a
   person, how it derives the person identifier or name, known defects or
   TODOs in comments.
3. **Silver** — the landing table(s) and columns (`edgar_warehouse/silver_schema.py`,
   `infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql`), dedupe
   key, the dbt silver collapse model, the `mdm_entity_id` back-propagation
   column if any.
4. **Legacy MDM** — which resolver/derivation consumes it
   (`edgar_warehouse/mdm/resolvers/`, `pipeline.py`), matcher chain and
   thresholds, what fields it writes to `mdm_entity`/attributes, which
   relationship type(s) it derives and the exact derivation code, how
   changes/retirements are handled.
5. **Downstream** — gold models, graph edges (`snowflake_graph.py`,
   `graph.py`), API routers, Agent Query Surface contracts that read the
   person or its edges.
6. **Clean MDM's stated target** for this source — the exact row in
   `docs/specs/clean-mdm/pipeline-inventory.md` and anything in
   `domain-model.md` (read from `origin/codex/clean-mdm-integration` with
   `git show`; never edit).

## Answer

[research/11](../research/11-ownership-person-pipeline.md), 2026-09-20.
Written by a background trace cut off by a session limit during its own
citation spot-check; the load-bearing citations were re-verified by hand
(`database.py:304`, `match.py:123-132`, `resolvers/person.py:154-164`,
`002_seed_data.sql:62-64`, `parsers/ownership.py:24-67`). Key facts:
`owner_cik` is the only identifier and legacy stores it nullable and
non-unique; the legacy fuzzy-name "issuer context" is **inoperative**
(candidates never carry `issuer_cik`, so every fuzzy match is capped below
auto-merge and lands in REVIEW — which, in ordinary mastering, still
binds); the only classification rule is "CIK ∈ known company CIKs ⇒ not a
person"; every transaction is hard-attached to `owner_index = 1`, so
`HOLDS` on multi-owner filings is wrong at the source; silver's
`mdm_entity_id` on the reporting-owner row is a legacy person id that a
merge can silently re-point, so it is not a stable key.
