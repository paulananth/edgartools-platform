# 05 — Bulk mode state machine shape

Type: grilling
Status: resolved
Blocked by: 03, 04

## Question

Design the bulk/backfill state machine for the full historical company
universe, in the shape of the platform's existing `load_history` (parallel
bronze/silver Map, then sequential MDM entity resolution, then gold), but
scoped to company-identity data only:

- Parallel Map over the company-identity Bronze/Silver capture mechanism
  ticket 04 settles, at what concurrency?
- `mdm run --entity-type company` + `mdm sync-graph --entity-type company`
  as the MDM/graph stage (pending ticket 03's confirmation these behave
  cleanly company-only).
- Does this need its own gold-refresh step, or does company data feed the
  existing gold tables without a dedicated refresh?
- New state machine name/identity, or a new mode of an existing one?

## Blocked by

03, 04

## Answer

Woven into `load_history` as a new Stage 0, not a standalone state machine:

- **Sequencing:** a new company-identity Map runs immediately after
  `ComputeWindows`, before `Stage1Parallel` (Branch A ownership bootstrap).
  Matches the destination's stated ordering requirement (company data before
  ownership/ADV) and reuses `ComputeWindows`' existing window-batching
  machinery instead of duplicating it.
- **Concurrency:** `MaxConcurrency=1`, matching every existing Branch B stage
  (`entity-facts`/`per-filing`/`thirteenf`). Not a scaling choice — all
  Branch B modes write the same S3-backed unified silver DuckDB file, so
  running two writers concurrently risks a lost publish. True parallelism
  with Branch A isn't safe at any concurrency setting for the same reason;
  sharding the storage layer to unlock real parallelism was explicitly
  ruled out of scope.
- **Per-window command:** `bootstrap-fundamentals --mode company-identity
  --cik-offset <offset> --cik-limit <limit> --run-id <execution-name>` —
  identical shape to entity-facts/per-filing/thirteenf's existing windowed
  Map states (DISTRIBUTED mode, ItemReader over `cik_windows.jsonl`).
- **MDM/graph stage:** none dedicated. `load_history`'s existing `mdm run
  --entity-type all` already resolves companies internally (`run_all()`
  calls `run_companies()` as part of its sweep) — a separate `--entity-type
  company` call would just re-do that work. Company-identity's stage only
  needs to land its silver writes before the existing single MDM chain
  (MdmRun → MdmBackfill → MdmExport → MdmSync → MdmVerify) runs later in
  the same execution.
- **Gold-refresh:** none dedicated — feeds the existing single gold-refresh
  at the end of `load_history`, since company silver data is already on
  disk well before that point.
- **Failure handling:** strict (`ToleratedFailurePercentage=0`, no `Catch`),
  matching Branch A rather than Branch B's lenient AD-13 pattern —
  `IS_INSIDER` relationship derivation depends on resolved Company entities,
  so silently proceeding with unresolved company data would reintroduce the
  exact coupling problem this effort exists to untangle.
- **New state machine vs. mode of existing:** no new state machine —
  `load_history` gains a new phase.

Also surfaced and fixed as a prerequisite: `load_history`'s and
`bootstrap`'s existing windowed Branch B stages share the exact
full-copy-candidate OOM already fixed for company-identity's ad-hoc
`--cik-list` path (see TODOS.md "windowed publish OOM 5-whys", resolved via
`_delta_rows_as_dicts`/SQL `EXCEPT` in `silver_protection.py`, PR #215) —
both `edgartools-prod-load-history` and `edgartools-prod-bootstrap` had zero
prod executions ever, so this was a live landmine, not a hypothetical, and
had to be closed before this new stage could safely run at all.
