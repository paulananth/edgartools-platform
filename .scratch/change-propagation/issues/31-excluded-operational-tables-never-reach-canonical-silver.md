# 31 — `EXCLUDED_OPERATIONAL_TABLES` content never reaches canonical silver once canonical exists

**What to build:** `silver_protection.py`'s `merge_candidate_into_canonical`
is the sole function that copies a local silver candidate's data into a
merged output destined for canonical S3 storage (`_publish_silver_database_if_remote`
only takes the "upload the whole local file as-is, no merge" path when
canonical doesn't exist yet — the `else` branch at
`warehouse_orchestrator.py:1199-1204`). Once canonical exists (the normal,
steady-state case for a live prod database), every publish goes through the
`if baseline.exists:` branch, which merges via
`merge_candidate_into_canonical`. That function's only content-copying loop
(`for table_name, policy in PROTECTED_TABLE_REGISTRY.items(): ...`) iterates
exclusively over `PROTECTED_TABLE_REGISTRY` — tables in
`EXCLUDED_OPERATIONAL_TABLES` (`schema_migration`, `stg_daily_index_filing`,
`sec_daily_index_checkpoint`, `discovery_checkpoint`, `sec_parse_run`,
`sec_sync_run`, `pipeline_run`, `pipeline_run_lease`, `gold_manifest`,
`sec_source_checkpoint`, `sec_company_sync_state`, `sec_reconcile_finding`,
plus more listed in `silver_protection.py`) are used only to satisfy the
fail-closed "unclassified table" check — the merge loop never touches them,
so `output_path` (which starts as an exact `shutil.copy2` of canonical)
retains canonical's stale copy of every excluded table, forever, on every
merge-publish cycle. This directly contradicts the function's own documented
intent for these tables: "a candidate is always free to overwrite them" (the
comment above `EXCLUDED_OPERATIONAL_TABLES`'s definition).

Discovered live during Ticket 29's prod dry run: `load-daily-form-index-for-date`
(whose entire purpose is writing `stg_daily_index_filing`/
`sec_daily_index_checkpoint` — both `EXCLUDED_OPERATIONAL_TABLES`) reported
`"skipped": true, "tables_merged": []` for its silver-database publish step.
A second, independent bug compounds this and was found and fixed first (see
Ticket 29's Answer): `compute_silver_fingerprint`'s skip-if-unchanged
optimization also only fingerprints `PROTECTED_TABLE_REGISTRY` tables, so a
command that writes exclusively to excluded tables always computes an
"unchanged" fingerprint and skips the whole publish cycle outright — masking
this deeper bug, since the merge loop's inability to copy excluded tables was
never actually reached to be observed until the fingerprint gap was fixed
first. **Do not assume fixing the fingerprint (Ticket 29's own fix) is
sufficient** — it removes the false "unchanged" skip, but the underlying
merge still will not copy `stg_daily_index_filing`/`sec_daily_index_checkpoint`
content into `output_path`, so the publish will very likely still not
persist what the caller expects. This needs its own fix, verified
independently of the fingerprint fix.

Real-world impact is plausibly wider than the two tables Ticket 29 needs:
`sec_source_checkpoint` shows 27,342 rows in canonical prod today, which is
consistent with either (a) this table's real growth happening almost
entirely during very early, pre-scoped-merge runs or the very first
canonical-doesn't-exist-yet publish (raw whole-file upload, no merge
involved), with canonical's copy silently stale ever since for any run that
published *after* canonical already existed — or (b) some other explanation
not yet investigated. Do not assume `sec_source_checkpoint` (or any other
`EXCLUDED_OPERATIONAL_TABLES` member) is fine just because it has rows;
verify each one's actual freshness against what local candidates have
recently written, rather than trusting a nonzero row count.

**Blocked by:** None — can start immediately. Surfaced while resolving
[29 — Deploy the gated acquisition path to prod and dry-run it](29-deploy-and-dry-run-gated-acquisition-path.md),
which cannot complete its live dry-run checkboxes until this is fixed.

**Status:** ready-for-agent

- [ ] Decide the right fix shape: `merge_candidate_into_canonical` needs a
  second code path (distinct from the `PROTECTED_TABLE_REGISTRY` merge loop,
  since these tables have no `authority_column`/business-key conflict
  semantics — that's *why* they're excluded from that loop, and must stay
  excluded from it) that actually copies each `EXCLUDED_OPERATIONAL_TABLES`
  table's candidate content into `output_path` — most likely a blind
  overwrite (`DELETE FROM out.<table>; INSERT INTO out.<table> SELECT * FROM
  cand.<table>`, or an equivalent DuckDB-native bulk replace) matching the
  "candidate is always free to overwrite them" comment's literal intent, run
  only for excluded tables the candidate actually has data for.
- [ ] Reconcile with the skip-if-unchanged fingerprint fix from Ticket 29: once
  this merge fix exists, decide whether `compute_silver_fingerprint`'s
  `PUBLICATION_SIGNIFICANT_OPERATIONAL_TABLES` addition (or its equivalent)
  needs to expand to cover any other `EXCLUDED_OPERATIONAL_TABLES` member
  whose freshness actually matters downstream, using evidence (a live
  reproduction per table, not blanket inclusion) the same way Ticket 29's own
  fix was scoped.
- [ ] Audit `sec_source_checkpoint`'s live prod staleness (compare its most
  recent `updated_at`/equivalent timestamp against when the runs that should
  have refreshed it actually executed) to establish whether this bug's
  real-world impact predates today's discovery, and note the finding either
  way.
- [ ] Add a regression test at the seam that would have caught this: build a
  candidate + canonical pair where only an `EXCLUDED_OPERATIONAL_TABLES`
  table differs, run `merge_candidate_into_canonical`, and assert the
  merged output actually reflects the candidate's data for that table (this
  test does not exist today — every existing test for this function only
  exercises `PROTECTED_TABLE_REGISTRY` tables).
- [ ] Rebuild/redeploy the warehouse image and re-verify
  `load-daily-form-index-for-date` against prod actually persists to
  canonical (`tables_merged` reflecting the excluded-table copy, or an
  equivalent new signal) before Ticket 29's dry run can proceed.
