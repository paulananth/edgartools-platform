# Silver outputs

Type: task
Status: open
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
