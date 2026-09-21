# Decommission the legacy Person code, its tests, and its dead columns

Type: task
Status: open
Blocked by: none (06 resolved 2026-09-20)

## Question

Nothing to decide. [Ticket 06](06-decide-legacy-person-id-crosswalk.md)
resolved that legacy Person IDs are **dropped, not cross-walked** — so the
code that produces them, the tests that pin its behaviour, and the columns
that carry it are dead weight, not a fallback. Operator instruction,
2026-09-20: note the decommissioning of the code and tests.

This is an inventory, not a plan: sequencing and safety are the owner's.
Counts verified 2026-09-20 against `main`.

## Code

| Surface | Path |
| --- | --- |
| Person resolver (`CIKExactMatcher` → `FuzzyNameMatcher` → unused Splink) | `edgar_warehouse/mdm/resolvers/person.py` |
| Person mastering entry | `pipeline.py` `run_persons`; `mdm/cli.py:1007-1009`, `--entity-type person` (`:138`, `:249`), issuer-CIK filter (`:303`), person block at `:872` |
| `IS_INSIDER` / `HOLDS` derivation | `pipeline.py:1740-1938`, `:1940-2139`; closers `:582-656`, `:658-720` |
| `mdm_person` model and golden-record writer | `mdm/database.py:296-318`; upsert `resolvers/person.py:174-203` |
| Person id back-propagation to silver | `edgar_warehouse/mdm_entity_backfill.py` (person branch `:115-120`); CLI `backfill-mdm-entity-ids` (`cli.py:303`, `:1450`) |
| Person read surfaces | `mdm/api/routers/persons.py`; `MDM_PERSON` mirror (`mdm/export.py:26`); graph person nodes (`snowflake_graph.py:1355-1372`) and `GRAPH_EDGE_IS_INSIDER` / `GRAPH_EDGE_HOLDS` views (`:1559-1567`); `dashboard_readonly.py`; `coverage.py` |
| Thresholds and survivorship seeds | `002_seed_data.sql:54-55`, `:62-64`, `:240-249` |

## Tests

15 files under `tests/` reference `MdmPerson`, `PersonResolver`,
`run_persons`, `_derive_is_insider` or `_derive_holds` — including
`test_run_persons_skip_unchanged.py`,
`test_run_securities_persons_concurrency.py`,
`test_pipeline_relationships.py`, `test_api.py`,
`test_relationship_coverage.py`. They pin legacy behaviour that the
Person contract deliberately replaces (notably that `REVIEW` binds), so
they are **removed with the code, not ported**.

## Dead columns

`sec_ownership_reporting_owner.mdm_entity_id` and
`sec_adv_filing.mdm_entity_id` are frozen as legacy: never read, never
rewritten by Clean MDM (ticket 06). Whether they are dropped from
`silver_schema.py` / `11_silver_landing_schema.sql` or left in place is
the silver owner's call — they are held equal by
`tests/unit/test_silver_schema_snapshot.py`, and both columns are also
selected by the dbt silver passthrough models
(`models/silver/sec_ownership_reporting_owner.sql:26`,
`sec_adv_filing.sql:21`). Note `sec_ownership_*_txn.mdm_entity_id` is a
**security** id, not a person id (`mdm_entity_backfill.py:122-134`) — out
of scope here.

## Sequencing

Do not start before the Clean MDM Person consumer is live: until then
these paths are the only Person production there is, however flawed. The
gate is the Person contract's release gates ([ticket 08](08-write-person-consumer-spec.md)),
not this map's completion.

Production code: own branch, the mandatory `/gof-refactor-reviewer`
consult, the three-axis `/code-review`.
