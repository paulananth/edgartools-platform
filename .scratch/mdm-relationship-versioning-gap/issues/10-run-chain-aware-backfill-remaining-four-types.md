Type: task
Status: resolved
Blocked by: 09

## Question

Run the already-proven chain-aware quarantine backfill (Ticket 09's
`relationship_quarantine_backfill.py`, deployed and live-verified for
INSTITUTIONAL_HOLDS) against the remaining four relationship types this
map's Destination names: `COMPANY_HOLDS`, `HOLDS`, `EMPLOYED_BY`,
`IS_INSIDER`. No code change is expected -- confirmed live (grep) the
mechanism has zero INSTITUTIONAL_HOLDS-specific logic, just a rollout-
sequencing comment; `relationships_conflict`/`confirmed_chronologically_after`/
`resolve_source_priority`/`_resolve_source_priority_cached` are all generic
over `rel_type_id`. `MANAGES_FUND` stays out of scope (Ticket 08's own
"Out of scope" correction: a structurally different, write-time
conflict-blindness bug, not a backfill-design gap -- needs its own future
map).

Per this map's own standing preference: real measurements against live
prod data, not estimates -- a dry-run first per type (or combined) to
capture the actual quarantine-row shape (conflict counts, chain depth,
skip-category breakdown) before any real (non-dry-run) execution, which
needs its own explicit go-ahead per this map's established precedent.

Per CLAUDE.md hard rule: `/gof-refactor-reviewer` before any code change
(not expected to be needed here), full 3-axis `/code-review` before any
commit (only applies if a real code change turns out to be needed).

After each type's real run: rebuild the Snowflake graph
(`mdm publish-relationships` -> `mdm reconcile --generation-id` ->
`mdm graph-activate`, the same three-step lifecycle Ticket 09 used) so
the graph reflects the correction, not just Postgres.

## Answer

**Combined dry-run against all 4 types** (real prod, exit 0, ~10.4 min):
7,672 relationship_ids examined, 133,184 closed, 155,881 reopened,
skipped_ambiguous_order 7,262,670, skipped_multiple_conflicts 123,386,
skipped_cross_source 363. That `skipped_ambiguous_order` figure is ~16x
higher per-relationship_id than INSTITUTIONAL_HOLDS' own dry-run --
investigated before proceeding rather than assumed benign.

**Per-type breakdown found the cause: COMPANY_HOLDS is contaminated,
the other 3 are clean.** Live query against Postgres:

| type | distinct quarantined rel_ids | max rows/rel_id | max same-date group |
|---|---|---|---|
| COMPANY_HOLDS | 3,916 | 27,849 | 873 |
| HOLDS | 1,116 | 676 | 342 |
| EMPLOYED_BY | 2,472 | 31 | 9 |
| IS_INSIDER | 168 | 179 | 18 |

COMPANY_HOLDS' outlier rows all trace to individual people (Mark
Zuckerberg, Jensen Huang, Javier Olivan and ~32,948 others) misclassified
as `company` entities instead of `person` -- a pre-existing, unrelated
upstream data-quality bug, not a quarantine-backfill-mechanism issue. Full
root cause and blast radius:
[individual-filer-company-misclassification map](../../individual-filer-company-misclassification/map.md).

**Decision (explicit, this session):** split COMPANY_HOLDS out of this
ticket's scope entirely -- backfilling its quarantine flags now would
resolve conflicts sitting on top of contaminated entity data, making the
contamination look clean instead of surfacing it. HOLDS/EMPLOYED_BY/
IS_INSIDER are confirmed clean at normal scale and proceed under this
ticket. COMPANY_HOLDS is blocked on the misclassification map's fix +
cleanup decision, not tracked as a sub-item here.

**Real (non-dry-run) backfill executed against prod 2026-09-10, scoped to
`--relationship-type HOLDS --relationship-type EMPLOYED_BY
--relationship-type IS_INSIDER`.** Exit code 0, ~28.8 min. Final summary:

```json
{
  "closed": 19756,
  "relationship_ids_examined": 3756,
  "reopened": 19960,
  "skipped_ambiguous_date": 0,
  "skipped_ambiguous_order": 292801,
  "skipped_cross_source": 363,
  "skipped_multiple_conflicts": 16929,
  "skipped_priority_now_configured": 0
}
```

Graph rebuild completed same-day: `mdm publish-relationships` (generation
`ae0db138-2aeb-4e69-87ba-f812da92b2eb`, 233,647 nodes / 575,485 edges,
exit 0) -> `mdm reconcile --generation-id` (exact parity, `"parity": "ok"`,
`"capability": "ok"`, exit 0) -> `mdm graph-activate` (activated,
superseding `db802e24-...`, exit 0). All four now-live types
(INSTITUTIONAL_HOLDS + HOLDS/EMPLOYED_BY/IS_INSIDER) are corrected in both
Postgres and the Snowflake graph.

COMPANY_HOLDS remains blocked on
[individual-filer-company-misclassification](../../individual-filer-company-misclassification/map.md)
-- resolved as its own map, not tracked further under this ticket.
