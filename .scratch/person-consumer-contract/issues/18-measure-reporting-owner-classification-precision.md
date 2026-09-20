# Measure which reporting-owner classification rule reaches 99% precision

Type: research
Status: resolved
Blocked by: none

## Question

Ticket 03 must choose the rule that classifies each
`sec_ownership_reporting_owner` row as **person**, **company**, or
**deferred** before any binding. The operator's bar (ticket 02, Q11
amendment): automatic decisions need a **measured ≥ 99% precision**;
anything below goes to a Steward, and the operator does not want manual
work. Which candidate rule — or combination — meets 99% precision while
deferring the fewest rows?

Candidate evidence, in the order ticket 03 proposed:

1. **SEC `entityType`** of the owner CIK (`submissions.json`:
   `operating`/`investment` = reporting company; `other` = individual *or*
   passive entity such as a trust, LLC, family partnership, fund).
2. **Relationship flags** on the row: `is_officer` (+ `officer_title`),
   `is_director`, `is_ten_percent_owner`, `is_other`. Known hazard:
   *director by deputization* (an entity ticking director because its
   designee sits on the board); the parser keeps neither footnotes nor the
   `otherText`, so the raw XML must be read for this.
3. **Name form**: entity tokens (`LLC`, `L.P.`, `LP`, `TRUST`, `FUND`,
   `INC`, `CORP`, `LTD`, `PARTNERS`, `HOLDINGS`, `CAPITAL`, `MANAGEMENT`,
   `FOUNDATION`, `ESTATE`, `ASSOCIATES`, `GROUP`, `CO`, …) versus EDGAR's
   conformed person form `LAST FIRST MIDDLE`.
4. Other `submissions.json` fields of the owner CIK (`sic`,
   `stateOfIncorporation`, `ein`, `category`, `formerNames`, filing-form
   history) — as supporting evidence or as part of the labeling.

Measure, from bronze only (Snowflake will not be restored):

- Parse every Form 3/4/5 XML under
  `s3://edgartools-prod-bronze-690839588395/warehouse/bronze/filing_artifact/`
  (content-addressed objects, ~5,356 total, not all ownership) into
  reporting-owner rows: owner CIK, name, the four flags, officer title,
  `otherText`, and any footnote text mentioning deputization.
- Join each owner CIK to
  `s3://edgartools-prod-bronze-690839588395/warehouse/bronze/submissions/sec/…`
  where present; record how many owner CIKs have no submissions file at
  all (the "never fetched" case ticket 03 must also rule on).
- Build a labeled truth set: a stratified sample (by flag combination and
  by presence/absence of an entity token) of at least 300 owners, labeled
  person / entity by reading name + submissions fields + the filing
  itself. Record the labeling rule and every uncertain case.
- Score each candidate rule and the sensible combinations: precision of
  the automatic `person` decision, precision of the automatic `company`/
  entity decision, share of rows deferred, and the 95% confidence interval
  given the sample size. Show which rule(s) clear 99% and at what deferral
  cost.
- Report the flag-combination distribution over all rows (officer,
  director, 10%-only, other-only, and mixes) and the share of rows whose
  transactions attach to a multi-owner filing, since ticket 03's rule must
  say what a 10%-only row becomes.

Fair access if any SEC fetch is needed for a missing `submissions.json`:
`User-Agent` from `EDGAR_IDENTITY`, ≤ 1 request/second, stop on 403/429,
cap 300 requests; prefer bronze and do not fetch at all if bronze covers
the sample.

Write findings to
`.scratch/person-consumer-contract/research/18-reporting-owner-classification-precision.md`
with `path:line` citations, the parsing/scoring script beside it, and the
labeled sample as JSONL so the numbers can be rechecked.

## Resolution

Resolved 2026-09-20 from bronze alone (5,356 `filing_artifact/` objects -> 5,743 owner rows -> 4,831
owner CIKs, every one with a bronze `submissions.json`; zero SEC fetches). 1,220 owners labeled
(851 person / 369 entity; 4 uncertain, all listed).

- **Automatic `person` clears 99%**: "no legal-form token AND structurally-empty `submissions.json`
  (no sic/stateOfIncorporation/ein/tickers/ownerOrg/FYE) AND person-shaped name" -> 841/841, Wilson
  95% LCB 0.9955. Flags are not needed; requiring officer/director only defers ~2.6% of owners.
- **Automatic entity by name token measures 99.6% (518/520 pooled with a 160-owner legacy-corpus
  supplement), LCB 0.986 -- not certified at 99%.** Both errors are persons whose surname is a
  legal-form token (`Trust Jane`, `Council LaVerne H`). With a post-hoc guard that defers
  single-token, person-shaped, structurally-empty names (C-J) the entity arm is 507/507, LCB 0.9925
  -- clears 99% only under a guard written after both errors were seen.
- Rules that read a populated `stateOfIncorporation`/`FYE` as "entity" (incl. edgartools'
  `_classify_is_individual`, which the repo parser already runs with a live SEC fetch per owner)
  top out 97.6-98.1%: SEC sets those fields on ~0.7% of person CIKs.
- `entityType` (`other` -> person) is 71% precise; flags-only (`10%-only` -> entity) is 72%: 50 of 60
  labeled no-token 10%-only owners are natural persons. Deputization: 50 rows (0.9%), 15 filings
  (3.1% of rows in the 101k-row legacy corpus).
- Deferral cost: C-H 1.1% of rows / 1.0% of owners; C-J 1.2% / 1.1%.
- Findings: [research/18](../research/18-reporting-owner-classification-precision.md); script
  `18-classify.py`; data `18-owners.jsonl`, `18-sample.jsonl`, `18-summary.json` (+ `18-extension-*`).
