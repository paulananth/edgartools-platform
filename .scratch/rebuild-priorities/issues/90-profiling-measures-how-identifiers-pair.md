# Profiling measures how two identifiers of one entity pair

Priority: 90, tier 1. Map: [Rebuild priorities](../map.md).

Type: task (data-profiling skill). Status: coded, in review (branch `claude/profiling-identifier-pairs`).

## Why

Operator, 2026-10-15: "Do not repeat profiling many times do it once and capture all relevant information for mdm rdm data quality data catalog and silver".

The findings name each identifier column's shape and check digit, and whether it should join or be a cross-reference. They do not say how two joining identifiers of one entity pair up. For MDM, a matching rule on a second identifier needs that answer:
- how many values of A come with exactly one value of B;
- how many come with several;
- how many values of B come with several values of A (a conflict a matching rule would merge wrongly);
- how often one carries the other inside it.

Found while onboarding the Security from N-PORT (ticket 79). CUSIP sits on the holding row and ISIN sits on the holding's identifier rows, linked by the holding's key. Answering this took a second scan of the data, which the run-once rule now forbids.

## What changes

- For each master part with two or more identifier columns, measure every pair. This includes an identifier reached through a link from another part (the holding to its identifier rows). Record it under the part's `identifiers` as `pairs`: the counts above, with no values, since the repository is public.
- Profile once: the change applies to the next source profiled. Approved findings are not re-profiled to add it.

## Checklist

- [x] The operator's word to code it: "Goal set: fix all issues and wayfinder tickets" (2026-10-16) 2026-10-16 08:37 ET
- [x] GoF consult: the profiler's identifier module: leave both; `_part` grows by a field with every finding, so the pairs are their own pass after classification (`run._identifier_pairs`), and the SQL sits in `keys.py` with the other column-pair queries, not in `identifiers.py`, which holds no SQL 2026-10-16 08:37 ET
- [x] `pairs` measured within a part and across one link; tests on a small invented data set: `keys.pairing` (within a part, across a link, one value holding the other) and the pass on a master part, 4 tests; an entity found inside a part is measured on its source part's rows; profiling tests 256 pass 2026-10-16 08:37 ET
- [x] `docs/specs/profiling/findings.md` and the data-profiling skill's "Reading the findings" 2026-10-16 08:37 ET
- [x] Three-axis review 2026-10-16 08:43 ET. GoF (fixed): the "real value" filter and the local-counter test were each written in several files, now `identifiers.real_value_sql` and `identifiers.local_counter`. Standards (fixed): a link between a number and a text column crashed the join (now compared as text, digits as numbers, as `inclusion` does); a blank counted as a value and as "one holding the other" (now left out). Spec (fixed): a nested list's rows were never paired (child links now count); a sampled part says `scan: sampled`; a found entity no longer pairs with another entity's identifier found on the same rows; a pair is measured once; the count is `distinct_pairs`. Tests: 3 more (an entity inside a part, a text-to-number link with a non-number, blanks); profiling tests 257 pass
- [ ] PR, CI green, merge on the operator's word
- [x] Learning → skill: data-profiling "Reading the findings" gains `pairs`, so a second joining identifier's matching rule is decided from the findings, with no second scan 2026-10-16 08:43 ET
