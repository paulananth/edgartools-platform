# A Security's issuer name and class title: which filed words it keeps

Priority: 84, tier 2. Map: [Rebuild priorities](../map.md).

Type: grilling, then task. Status: claimed (Claude, 2026-10-18 ET, branch `claude/t84-source-order`). Blocked by: 79 (Onboard funds and securities with the skills: the Security master these words sit on).

## Why

Found onboarding the 13F information tables (ticket 79). The operator ruled "A" (2026-10-14): the Security carries the issuer name and class title as filed. The filers do not agree on them:

- 999 local files, 31,071 CUSIPs as filed: 83,785 CUSIP and name pairs, 89,557 CUSIP and title pairs. A CUSIP is filed with about three names and three titles on average.
- Profiling counts 381,219 of 2,953,581 holding rows (13%) whose class title differs from the most common title of their CUSIP (`carried_value_disagrees`, titleOfClass), and 28,772 that differ from the most common one of their FIGI.
- The information tables carry no filing date, so the reduction keeps the **lexically first** name and title of each CUSIP (`reduce.yaml`, `sample_limit: 1`), not the most common one profiling compares against. The two choices differ.
- No record-level data quality check can catch this: each Security record holds one name and one title after the reduction, so the disagreement is between holding rows, not within a record. The data-quality helper drafts 0 checks for the part (ticket 79's quality step).

## Question

Which name and title does a Security keep when its filers disagree, and is a filed word ever normalised (for example an abbreviation of a class such as common stock written several ways)?

Options to put to the operator, one at a time:
1. Keep the most common filed word per CUSIP (needs a reduction mode that keeps the member with the largest count; a source-engine change, for a code ticket).
2. Keep the lexically first (today: deterministic, no engine change, but arbitrary).
3. Take the name and title from a better source once onboarded: N-PORT's issuer name and LEI (ticket 79's N-PORT parts), or OpenFIGI's name and security description (ticket 80), ranked first in `rules/merge/kinds/security.yaml`.
4. A code set for class titles in RDM (normalised titles with synonyms), with the filed title kept beside it.

## Checklist

- [x] The operator's ruling on which filed word a Security keeps: "explain the issue rerun the data profile on both sources and make openfigi priority 1 and 13f last" (2026-10-18), then, on the title, "Name only (Recommended)" (2026-10-18): OpenFIGI fills the name and ranks first, then N-PORT, then 13F; the title keeps the filed words, N-PORT before 13F (2026-10-18 13:19 ET)
- [x] The issue, measured. "Rerun the data profile on both sources" was read as profiling the sources together: data-profiling's new rank mode (`rank_sources.py`, ticket 110; `ranking.yaml` and `RANKING.md` here), not a second per-source `profile_data.py` run of findings already approved (the skill's "Profile once"). The run ( over the three sources' extracted rows: 13F 5,907,162 name and title rows, N-PORT 4,716,318 holding rows, OpenFIGI 872,383 listings; 2 min 35 s): OpenFIGI states one name for 99.7% of its 353,491 CUSIPs, N-PORT for 62.4% of 385,382, 13F for 59.9% of 29,942. OpenFIGI's names agree with N-PORT's on 10.5% of the CUSIPs both fill, with 13F's on 63.9%. OpenFIGI's `securityType` is a kind of instrument, not a class title (0.1% agreement with N-PORT's titles), so it fills no title (2026-10-18 13:19 ET)
- [x] No reduction mode needed: OpenFIGI's name is kept only where its listings state one (the existing `members` reduction and `where: {names: 1}`); configuration only
- [x] The configuration changed to the ruling: OpenFIGI's reduce, combine and record carry its name, both OpenFIGI contracts map `name_of_issuer` (versions `openfigi-security-v2`, `openfigi-security-isin-v2`: new record ids, same source codes), `security.yaml` lists OpenFIGI first and 13F last; the Mapping Documents regenerated
  - [x] Tests (2026-10-18 13:19 ET): OpenFIGI's name only where its listings state one (a second name gives none); a Security takes OpenFIGI's name over 13F's and keeps the filed title; 884 affected tests pass, `mapdoc check` clean
  - [x] Whole population, from the extracted rows (`name-change-count.json`; 2026-10-18 13:19 ET): of 405,016 filed CUSIPs, 352,495 take OpenFIGI's name (996 more get none from it, its listings stating two or more); 331,274 change words, 4,042 spelling only, 69,700 keep their name; among them, 1,700 that OpenFIGI names no single way move from 13F's name to N-PORT's (N-PORT now ranks before 13F)
  - [x] The full OpenFIGI chain with the new contracts (`openfigi-run.json`; 7,714 capture files, 11 min): 353,491 CUSIP and 380,047 ISIN records accepted; each record's name and cross-references equal a direct count from the capture (0 differences each). Found on the way and fixed: a listing with no name stopped the reduction (now a `names` table of the listings that carry one, tested), and the names group took the reduction past its 1,000,000-key budget (now 2,000,000) (2026-10-18 13:44 ET)
  - [x] Cohort Proving Run (`proving-run.json`, ticket 80's pinned cohort, 33 s on Docker Postgres): of 3,927 Securities, 3,688 take OpenFIGI's name (1,868 by CUSIP, 1,820 by ISIN), 239 keep N-PORT's (OpenFIGI states none or two); every title stays N-PORT's; OpenFIGI creates no Security; 0 CUSIPs and 0 ISINs on two Securities; a second pass changed nothing (2026-10-18 13:44 ET)
  - [x] Approval of the source order and the contract versions: the operator's rulings above, recorded under the standing words (2026-10-15, "Approved the rules always") with this test evidence (2026-10-18 13:44 ET)
- [x] Every skill gap found on the way: fixed in the skill, on its own branch: no skill could set a source order from the data; ticket 110 added data-profiling's rank mode, and refining-rules and data-onboarding now measure before reordering (#1080, merged 2026-10-18 13:07 ET) (2026-10-18 13:48 ET)
- [x] Three-axis review (2026-10-18 13:48 ET): Standards found a misplaced comment and a skipped part's format (fixed); Spec asked for the ranking evidence committed, the reading of "rerun the data profile" said plainly, and the 1,700 13F-to-N-PORT moves named (done); GoF: leave it
- [ ] PR, CI green, merge on the operator's word
- [x] Learning → skill: data-profiling's "Rank several sources" (#1080): a source order is set from measured coverage, one-value rate and pairwise agreement; a source's contract must map the field for its rank to matter
