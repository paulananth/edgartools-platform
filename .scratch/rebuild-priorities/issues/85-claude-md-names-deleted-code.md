# CLAUDE.md names code the rebuild deleted

Priority: 85, tier 2. Map: [Rebuild priorities](../map.md).

Type: task (documentation). Status: open. Blocked by: 78 (Skills hold every learning: its sweep routed the hard-won rules first).

## Why

Found in ticket 78's sweep (2026-10-15). `CLAUDE.md` is read at the start of every Claude session, and several of its sections still describe the old pipeline, whose code is gone. A session that trusts them looks for files that do not exist, or follows rules for commands that no longer run. Operator, 2026-09-26: the rebuild is the only system; do not preserve old behaviour.

Paths `CLAUDE.md` names that no longer exist on main:
- `edgar_warehouse/application/warehouse_orchestrator.py` (Quick Navigation, the Architecture diagram, Key invariants, Key Large Files);
- `edgar_warehouse/runtime.py`, `edgar_warehouse/application/command_router.py`;
- `edgar_warehouse/serving/source_dimensional_export.py`, `edgar_warehouse/silver_landing_store.py`;
- `edgar_warehouse/parsers/ownership.py`, `edgar_warehouse/parsers/adv.py` (with the "Key import pattern" section built on them).

Still present: `edgar_warehouse/silver_schema.py`, the Streamlit apps, `scripts/batch/`.

Sections to check whole: Quick Navigation, Architecture, Phased Pipeline (and its Key invariants, graph storage and MDM database notes), Known open items, Key Large Files, edgartools Dependency.

## Rule for each line

- A line about deleted code goes. Snowflake and deployment rules stay (operator, 2026-10-14: "Snowflake is still the target platform").
- A line still true but stale in its names is reworded to what exists now.
- What the rebuild has in their place (the source engine, Bookkeeping, Clean MDM, the skills) gets a short pointer, not a description: the skills and `AGENTS.md` hold the detail.

## Checklist

- [ ] List every path, command and state machine `CLAUDE.md` names, and check each against main (a script, so it can run again)
- [ ] Remove or reword each stale line, by the rule above
- [ ] The same check on `AGENTS.md`
- [ ] PR, CI green, merge on the operator's word
- [ ] Learning → skill
