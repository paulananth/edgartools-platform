# Silver outputs

Type: task
Status: superseded (2026-10-08) by profiling plan decision 36 and profiling ticket 06 (`.scratch/profiling/issues/06-silver-writer.md`): silver for the trials and the proof is a `silver` schema on PostgreSQL 16 behind one sink interface, written by `edgar-warehouse silver` from profiling's silver table specs. The Delta and Lakebase outcome below, and its `deltalake` extra, are not built. A `rules run --target silver` entry point is not built; scheduled landing waits for a silver output worker (Bookkeeping) and a warehouse sink, each its own ticket.
Earlier: open: listed under Not yet specified in `mastering-to-done/map.md` (2026-10-02 audit, mastering to-do 01).
Was: open
Blocked by: 03

## Outcome

`rules run <source> --target silver` writes typed rows to `lakehouse` (Delta
tables, merged on the key, partitioned) and/or `lakebase` (Postgres upsert),
as set in `rules/outputs.yaml`. Built for Databricks lakehouse and Lakebase.

## Checklist (times ET)

- [ ] `/gof-refactor-reviewer` before code.
- [ ] `silver.py`: a pyarrow table, then `deltalake` write/merge, and a
  Postgres `ON CONFLICT` upsert.
- [ ] New optional extra `rules = ["jsonschema", "deltalake"]`, added to the
  CI `uv sync` lines.
- [ ] Tests:
  - a Delta merge rerun is idempotent;
  - the partition layout is right;
  - the Postgres upsert works;
  - a changed schema is refused without a new version.
- [ ] Three-axis `/code-review`, then PR and CI.
