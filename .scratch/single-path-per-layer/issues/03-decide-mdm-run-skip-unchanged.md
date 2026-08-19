# Decide How Full `mdm run` Should Skip Already-Resolved, Unchanged Entities

Type: `wayfinder:grilling` (HITL)

Status: open

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
