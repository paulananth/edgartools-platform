# 09 Profiler gap: objects keyed by data are read as columns

Priority: 41, tier 3, product value. Map: [Rebuild priorities](../map.md). Moved from `.scratch/company-financials/issues/09-profiler-reads-object-keys-as-columns.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task. Status: claimed. Blocked by: none. Map: [map](../../company-financials/map.md).

## Question

The data-profiling skill reads a JSON object's keys as columns, so a document keyed by data (company facts: one key per concept, 633 in one filer) becomes thousands of columns. Generic fix in the skill (Claude's path): when an object's keys are many and its values share one shape, read it as a list with its key as a column. Until then `capture/to_facts_parquet.py` writes the long form. Its own branch, tests, three-axis review.

## Checklist

- [x] Inspect existing JSON flattening and its change history; complete the GoF consult and check overlap before production edits — 2026-10-16 14:10 ET; existing boundary dispatch retained, no pattern warranted, guard passed before code edits.
- [x] Reproduce keyed-object expansion with invented fixtures and specify conservative detection, key preservation and parent links — 2026-10-16 14:10 ET; 52 input tests passed in 34.94 s, including nine new shape cases; precision review follow-up below remains under test.
- [x] Implement the generic keyed-object reader without a source-specific special case — 2026-10-16 14:12 ET; expected rows, keys and parent links verified with invented root, nested, JSONL and streamed JSON fixtures.
- [x] Run affected input/profiling tests with testmon, each run bounded to five minutes — 2026-10-16 14:12 ET; initial inputs: 52 passed in 34.94 s; broader area before precision follow-up: 131 passed / 135 deselected in 49.12 s; final affected inputs/run/genericity: 58 passed / 110 deselected in 3.48 s.
- [x] Review Standards, Spec and GoF; verify no unrelated shape regression and no private data in the public diff — 2026-10-16 14:12 ET; independent three-axis rechecks clean after claimed-state/checklist and precision fixes. Spec independently reproduced both-order, cross-document and nested refusals with no loaded tables.
- [ ] Commit and push on this ticket's fresh branch after overlap checks; open its separate PR.
- [x] Learning → skill — 2026-10-16 14:12 ET; data-profiling SKILL.md, Objects keyed by data: inference threshold, key/value provenance, conservative exclusions, exact-number refusal, and approved-findings reuse. This ticket is the dedicated profiling skill-fix branch/PR.

## Review follow-up

Standards found the missing claimed state and stale checklist; corrected here. Spec reproduced a lossy mixed integer/fractional column on an invented large integer. Integer/fractional shapes are now distinct, and a cross-document/nested-list safeguard refuses a newly combined lossy column before table loading. Regression cases cover both value orders, nested observations, and exact homogeneous integers. No raw captures were used in these tests. GoF found no structural refactor warranted. Final validation and all three independent rechecks passed. This qualifies generic invented shapes; it does not qualify a production Company facts Dataset Contract or change existing approved findings.

## Review

### Standards

Dedicated fresh ticket branch/worktree; four named paths; invented examples only. Overlap guard passed before production edits and on the reviewed diff. No provider requests, production stores, merge rules or MDM migrations. Claimed state and checklists corrected during review.

### Spec

Many same-shape object entries become rows with their original key; nested children preserve parent links. Small/mixed/empty maps retain dotted fields. Large integers are not silently rounded by a new mixed numeric column: the run refuses before loading instead. The full Company financials reader remains ticket 45 after its operator decisions.

### GoF

The available gof-refactor-reviewer method reviewed the existing flattener and history before code and reviewed the final diff afterward. Keep the existing input adapter and recursive traversal; no pattern hierarchy is justified.
