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

## Parts

- [x] 2026-11-16 12:26 ET Ruling recorded and the evidence counted.
- [ ] A Rust test that fails first: `compare: [jurisdiction]` agrees for two addresses with one jurisdiction, and not for two, or for a missing one.
- [ ] A Python test that fails first: the waterfall pairs a filer and entity that agree on the jurisdiction only.
- [ ] The engine change (Rust and Python) and its tests.
- [ ] The jurisdiction in the SEC and GLEIF matching addresses, and the declared pass (not switched on).
- [ ] The proof: a labelled sample of the pairs the pass adds, with adversarial pairs, on a disposable store; then the operator's word to switch it on.
- [ ] Mapping Documents regenerated.
- [ ] Learning → skill.
