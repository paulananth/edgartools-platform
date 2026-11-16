---
name: semantic-views
description: Draft, certify, and deploy an Explore-only Snowflake semantic view for one Gold fact grain. Use when creating OSSIE YAML, SYSTEM$CREATE_SEMANTIC_VIEW_FROM_OSSIE_YAML, dimensions, joins, facts, metrics, or Cortex Analyst questions.
---

# Snowflake semantic views

A Semantic View is an Explore-only question contract for one Gold fact grain. It is not a physical denormalized table and not an input to a Trading Decision. Read [CONTEXT.md](../../CONTEXT.md), [ADR 0017](../../docs/adr/0017-semantic-view-is-explore-only.md), [data modeling](../data-modeling/SKILL.md), and [Snowflake operations](../aws-snowflake-operations/SKILL.md) first.

## The four objects

| Object | Comes from | Rule |
|---|---|---|
| Dimension | Gold-approved MDM master, or gold-approved RDM code set | An RDM Dimension names its approved code-set version. A date is a Dimension with a time meaning. |
| Join | The fact grain's named link to one Dimension | Must not multiply the grain. Two Joins may reach the same Dimension when each names a different role. Use the time scope that Gold table already declares. Stop if it declares none. |
| Fact | That one Gold table | Row-level amount, quantity, date, or link key. Never a copied MDM or RDM field, and never Silver. |
| Metric | An aggregation over those facts | Qualify it by its logical table. `SUM(orders.total_amount)` deploys. `SUM(TOTAL_AMOUNT)` is rejected. |

Descriptions and synonyms are words on these objects, not a fifth object. A Join is not an MDM relationship. MDM may be the evidence for the link.

## Choose the tool

| Job | Tool | Do not |
|---|---|---|
| Draft the four objects from the approved Gold tables | AutoOntology | Scan unapproved tables, or hand-write the first model |
| Certify the model | A person | Treat AutoOntology output, or a passing question test, as certification |
| Deploy | `SYSTEM$CREATE_SEMANTIC_VIEW_FROM_OSSIE_YAML` | Query through AutoOntology after deploy |
| Ask questions | Snowflake-managed MCP `CORTEX_ANALYST_MESSAGE` | Expose `SYSTEM_EXECUTE_SQL` on that server, or bind the view into the Agent Decision Surface |

Binding a certified view version into the Agent Decision Surface is a separate decision. This skill does not perform it.

## Deploy

1. Name the question, the one Gold fact table, its grain, its declared time scope, the Dimensions, the Joins, and the reader role. Stop if the grain, key, or time scope is unknown.
2. Inspect those tables read-only. Keep exact types: integers are `BIGINT`; decimals are `NUMBER(precision, scale)`. Never print secrets or raw rows.
3. Draft Ossie YAML version `0.1.1`. Each field and metric needs a `SNOWFLAKE` expression. Other dialects are silently skipped. A person certifies it against this contract.
4. Prove the certified YAML on a disposable database and invented rows. Read the procedure result, then drop that database.
5. Deploy only to the approved schema. The view name comes from the YAML `name`. Replacement preserves grants. Grant only the approved reader role and read the grants back.
6. Point the MCP Analyst tool at that view. Compare generated SQL and results with an independent expected answer. A match does not certify the view and does not bind it for a Trading Decision.
7. Save reviewed question-SQL pairs as verified queries. A synonym or metric change needs the YAML certified again.

## Hard stops

- No Silver query, no second fact grain, and no Join that multiplies facts.
- No production deploy without the named schema, role, and person-certified YAML.
- No `ACCOUNTADMIN`, broad grants, credential-bearing SQL, or secrets in the YAML, prompts, logs, or verified queries.
- No claim of correctness from the procedure message alone.
- Dev Snowflake is decommissioned. Name the production connection explicitly.

## Completion

The certified model, deployed view, grants, and question tests name the same Explore-only view. The Agent Decision Surface is unchanged. Open gaps stay explicit.
