# Profiling ranks several sources from their data

Priority: 110, tier 1, in flight (raised by the operator, 2026-10-18). Map: [Rebuild priorities](../map.md).

Type: task (data-profiling skill). Status: done (#1080 merged 2026-10-18 13:07 ET). Blocked by: none. Unblocks: 84 (which filed words a Security keeps).

## Why

Operator, 2026-10-18: "rewrite the data profiling skill to profile multiple data source and re pritiase based on the data", after ruling on ticket 84: "explain the issue rerun the data profile on both sources and make openfigi priority 1 and 13f last".

A master field takes its value from the first source in its priority list that supplies it (`kinds.<kind>.defaults.sources`, or a field's own `sources`). Today that order is written by hand. The profiler measures one data set at a time, so nothing measures which source states a field best.

## Design

- A new script beside `match_names.py`: `rank_sources.py`. It does not change `profile_data.py` or `profiling/`, so every source's `profiled_with` fingerprint stays and approved findings stay reused.
- Input: each source's records (JSON Lines, CSV or Parquet), its key (the shared identifier), and per field the column or dotted path holding it (lists walked). A key may repeat (one row per filing), so a source's disagreement with itself is measured.
- Per field and source, values compared normalised (upper case, trimmed, punctuation and spaces folded):
  - **coverage**: keys it fills, of all keys any source fills;
  - **one value**: of the keys it fills, those with exactly one value;
  - **agreement**, pairwise only: of the keys two sources both fill, those where they share a value. Never agreement with a majority: two sources copying one filer's words can agree and both be wrong.
- Recommended order per field: by one value, then coverage (the first source wins where it fills, so it should state one value; the next fills its gaps). A field-level `sources` list and a `defaults.sources` list, in the form the merge rules take. Advice only: refining-rules applies it.
- Output `ranking.yaml` (agents) and `RANKING.md` (operator): names and counts only, no values.

## Checklist

- [x] GoF consult: a new script, no existing code touched; the reader idiom follows `match_names.py`; leave it (2026-10-18 12:56 ET)
- [x] `rank_sources.py` with tests on invented records: each measure, the order, a key repeated, nested paths, a field-level order and a tie, a JSON array and number keys joining text keys, counts only, and the profiler's fingerprint unchanged by a changed copy of the script (it moves when `profiling/` changes); 8 tests and the genericity test pass (2026-10-18 13:01 ET)
- [x] SKILL.md: the mode in the Modes table and "Rank several sources"; the discovery-story section unchanged; refining-rules (measure before reordering) and data-onboarding (rank a new source of a kind) point to it (2026-10-18 13:01 ET)
- [x] Three-axis review (2026-10-18 13:01 ET): Standards found a `.json` file retyped by DuckDB and a float key that would not join (both fixed, tested) and an overstated memory claim (reworded); Spec asked for the order in the kind file's shape (`merge_rules`), named ties and a fingerprint test that can fail (all done); GoF: leave it
- [x] PR, CI green, merged on green: #1080, merged 2026-10-18 13:07 ET
- [x] Run it for ticket 84 (OpenFIGI, N-PORT, 13F); the numbers on that ticket: 405,016 CUSIPs, 2 min 35 s, `ranking.yaml` and `RANKING.md` beside ticket 84's evidence (#1085, merged 2026-10-18 14:04 ET)
- [x] Learning → skill: data-profiling's "Rank several sources"; refining-rules measures before reordering; data-onboarding ranks a new source of a kind (#1080)
