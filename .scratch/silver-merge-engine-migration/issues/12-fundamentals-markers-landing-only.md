# 12 — Make the fundamentals markers landing-only

**Type:** task

**Status:** resolved in code 2026-09-14; live verification owed with Tickets 02/03's entity-facts run.

## Question

`SilverDatabase.mark_fundamentals_accession_processed` and `mark_entity_facts_refreshed` are the
last fundamentals writers that still touch local DuckDB. Each runs `INSERT ... ON CONFLICT ...
RETURNING` and then records the returned row to `landing_export`. The local copy is dead:
- Cutover Ticket 10 made the local store ephemeral.
- Both readers already query Snowflake silver through `source` (cutover Ticket 17):
  - `_get_processed_accessions`, the per-filing and 13F skip;
  - `get_ciks_with_new_qualifying_filing`, the entity-facts trigger.

Move both writers onto `_record_landing_passthrough`, the same shape as Tickets 02–06. This takes
the "marker move" off Ticket 09's blockers; that clause pointed at the
bootstrap-fundamentals-crash-resume map. That map's per-CIK resume ledger is a separate goal
that DuckDB removal does not need.

**Done:**
- Both writers are landing-only, with `processed_at`/`entity_facts_refreshed_at` stamped per write.
- A repeated mark appends a second landing row, which the dbt silver model collapses on its key.
- The stale `_get_processed_accessions` docstring is fixed.
- Tests follow Ticket 05's treatment: writer assertions use `open_landing_db`, and reader and merge
  tests seed with `insert_silver_rows`.

**Blocked by:** none — frontier.

## Answer

Resolved 2026-09-14 in code.

- Both writers call `_record_landing_passthrough` with a one-key row and a stamp:
  `processed_at` / `entity_facts_refreshed_at` = `datetime.now(UTC)` (tz-aware, so the
  Ticket 22 UTC-pinned load labels it correctly). The DuckDB `INSERT ... ON CONFLICT ...
  RETURNING` and the direct `landing_export.record` are gone. DuckDB DDL kept (the helper reads
  its NOT NULL set). A `None` key raises `ValueError` before recording, as in Tickets 04/05.
- Collapse keys verified: the dbt silver models keep one row per `(mode, accession_number)` and
  per `cik`, by landing `parse_sequence`. Across runs that is the latest load, matching the old
  `DO UPDATE SET <timestamp>`. Between two marks of the same key in one flush the survivor is
  arbitrary (`parse_sequence` is assigned by an unordered UPDATE after COPY); the values differ
  by microseconds and every passthrough table has the same limit. Noted, not fixed.
- Readers confirmed on Snowflake silver: `_get_processed_accessions` is called with `source` at
  both sites (its parameter is renamed from `db` and its docstring corrected);
  `get_ciks_with_new_qualifying_filing` reads `read_source`, which is `source` in production.
  No production reader of either table uses local `db`.
- `silver_protection.py`'s `PUBLICATION_SIGNIFICANT_OPERATIONAL_TABLES` comment for the pair
  updated: the local tables stay empty now, so the merge pass copies nothing for them; the entries
  and their merge test stay until Ticket 09 deletes the engine.
- Tests: marker writer tests assert on the recorded landing rows via `open_landing_db` (and that
  the local table stays empty); the reader SQL tests and the merge test seed with
  `insert_silver_rows`. The three new writer tests were confirmed red against the old writers.
  Full suite: 3504 passed; the 8 failures are in `tests/integration/test_*_postgres.py` and fail
  identically on `origin/main` (no local Postgres role setup), unrelated to this change.
- Reviews: `/gof-refactor-reviewer` before the edit (leave it) and the three-axis `/code-review`
  after; the docstring/comment/test-name findings above were applied.
- Ticket 09's "marker move" blocker now points here. Crash-resume Ticket 03 got a note: the
  landing marker flushes once per task, so it cannot be a resume point; that map's per-CIK S3
  ledger remains its own work.

**Still owed:** the live entity-facts run Tickets 02/03 already owe should also show
`SEC_ENTITY_FACTS_REFRESH_WATERMARK` landing rows with a UTC `entity_facts_refreshed_at`, and a
second run skipping those CIKs.
