# 250: A name pass compares the state of incorporation

Type: task (an engine change, then configuration). Status: open. Blocked by: none. Related: ticket 249 (GLEIF creates its Company), ticket 09 (the cascade).

## Ruling

Operator, 2026-11-16: "engine change for jurisdiction". After ticket 249, an SEC filer whose GLEIF twin the name pass has not paired would create a second Company. The pass compares only street, city and postcode (and country); the SEC business address and GLEIF's legal or headquarters address agree on city or postcode for 237 of 993 look-alike issuer names, but the SEC state of incorporation agrees with GLEIF's jurisdiction for 635 (country agrees for 850). A pass may now compare the jurisdiction.

## Evidence (hosted counts, 2026-11-16)

993 GLEIF issuer records have a name equal to an SEC filer's (legal form dropped, so an upper bound): 990 match exactly one SEC filer. Country agrees 850, state of incorporation against jurisdiction 635, city or postcode 237. The jurisdiction helpers already exist (`names.jurisdictions_agree`, the Rust `places_agree`).

## Design

1. **Engine (Rust, `record_pairs.rs`):** `part_agrees` gains the part `jurisdiction`: the two prepared addresses' `jurisdiction` values agree by `places_agree` (a territory's own code, a country, a subdivision of it).
2. **Python (`cascade.py`):** `PARTS` gains `jurisdiction`; a `Place` carries it; `_part_agrees` compares it with the same function, so the waterfall and the Merge Stage's re-check say the same.
3. **Configuration:** the SEC record's matching address carries the ISO jurisdiction of its state of incorporation, and GLEIF's matching addresses carry `jurisdiction`; a new pass `sec-gleif-name-jurisdiction` is declared, **not switched on**: a rule other than an issued identifier is switched on only after a measured proof at its kind's bar (labelled sample and adversarial pairs).

## Revised design (operator, 2026-11-16: "Option 1 then option 2 test")

The address objects are built from the displayed address field and copy every key, so a `jurisdiction` key there would show in the master's address, and the state-to-ISO crosswalk lives only in Python. So the part reads the two **records' fields** (catalog keys `left_jurisdiction_field` and `right_jurisdiction_field` in `rules/mastering/engine-v1.yaml`: `state_of_incorporation` and `jurisdiction`). The Rust re-check turns a US state's code (the 50 states, the District, the territories) into `US-` and the code, and compares it with GLEIF's jurisdiction by `places_agree`; another country's code agrees with nothing. The Python waterfall passes the same value (`cascade._us_state`). Option 2, the full crosswalk in the engine, is measured below before it is built.

## Option 2 built (operator, 2026-11-16: "build option 2")

The Rust command takes the pinned crosswalk as data (`jurisdictions`, from `names._EDGAR_ISO`, 308 codes), so the re-check handles every country: A1 is British Columbia (CA-BC), E9 the Cayman Islands (KY), a code the crosswalk does not hold agrees with nothing. The US-only table and the waterfall's `_us_state` are gone. Measured before building, on 732 look-alike issuer records that match one SEC filer by name (legal form kept): 480 agree by the US states alone, 616 by the crosswalk, 136 more.

## Parts

- [x] 2026-11-16 12:26 ET Ruling recorded and the evidence counted.
- [x] 2026-11-16 12:29 ET A test that failed first through the Rust re-check: `test_a_cascade_pass_may_compare_the_jurisdiction_and_rechecks_it_on_the_stage_rows` (`A pass compares an unknown address part: jurisdiction`): one jurisdiction agrees; two, or a missing one, do not.
- [x] 2026-11-16 12:29 ET A test that failed first in the waterfall: `test_a_pass_that_compares_the_jurisdiction_pairs_places_that_differ_but_the_state` (`ValueError: A pass compares an unknown address part: jurisdiction`).
- [x] 2026-11-16 12:29 ET The engine change: the part `jurisdiction` in `record_pairs.rs` (`part_agrees`, by `places_agree`) and in `cascade.py` (`PARTS`, `Place.jurisdiction`, `_part_agrees`, the same function). The Rust tests and 1,243 mdm, waterfall and architecture tests pass.
- [x] 2026-11-16 13:22 ET The catalog keys, the Rust reading of the two fields (US states only) and the declared pass `sec-gleif-name-jurisdiction`, **not switched on** (`test_the_jurisdiction_pass_is_declared_and_not_switched_on`); Mapping Document regenerated; the company fixture's policy digest updated. 1,355 unit and 1,320 mdm tests and the Rust tests pass; the installed-bundle tests build from the committed tree.
- [x] 2026-11-16 13:33 ET Option 2: the crosswalk in the engine (`record_pairs.rs`, `matching.compare_candidate_records`); tests that failed first: non-US pairs agree (`assert False`) and the waterfall pairs a province (`KeyError: '1'`); the Rust tests and 1,268 mdm, architecture and waterfall tests pass.
- [ ] The proof: a labelled sample of the pairs the pass adds, with adversarial pairs, on a disposable store; then the operator's word to switch it on.
- [ ] Mapping Documents regenerated.
- [ ] Learning → skill.
