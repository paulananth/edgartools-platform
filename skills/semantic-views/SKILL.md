---
name: semantic-views
description: Draft a semantic model in AutoOntology, deploy it as a Snowflake semantic view, and query it through Snowflake MCP. Use when creating or revising OSSIE YAML, SYSTEM$CREATE_SEMANTIC_VIEW_FROM_OSSIE_YAML, logical tables, metrics, Cortex Analyst, or verified queries.
---

# Snowflake semantic views

A semantic view is a **serving projection**. Rules/`CONTEXT.md` own meaning; MDM owns identities and relationships; RDM owns code sets; Silver owns transaction facts. AutoOntology drafts the model. Snowflake deploys and serves it. Read [AutoOntology](../auto-ontology/SKILL.md), [data modeling](../data-modeling/SKILL.md), and [Snowflake operations](../aws-snowflake-operations/SKILL.md) first.

## The four objects

A semantic view has only dimensions, relationships, facts, and metrics. A date is a dimension with a time meaning, not a fifth object.

| Object | Comes from | Rule |
|---|---|---|
| Dimension | Gold-approved MDM master, or gold-approved RDM code set | Identity, descriptive attribute, or code meaning. Never a copied master field. |
| Relationship | The fact table's declared link to that master or code | Foreign key to primary key. State cardinality. Reject a join that multiplies facts. |
| Fact | The fact table, at its own grain | Row-level amount, quantity, date, or link key. Do not repeat an MDM or RDM field here. |
| Metric | An aggregation over a fact, qualified by its logical table | `SUM(orders.total_amount)` deploys. `SUM(TOTAL_AMOUNT)` is rejected. |

The view denormalizes at query time through relationships. It does not create a physical table that copies dimensions onto facts.

## Choose the tool

| Job | Tool | Do not |
|---|---|---|
| Draft logical tables, dimensions, facts, joins, metrics, and synonyms from approved Snowflake tables | AutoOntology | Hand-write the first model, or let it scan unapproved tables |
| Certify the model | A person, against Rules/MDM/RDM/Silver | Treat AutoOntology output as authority |
| Deploy | `SYSTEM$CREATE_SEMANTIC_VIEW_FROM_OSSIE_YAML` | Query through AutoOntology after deploy |
| Ask questions | Snowflake-managed MCP `CORTEX_ANALYST_MESSAGE`, or a Cortex Agent in front of it | Expose `SYSTEM_EXECUTE_SQL` on that same MCP server |

AutoOntology's export is Apache Ossie YAML (`semantic_model.yaml`). It is not a live Snowflake object. After deploy, disconnect AutoOntology as a query path so it cannot become a second model.

## Deploy

1. Scope the questions, database, schema, approved tables, grain, and reader role. Stop if a key or grain is unknown.
2. Inspect sources read-only. Keep exact types: integers are `BIGINT`; decimals are `NUMBER(precision, scale)`. Never print secrets or raw sensitive rows.
3. In AutoOntology, generate and certify Ossie YAML version `0.1.1`. Each field and metric needs a `SNOWFLAKE` expression, with `ANSI_SQL` only as fallback. Other dialects are silently skipped.
4. Qualify every metric by its logical table. `SUM(orders.total_amount)` deploys. `SUM(TOTAL_AMOUNT)` fails on this account with `Unsupported expression in the definition of derived metric`.
5. Prove the YAML on a disposable database and invented rows. Read the procedure result, then drop that database. Do not use a production schema for the proof.
6. Deploy the certified YAML to the approved schema:

```sql
CALL SYSTEM$CREATE_SEMANTIC_VIEW_FROM_OSSIE_YAML(
  '<database>.<schema>',
  $$<certified Ossie 0.1.1 YAML>$$
);
```

The view name comes from the YAML `name`. Replacement preserves grants. The role needs `CREATE SEMANTIC VIEW` on the schema and `SELECT` on every referenced table.
7. Read back the view, owner, and grants. Grant only the approved reader role.
8. Create or update the MCP server so its Analyst tool identifier is that view. Ask positive, negative, boundary, null, and multi-table questions. Compare generated SQL and results with an independent expected answer.
9. Save only reviewed question-SQL pairs as verified queries. Change one element at a time and retest.

## Hard stops

- No production deploy without the named schema, role, and certified YAML.
- No view over an unknown grain, unapproved relationship, or copied MDM field in Silver.
- No `ACCOUNTADMIN`, broad grants, credential-bearing SQL, or secrets in YAML, prompts, logs, or verified queries.
- No claim of correctness from the procedure message alone. Require SQL and result readback.
- Dev Snowflake is decommissioned. Name the production connection explicitly.

## Completion

The certified Ossie model, deployed view, least-privilege grant, MCP Analyst binding, and reviewed question tests all name the same view. Open gaps stay explicit.
