# Claude → Codex: the Person name normalizer to import (`person-name@v2`)

Date: 2026-09-21. From: Claude (Person consumer contract). For: whoever builds
Clean MDM's Person consumer. Nothing here edits a Codex file.

## What exists

`edgar_warehouse/domain/policy/person_name.py` — pure functions, no I/O, no
network, 52 unit tests (`tests/unit/test_person_name.py`):

| Name | Use |
|---|---|
| `parse_conformed(name)` | EDGAR `LAST FIRST MIDDLE [SUFFIX]` — Form 3/4/5 reporting owners. Read silver `owner_name_raw` (ticket 19), **not** `owner_name`, which is edgartools' display reversal |
| `parse_western(name)` | free text `First Middle Last` — 8-K Item 5.02 `person_name`, DEF 14A `exec_name` |
| `is_person_name_candidate(name)` | eligibility for free-text name fields: no role/entity vocabulary, parsable shape |
| `PersonName.key_mi` | ticket 20's name component: `surname|given|middle initial` |
| `PersonName.generational` | the set ticket 20's suffix veto compares (`JR`/`SR`/`II`/`III`/`IV` only) |
| `NORMALIZER_VERSION` | `"person-name@v2"` — record it with every Tier B decision |

## Why it matters to you

`docs/specs/person/consumer.md` release gate 2: Tier B activation **requires**
this normalizer in the same release. Research 17's normalizer (`v1`), the one
research 21 measured, had three defects (ticket 25); v2 repairs them and
re-scores research 21's census with the only measured false merge gone (1 of
11 same-issuer homonym CIK pairs → 0) and precision unchanged. Details and
numbers (n = 656, LCB97.5 0.99142 conservative, 0 of 11 homonym merges):
`.scratch/person-consumer-contract/issues/25-fix-person-name-normalizer-defects.md`,
`research/25-rescore.json`.

## Asks

1. Import it rather than re-implement: Tier B's calibration (n = 656,
   LCB97.5 0.99142) holds for **this** normalizer, not an equivalent one.
2. When the Person policy's `compound_key_equal` components and the 8-K
   eligibility steps are written, reference this module through registered
   `name@version` pairs that carry `person-name@v2` in the version string
   (e.g. `normalize_person_name@conformed-v2` / `@western-v2`), so a policy
   version pins it. How that maps onto the policy language's §5 registry is
   your call; tell Claude if a new primitive is needed.
3. Two declarations of one concept to reconcile when you do: the policy
   prototype's `person_suffix` (rule C-J's `name_shape` list) carries
   `MR`/`MRS`/`MS`/`DR` as suffixes; this module treats them as titles
   (`CONFORMED_HONORIFICS`). Same effect on the key; different declaration.
4. Eligibility (`is_person_name_candidate`) is for free-text sources only.
   A Form 3/4/5 owner's person-or-entity decision is rule C-J's, upstream.
5. Disagreement or a needed change: a note under `.scratch/handover/`.
   Claude owns this module and its tests until your Person consumer takes
   it over by handover.
