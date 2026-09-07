# 03 — `run_securities()` attributes a security's issuer to an individual via still-uncleaned bad `mdm_company` rows

**Status:** open

**What was found (2026-09-07):** follow-on to Ticket 01/02, prompted by the
user questioning securities-data composition (total `mdm_security` is
6,860 — already under a "publicly traded < 10,000" bar — but the
*composition* is badly wrong).

**Root cause, confirmed with a direct example (not just correlation):**

1. Accession `0001193125-26-368711` (a Form 4) has exactly one row in
   `sec_company_filing`: `cik=942082` — that's the **reporting owner's own
   CIK** (Carl H. Lindner III), not the real issuer's. The true issuer was
   never bootstrapped/tracked, so its own submissions history never
   produced a `sec_company_filing` row for this accession.
2. `run_securities()`'s SQL (`edgar_warehouse/mdm/pipeline.py:733`) LEFT
   JOINs `sec_company_filing` on `accession_number` alone (no `owner_index`
   scoping) to get `issuer_cik`, then applies `txn_qualify =
   prefer_non_owner_cik_qualify(...)` to prefer a non-owner-CIK candidate
   when more than one exists. When there is **no** other candidate (this
   case), the QUALIFY's documented fallback — "whatever single match
   exists... including the owner's own row" — returns the owner's own CIK
   as `issuer_cik`. This is a deliberate, documented behavior (added by
   duckdb-retirement-cutover Ticket 16, explicitly to avoid regressing a
   previously-working single-match case to NULL), not a new bug in the
   QUALIFY logic itself.
3. `_company_entity_ids()` then looks up `mdm_company` for that
   self-referential CIK and finds a real (though wrong) entity — because
   Ticket 01's individual-reporting-owner contamination in `mdm_company`
   has **not yet been cleaned up** (explicitly deferred, per Ticket 01's
   own checklist). `SecurityResolver.resolve_one` then confidently sets
   `issuer_entity_id` to that individual's entity, attributing the
   security to a person as its issuing "company."

**Quantified at scale** (live prod, MDM Postgres + Snowflake):

| | Count | % |
|---|---|---|
| Distinct issuer CIKs behind `mdm_security` | 5,266 | — |
| ...classified as individuals (Ticket 01's ownership-forms-only discriminator) | 3,292 | 62.5% |
| Securities with a resolved (non-NULL) issuer | 6,763 | — |
| ...attributed to one of these individuals | 4,030 | **59.6%** |

**Separately, a genuine backlog/coverage gap** (distinct from the
misattribution bug above, surfaced by the same investigation): of 8,028
real ticker-listed (genuinely publicly traded) CIKs, only 1,462 have any
resolved security at all — 6,566 real public companies have **zero**
resolved securities. This is consistent with `MDM_RUN_LIMIT` having been
capped at 100/day for most of this pipeline's history (recently made
unbounded, this session) and `run_securities()`'s query having no
`ORDER BY` before its `LIMIT` — the same rows (in whatever scan order the
`UNION ALL` returns) get reselected every bounded run, so genuinely new
issuers may never have been reached. Not chased further in this ticket;
noted as a separate, lower-severity finding that should resolve on its own
once a full unbounded `mdm mastering --entity-type security` run
completes, unlike the misattribution bug above.

**Why this connects directly to Ticket 01's deferred items:** this is a
second, now-confirmed instance of the "likely compounding correctness bug"
Ticket 01 already flagged for `_derive_is_insider` (`owner_cik in
company_ciks` being unreliable once `company_ciks` contains real
individuals) — except here it's not a skip-check, it's an active
mis-assignment, and it's quantified at 59.6% of all resolved securities.
Leaving Ticket 01's bad `mdm_company` rows in place is no longer just a
company-count/classification issue — it is actively corrupting downstream
security-issuer relationships today.

**Open questions before implementing anything (not yet decided):**

1. **Forward-looking fix candidate:** change `run_securities()`'s fallback
   so that when no non-owner-CIK candidate exists in `sec_company_filing`
   for an accession, `issuer_cik` resolves to `NULL` (unknown) rather than
   self-referencing the owner's own CIK. `SecurityResolver.resolve_one`
   already has a documented NULL-issuer code path (used for the
   NULL-issuer-entity concurrency case), so this looks like a safe,
   narrow, non-destructive change — but needs validation that a
   NULL-issuer security is handled correctly everywhere downstream (e.g.
   `MANAGES_FUND`/`HOLDS` derivation, gold export) before treating it as
   free.
2. **Existing-data correctness:** a forward-looking fix does not undo the
   4,030 already-mis-attributed securities. Does fixing this need its own
   remediation pass (re-run affected securities' issuer resolution once
   Ticket 01's `mdm_company` cleanup happens), or does it fall out
   naturally once Ticket 01's cleanup removes the individual `mdm_company`
   rows these securities currently match against (in which case
   `_company_entity_ids()` would simply find nothing and set
   `issuer_entity_id` to NULL on the next `mdm mastering` pass — need to
   confirm `SecurityResolver` actually re-evaluates and updates
   `issuer_entity_id` on an existing, already-resolved security row, not
   just on first creation)?
3. **Sequencing:** this ticket's fix is now a strong argument for
   prioritizing Ticket 01's deferred `mdm_company` cleanup decision ahead
   of its other deferred items — leaving bad `mdm_company` rows in place
   keeps actively corrupting new data via this exact mechanism on every
   future `run_securities()` pass, not just sitting inertly.
4. **Root tracking gap, still open:** the real issuer of accession
   `0001193125-26-368711` was never bootstrapped/tracked at all (separate
   from person/company discrimination) — is that itself worth
   investigating (why wasn't a real, presumably-active issuer tracked?),
   or is it expected/acceptable that some issuers are legitimately never
   bootstrapped?

**Status:** root cause confirmed live with a direct example; quantified at
scale; no fix implemented; scope/sequencing decision needed, especially
relative to Ticket 01's still-open `mdm_company` cleanup item.

- [x] Quantify securities-data composition and confirm total isn't the
      issue (6,860, under 10K) — the issuer attribution is
- [x] Confirm root cause with a direct example (not just correlation)
- [x] Quantify blast radius (62.5% of issuer CIKs, 59.6% of resolved
      securities)
- [ ] Decide forward-looking fix (NULL-issuer fallback instead of
      self-reference) and validate downstream NULL-issuer handling
- [ ] Decide whether existing mis-attributed securities self-heal once
      Ticket 01's cleanup lands, or need their own remediation pass
- [ ] Decide sequencing against Ticket 01's other deferred items
