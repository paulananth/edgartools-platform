# 05b Relationships at a past recording time (`--as-at`)

Type: task. Phase: A. Blocked by: 05. Map: [map](../map.md). Plan: [plan](../plan.md).

Ticket 05 deferred `edgar-warehouse context relationship <entity> --as-at <time>`:
no index finds one entity's links in the batch history
(`docs/specs/agent-context/spec.md` §2: "A versioned relationship table would
make it cheap"). The operator, 2026-10-08: "Yes" (take relationship
`--as-at` next, while Codex finishes the old-parser retirement).

## Design (for the operator's approval)

- **New table `mdm.relationship_version`** (migration 010), shaped like `mdm.company`: one row per relationship
  per change, `relationship_id`, `from_generation`, `to_generation`, `valid_from`, `valid_to` (recording time),
  `batch_id`, `source_id`, `target_id`, `type`, `body`; indexes on `source_id` and `target_id`.
- **Written by a trigger** on `mdm.current_record` for relationship rows: a changed body closes the open version
  and opens a new one; an unchanged body writes nothing. `write_batch` is not rewritten.
- **Backfill** in the same migration from `mdm.batch.effects`, in generation order, so history before the
  migration is kept; tested on a populated database.
- **`--as-at`:** the walk reads the versions open at the generation `--as-at` picks (the same generation the
  entity lookup uses); `--as-of` and no flag read `current_record` as today.

## Checklist

- [x] Design approved by the operator (data model): "Approve (Recommended)" 2026-10-08 10:11 ET
- [x] GoF consult on context.py's walk and the batch write path: the walk gains a second FROM (versions at a generation) beside current_record, one query either way; the write path is untouched (a trigger, as company versions are a function call); Rule 0, no pattern needed 2026-10-08 10:11 ET
- [x] Migration 010: table, comments, indexes, trigger, backfill (stops if history does not end at the current state); registered in store.py 2026-10-08 10:21 ET
- [x] Tests on PG16 (`tests/integration/test_clean_relationship_version_postgres.py`, 3): every change one version and an unchanged link none, the open version equals the current state; `--as-at` before and after a parent change, for the relationship walk and the entity lookup, each within 8 KB; 010 dropped and re-applied on a populated store gives the same history and the trigger writes again 2026-10-08 10:21 ET
- [x] context.py: `--as-at` reads versions at its generation (relationship walk and the entity lookup's related links); the refusal and the note removed; the trust block is that generation's 2026-10-08 10:21 ET
- [x] Spec §2 and ticket 05's deferral updated; no CONTEXT.md term changes 2026-10-08 10:21 ET
- [x] Affected tests: 225 clean-MDM, fresh-mastering and context PG tests pass (1 expected failure); testmon over unit and mdm: 405 pass 2026-10-08 10:21 ET
- [ ] Three-axis review (Standards, Spec, GoF)
- [ ] PR, CI, merge on the operator's word
- [ ] `mdm migrate` for 010 in prod: blocked like 005–009 (no login), listed
