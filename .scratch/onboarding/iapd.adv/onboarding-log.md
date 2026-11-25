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

## Commands named by the skill that did not exist

(none yet)
