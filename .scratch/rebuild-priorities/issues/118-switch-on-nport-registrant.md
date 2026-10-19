# Switch on the N-PORT registrant over the captured quarter

Priority: 118 (operator, 2026-10-19: "Can you turn on company mastering one source at a time sec, geilf, and the rest"; the N-PORT registrant follows SEC Company). Map: [Rebuild priorities](../map.md).

Type: task (configuration only). Status: in progress (Claude, 2026-10-19). Blocked by: #1113 (a source with no feed of its own activates) for the switch-on.

## Checklist

- [x] A `mastering` target declared (configuration only): the filing dates (`submissions.yaml`), the registrant rows with them (a lookup from that reading), each CIK (`reduce.yaml`), its latest filing (`combine.yaml`), one record each (`record.yaml`, new: the row as the record), prepare, merge, processed; `rules/source-sequence.yaml` names `mastering`; a `receipts.jsonl` beside the captured 2026 Q2 data set (2026-10-19 12:50 ET)
- [x] `rules test`, two passes on a fresh store (2026-10-19 12:50 ET; 1 min 37 s): passed, the second pass changed nothing; 1,947 registrant Companies (the profile's 1,947 CIKs, ticket 79 part 2), no open review, no identifier on two masters
- [ ] Save, record the test run, approve under the standing approval, activate in the `company-on` store; `rules run` over the quarter
- [ ] Three-axis review, PR, CI, merge
- [ ] Learning → skill
