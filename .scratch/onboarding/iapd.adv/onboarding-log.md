# Onboarding log: iapd.adv private funds (Schedule D 7.B)

Ticket: [Implement the current-model hosted ADV private-fund load](../../hosted-adv-private-fund-ingestion/issues/01-implement-current-model-hosted-adv-private-fund-load.md).

Operator, 2026-11-24 19:11 ET: "implement hosted-adv-private-fund-load". The ticket was marked claimed by Codex
(2026-11-19) in an uncommitted worktree only; `main` had it open. Claude takes it on these words.

## The source

- Feed: `sources/iapd.adv` (live). Today it masters adviser filings (`IA_ADV_Base_A`) into Company by CRD, custodians
  (5.K(3)) into Company, and lands custody amounts in silver. It reads no 7.B table and no ERA table.
- Kinds: `fund_structure` exists (`rules/merge/kinds/fund_structure.yaml`, N-PORT and N-CEN series, joined by SEC
  series id and LEI). Company exists.
- RDM `mdm-relationship-types` 6 already holds `INVESTMENT_ADVISER_TO` (capacities `advisor`, `subadvisor`, both
  N-CEN's words) and `IS_FEEDER_TO`; both definitions name Form ADV as a source.
- No identifier type for the private fund id (PFID) exists in `rules/identifiers/`.
- Captures with receipts: `iapd.adv/p07-2026-03` and `iapd.adv/p07-2026-06` (two months, each `receipts.jsonl`).
  The ticket's "13-month window" has no receipt-backed capture beyond these two.
- Provider: SEC IAPD. No provider request was made.

## Discover (measured on the March and June captures; counts only)

Profile: `~/.local/share/edgartools/mdm/profiling/iapd.adv-7b-2026-03/findings.yaml` (private, outside Git), one
run over IA and ERA 7.B(1), 7.B(2) and both Base tables of March. Operator, 2026-11-24 19:26 ET: "Approve the findings (Recommended)" (recorded with `profile_data.py approve`). IA 7.B(1) is not in that profile (the profiler refused it for the malformed rows); its counts above were measured with Python's CSV reader on the same file.

| Table | Rows | PFIDs | Filings |
|---|---|---|---|
| IA 7.B(1), March | 68,253 read (3 malformed) | 63,746 | 5,529 |
| ERA 7.B(1), March | 49,740 | 49,065 | 4,339 |
| IA 7.B(2), March | 4,163 | 3,407 | 815 |
| ERA 7.B(2), March | 8,200 | 6,934 | 591 |
| IA 7.B(1), June | 13,798 | | |
| ERA 7.B(1), June | 25,421 | | |

- **PFID** has one shape on every row of every table: three digits, a hyphen, ten digits. No row lacks one. A PFID
  appears at most once per filing.
- **One fund, several filings in a month:** 3,833 IA and 657 ERA PFIDs are on two or more filings (amendments, or
  several advisers reporting one fund). 197 PFIDs are in both IA and ERA 7.B(1).
- **7.B(2)** (a fund another adviser reports in full): 10,110 PFIDs, 8,354 with a 7.B(1) row in the same month;
  1,756 without.
- **Every 7.B(1) filing is in its Base table** (IA 5,529 of 5,529 in `IA_ADV_Base_A`; ERA 4,339 of 4,339 in
  `ERA_ADV_Base`). ERA filings are not mastered today, so an ERA fund's adviser has no Company record from this feed.
- **Master-feeder:** IA "Master Fund ID" is filled on 3,182 rows (1,727 masters), 2,931 of them found as a 7.B(1)
  fund the same month. "Feeder Fund" is Y on 3,623 rows.
- **Subadviser** (7.B(1)): Y on 1,256 of 68,253 IA rows.
- **Defect: three malformed rows.** March's IA 7.B(1) has 3 rows with a stray quote mark, so each reads as 30
  fields of 38. The engine's CSV reader (`crates/source-contract/src/formats.rs`, `delimited`) refuses a whole
  artifact on such a row (`malformed`), so March's IA funds cannot be read as configured. The profiler also refused
  that table. June's four tables are clean.

## Questions and answers

- Scope, IA or ERA funds (asked with the counts above; recommendation IA first). Operator, 2026-11-24 19:26 ET: "IA first, then ERA (Recommended)". IA funds are part 1; ERA funds, with ERA adviser filings mastered by CRD, are part 2 of this ticket.
- Fund identity (asked: join by PFID only, or PFID plus a lookup-only name id). Operator, 2026-11-24 19:26 ET: "Join by PFID only (Recommended)". A new identifier type `pfid`, one matching rule, one PFID per Fund Structure; a name never joins.
- Capacities (asked: reuse N-CEN's `advisor`/`subadvisor`, Form ADV's own `adviser`/`subadviser`, or none). Operator, 2026-11-24 19:26 ET: "Reuse advisor/subadvisor (Recommended)". Their reference-data definitions gain Form ADV 7.B(1)'s subadviser answer.
- Feeder link (asked: `IS_FEEDER_TO` from "Master Fund ID" by PFID, or not now). Operator, 2026-11-24 19:26 ET: "Yes, IS_FEEDER_TO by PFID (Recommended)".
- 7.B(2) funds (asked: a 7.B(2) row creates its fund by PFID, or only links). Operator, 2026-11-24 19:26 ET: "Yes, by PFID (Recommended)". 7.B(1) ranks first for every field.
- The 3 malformed March rows (asked: an engine change that sets a wrong-width row aside, counted, off by default; or load June only). Operator, 2026-11-24 19:26 ET: "Code: set the row aside (Recommended)". GoF consult before code; test first.
- 7.B(2) capacity (asked: `advisor`, a new capacity, or no link). Operator, 2026-11-24 19:34 ET: "advisor (Recommended)".
- Approval of the rules versions this onboarding makes (`iapd-adv-private-fund-2026-11-24.pfid`, rule
  `iapd-adv-fund-pfid` 2026-11-24.pfid, `fund_structure-2026-11-24.adv-private-funds`,
  `iapd-adv-filing-csv-2026-11-24.adviser-profile`): recorded as given under the standing rule (operator,
  2026-10-17: "auto merge and not ask for approval"), 2026-11-24 19:34 ET. What it changes: Form ADV's private funds become
  Fund Structures by PFID, linked to their advisers and masters, and the Form ADV adviser filings give the adviser
  role. Evidence: the integration test and the June proof below.

## Proof on the real June file (disposable store `advfund-proof`, stopped after)

`edgar-warehouse load` of `iapd.adv` then `iapd.adv.fund` over `iapd.adv/p07-2026-06`, then `silver links` (2026-11-24 19:30 ET).
Counts only; expected counts computed from the same file with Python's CSV reader.

| Measure | Expected from the file | Loaded |
|---|---|---|
| Fund Structures | 12,533 distinct PFIDs (7.B(1) and 7.B(2)) | 12,533 |
| INVESTMENT_ADVISER_TO, advisor | 12,444 (adviser, fund) pairs | 11,677 linked |
| INVESTMENT_ADVISER_TO, subadvisor | 305 | 295 linked |
| IS_FEEDER_TO | 802 feeder pairs, 654 with the master in the file | 652 linked, 1 a hierarchy cycle |
| Reviews | | 30 Companies in review, no fund |

- Corrected 2026-11-24 20:42 ET: the cause below was only part of it on a two-month load (see "Proof, IA and ERA").
- The 777 adviser links not made: inferred to start at the 30 advisers in review (`unresolved_endpoint_identity`, 781
  with other types); the review reasons were not read (the review table showed no open row), so the cause is not
  measured. No link creates a master.
- The 148 feeder links whose master is not in June's file wait (`unresolved_endpoint`, 4,585 with this load's
  CUSTODIAN and RELATED_PERSON links, whose targets this store did not load).
- A second load of the same month: "all 1 documents already loaded", nothing changed.
- June's fund run took 0.2 minutes.

## Commands named by the skill that did not exist

- `edgar-warehouse rules test` (data-onboarding, **test**): not in this build. Used `edgar-warehouse load` on a
  disposable store from `local-test-stores.py up`, then `silver links`; the store needed `deploy-silver.sh` first.

## Proof, IA and ERA, March and June (disposable stores, stopped after; 2026-11-24 20:42 ET)

118,554 Fund Structures and 23,167 filing records, equal to the files. Adviser links: 130,036 expected from the files, 126,295
made, 3,737 at advisers in review, 4 of two advisers whose filings of one month state both roles for one fund. The first run,
with the links on the fund's record, made 120,749: 5,550 March links were dropped when June re-reported the fund.
Approval of `iapd-adv-fund-filing-pfid` (2026-11-24.pfid), `fund_structure-2026-11-24.adv-links-per-filing` and
`iapd-adv-fund-filing-2026-11-24.links-per-filing`: under the standing rule ("auto merge and not ask for approval") and the
ruling "Join by PFID only (Recommended)", on this evidence, 2026-11-24 20:42 ET. Data quality, fund name: "Set it aside (Recommended)".
