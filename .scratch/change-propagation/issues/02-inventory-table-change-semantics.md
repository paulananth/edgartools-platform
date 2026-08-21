# Inventory table-specific change and dependency semantics

Type: task
Status: open
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
