# Decide Person processing cadence and the initial backfill scope

Type: grilling
Status: resolved 2026-09-20
Blocked by: 05-decide-person-relationships.md

## Answer

**Three jobs**, mirroring the Company consumer: a **daily refresh** on the
issuers that `daily_incremental` touched (binds, opens and extends
intervals, publishes edges; never rematches the universe); a **weekly
candidate backstop** over deferred records and Tier C candidates; and a
**monthly full reconciliation**, keyed to the ADV FOIA archive's own
release, which is the **only job permitted to close an interval by
absence**. Ticket 05 forces that last clause: two of its three closers are
absence-shaped and need a complete later filing set, so a late or
out-of-order filing can never retire a directorship on the daily path.

**The initial backfill is bounded by evidence class, not company count.**
Wave 1 is every reporting owner and every ADV Schedule A/B row that binds
at **Tier A**, plus rule C-J's automatic person arm — deterministic, no
review queue, and it yields the complete Person spine. Wave 2 adds C-J's
entity arm once its post-hoc guards are re-measured; wave 3 adds 8-K once
ticket 21 clears Tier B at 97.5%. DEF 14A follows ticket 10. Waves are
gated on evidence, never time-boxed.

**Replay re-enters at the pre-merge candidate stage** (operator), not at
re-projection — because only that can correct a wrong *binding*, which is
what a rule change alters. This makes the pre-merge candidate table a
**requirement** of the contract, not a proposal. Checkpoints stay per
(source family, job) on the durable artifact: `accession_number` for the
three SEC sources, the release month for the ADV archive. A missed run is
recovered by the next run's widened window; an unprovable gap does not
move the watermark and escalates to the monthly reconciliation. A policy
digest change triggers a **bounded rebuild from the pre-merge stage** over
the identities the changed rules reach, with the scope recorded in run
evidence — fixing for Person what the Mastering Policy spec §11 leaves
Open.

**Ids survive replay by default.** Unchanged decision → same id; a split
keeps the id with the surviving authoritative identifier and mints new
ones for the rest; a merge retires the loser with `superseded_by`. Nothing
is deleted and retired ids stay resolvable forever, so the graph's
published generations remain safe. Every change is a recorded disposition
naming rule, version and run — which also measures how much the
superseded rule over-merged.

## Grilling log

**Q1 — processing shape (2026-09-20).** **(a) three jobs, mirroring the
Company consumer** (`gleif-company-augmentation/spec.md:197-206`):

| Job | Does | Cadence |
| --- | --- | --- |
| **Person Daily Refresh** | on the issuers touched by that `daily_incremental` execution only: bind new records, open and extend intervals, publish edges. Never rematches the universe. | daily (`daily_incremental`, `cron(0 12 ? * MON-SAT *)` = 8am ET) |
| **Person Candidate Backstop** | re-evaluate deferred records and Tier C review candidates — owners with no `submissions.json` (~1.1%, ticket 03), edges waiting on an unaccepted endpoint (ticket 05 Q7), unresolved names | weekly |
| **Person Full Reconciliation** | complete roster comparison and source-to-MDM parity; **the only job permitted to close an interval by absence** | monthly, keyed to the ADV FOIA archive's own monthly release |

Forced by ticket 05: two of its three interval closers are
absence-shaped (a later Form 3/4/5 that omits a previously-carried
capacity flag; absence from a later ADV Schedule A/B roster), and neither
can be evaluated from a single filing — they need the complete later
filing set. ADV Schedule A/B is a monthly archive fetched whole by
`FetchAdvBulk` (Stage 1C, not CIK-scoped), which sets the reconciliation
period for free. Confining "close by absence" to that job means a late or
out-of-order filing can never retire a directorship on the daily path.

**Q2 — initial backfill (2026-09-20).** **(a) deterministic-only
universe first, then widen by gate** — bounded by **evidence class**, not
by company count:

| Wave | Scope | Gate to enter |
| --- | --- | --- |
| 1 | every reporting owner in silver and every ADV Schedule A/B row that binds at **Tier A** (shared cross-reference id: `owner_cik`, `OwnerID`), plus rule C-J's automatic **person** arm | none — deterministic by construction; ~100% of both id-bearing sources; no review queue |
| 2 | rule C-J's **entity** arm | its post-hoc guards re-measured in production (ticket 03) |
| 3 | 8-K Item 5.02 (4,193 eligible rows) | [ticket 21](21-extend-tier-b-labelling-to-97-5.md) clears Tier B at one-sided 97.5% (ticket 20); otherwise these rows land in Steward review on day one |

DEF 14A enters after [ticket 10](10-fix-proxy-executive-name-parser-leak.md)
and its own re-measurement (ticket 20 Q4). Population for sizing
(research 17): 72,981 Form 3/4/5 owner decisions over 21,727 distinct
owner CIKs; 79,768 ADV Schedule A/B rows at 99.7% `OwnerID` coverage.

Not a bounded issuer cohort (Company's pattern): Company bounded its
first slice because GLEIF matching was unproven, whereas Tier A binds
without judgment — so processing all of it is no riskier than a tenth,
it yields the complete Person spine that waves 2 and 3 attach to, and a
per-issuer cohort would split people who serve at several issuers. Waves
are gated on evidence, never time-boxed, and the review queue stays empty
until a measured rule exists to fill it.

**Q3 — recovery and replay (2026-09-20).** Operator: **"it must be
reprocessed from the pre-merge stage."** So replay is not re-projection:
the unit of replay is **source assertions → normalization → candidate
generation → decision → commit → projection**, re-entered at the
**pre-merge candidate stage**. Re-running survivorship over already-merged
state is not permitted, because it can only correct projected values,
never a wrong binding — and binding is exactly what a rule change (rule
C-J, the Tier B key, the identifier veto) alters.

Consequences:

- **Depends on the pre-merge candidate table**, the proposal already with
  Codex (record → entity candidates, after matching and before the MDM
  Committer). This contract now *requires* it rather than merely
  proposing it; the handover says so.
- **Checkpoints stay per (source family, job)** on the durable artifact —
  `accession_number` for Form 3/4/5, DEF 14A and 8-K; the archive release
  month for ADV Schedule A/B, which arrives as a whole file. A missed
  daily run needs no special handling: the next run's window widens to
  the unprocessed accessions (SEC artifacts are additive and immutable).
  A gap that cannot be proven contiguous does not move the watermark; it
  escalates to the monthly reconciliation, which sees a complete
  population — the foundation's fail-closed rule, not a new one.
- **A policy digest change triggers a bounded rebuild from the pre-merge
  stage** over the identities the changed rules can reach, with the
  computed scope recorded in run evidence rather than defaulting to
  "everything". This fixes for Person what the Mastering Policy spec §11
  leaves Open, and hands Codex a concrete case.
- Rebuild is the correction path for a wrong kind or a wrong bind —
  never an entity merge (`domain-model.md:41-44`).

**Q4 — Person ids across a replay that changes a binding (2026-09-20).**
**(a) ids are stable by default; every change is a recorded disposition,
never silent.**

- Unchanged decision → **same id**, always.
- **Split** (one Person becomes two): the id stays with the records
  holding the surviving authoritative identifier (`owner_cik`,
  `OwnerID`); the rest get a new id. A `split` disposition names both
  sides, the rule id and version that caused it, and the run.
- **Merge** (two become one): the survivor is chosen by the same
  identifier rule; the other id is **retired with a `superseded_by`
  pointer**, never deleted.
- Retired and split ids stay resolvable **forever** — a consumer holding
  an old id gets an answer, not a 404. This is what makes replay safe for
  the graph, which stores ids inside published generations.

This keeps ticket 02's "one Person, one id" true **through time**, not
only within a run. The disposition record also measures the damage of the
superseded rule: the count of splits a new rule version causes is exactly
how much the previous one over-merged — the measurement ticket 06 wanted
from legacy, applied to ourselves.

## Question

Ownership filings already flow through `daily_incremental`; proxy and 8-K
through the fundamentals stages. Does the Person consumer run per
`daily_incremental` execution on impacted issuers only, with a periodic
full reconciliation like GLEIF's monthly one? And is the initial backfill
"every reporting owner in silver" (deterministic CIK binds only), or a
bounded cohort first, the way Company's first slice was bounded?
