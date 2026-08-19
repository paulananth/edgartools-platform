# Decide How Full `mdm run` Should Skip Already-Resolved, Unchanged Entities

Type: `wayfinder:grilling` (HITL)

Status: resolved

Blocked by: none

## Question

A fresh full `mdm run` (no `resume_ledger_run_id` reuse) re-resolves the
entire company/security/person/adviser/fund universe from scratch every
time, including rows already correctly resolved and unchanged since the
last run. `CompanyResolver._existing_candidates` scopes match-candidate
lookup to the row's own CIK, so re-matching an unchanged row is idempotent
(safe) but wasted work — this is separate from the
[mdm-run-throughput](../mdm-run-throughput/map.md) map's concurrency fix,
which improved throughput per row but did not reduce how many rows get
touched on a fresh run.

Design a skip-if-unchanged fast path for `MDMPipeline.run_companies` (and
decide whether `run_securities`/`run_persons`/`run_advisers`/`run_funds`
need the same treatment, given adviser/fund already run a different, bulk
execution shape than company/security/person). Cover:

1. What "unchanged" means per entity type — a content hash on the silver
   row compared against a stored value from the last successful
   resolution? A `last_resolved_at` timestamp compared against the row's
   last silver write time? Something else?
2. Where the "last known state" gets stored/compared — a new column, a
   side table, a sidecar file (mirroring the shard-publish fix's fingerprint
   sidecar pattern), or something keyed differently given MDM's candidate
   pool lives in Postgres, not local DuckDB/S3?
3. Whether this reuses or extends `company_resume.py`'s existing
   snapshot/resume-ledger mechanism, or is a genuinely separate concept
   (resume skips *already-succeeded-this-run_id* rows; this ticket is about
   skipping *unchanged-since-a-prior-run* rows — related but not the same
   problem).
4. Whether a company that's unchanged in `sec_company` but has new
   ownership/ADV activity referencing it still needs re-resolution (i.e.
   is "unchanged" scoped to the resolved entity's own row, or does it need
   to consider downstream referencing tables too).

## Answer (2026-08-19)

Implemented for `run_companies` only, per grilling decision (Q4): adviser/
fund already run a bulk shape, security/person need their own field-scoping
investigation before design — left for a future ticket.

1. **What "unchanged" means**: a content hash (`edgar_warehouse/mdm/
   resolvers/base.py`'s `content_hash()`, sha256 over sorted-key JSON) of
   the exact fields `resolve_one` stages — `canonical_name`, `ein`,
   `sic_code`, `sic_description`, `state_of_incorporation`,
   `fiscal_year_end`, `primary_ticker`, `primary_exchange`,
   `tracking_status`, and the raw parent-CIK source input (not the derived
   `parent_company_entity_id`, which requires a query and is always `None`
   in production today — no `sec_company` column feeds it).
2. **Where it's stored**: a new nullable column,
   `mdm_source_ref.source_content_hash` (migration
   `011_source_ref_content_hash.sql`), on the row `_register_source`
   already writes per match. No new table — `MdmSourceRef` is already
   keyed exactly right.
3. **Relationship to `company_resume.py`**: confirmed genuinely separate,
   as suspected. Resume skips already-succeeded-this-run_id rows (crash
   recovery, S3-backed); this skips unchanged-since-last-successful-
   resolution rows (cross-run, Postgres-backed). Independent, coexist
   without interaction.
4. **Downstream referencing tables**: out of scope by construction — the
   hash covers exactly the 3 tables `resolve_one` actually reads
   (`sec_company`, `sec_company_ticker`, `sec_tracked_universe`), confirmed
   by reading the resolver's own inputs rather than guessing.

**Mechanism**: `BaseResolver._skip_if_unchanged` (generic, `base.py`) looks
up the stored hash for `(source_system, source_id)`; on a match,
`resolve_one` returns early with `MatchAction.SKIPPED_UNCHANGED`, skipping
candidate lookup, the match pipeline, survivorship, and the golden-record
upsert entirely — reusing the existing `entity_id`. `run_companies` tracks
a `skipped_unchanged` counter and emits it in both the periodic
`mdm_progress` event and a new `mdm_company_resolution_completed` summary
event, for live verification once deployed.

**Real bug found and fixed along the way, not originally in scope**: while
testing (a genuinely-changed field between two `run_companies` calls),
found `mdm_entity_attribute_stage` rows are never cleaned up across
separate runs, and `survivorship.py`'s priority-tie-breaking had no
recency signal — a stale, first-ever-staged value could permanently win
over a genuinely newer one on a priority tie. Confirmed via direct
inspection (both old and new staged rows present, `was_selected=True`
still on the old one). Pre-existing, unrelated to skip-if-unchanged, but
newly *exercised* by it (my test was the first in this codebase to run
`run_companies` twice with a real field change between runs). User chose
to fix rather than defer. Fixed by using `mdm_entity_attribute_stage.
loaded_at` (already in the schema, server-defaulted `NOW()`, never
previously read) as the final tie-break signal across every rule type's
sort in `_pick_by_rule` — most-recently-staged wins a tie, instead of
first-ever-staged. `immutable`'s "never override once set" semantics is
untouched (the fix only affects which of several simultaneous
first-assignment ties wins, not whether an existing value gets
overridden).

Tests: `tests/mdm/test_run_companies_skip_unchanged.py` (9 cases — content
hash determinism/order-independence/sensitivity, skip-on-unchanged with
zero new `MdmChangeLog` rows as proof survivorship didn't rerun,
entity_id reuse, a genuinely-changed field both avoiding the skip AND
correctly updating the golden record, `_skip_if_unchanged`'s own
none/mismatch cases). One existing test
(`test_missing_sync_state_table_is_skipped_and_logged`) updated for the
new completion-summary log line. One existing test
(`test_postgres_migrate_routes_to_postgres_schema`) updated for the new
migration file. Full `tests/mdm/` suite green (506 passed). Full repo
suite run before commit.
