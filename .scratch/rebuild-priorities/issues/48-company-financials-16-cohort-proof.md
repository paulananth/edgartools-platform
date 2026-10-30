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
- [ ] The cohort's Companies mastered by the installed Company target (`mdm prepare-clean-company`, then the
  `mastering` run: one bundle of the 323 documents, with 135's population and Name Census)
- [ ] Silver initialized; `company_fact`, `company_line_item` and `company_measure` registered from their specs
- [ ] `company_fact` landed by `silver land` from facts.yaml's reading of the 368 files, each row's Company MDM
  id filled; a second landing changes nothing
- [ ] `silver line-items` and `silver measures` build the two tables
- [ ] Read back from the stored tables (counts only, report kept on this machine): rows per line item and per
  measure; coverage by fiscal year; every null with its reason; every value's accession found among the
  filer's `company_fact` rows; the measures equal to the answer key (value at 10 places, null reason)
- [ ] An agent reads one company's measures (`edgar-warehouse silver describe`, and `context` if built)
- [ ] The proof script committed (`.scratch/company-financials/proof/`), counts only
- [ ] GoF consult, three-axis review
- [ ] PR, CI green, merged
- [ ] The operator accepts the proof (the operator's decision, never ticked for them)
- [ ] `skills/company-financials/SKILL.md`, "Status of each rule": the rules proved live, once accepted
- [ ] Learning → skill
