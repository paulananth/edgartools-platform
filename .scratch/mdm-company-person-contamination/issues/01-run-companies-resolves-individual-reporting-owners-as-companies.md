# 01 — `run_companies()` resolves individual Form 3/4/5/144 reporting owners as `mdm_company` entities

**What was found (2026-09-07):** investigating why `mdm_company` has 72,379
rows while the user's expectation of "active tracked companies" was much
smaller. Live data shows `sec_company_sync_state`'s `active` count is
actually 73,677 (not ~10K) — closely matching `mdm_company`'s count. There
is no separate "72K vs 10K" numeric gap; both numbers are inflated by the
same contamination.

**Root cause, confirmed with three independent live signals:**

`sec_company` (silver layer) — the table both the daily-index discovery/
tracking pipeline and `MDMPipeline.run_companies()`
(`edgar_warehouse/mdm/pipeline.py`) treat as "the company universe" —
contains every CIK this pipeline has ever discovered, **including
individual Form 3/4/5/144 reporting owners, not just genuine operating
companies**. Nothing in the discovery/tracking/resolution chain
discriminates person-CIK from company-CIK:

1. Daily-index discovery surfaces every CIK involved in a day's filings —
   Form 4s list both the issuer's CIK and the individual reporting owner's
   CIK (the same mechanism behind duckdb-retirement-cutover's Ticket 16).
2. `sec_company_sync_state` marks both as `active` — no person/company
   discrimination anywhere in the tracking logic.
3. `sec_company` captures an `entity_name` for every tracked CIK from its
   own submissions.json — including individuals' own name records
   ("Winnefeld James A Jr", "Wyden Adam D", "Hill Michael Douglass").
4. `run_companies()` (`edgar_warehouse/mdm/pipeline.py:306`) does a bare
   `SELECT * FROM sec_company` (also `SELECT * FROM sec_company WHERE cik
   IN (...)` for scoped runs) — no filter — so `CompanyResolver` creates an
   `mdm_company` entity for every one of them.

**Evidence:**

- Random 10-CIK sample of `active`-tracked CIKs: 6 of 10 were individual
  names, not companies.
- Broad company-keyword sweep (INC, CORP, LLC, TRUST, FUND, PARTNERS,
  CAPITAL, THERAPEUTICS, etc. — wide enough to catch nearly every real
  company/fund/trust naming pattern) across all 73,691 `sec_company` rows:
  32,616 (44.3%) match none of them.
- CIK-also-appears-as-`owner_cik` cross-reference (a known undercount per
  Ticket 16's own finding — misses individuals whose ownership XML was
  never parsed): at least 9,458 confirmed.
- **Form-type discriminator (most reliable, validated 6/6 on known
  examples):** a CIK whose entire `sec_company_filing` history consists
  only of beneficial-ownership/insider forms (`3`, `4`, `5`, `144` +
  `/A` variants, `SC 13D`/`SCHEDULE 13D` + `/A`, `SC 13G`/`SCHEDULE 13G` +
  `/A`, `DFAN14A`) — i.e. never a `10-K`, `10-Q`, `8-K`, `S-1`, `424B*`,
  `13F-HR`, `13F-NT`, `DEF 14A`, etc. — is reliably an individual, not an
  operating registrant. Confirmed correct on Revvity/JPMorgan/Google LLC
  (companies, all have non-ownership forms) and Michas/Davis/Winnefeld
  (individuals, all ownership-forms-only). A random 300-CIK sample from
  `sec_company_filing` classified 111/300 (37%) as ownership-forms-only —
  consistent in magnitude with the other two signals.

**Likely compounding correctness bug:** `_derive_is_insider` and its
siblings (`_derive_holds`, `_derive_company_holds`) skip a reporting owner
as "corporate" via `owner_cik in company_ciks`, where `company_ciks` is
`mdm_company`'s CIK set. Since that set contains tens of thousands of real
individuals, this check likely **wrongly skips genuine IS_INSIDER
relationships** for any individual whose own CIK happens to have been
(mis)resolved into `mdm_company` — a second, silent data-quality bug
stemming from the same root cause. Not yet quantified live.

**Fix direction (forward-looking, not yet decided/implemented):** filter
`run_companies()`'s source query to exclude CIKs whose entire
`sec_company_filing` history is ownership-forms-only, using the validated
form-type discriminator above. This is fully computable from data already
captured — no new SEC fetches needed. Candidate SQL shape: an anti-join
or `NOT EXISTS`/aggregate-based exclusion against `sec_company_filing`
grouped by `cik`, checking `every form is in the ownership-forms set`.

**Separate, larger, unaddressed question — cleanup of already-corrupted
data:** an estimated ~30-40K `mdm_company` rows already exist for
individuals. A forward-looking query fix does not remove them. Deleting
existing entities is destructive and could cascade (relationships,
`mdm_company_entity` gold exports, graph nodes/edges referencing these
entity_ids) — needs an explicit operator decision on scope/approach
before any deletion, separate from the forward-looking fix.

**Also unaddressed:** whether the SAME contamination needs fixing at the
`sec_company_sync_state` tracking layer (daily-index discovery marking
individual CIKs `active`) — the "MDM_RUN_LIMIT unbounded" decision earlier
this session means `run_companies()` (once filtered) would now attempt to
resolve the FULL active-tracked backlog every day, so leaving individual
CIKs marked `active` upstream means every future run still has to check
and skip them, at real cost, even after this fix.

**Status:** root cause found and validated live; forward-looking fix not
yet implemented; existing-data cleanup and tracking-layer fix both
explicitly deferred pending operator decision.

- [x] Investigate and confirm root cause with live evidence
- [x] Validate a reliable, computable-from-existing-data discriminator
      signal (form-type based)
- [ ] Implement `run_companies()` query filter (forward-looking)
- [ ] Decide cleanup approach for already-created individual `mdm_company`
      rows (operator decision needed — destructive, cascading)
- [ ] Decide whether to also fix `sec_company_sync_state`'s tracking layer
- [ ] Quantify and, if confirmed, fix the `_derive_is_insider` "skipped as
      corporate" compounding bug
