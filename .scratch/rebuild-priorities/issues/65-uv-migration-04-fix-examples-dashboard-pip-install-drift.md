# Fix examples/dashboard's bare pip install drift against CLAUDE.md's own dev command

Priority: 65, tier 4, housekeeping. Map: [Rebuild priorities](../map.md). Moved from `.scratch/uv-migration/issues/04-fix-examples-dashboard-pip-install-drift.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task
Status: open
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
