# Switch on SEC Person over captured submissions

Priority: 117 (operator, 2026-10-19: "Can you turn on company mastering one source at a time sec, geilf, and the rest"; Person follows GLEIF in `rules/source-sequence.yaml`). Map: [Rebuild priorities](../map.md).

Type: task. Status: in progress (Claude, 2026-10-19). Blocked by: none.

## Found (2026-10-19 ET)

- Person declares no feed of its own: it reads the submissions files SEC Company's feed captures. Activation refused a source that masters with no `acquisition` ("Source MDM activation requires approved acquisition authority"), and dataset registration required a feed naming each dataset. Under the 2026-10-19 ruling (the pipes switch on apart from live data), neither is needed to switch the pipes on.
- Person's last proof: the switch-on proof of 2026-10-14 15:08–15:54 ET (ticket 11): all 76,230 captured submissions, 31,326 people, no CIK on two people or on a Person and a Company, the second pass changed nothing. Its rules changed once since: #1095 (the Bookkeeping section in version 2, with its own `rules test` on Person).

This finishes the decoupling ticket 114 made (slice 1, #1108) under the operator's approval of generic platform changes (2026-10-19, "Yes, both generic (Recommended)"): it is not a change for Person alone; every source that reads another source's captured files switches on the same way.

## Checklist

- [x] A source with no feed of its own activates and registers its datasets on its pipes alone (`registration_authority` checks a feed only when the source declares acquisition; `Rules.activate` no longer refuses it) (2026-10-19 12:39 ET). GoF consult: one condition moved, no new structure. Test: `tests/integration/test_local_test_stores_postgres.py` activates Person's real document into a store's MDM and finds its dataset registered (6 passed with `tests/unit/test_processing_authority.py`)
- [x] Saved as `person-2026-10-19.pipes-on`, the 2026-10-14 proof carried forward (#1095 named), approved under the standing approval, active in the `company-on` store after Company and GLEIF; `rules run` (no feed) over the same 512-document bundle (2026-10-19 12:45 ET): complete in 59 s, every step verified; the bundle is Company's cohort, so the Person rule makes no Person master: 398 more filers held back `classification_deferred` (424 with Company's 26) and 114 `classification_entity_undetermined`; Company (486) and GLEIF (225 bound) unchanged, no identifier on two masters
- [x] Three-axis review (2026-10-19 12:43 ET): GoF: leave it. Spec: stale lines in `docs/specs/source-readiness.md` and Bookkeeping SPEC rewritten; both registration cases tested; this change linked to the generic ruling. Standards: a source with no feed of its own must name the family it reads (`bronze.family`) for each dataset; a dataset belongs to the source that first registered it, and another source's activation is refused; scope: every source with no feed of its own switches on the same way (gleif, iapd.adv, sec.ownership, sec.thirteenf.information_table, sec.nport.*), as the ruling covers "the rest" (each still needs its run target and its own switch-on). Tests: 7 unit, 2 integration passed
- [x] PR, CI, merge (#1113 merged 2026-10-19 13:03 ET)
- [x] A run over captured filings of people (operator, 2026-10-19: "Can you turn on person") (2026-10-19 13:51 ET): `rules run` (no feed) in `company-on` over the 500 filings of the earlier Person test (`person-1000/documents-1.json`, 496 found in the capture), complete in 47 s, every step verified: 194 Person masters; the rest held back with open reviews, 221 `classification_entity_undetermined` and 81 `classification_deferred` (39% people, as in the 2026-10-14 proof's 31,326 of 76,230); Company (2,433), Funds (12,937) and GLEIF unchanged; no identifier on two masters
- [ ] Learning → skill
