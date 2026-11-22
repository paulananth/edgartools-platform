# 17: The silver writer loads without a staging table

Status: open
Type: task

Operator, 2026-11-22, asked what the TEMPORARY privilege part of ticket 14 meant, then ruled: "no staging table needed remember 7 wastes".
The writer (`edgar_warehouse/silver_writer/relational.py`, `DatabaseSink.write`) creates a temporary table per delivery on PostgreSQL, loads the
delivery into it and merges that into `silver.<table>`. That moves every row twice (Transport and Over-processing, the seven wastes of the
data-platform skill) and needs the `TEMPORARY` privilege, which the no-DDL rule says a worker should not hold.

## What the staging table does today (read from the code)

1. Finds a key delivered more than once (a refusal).
2. Finds the rows the table lacks (insert), the rows whose values differ (count, then update) and, for append tables, refuses a changed row.
3. Updates the MDM id and quality columns where they differ.
4. For a snapshot table, deletes the rows the delivery does not hold, after refusing an empty delivery.

## Ruling (operator, 2026-11-22)

"why do we have a staging before silver the staging is part of source processing all that silver needs is final list of tables".
Source processing owns the final rows of a table, so it owns a key delivered twice; silver applies the rows by key. Silver's own
duplicate check and staging table are the same work done a second time (Over-processing).

## What silver still has to do, and what is open

- [ ] Apply by key, idempotently, in batches: insert a missing key, update a changed one, leave an equal one (a retry lands the same rows again with no change). Append tables refuse a changed row.
- [ ] Where the duplicate-key refusal now lives: in source processing. Finding (read 2026-11-22): a Source Extract does not guarantee it. The source-contract engine rejects duplicate JSON keys and header names, not a table's silver key; the source-contract spec (section 13.1) only *proposes* a validator that an adapter's record key columns are unique, and `source.combine` groups and joins by declared key without a uniqueness check. Silver's check is today the only one, so it stays until source processing refuses a repeated key (a declared check in the contract or in `source.combine`), proved by a test at the source extract.
- [ ] Snapshot tables (three of the registered specs): who removes a row the final list no longer holds. Recommendation: source processing hands the removal with the list, since it holds the previous final list; silver deletes by key.

## Decision (operator, 2026-11-22: "recommend a declared uniqueness check in the source contract")

A source contract declares the key of each table it reads, and the engine refuses a source extract whose table repeats it. What I found when
scoping it: the contract spec's `silver:` block names a `key`, but the sources in the repository no longer carry that block; the key of a
silver table lives in its registered spec (`rules/silver/*.yaml`), and the engine's Rust crate never reads a key. So the declaration is new
in `read.tables.<table>`, and a catalog check refuses a contract whose declared key differs from the registered silver spec's key (one fact
written twice must be proved equal, not trusted). The check is on one source extract, one captured file: a key repeated across two files is
a later delivery of the same row, which the per-key apply already leaves unchanged. A refusal names the table and the key columns, never a value.

## Checklist

- [ ] Spec first: `docs/specs/source-contract/spec.md` section 8.4 gains `key` on a table and the refusal; the section 13.1 proposal becomes the rule
- [ ] Test first at the source extract: a table with a repeated key is refused (names the table and columns, no value); a table with distinct keys passes
- [ ] The engine enforces it (the Rust crate and its Python caller), by the cheapest proof for a large extract (sorted keys, not an in-memory set of every row)
- [ ] The catalog check: a declared contract key must equal the registered silver spec's key
- [ ] Every source in `sources/` declares its tables' keys; the sources already holding repeated keys are listed and fixed in their own parts


- [ ] Consult `/gof-refactor-reviewer` on `relational.py` before code (more than ten lines)
- [ ] Failing test first, at the public `write`: a PostgreSQL delivery on a role that holds no `TEMPORARY` privilege succeeds, and a duplicate key still refuses
- [ ] One batched upsert path for every load mode; MySQL's shared staging table is handled in the same change or kept as its own deferred part
- [ ] Storage-adapter tests on PostgreSQL and MySQL (`bash scripts/dev/adapter_test.sh`)
- [ ] `TEMPORARY` revoked from the loader in provisioning and the reset script, tested
- [ ] Standards, Spec and GoF review of the diff
- [ ] Learning → skill: name the skill line this ticket changed, or "none"
