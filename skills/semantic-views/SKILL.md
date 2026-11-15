---
name: semantic-views
description: Design, validate, deploy, and test Snowflake semantic views for governed business questions. Use when creating or revising CREATE SEMANTIC VIEW definitions, logical tables, dimensions, facts, metrics, relationships, Cortex Analyst context, grants, or verified query pairs.
---

# Snowflake semantic views

A semantic view is a **serving projection** for business questions. It is not a new system of record. Rules/`CONTEXT.md` own definitions and processing policy; MDM owns mastered identities and relationships; RDM owns approved code sets; Silver owns transaction facts; OpenMetadata catalogs the governed assets. Read [data catalog](../data-catalog/SKILL.md), [data modeling](../data-modeling/SKILL.md), and [Snowflake operations](../aws-snowflake-operations/SKILL.md) before changing a view.

## Workflow

1. **Scope the question.** Record the business questions, audience, target database/schema, selected physical tables, grain, freshness need, and permitted role. Name what the view will not answer. Resolve the source product and table list from Rules/OpenMetadata; do not invent tables from a screen.
2. **Inspect sources read-only.** Read columns, exact types, primary/unique and foreign keys, nullability, row counts, sample shapes, date ranges, existing queries, and current grants. Use the approved Snowflake connection and reader role. Never print connection values or raw sensitive rows. If a table's grain or key is unknown, stop and mark it unresolved.
3. **Map logical tables.** For each physical table, define a stable logical name, business description, grain, primary key, source relation, and ownership. Reuse platform logical identities; a semantic-view name is not a new business identity.
4. **Classify columns.** Mark dimensions for grouping/filtering, time dimensions for dates/timestamps with timezone and business meaning, and facts for row-level numeric values. Keep exact numeric types: integers are `BIGINT`/64-bit; decimals are exact `NUMBER(precision, scale)`. Do not expose a duplicated MDM field from Silver as a new fact.
5. **Define relationships.** Use declared foreign-key-to-primary-key paths or evidence-backed joins. State cardinality, direction, null behavior, and grain preservation. Reject many-to-many joins that multiply facts unless a bridge and aggregation rule are explicit. A similar name is not a join key.
6. **Add metrics.** Define exact aggregations, units, grain, filters, null handling, denominator, and time basis. Examples: `SUM(amount)` as revenue; `COUNT(DISTINCT customer_id)` as customers. Test additive and non-additive measures separately. Reuse approved Rules/MDM/RDM meanings; do not create a conflicting definition in the view.
7. **Add business context.** Write plain descriptions, synonyms, and usage/avoidance notes for tables, columns, dimensions, facts, relationships, and metrics. Keep review state separate from creation. Include the source logical key and rules/provenance reference in the design artifact.
8. **Generate and validate DDL.** Produce `CREATE SEMANTIC VIEW` from the reviewed model, not by hand-editing a deployed copy. Compile in an isolated target first. Fix syntax, identifier, type, join, aggregation, and unsupported-feature errors. Preserve a deterministic DDL artifact and review diff.
9. **Deploy safely.** Use the explicit production Snowflake connection and approved deployer/loader ownership rules. Apply through the repository's approved Snowflake/dbt/deploy path; never use a deprecated dev target or an ad hoc account role. Create or replace only the named view, preserve grants where supported, and grant the minimum reader role. Read back definition, dependencies, owner, and grants.
10. **Test business questions.** Send positive, negative, boundary-date, null, duplicate-key, and multi-table questions through Cortex Analyst. Inspect generated SQL, selected tables, joins, filters, grain, aggregations, row counts, truncation, and results. A successful response is not proof of correctness; compare against an independently computed expected answer.
11. **Add verified query records.** Save only reviewed question-and-SQL pairs with the semantic-view version, source revision, expected grain, and validation evidence. A VQR is an optimization and regression fixture, not a business-definition authority. Never store secrets or raw sensitive values in it.
12. **Iterate by evidence.** Audit unanswered, ambiguous, wrong-grain, duplicated-row, and wrong-metric questions. Change one semantic element at a time, recompile, reread grants, and rerun affected positive and negative questions. Keep a rollback DDL and the prior verified query set.

## Hard stops

- No production write without the explicit target, role, scope, and reviewed DDL.
- No semantic view over an unqualified table, unknown grain, or unapproved relationship.
- No copied master fields in Silver or redefinition of MDM/RDM meaning.
- No broad grants, `ACCOUNTADMIN`, credential-bearing SQL, or secrets in files, prompts, logs, VQRs, or output.
- No claim that a view is correct from compilation alone; require SQL and result readback.

## Completion

The view has an approved question scope, source/grain/key mapping, dimensions/time dimensions/facts, evidence-backed relationships, exact metrics and context, compiled DDL, least-privilege grants, readback, positive and negative Cortex Analyst tests, and reviewed VQRs. Open gaps remain explicit.
