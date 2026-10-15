# Profiling measures how two identifiers of one entity pair

Priority: 90, tier 1. Map: [Rebuild priorities](../map.md).

Type: task (data-profiling skill). Status: open, waiting for the operator's word to code it.

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

- [ ] The operator's word to code it
- [ ] GoF consult: the profiler's identifier module
- [ ] `pairs` measured within a part and across one link; tests on a small invented data set
- [ ] `docs/specs/profiling/findings.md` and the data-profiling skill's "Reading the findings"
- [ ] Three-axis review; PR, CI green, merge on the operator's word
- [ ] Learning → skill
