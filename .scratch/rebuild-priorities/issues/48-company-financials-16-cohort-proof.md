# 16 Proof: the cohort's financials end to end

Priority: 48, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/company-financials/issues/16-cohort-proof.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task. Status: in progress (Claude, 2026-10-30 09:54 ET; operator: "start 48"). Blocked by: 47 (resolved 2026-10-29 18:03 ET). Map: [map](../../company-financials/map.md).

## Question

Run the build on the whole cohort from the local capture: counts per line item and measure, coverage by year, every null with its reason, the answer key matched, every value traced to its fact and filing; an agent reads one company's measures (profiling ticket 05's `context` command, if built). Recorded under `.scratch/company-financials/proof/`. This ends the map.

## What this proof adds to 47's

47 matched all 168,360 measures with the answer key, in a disposable PostgreSQL, the filers' SIC and place
read from their submissions files. This proof runs the installed path instead, and proves what 47 did not:
the installed commands land and build silver (`silver land`, `silver line-items`, `silver measures`); each
filer's statement format and country come from its Company master; every value is read back from the stored
tables, traced to its fact and filing; an agent reads one company's measures.

## Checklist

- [x] Inputs on this machine, no SEC request (2026-10-30 09:54 ET): the cohort's 368 company facts files
  (`clean-mdm/proving/company-facts/cohort`); each of the 368 has a captured submissions file (`all-76230`);
  323 of them are among the 6,726 Company documents of ticket 135's population proof (`cm27-raw`); the other
  45 are not counted as Companies there, so a measure that needs the statement format is null for them,
  "statement format unknown" (ticket 47's rule)
- [x] Store chosen (2026-10-30 09:54 ET): `company-on` holds 30 of the 368 Companies and has no silver database, so the proof
  runs on its own empty stores, as 135's did: Companies mastered by the installed `mastering` target, silver
  initialized there; nothing shared changes
- [x] The cohort's Companies mastered by the installed Company target (`mdm prepare-clean-company`, then the
  `mastering` run: one bundle of the 323 documents, with 135's population and Name Census) (2026-10-30 12:22 ET, full run, 31.4 min): 321 of the
  368 filers have a Company master, in 1.8 min; each master's SIC and place equal its submissions file's for 319
- [x] Silver initialized; `company_fact`, `company_line_item` and `company_measure` registered from their specs (2026-10-30 12:22 ET, full run, 31.4 min)
- [x] `company_fact` landed by `silver land` from facts.yaml's reading of the 368 files, each row's Company MDM
  id filled; a second landing changes nothing (2026-10-30 12:22 ET, full run, 31.4 min): 5,134,979 rows from 329 files with facts (39 have none),
  5,113,685 with an MDM id; landing again changed 0 of 10,000. One landing takes 16 min (about 3 min a million rows)
- [x] `silver line-items` and `silver measures` build the two tables (2026-10-30 12:22 ET, full run, 31.4 min): 96,807 line items, 168,360 measures, in 6 min
- [x] Read back from the stored tables (counts only, report kept on this machine): rows per line item and per
  measure; coverage by fiscal year; every null with its reason; every value's accession found among the
  filer's `company_fact` rows; the measures equal to the answer key (value at 10 places, null reason) (2026-10-30 12:22 ET, full run, 31.4 min):
  74,030 line items with a value, each filing found among the filer's facts (74,030 of 74,030); 86,492 measures
  with a value, every input a stored line item (86,492 of 86,492); fiscal years 1987 to 2026 (35 years); every
  null has a reason (line items: no concept filed 22,777; measures: missing year 32,230, no concept filed 27,592,
  not meaningful 17,008, financial services 3,228, denominator 1,368, no country 184, format unknown 108, mixed
  currencies 103, fiscal year changed 47); the hand key 1,600 of 1,600; the rules oracle 168,244 of 168,360:
  108 differ because those filers have no Company master (statement format unknown, as expected), 8 on mastered
  filers (6 values, 2 missing year)
- [x] An agent reads one company's measures (`edgar-warehouse silver describe`, and `context` if built) (2026-10-30 12:22 ET, full run): `silver describe company_measure` from the installed bundle gives its definition, grain, key, links, time and trust; `context` is not built for silver measures
- [x] The proof script committed (`.scratch/company-financials/proof/`), counts only (2026-10-30 11:51 ET, 91d1fec3)
- [x] Finding: the installed bundle did not ship `edgar_warehouse.financials`, so `silver line-items` failed
  (first full run, after 40 min). Fixed in the bundle's file list; the bundle test now asserts every module
  a shipped file imports is installed: failed before the fix on that module alone, passes after (2026-10-30 10:40 ET)
- [x] Finding: `line_items` and `measures` looked for their rules files beside a checkout
  (`parents[2] / "rules"`), absent from the bundle (second full run, after 40 min). They now use
  `rules.files.ROOT`; the bundle test loads both files from the installed bundle: failed before the fix with
  the proof's error, passes after, 3 min; 889 affected unit tests pass (2026-10-30 11:29 ET)
- [x] Waste removed (operator, 2026-10-30: "why do we need to run it multiple time"): `COHORT_PROOF_SAMPLE=1`
  runs every step on the answer key's 3 filers in 2.2 min before the full run; the second landing repeats the
  first 10,000 rows, not all 5.1M (it took 16 min a run) (2026-10-30 11:50 ET)
- [x] Found by the sample, all in the proof, none in silver: the submissions path (`filed()` found no file,
  so the oracle had no SIC: 60 "financial services" differences); measure inputs are an object, and a computed
  figure (free cash flow, NOPAT) traces through its parts: 879 of 879 measures with a value trace to stored
  line items; the hand key keeps 12 places, silver 10: compared within silver's rounding step, 1,600 of 1,600
  equal (rounding the key again moved 4 by one in the last place). Sample: masters' SIC and place equal the
  submissions file's 3 of 3; silver equals the rules oracle 1,600 of 1,600 (2026-10-30 11:50 ET)
- [x] The full proof runs once with the stronger checks (operator, 2026-10-30 13:09 ET: "no more weaker check stronger
  checks must run once with the appropriate checks"): the 12:22 ET run's weaker checks are not the evidence;
  the run started 12:44 ET is, with the Spec review's checks, each first passed on the sample. Passed
  (2026-10-30 13:21 ET, 32.1 min): 70,366 of 70,366 filed line items equal a fact of their filing (concept, period end,
  value; a cover-page figure at its own date); 0 empty values without a reason in either table; 86,492 of
  86,492 measures with a value trace by name and year to stored line items; no measure on one side only;
  the hand key 1,600 of 1,600; the rules oracle 168,244 of 168,360; every count above as in the 12:22 run
- [x] The 8 measures on mastered filers that differ from the rules oracle (2026-10-30 13:21 ET, by filer, on this machine
  only): all one filer's ROIC (beginning and average, 4 years each). Its Company master holds a place of
  incorporation; its latest submissions file has none. Silver reads the master, as the rule says, so it finds
  the statutory rate (6 values; 2 then "missing year"); the oracle, fed the file, says "no country of
  incorporation". Silver follows the rule; the difference is in the oracle's input
- [ ] Follow-up, not this ticket's: 2 Company masters hold a place of incorporation other than their own latest
  file's (one filled where the file is empty, one empty where the file has one). Each place is copied from the
  file as filed, so survivorship across a merged master's records is the likely source; for the Company master's
  owner (MDM), not financials
- [ ] Open: the test server dropped a connection during the Company merge in 3 of 13 sample runs
  (`server closed the connection unexpectedly`); its log is now kept on every run; neither full run had one
- [x] GoF consult, three-axis review (2026-10-30 12:31 ET): GoF, leave the bundle's hand-kept file list (14 additions
  one at a time, but the new test now fails on any miss); Standards, no hard violation; Spec, five gaps in the
  proof's checks, all fixed and passed on the sample, then at full size (13:21 ET)
- [ ] PR, CI green, merged
- [ ] The operator accepts the proof (the operator's decision, never ticked for them)
- [ ] `skills/company-financials/SKILL.md`, "Status of each rule": the rules proved live, once accepted
- [x] Learning → skill (2026-10-30 13:27 ET, PR #1246 merged): `skills/mdm-engineering/SKILL.md`, "Choose the cheapest proof": a full-size proof runs once, with its final checks (reviewed, passed on a sample first); a rules file is read through `rules.files.ROOT` 
