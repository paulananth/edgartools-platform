# 01d Profiling follow-ups (deferred parts of 01b and 01c)

Type: task. Phase: A. Blocked by: 01b, 01c. Map: [map](../map.md). Plan: [plan](../plan.md).

The deferred parts of 01b and 01c that can be done locally now (operator,
2026-10-08: "Yes", after the list of what can be worked on). One PR each.
Still blocked and left on their tickets: Snowflake in place (no non-prod
Snowflake; profiling never reads prod), the placeholder EIN, `TYPES_V0`, roles on
real data, approvals in a Rules Database.

## Checklist

- [x] Distribution drift in compare: each column's distribution in findings.yaml (quantiles of a number or date, shares of a code's values; none for personal columns); compare reports PSI for codes and KS for numbers and dates (01b line 24): `profile.distribution`, `drift.distribution_drift`, `psi`, `ks`; GoF consult: one more section in `compare` and two small measures, Rule 0; chi-square left out (on a large delivery any difference is significant); tests: distributions kept and never for a personal column, a tripled amount and a moved group reported, PSI and KS values (135 profiling tests pass); findings spec §2 and §7, SKILL.md compare 2026-10-08 11:02 ET
- [x] Drift review (Standards, Spec, GoF): GoF leave it; fixed: a long code list no longer drifts when values only swap out of the listed top 200 (a value missing from an incomplete list joins "other"), a zoned time is its own instant, a column whose measure changed kind is reported, infinite values left out of quantiles, KS exact at a jump, the thresholds' source stated correctly (138 profiling tests pass) 2026-10-08 11:05 ET
- [x] Drift: PR, CI, merge on the operator's word: #869, CI green, merged by the operator as 5ddf3d7b 2026-10-08
- [x] Coincidental dependencies told from real hierarchies (01c line 20): lift over guessing the parent's commonest value ≥ 0.5, at least half the rows with a child value seen twice (a list of codes exempt), a rejected level ends the child's search; a yes/no flag is never a level (operator, 2026-10-08: "Flag is not a level (Recommended)"); `dependencies_not_hierarchies` in findings; 500 SEC documents: no false hierarchies left; Trial B 52 of 52; review fixed a lost finest level, a skipped level and a too-strict lift; #870, CI green, merged on the operator's word as 9f903a00 2026-10-08 13:33 ET
- [x] GoF consult on level tables: a new finder beside `by_link_part`, one call in `_hierarchies`; Rule 0 2026-10-08 13:41 ET
- [x] Evidence from separate level tables (01b line 22): `hierarchy.by_level_tables`; a reference part may point at one smaller list as its coarser level; a part's own counter key never links to another part's key under another name (the false links that hid the levels); the same hierarchy found by dependency inside a list is left out. Tested: a synthetic set (division > group, an orphan marked); AdventureWorks' product category and subcategory lists (Microsoft sample, local only, not committed): `productcategory > productsubcategory` found, both reference; Sakila (real) has no reference level tables (its city and country are master data with names); Trial B 52 of 52; 500 SEC documents unchanged; 143 profiling tests pass 2026-10-08 13:41 ET
- [x] Level tables review (Standards, Spec, GoF): fixed from GoF: one function builds every hierarchy record (four copies had drifted), the chain's links stored in the record (`via`); fixed from Standards and Spec: a list naming one list twice crashed the run (a chain needs one parent per level and two parts), the counter-key rule dropped a real extension link (now only a key named for its own part and not the other is a coincidence), free-text notes pointing at a smaller part were classed reference (a level must be a list of codes: a short key label, no measures), orphans compared as numbers when the link was, the 0.99 bar applied, the level column is the key the link names; negative tests added; AdventureWorks, Trial B (52 of 52) and the 500 SEC documents rerun unchanged; 145 profiling tests pass 2026-10-08 13:49 ET
- [ ] Level tables: PR, CI, merge on the operator's word
- [ ] Snapshot-or-changes, versions per key, refresh rate and key persistence from two deliveries, on fixtures (01b line 27); a real-data result needs a second delivery of a local feed
- [ ] A hierarchy check in the engine (01c line 21): new code; using it in a live quality.yaml is a rule version for the operator's approval
- [x] Ticket 05b: its PR, CI and merge part checked (#868, 1539704d) 2026-10-08 11:00 ET
