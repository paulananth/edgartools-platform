# Audit dbt invocation sites against the uv convention

Priority: 64, tier 4, housekeeping. Map: [Rebuild priorities](../map.md). Moved from `.scratch/uv-migration/issues/03-audit-dbt-invocation-sites.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task
Status: in review (2026-10-18)
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

## Answer: each site (read in context, 2026-10-18 12:37 ET)

| Site | Decision | Why |
|---|---|---|
| `docs/runbook.md` prod deploy step (`dbt deps`, `dbt run --target prod`, `dbt test --target prod`) | fixed | an operator runs it as written; now `uv run --with dbt-snowflake dbt ...` |
| `docs/runbook.md` verify step (`dbt test --target prod`) | fixed | the same |
| `edgar/ai/skills/platform/pipeline-setup.md:341,376` | none | the file no longer exists |
| `infra/scripts/deploy-snowflake-stack.sh` ("Running dbt deps/run/test") | leave | a log line; the three commands below it already run through `uv run --with dbt-snowflake` |
| `infra/scripts/install.sh` | leave | already `uv run --with dbt-snowflake dbt run` |
| Prose that names a dbt command (`docs/runbook.md` overview and step lists, `CLAUDE.md`, `TODOS.md`, `CONTEXT.md`, `docs/data-architecture.md`, `docs/prodb-to-prod-promotion.md`, ADR 0003, SQL comments; `AGENTS.md`'s commands already use `uv run --with dbt-snowflake`) | leave | describes a command, does not run one |

## Checklist

- [x] Every bare `dbt deps|run|test|compile|build|seed|debug` outside `.scratch/` and `.planning/` found by grep and read in context; table above (2026-10-18 12:37 ET)
- [x] The two runbook sites fixed (2026-10-18 12:37 ET)
- [x] Three-axis review (2026-10-18 12:45 ET): Standards and GoF no findings; Spec found two prose files the table did not name (named)
- [ ] PR, CI green, merged on green
- [ ] Learning → skill
