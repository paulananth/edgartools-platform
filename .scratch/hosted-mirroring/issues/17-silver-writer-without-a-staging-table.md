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

## Decision to take (one at a time, with a recommendation)

- [ ] Duplicate keys in one delivery without a staging table. Recommendation: the batched upsert stamps each row it writes with the delivery's own time, so a key met a second time finds its row already stamped by this delivery and refuses. Needs the added-time column on every spec: read which specs lack it first.
- [ ] Snapshot deletes without a staging table. Recommendation: the delivered keys are held on disk in sorted runs (`keyset.py` already does this) and the table's keys are read in key order and compared with them; absent keys are deleted in batches. Alternative: stamp every delivered row (writes unchanged rows too).

## Checklist

- [ ] Consult `/gof-refactor-reviewer` on `relational.py` before code (more than ten lines)
- [ ] Failing test first, at the public `write`: a PostgreSQL delivery on a role that holds no `TEMPORARY` privilege succeeds, and a duplicate key still refuses
- [ ] One batched upsert path for every load mode; MySQL's shared staging table is handled in the same change or kept as its own deferred part
- [ ] Storage-adapter tests on PostgreSQL and MySQL (`bash scripts/dev/adapter_test.sh`)
- [ ] `TEMPORARY` revoked from the loader in provisioning and the reset script, tested
- [ ] Standards, Spec and GoF review of the diff
- [ ] Learning → skill: name the skill line this ticket changed, or "none"
