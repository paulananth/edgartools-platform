# 160: Pipeline names say what they do

Priority: 160. Map: [Rebuild priorities](../map.md). Opened 2026-11-01 20:43 ET, from the catalog review (operator, 2026-11-01: "agreed", "sec.thirteenf.extract ? agreed").

Type: task. Status: open. Blocked by: none.

## Question

Three catalog pipelines have names that say nothing or use a forbidden word. Can each be renamed in the rules, the engine and the catalog without losing a run or an approval?

## Parts

- [ ] `sec.company` target `mdm` becomes `merge-batch`. The engine check at `edgar_warehouse/bookkeeping/clean/engine.py` keys the approval on the target name `mdm`; first make it key on the step operation (`mdm.merge`), with a test that a merge target of any name still needs the approved digest
- [ ] `gleif` target `lei` becomes `subfund-pairs`, with the `run: {source: gleif, target: lei}` reference in `rules/sources/sec.nport.security/source.yaml`
- [ ] `sec-13f-reading` becomes pipeline `sec.thirteenf.extract`, target `extract`, step `extract-information-tables` (Source Extract, not "reading"), with its two engine tests and the run command in `docs/configured-13f-reading.md` and `docs/specs/source-readiness.md`
- [ ] `sec.nport.registrant` keeps its ID and gets the display name "N-PORT registrants → Company"
- [ ] The renamed rules are approved again under the standing rule-approval ruling (2026-10-15), with test evidence on the ticket
- [ ] The three-axis review; PR
- [ ] Publish to the local OpenMetadata and read back: the new names are in, the old pipelines are gone
- [ ] Learning → skill: name the rule that an engine check keys on an operation, not a target name, in the bookkeeping or mdm-engineering skill, or write "none"
