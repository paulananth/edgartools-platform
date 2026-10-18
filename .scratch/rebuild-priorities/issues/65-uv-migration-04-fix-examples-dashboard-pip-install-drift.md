# Fix examples/dashboard's bare pip install drift against CLAUDE.md's own dev command

Priority: 65, tier 4, housekeeping. Map: [Rebuild priorities](../map.md). Moved from `.scratch/uv-migration/issues/04-fix-examples-dashboard-pip-install-drift.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task
Status: in review (2026-10-18)
Blocked by: uv-migration 01

## Question

`examples/dashboard/README.md:45` instructs `pip install -r
examples/dashboard/requirements.txt`. CLAUDE.md's own Development Commands
section documents the dev setup for this exact directory as `uv pip install
-r requirements.txt` (under "Standalone dashboard (local)"). [Ticket
01](../../uv-migration/issues/01-scope-boundary-internal-vs-user-facing.md) confirmed this is category
1 (this repo's own dev setup, already prescribed to use uv elsewhere in the
same repo's docs) — not a category-2 published-package install hint, so it's
in scope for this migration.

Update `examples/dashboard/README.md` to match CLAUDE.md's `uv pip install`
command, and check whether any other line in that README (or a sibling
`requirements.txt`-driven setup step) has the same drift.

## Checklist

- [x] `examples/dashboard/README.md`: `uv venv` and `uv pip install -r examples/dashboard/requirements.txt`, as CLAUDE.md's "Standalone dashboard (local)" says (2026-10-18 12:37 ET)
- [x] The same drift elsewhere in this repo's own setup steps, `docs/runbook.md`: the tools table (uv; SnowCLI by `uv tool install`; dbt-snowflake fetched per run by `uv run --with`), the clone step (`uv sync --extra s3 --extra snowflake`) and the external Streamlit step (`uv pip install`), and the verify step's `edgar-warehouse --help` and `python -c` (now `uv run`, since `uv sync` activates nothing; found by the Spec review). Verified by `grep -rn "pip install"` over the repo outside `.scratch/` and `.planning/`: only `uv pip` lines and the deps Dockerfiles (image builds, out of scope) (2026-10-18 12:37 ET)
- [x] Three-axis review (2026-10-18 12:43 ET): Standards asked for the grep's scope and result (now named); Spec found the two verify commands (fixed); GoF: leave it
- [ ] PR, CI green, merged on green
- [ ] Learning → skill
