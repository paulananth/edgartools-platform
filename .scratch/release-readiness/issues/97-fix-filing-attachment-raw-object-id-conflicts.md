# Fix sec_filing_attachment raw_object_id ambiguous conflicts blocking publication

Type: task
Status: resolved

## Question

Ticket 42's sample backfill retry (`ticket42-sample-artifacts-retry3-postticket96-1785887896`,
ECS task `885b85b3072b49c5b6297829e49141f7`, exited code 2 at 2026-08-05T01:02:06Z) failed at
the final silver-merge/publish step with **147 ambiguous same-key conflict(s) block
publication**. What is the root cause, and how should it be fixed?

## Root cause

Confirmed live via CloudWatch (`/aws/ecs/edgartools-prod-warehouse`,
`warehouse-large/edgar-warehouse/885b85b3072b49c5b6297829e49141f7`): every one of the 147
conflicts is the same shape — `sec_filing_attachment` rows where `raw_object_id` differs
between canonical and the candidate, for the same `(accession_number, document_name)` key
(e.g. `0000764180-23-000066 / a2023defa14amay2023.htm`). No other table, no other column.

`sec_filing_attachment`'s `ProtectedTablePolicy` (`silver_protection.py:182-184`, pre-fix)
declared **no `authority_column` at all** — `_resolve_conflict` returns `None` (ambiguous)
unconditionally for any differing column when `authority_column is None`. Unlike
`sec_company`/`sec_raw_object`/etc., this table's DDL (`silver_store.py:420-431`) has no
timestamp column whatsoever (only `accession_number`, `sequence_number`, `document_name`,
`document_type`, `document_description`, `document_url`, `is_primary`, `raw_object_id`,
`last_sync_run_id`), so there was nothing to declare as authoritative even if desired.

`raw_object_id` is a content hash (sha256) pointing at externally-fetched bytes. It drifts
on refetch because SEC serves slightly different bytes for "the same" document over time —
the identical phenomenon `sec_raw_object`'s own `provenance_columns` already documents and
handles (see that policy's inline comment, `silver_protection.py:142-165`, and its
`Regression (2026-07-22, Ticket 20)` note). `sec_filing_attachment` was never given the same
treatment when it was added — a registration gap in the same shape as ticket 67's
`sec_company_filing` false-positive-conflict fix, but for a genuinely drift-prone content
pointer rather than a bumped-on-every-resync timestamp.

Confirmed via repo-wide grep that `sec_filing_attachment.raw_object_id` is not read
downstream at all (no hits in `gold.py`, `serving/`, `mdm/` outside one unrelated test-
scaffolding default) — the real content-hash identity work already happens through
`sec_raw_object`, keyed by the hash itself, independent of this table.

## Decision (grilled 2026-08-05)

1. Treat this as a real decision, not a one-line patch (both other authority-column-less
   tables in the registry were checked and ruled out: they're deterministic parser-output
   tables keyed by parse position — `owner_index`, `event_index`, etc. — with content that's
   reproducible given the same source bytes, not externally-fetched content pointers, so
   they don't share this failure mode; `sec_filing_attachment` is the only table whose
   declared value column is itself an externally-fetched content hash).
2. Resolve the conflict by **excluding `raw_object_id` from same-key comparison** (declaring
   it a `provenance_columns` entry), not by adding a real `fetched_at` authority column.
   Mirrors `sec_raw_object`'s existing pattern for the identical phenomenon; avoids a schema
   migration + backfill-value decision against ~3M live canonical rows for a column nothing
   downstream consumes. Canonical's first-observed `raw_object_id` simply stays authoritative
   and uncontested, the same way `sec_raw_object`'s own recurrence class is handled.

## Fix

`edgar_warehouse/silver_protection.py`: added `provenance_columns=frozenset({"raw_object_id"})`
to `sec_filing_attachment`'s `ProtectedTablePolicy`, with an inline comment recording the
live 147-conflict evidence and the downstream-non-consumption check.

## Validation

- New regression test `test_merge_treats_filing_attachment_raw_object_id_drift_as_non_conflicting`
  (`tests/application/test_warehouse_orchestrator_mdm.py`) reproduces the exact production
  shape (same accession_number/document_name, differing raw_object_id) — confirmed to fail
  with the identical prod error message (`1 ambiguous same-key conflict(s) block publication:
  sec_filing_attachment{...}: ['raw_object_id']`) pre-fix via `git stash`, passes post-fix.
- New regression test `test_merge_still_flags_filing_attachment_genuine_content_conflict`
  proves the exclusion is scoped only to `raw_object_id`, not a blanket exemption: a same-key
  row differing on a real business column (`document_type`) still raises
  `SemanticMergeConflictError` as before.
- Full suite (`tests/unit tests/application tests/architecture tests/mdm`): 1773 passed, 4
  skipped, 1 pre-existing unrelated failure (`test_go_live_wizard.py::test_plan_prints_preview_only_aws_ordered_commands`,
  an AWS-profile/environment-dependent test, same one every other recent ticket in this map
  has hit).

## Done when

Fix implemented and tested; PR merged; prod warehouse image rebuilt/redeployed; ticket 42's
sample backfill retry re-run and confirmed to pass the silver-merge/publish step without
raw_object_id conflicts.

**Done — confirmed live 2026-08-05.** Merged as PR #354 (`61902a40`), warehouse image rebuilt
(digest `sha256:2ab0b426187e955b0c2250eea707db72a4a242d736de1ca8367732d75b51fb12`, confirmed via
direct `docker run` that `sec_filing_attachment`'s `provenance_columns` contains `raw_object_id`
before deploying), deployed to prod (`edgartools-prod-large:132`). Re-ran ticket 42's exact
20-CIK sample backfill (`ticket42-sample-artifacts-retry4-postticket97-1785894075`, ECS task
`20a3e448c6ae4a91940234a761c5eb90`): **exited 0** for the first time across 4 attempts (prior 3
all failed at the merge step, exit code 2). Live `silver_table_merged` event for
`sec_filing_attachment`: `rows_inserted: 8212, rows_updated: 0, rows_unchanged: 327205` — zero
conflicts, exactly the table/column that blocked all prior attempts. Every other protected table
also merged cleanly (13F holdings at 6.8M rows, ownership transactions with real inserts,
financial facts, etc.), circuit breaker stayed closed, and a run manifest was published to
bronze. Full run: 42.8 min artifact-fetch phase (3,149 accessions, 221 known immutable-object
conflicts correctly skipped) + a few minutes of merge/publish, well within the historical
timing envelope.
