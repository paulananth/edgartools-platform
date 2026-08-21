# MDM Resolver Skip-If-Unchanged Audit

## Destination

Every entity resolver actually reachable from a live `mdm run` execution
either has the skip-if-unchanged fast path (the fix that closed
`SecurityResolver`'s unbounded `mdm_entity_attribute_stage` growth bug,
commit `091809b0`) or has a documented, evidenced reason it doesn't need
it. No resolver left in the ambiguous state SecurityResolver and
PersonResolver were in before this map: append-only staging with no
resumable ledger, silently duplicating stage rows on every `mdm run`
restart.

## Notes

Domain: `edgar_warehouse/mdm/resolvers/` (CompanyResolver, AdviserResolver,
SecurityResolver, PersonResolver, FundResolver) plus `edgar_warehouse/mdm/
adv_bulk.py` (the actual live path for adviser/fund data — see Ticket 01).

**This effort carries execution into the map itself** (Wayfinder's
plan-don't-do default is overridden here): the fix pattern was already
designed and proven twice before this map existed (CompanyResolver,
single-path-per-layer map Ticket 03; SecurityResolver, this session's
`/diagnosing-bugs` pass, commit `091809b0`). Porting a proven pattern to a
third call site with the identical shape is mechanical, not a fresh design
decision — so tickets here resolve with code + tests directly, not just an
answer.

## Decisions so far

- [Audit which resolvers are actually reachable from a live `mdm run`](issues/01-audit-resolvers-reachable-from-mdm-run.md) — 5 resolver classes exist; only 3 are ever instantiated by the pipeline (Company, Security, Person). `AdviserResolver`/`FundResolver` are dead code — `run_advisers()`/`run_funds()` call `adv_bulk.py`'s `resolve_advisers_bulk`/`resolve_funds_bulk` instead, which never construct either class.
- [Fix PersonResolver's skip-if-unchanged gap](issues/02-fix-personresolver-skip-if-unchanged-gap.md) — Confirmed live via a red/green repro (git-stash proof, stage-row count doubled 6→12 without the fix). Ported the same content-hash pattern used for Company/Security, hashing `issuer_cik` too even though it's never staged, since it's a match-context field. 3 new regression tests, all pass.
- [Decide disposition of AdviserResolver/FundResolver's identical resolve_one() gap](issues/03-decide-adviserresolver-fundresolver-dead-code-disposition.md) — Ruled out of scope: fixing dead code that no test or production path ever calls would be speculative work this session's own precedent (the PersonResolver-flagged-not-fixed note in commit `091809b0`) explicitly avoids. See Out of scope below.

## Not yet specified

(none — the destination is fully reached: every resolver reachable from
`mdm run` has been audited and either fixed or has a documented reason it
was already safe.)

## Out of scope

- **`AdviserResolver.resolve_one()` / `FundResolver.resolve_one()`'s
  identical skip-if-unchanged gap** — real, same code shape, but neither
  method has a live caller (production or test). The actual live adviser/
  fund path, `adv_bulk.py`'s `resolve_advisers_bulk`/`resolve_funds_bulk`,
  already dedupes via a `source_id`-existence check (`_existing_source_ids`)
  that skips staging entirely for any already-seen accession — a different,
  arguably stronger mechanism than content-hash skip, and it does **not**
  have SecurityResolver's bug (confirmed by reading the function: stage
  rows are only ever appended for source_ids not already in
  `MdmSourceRef`). Fixing the dead classes would touch code nothing
  exercises. See [Ticket 03](issues/03-decide-adviserresolver-fundresolver-dead-code-disposition.md)
  for the full reasoning; whether to delete `AdviserResolver`/`FundResolver`
  outright (dead-code cleanup) is a separate, smaller decision not made
  here.
- **`resolve_advisers_bulk`/`resolve_funds_bulk`'s bare `SELECT * FROM ...
  LIMIT N`, no `ORDER BY`/exclusion** — discovered incidentally while
  auditing Ticket 01. This is a *different* bug shape: the same
  "re-fetches the same first N rows forever, no cumulative progress across
  restarts" plateau bug that release-readiness Ticket 94 found and fixed
  for `run_companies()` — not the skip-if-unchanged/append-only-staging
  bug this map's destination is scoped to. Filed as
  [release-readiness Ticket 100](../release-readiness/issues/100-adv-bulk-select-limit-plateau-on-restart.md)
  rather than as a ticket on this map, since fixing it means porting
  Ticket 94's bounded-window pattern, not this map's skip-if-unchanged
  pattern, and release-readiness is where Ticket 94's precedent already
  lives.
