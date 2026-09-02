# 54 — Bookkeeping Sits Outside This Map's PostgreSQL Authority and End-to-End Change Tracking

Type: research
Status: open

## Question

Should `daily_incremental`'s legacy Bookkeeping-store checkpoint mechanism
and this map's Change Ledger be consolidated onto one PostgreSQL store,
and does that consolidation need new design work, or does it fall out of
work this map has already sequenced?

## Context: a second instance of the same coordination gap Ticket 45 found once

[Ticket 03](03-decide-bronze-consumption-ledger.md) locked this map's
scope: **"PostgreSQL owns local acquisition/processing state"** — singular
authority, by design. The Change Ledger (`AcquisitionLedger`,
`source_fetch_decision`/`source_revision`/etc., `edgar_warehouse/
acquisition/models.py`) implements that decision, and lives in **MDM's**
Postgres database (`MDM_DATABASE_URL` — confirmed via
`edgar_warehouse/mdm/database.py:132` and every acquisition-path caller's
`from edgar_warehouse.mdm.database import get_engine`).

But `daily_incremental` — still on the legacy bypass path this map's own
[Ticket 27](27-contract-legacy-acquisition-bypasses.md) is meant to
retire — does its own, separate change detection entirely outside this
system: `_apply_submission_snapshot_to_silver`
(`edgar_warehouse/application/warehouse_orchestrator.py:5109`) compares a
freshly-fetched SHA256 against `bookkeeping.get_source_checkpoint(...)`, a
table in the **Bookkeeping** Postgres store (`BOOKKEEPING_DATABASE_URL`) —
a third, physically separate database, created later by the
`duckdb-retirement-cutover` map's own Ticket 02 as a pure lift-and-shift of
DuckDB's legacy checkpoint/sync-state tables. That effort's own scope
(`sec_source_checkpoint`, `sec_company_sync_state`, etc. — "none of them SEC
content or MDM data") never references this map, `AcquisitionLedger`, or
its locked "sole PostgreSQL authority" decision at all.

This is the same shape of gap [Ticket 45](45-coordinate-with-duckdb-retirement-cutover.md)
already found once, in the opposite direction: there, DuckDB Retirement's
*earlier* plan didn't account for this map's *later* new callers
(`silver_acceptance.py`). Here, `duckdb-retirement-cutover`'s *later*
Bookkeeping effort didn't account for this map's *earlier*, already-locked
"sole PostgreSQL authority" principle. Two different maps, two independent
Postgres-provisioning decisions, no cross-check either time.

**Confirmed live consequence, found while debugging a real production
OOM today:** because Bookkeeping's checkpoint write and Silver's actual
publish are not tied together by any transaction or ledger-style state
machine (unlike the Change Ledger's `Ledger State Record` — "the atomic
pairing of constrained current state with immutable within-epoch
transitions, attempts, outcomes, and reasons"), a mid-run crash leaves the
checkpoint claiming content that was never durably published, and the next
run's skip-if-unchanged optimization then silently, permanently skips
re-staging it. Full writeup:
[duckdb-retirement-cutover's bronze-capture-oom Ticket 02](../bronze-capture-oom/issues/02-checkpoint-outruns-silver-publish-on-crash.md).
This is exactly the failure class this map's own `Ledger State Record`
design exists to prevent — `daily_incremental` just isn't covered by it.

## The two things being asked, and how they relate

1. **"Bookkeeping and Change Ledger should use the same data store."** This
   map's Ticket 03 already decided this in principle (singular PostgreSQL
   authority) — the gap is that Bookkeeping was built later, elsewhere,
   without anyone checking that decision. Two sub-questions, not one:
   - **Physical**: should Bookkeeping's tables live in the same Postgres
     *instance* as the Change Ledger/MDM, regardless of ownership? Smaller,
     mostly operational (one fewer database to provision/monitor/secure),
     doesn't require any behavior change.
   - **Functional**: should Bookkeeping's change-detection-relevant tables
     (`sec_source_checkpoint`, `sec_company_sync_state`,
     `sec_daily_index_checkpoint`, `stg_daily_index_filing`) be *replaced*
     by the Change Ledger's own tables, not just colocated? This is the
     real fix for today's data-loss bug, and it's bigger — it means
     `daily_incremental` itself needs to run on the ledger-gated path.
     Bookkeeping's *other* tables (`pipeline_run`, `pipeline_run_lease`,
     `sec_sync_run`, `sec_parse_run`, `gold_manifest`,
     `sec_reconcile_finding`) are genuinely unrelated to change detection —
     pipeline-run/audit bookkeeping — and don't need to move anywhere
     regardless of how this resolves.

2. **"One thing keeps track of the change getting to MDM and Gold."** This
   is already this map's stated Destination — "propagating only new,
   modified, or retired source facts... from bronze to silver, silver to
   MDM and gold, and MDM to the hosted Neo4j graph, with deterministic
   replay and one aligned Decision Watermark." It already exists, for
   every source family that's been migrated onto the ledger-gated path.
   `daily_incremental`'s captures simply aren't on that path yet — that's
   exactly what [Ticket 27](27-contract-legacy-acquisition-bypasses.md)
   is for.

**The functional consolidation and the end-to-end tracking goal are the
same fix, not two separate projects.** Finishing Ticket 27 for the
`submissions`/`filing_artifact`/`company_facts` families `daily_incremental`
currently captures via the legacy path would, as a byproduct: retire
Bookkeeping's overlapping checkpoint tables, close today's data-loss gap
(the Change Ledger's atomic state-transition design doesn't have this
failure mode), and give `daily_incremental`'s captures the same MDM/Gold
propagation tracking every other family already gets once migrated.

## Recommendation, not yet decided by the operator

**Don't design a new merge mechanism.** The path already exists and is
already sequenced — it just isn't finished. Concretely:

- [Ticket 46](46-wire-filing-artifact-into-daily-incremental.md) landed
  the ledger-gated driver but its own real production side-by-side proof
  (Decision 2, equal-or-superset vs. legacy, zero silent gaps) **has not
  run yet** — this is Ticket 27's actual blocker today, not a design gap.
- Running that side-by-side proof for at least one family is the highest-
  leverage next step: it's already scoped, already has a harness
  ([Ticket 51](51-build-filing-artifact-capture-parity-harness.md)), and
  unblocks Ticket 27 directly.
- The **physical** consolidation question (same Postgres instance) is
  smaller and doesn't need to wait on any of this — it's a provisioning
  decision, not a behavior change, and could be decided independently if
  the operator wants it sooner.
- Today's live data-loss exposure
  ([bronze-capture-oom Ticket 02](../bronze-capture-oom/issues/02-checkpoint-outruns-silver-publish-on-crash.md))
  still needs its own near-term remediation regardless of how this larger
  question resolves — it's not blocked on Ticket 27 landing.

## Not yet decided

- Whether to prioritize running Ticket 46's side-by-side proof now, given
  it's the real unlock for both the user's asks and today's data-loss bug.
- Whether the physical (same-instance) consolidation is worth doing as a
  smaller, independent near-term step, or whether it's not worth touching
  until the functional consolidation (Ticket 27) makes Bookkeeping's
  change-detection tables moot anyway.
- Whether `duckdb-retirement-cutover`'s own map needs a note added (same
  handoff pattern Ticket 45 used) now that this gap has been found from
  this map's side too.
