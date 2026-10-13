# Audit dbt invocation sites against the uv convention

Priority: 64, tier 4, housekeeping. Map: [Rebuild priorities](../map.md). Moved from `.scratch/uv-migration/issues/03-audit-dbt-invocation-sites.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task
Status: open
Blocked by: uv-migration 01

## Question

Once the scope boundary (ticket 01) is settled, read each of the following
in full context (not just the grep hit) and decide, per site, whether it
needs the explicit `uv run --with dbt-snowflake dbt ...` prefix or is
legitimately fine as-is:

- `docs/runbook.md:608-610` (`dbt deps` / `dbt run --target prod` / `dbt
  test --target prod`)
- `docs/runbook.md:696` (`dbt test --target prod`)
- `edgar/ai/skills/platform/pipeline-setup.md:341,376` (`dbt run`, `dbt
  test`)
- `infra/scripts/deploy-snowflake-stack.sh:427` (`echo "Running dbt
  deps/run/test"` — check what the actual command a few lines below this
  echo does, not just the log line)

Produces a definitive per-site list (fix / leave-as-is + why) that becomes
part of the eventual migration plan's action list.
