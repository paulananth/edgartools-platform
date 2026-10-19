# Switch on the N-PORT registrant and fund over the captured quarter

Priority: 118 (operator, 2026-10-19: "Can you turn on company mastering one source at a time sec, geilf, and the rest"; the N-PORT registrant follows SEC Company). Map: [Rebuild priorities](../map.md).

Type: task (configuration only). Status: in progress (Claude, 2026-10-19). Blocked by: #1113 (a source with no feed of its own activates) for the switch-on.

## Checklist

- [x] A `mastering` target declared (configuration only): the filing dates (`submissions.yaml`), the registrant rows with them (a lookup from that reading), each CIK (`reduce.yaml`), its latest filing (`combine.yaml`), one record each (`record.yaml`, new: the row as the record), prepare, merge, processed; `rules/source-sequence.yaml` names `mastering`; a `receipts.jsonl` beside the captured 2026 Q2 data set (2026-10-19 12:50 ET)
- [x] `rules test`, two passes on a fresh store (2026-10-19 12:50 ET; 1 min 37 s): passed, the second pass changed nothing; 1,947 registrant Companies (the profile's 1,947 CIKs, ticket 79 part 2), no open review, no identifier on two masters
- [x] Saved as `registrant-2026-10-19.pipes-on`, its test run recorded as its proof, approved under the standing approval, active in the `company-on` store after Person (activated with #1113's code); `rules run` (no feed) over the quarter (2026-10-19 12:51 ET): complete in 42 s, every step verified; MDM holds 2,433 Companies (486 SEC, 1,947 registrants; none joined, the bundle holds operating companies), no identifier on two masters
- [x] A step may read with another source's rules file (`<source>/<file>.yaml`, generic): the fund reads the registrant's readings for each filing's date and registrant CIK; that file's digest joins the processing identity (2026-10-19 12:56 ET). GoF consult: one naming rule, no new structure
- [x] The fund's `mastering` target declared (configuration): the registrant's two readings, its filings with both pair sets, each series (`reduce.yaml`), LEI pairs, the latest filing (`combine.yaml`), one record each (`record.yaml`, new), prepare, merge, processed; the sequence names `mastering` (2026-10-19 12:56 ET)
- [x] Fund `rules test`, two passes on a fresh store (2026-10-19 12:56 ET; 2 min 28 s): passed, the second pass changed nothing; 12,937 Funds and 7 waiting for an LEI that fails its check digit (12,944 series, the profile's), no identifier on two masters
- [x] Fund: saved as `fund-2026-10-19.pipes-on`, its test run recorded, approved under the standing approval, active in the `company-on` store after the registrant; `rules run` (no feed) over the quarter (2026-10-19 12:57 ET): complete in 80 s, every step verified
- [ ] Three-axis review, PR, CI, merge
- [ ] Learning → skill
