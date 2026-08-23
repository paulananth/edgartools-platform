# Inventory table-specific change and dependency semantics

Type: task
Status: resolved
Blocked by: none

## Question

What factual matrix must later decisions use for every current silver landing
table and downstream consumer?

Create `.scratch/change-propagation/assets/table-change-semantics.md` mapping:

- silver table and declared business key;
- append, upsert, replacement-scope, and retirement behavior in current writers;
- fields that are domain content versus volatile operational metadata;
- source identity and parser/schema version inputs;
- MDM entity/relationship consumers and required neighboring keys;
- dbt silver and gold descendants;
- graph node/edge eligibility impact; and
- current ability—or inability—to represent deletion, no-op, and retry.

This is a read-only inventory task. It does not choose the target contract or
implement any pipeline change; it provides the evidence those decisions need.

## Answer

[Silver table change and dependency semantics](../assets/table-change-semantics.md)
reflects all 31 current landing tables and records their business keys, writer
authority, source/version metadata, MDM and graph closure, dbt descendants, and
deletion/no-op/retry limits.

The inventory confirms that keyed DuckDB upserts are not equivalent to a
change-processing contract: Snowflake landing has no lifecycle operation,
source revision, semantic no-op identity, exact-file load barrier, or complete
empty scope. Local replacement deletes for ticker catalogs, former names, and
submission-file manifests are not exported, while downstream MDM/graph
dependencies currently live in dispersed code rather than a versioned registry.
