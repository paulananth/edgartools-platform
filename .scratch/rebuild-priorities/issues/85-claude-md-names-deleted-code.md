# CLAUDE.md names code the rebuild deleted

Priority: 85, tier 2. Map: [Rebuild priorities](../map.md).

Type: task (documentation). Status: in review (branch `claude/claude-md-deleted-code`). Blocked by: 78 (Skills hold every learning: its sweep routed the hard-won rules first).

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

- [x] List every path, command and state machine `CLAUDE.md` names, and check each against main (a script, so it can run again): `scripts/dev/stale_paths.py` (paths; git-ignored ones aside), held by `tests/unit/test_guides_name_existing_paths.py`; 37 missing paths in `CLAUDE.md`, 14 in `AGENTS.md`. Commands and state machines checked by search: `edgar-warehouse bootstrap` and the Step Function builders (`write_warehouse_mdm_gold_definition`, `load_history` and the rest) are gone; `mdm migrate`, `doctor`, `SNOWFLAKE_RUN_MANIFEST_TASK`, `LOAD_EXPORTS_FOR_RUN`, `REFRESH_AFTER_LOAD`, `GRAPH_ACTIVE_POINTER`, `gold_model_config`, `bootstrap-prod-mdm.sh` and the four Dockerfiles exist 2026-10-16 08:29 ET
- [x] Remove or reword each stale line, by the rule above: Quick Navigation and Architecture rewritten as pointers to the rebuild; the data layers reworded; the Phased Pipeline section (330 lines on deleted Step Functions, commands and the parser import pattern) replaced by its three Snowflake facts that are still live (gold refresh, graph inside Snowflake, MDM on Snowflake Postgres); four Known open items about deleted code dropped, and the orphaned-bootstrap-SQL item dropped as resolved (`install.sh` now runs 16 and 17); the Development Commands' deleted `bootstrap` example replaced by `doctor`; Key Large Files now lists files that exist. CLAUDE.md 1,385 to 960 lines after review 2026-10-16 08:29 ET
- [x] The same check on `AGENTS.md`: High-Value Files rows for the deleted runtime, settings, silver, gold and parsers replaced by the rebuild's; large-file list and the parser notes reworded 2026-10-16 08:29 ET
- [x] Three-axis review 2026-10-16 08:33 ET. GoF: leave it. Standards (fixed): the script's docstring claimed it checked bare top-level files; it now says what it skips. Spec (fixed): the ECS sizing section (deleted MDM commands) is now its method and a pointer to the evidence; the rule to look for a Step Function before running steps by hand contradicted the new text and now points at Bookkeeping; the dev-only deploy example and the dev `--full-refresh` gap are rewritten for prod and as the general grant rule; the `scripts/batch/` smoke-test rule, removed with the parser notes, is back under edgartools Dependency; the hosting line now says target versus provisioned. Dropped on purpose: the "two graph-generation activation paths" item, whose commands and Postgres tables are deleted; `GRAPH_ACTIVE_POINTER` in Snowflake stays, described under the Snowflake facts
- [ ] PR #1006, CI green, merge on the operator's word
- [x] Learning → skill: none; the rule (a guide names only what exists) is now a test, `tests/unit/test_guides_name_existing_paths.py` 2026-10-16 08:29 ET
