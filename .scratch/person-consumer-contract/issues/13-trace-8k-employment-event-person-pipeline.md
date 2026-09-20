# Trace the 8-K Item 5.02 employment-event Person pipeline from code

Type: research
Status: resolved
Blocked by: none

## Question

Scope: 8-K Item 5.02 officer/director changes: `sec_employment_event`, name-only, `EMPLOYED_BY`, `edgar_warehouse/parsers/item_502.py`.

Trace it from **primary source only** — the repo's code, migrations, dbt
models, and Step Functions definitions — citing every claim as
`path:line`. No data queries (Snowflake is gone). Write findings to
`research/13-8k-employment-event-person-pipeline.md` next to research 01, in the same shape: what was
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

[research/13](../research/13-8k-employment-event-person-pipeline.md),
2026-09-20. Background trace cut off during its own spot-check; key
citations re-verified (`pipeline.py:3520-3590` `_ensure_proxy_person`,
`uuid5(cik:lower(name))` stub key at `:3552`, `resolution_method =
"uuid5_proxy_stub"`). Key facts: the 8-K source carries no person
identifier; the only deterministic context is `(issuer CIK, person_name)`
and legacy's stub key is exactly that; legacy also binds by exact global
name across issuers, which the contract must forbid; `EMPLOYED_BY` from
this source has never been graph-populated, so nothing downstream depends
on its shape; rows are never retired; stub provenance is mislabeled
`proxy_filing`.
