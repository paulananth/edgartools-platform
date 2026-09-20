# Trace the DEF 14A executive-record Person pipeline from code

Type: research
Status: open
Blocked by: none

## Question

Scope: DEF 14A executive compensation records: `sec_executive_record`, name-only, `EMPLOYED_BY`. Research 01 found 47% of `exec_name` is role text — locate the exact split logic responsible.

Trace it from **primary source only** — the repo's code, migrations, dbt
models, and Step Functions definitions — citing every claim as
`path:line`. No data queries (Snowflake is gone). Write findings to
`research/12-proxy-executive-person-pipeline.md` next to research 01, in the same shape: what was
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
