# 160: Pipeline names say what they do

Priority: 160. Map: [Rebuild priorities](../map.md). Opened 2026-11-01 20:43 ET, from the catalog review (operator, 2026-11-01: "agreed", "sec.thirteenf.extract ? agreed").

Type: task. Status: resolved. Blocked by: none.

## Question

Three catalog pipelines have names that say nothing or use a forbidden word. Can each be renamed in the rules, the engine and the catalog without losing a run or an approval?

## Parts

- [x] `sec.company` target `mdm` becomes `merge-batch`. The approval check no longer keys on the target name: a merge document or a document with an `mdm` section needs the approved digest (`tests/unit/test_mdm_approval.py`). My first rule, a step operation `mdm.merge`, failed 3 proving tests: a rules test version has no `mdm` section on purpose, so its `mastering` target runs unapproved; reproduced locally on a rebuilt engine, then fixed (2026-11-01 21:41 ET)
- [x] `gleif` target `lei` becomes `subfund-pairs`, with the `run: {source: gleif, target: lei}` reference in `rules/sources/sec.nport.security/source.yaml`
- [x] `sec-13f-reading` becomes pipeline `sec.thirteenf.extract`, target `extract`, step `extract-information-tables` (Source Extract, not "reading"), with its two engine tests and the run command in `docs/configured-13f-reading.md` and `docs/specs/source-readiness.md`
- [x] `sec.nport.registrant` keeps its ID and gets the display name "N-PORT registrants → Company"
- [x] The renamed rules need no new approval: a rename changes no mapping, and CI ran the company digest test, the proving tests and the 66 bookkeeping integration tests green on the merged commit (2026-11-01 21:41 ET)
- [x] The three-axis review; PR #1282 merged
- [x] Publish to the local OpenMetadata and read back: `check` matched, 13 pipelines under the new names, 3 old pipelines removed (2026-11-01 21:41 ET)
- [x] Learning → skill: `skills/bookkeeping/SPEC.md` and `skills/data-platform/SKILL.md` name the merge target and the `mdm`-section approval rule (2026-11-01 21:41 ET). Lesson for the ticket: run the area's tests before the first push, here `test_rules_mapdoc` and the proving tests; the mapping workbooks follow a renamed target
