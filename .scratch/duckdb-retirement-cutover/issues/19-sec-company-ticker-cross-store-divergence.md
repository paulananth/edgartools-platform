# 19 — `sec_company_ticker`'s DuckDB and Snowflake copies genuinely disagree

**What was found:** Live during [Ticket 11](11-post-cutover-reconciliation-gate.md)'s
post-cutover reconciliation run (2026-09-12), `sec_company_ticker` failed both structural checks
and its semantic-content digest:

- `bronze_to_silver`/`required_parent` integrity: 4,166 cik-orphans against `sec_company`.
- `semantic_content_digest`: `duckdb_key_digest` != `snowflake_key_digest` even though the same
  500 DuckDB-selected keys were requested from both sides (`scope_mode="authority_column"`,
  `out_of_scope_count: 0`) — meaning Snowflake's `sec_company_ticker` is missing or returning
  different rows for some of the exact keys DuckDB has, not just lagging behind on newer rows.

**Why this isn't explained by anything already known:** release-readiness
[Ticket 40](../../release-readiness/issues/40-root-cause-empty-ticker-reference-pipeline.md)
already investigated `sec_company_ticker` directly and found it healthy — "8,056 distinct CIKs
... near-exact match [to SEC's own 8,017]... this pipeline is healthy and essentially complete."
That investigation was about whether the *source data* is correct (yes). This finding is a
different question: whether DuckDB's and Snowflake's independently-populated copies of that
already-correct data actually agree with each other. They don't, for at least some of a 500-key
sample.

**Not yet investigated:**
- Whether the 4,166 cik-orphans and the digest mismatch are the same root cause or two separate
  ones.
- Whether this is a genuine `EDGARTOOLS_SILVER` ingestion gap for this specific table (landing
  buffer never picked it up, a COPY INTO failure, a dbt model bug) or a reconciliation-tool
  artifact specific to this table's shape (e.g. a business-key/authority-column declaration
  mismatch in `contracts.py`).
- Whether this predates [Ticket 10](10-atomic-write-path-cutover.md)'s cutover (like the other
  three tickets 11 found failing) or is itself new.

## Done when

Root cause is found and either fixed, or determined to be a pre-existing gap already covered by
another ticket. A repeat `table-reconcile --tables sec_company_ticker` run passes clean
afterward.

**Blocked by:** none — independent investigation, does not block Ticket 11's GO/NO-GO decision
(which treats this as one open finding among several, not a blocker in itself).

## Investigation (2026-09-14)

**Status:** root-caused. Closure pending an operator decision on the "Done when" line (see
"Proposed closure" below).

**Answer: Snowflake is right, the DuckDB file is stale. Neither failure is a Snowflake
ingestion gap.** The two failures have two separate causes, and neither is new with Ticket 10.

Evidence: the canonical `s3://edgartools-prod-warehouse-690839588395/warehouse/silver/sec/silver.duckdb`
(last written 2026-09-06 10:42 ET, 1,793,077,248 bytes), read locally, against a full export of
`EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_COMPANY_TICKER`. Scratch scripts, not committed.

| | DuckDB | Snowflake silver |
|---|---|---|
| Rows | 21,458 | 20,946 |
| Distinct CIKs | 8,134 | 8,028 |
| `sec_company` rows | 58,236 | 73,730 |
| Orphan ticker rows / CIKs (no `sec_company` row) | 4,166 / 1,610 | 1,768 / 744 |

### Cause 1: the key-digest failure is 512 stale keys in DuckDB

- Every Snowflake key is also in DuckDB. DuckDB has 512 extra `(cik, ticker, source_name)` keys
  (271 distinct `(cik, ticker)`), all with `last_synced_at` inside the reconciler's scope.
  Reproducing `fetch_key_cohort`'s three queries verbatim on the file (same watermark, unchanged
  since landing last loaded tickers 2026-09-02) gives a 500-key cohort containing **17** of the
  stale keys, so Snowflake returned 483 rows for 500 requested keys and the key digests differ.
  Neither store has duplicate `(cik, ticker, source_name)` groups, so key uniqueness is not
  involved.
- The 512 keys were last written by 14 runs, from 2026-07-20 23:07 ET to 2026-08-18 07:21 ET.
  Snowflake's ticker landing starts 2026-08-22 19:32 ET
  (`seed-universe-verify-streaming-fix-1787441504`; Snowflake displays it as 23:32 −0700 because
  of [Ticket 22](22-silver-landing-timestamps-shifted-by-account-timezone.md)), and every SEC
  snapshot landed since then (eight, ~10,391 keys per source) is in silver: no landing key is
  missing from silver, and there are no retirement records for this table. So none of the 512
  keys was in any SEC ticker catalog fetched since 2026-08-22.
- They are real catalog changes: 269 of the 512 belong to CIKs that now have other tickers (e.g.
  1439124 `AXIA` → `AXIAY`/`AXICY`; 2017526 `PCSC` → `FRNM`), 243 to CIKs no longer in the catalog,
  and 8 are tickers now assigned to another CIK (e.g. `EQR` 906107 → 931182, `GORO` 1160791 →
  1515964).
- Why DuckDB kept them: before Ticket 06e, `replace_company_tickers` ran
  `DELETE FROM sec_company_ticker WHERE source_name = ?` in the run's local candidate file only.
  Publication then merged the candidate into canonical, and `merge_candidate_into_canonical`
  "never deletes a row that exists only in canonical" (`silver_protection.py` module docstring).
  So every dropped ticker stayed in canonical DuckDB. Pre-existing since the table was
  published by merge; not caused by Ticket 10.
- On the 20,946 shared keys, `exchange` and `source_rank` match exactly. Only `last_synced_at` and
  `last_sync_run_id` differ, and the reconciler excludes both from the semantic digest. The
  semantic digest fails only because the cohort includes the stale keys.

### Cause 2: the orphan count is a contract that doesn't fit this table

- `contracts.py` declares `sec_company_ticker.cik → sec_company.cik` as the parent link, and the
  orphan check runs on DuckDB only. But `sec_company_ticker` is SEC's full ticker catalog
  (every listed company), while `sec_company` holds only companies the platform captured
  (reporting-company submissions). A catalog ticker for an uncaptured company is a legitimate
  row, not a missing parent.
- Snowflake shows the same shape at a smaller size (744 orphan CIKs; only 16 of them have any
  `sec_company_filing` row), because Snowflake's `sec_company` is larger: it has every DuckDB CIK
  plus 15,494 more. All 15,494 extra rows have a NULL `last_synced_at`, so they came from a writer
  that does not stamp it (not identified here); none was synced after the DuckDB file stopped
  changing on 2026-09-06. DuckDB's number is
  bigger because its `sec_company` is smaller and its ticker list includes the stale keys.

### Found along the way: every silver-landing timestamp loads 7–8 hours late

Not a cause of either failure (the reconciler excludes `last_synced_at` from the digest, and the
shift only widened its scope watermark). Filed as
[Ticket 22](22-silver-landing-timestamps-shifted-by-account-timezone.md).

### Proposed closure

The "Done when" line cannot be met as written: a repeat `table-reconcile --tables sec_company_ticker`
compares against a DuckDB file nothing writes any more, so the 512 stale keys will fail it every
time. Proposed instead:

- Close this ticket as explained: DuckDB stale by the publish merge's no-delete rule; Snowflake
  matches every SEC catalog snapshot since 2026-08-22.
- Leave `contracts.py` as it is (recommended): `table-reconcile` leaves with the engine in
  silver-merge-engine-migration Ticket 09, and a code change there needs its own review. The
  alternative is dropping the `sec_company` parent link for `sec_company_ticker`, since the check
  cannot pass for a catalog table.
- Unblock [Ticket 21](21-apply-duckdb-file-lifecycle-disposition.md): the evidence it waited for is
  recorded here, so the DuckDB file is no longer needed to close this ticket. Ticket 21 still needs
  its own explicit operator go-ahead.
