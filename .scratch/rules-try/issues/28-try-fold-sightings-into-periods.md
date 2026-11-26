# Try Fold sightings into periods

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/link_periods.py` only. The person pastes sightings. The page calls `fold_sightings`. A missing later file does not invent an end. Do not import `link_masters.py`.

Invented pass: a dated sighting becomes the period the relationship held.

## Checklist

- [x] `link_periods.py` is the only production file this ticket adds. `tests/unit/test_rules_try_link_periods.py` is new. 2026-11-25 21:54 ET
- [x] A dated sighting becomes that period. `tests/unit/test_rules_try_link_periods.py`. 2026-11-25 21:54 ET
- [x] A missing later file does not invent an end. `tests/unit/test_rules_try_link_periods.py`. 2026-11-25 21:54 ET
- [x] This file does not import `link_masters.py`. `tests/unit/test_rules_try_link_periods.py`. 2026-11-25 21:54 ET
- [x] Learning → skill: none. The family is one call to the existing fold. 2026-11-25 21:54 ET

## Answer

`link_periods` shows the title "Fold sightings into periods (the rule box holds the sightings)" and no input box besides the rule. The fold has no other setting, and Show the full rule can only rewrite what is in the rule box, so the sightings are the rule: one JSON object with a `sightings` list. A sighting is `{"on", "held", "basis", "title", "assertion_id", "subject"}`: the capacity held (`held` true) or dropped (`held` false, null or absent) on the date `on`, observed or stated. Try calls `edgar_warehouse.mdm.relationships.fold_sightings` and returns `{"periods": [...], "contradictions": [...]}`. A dated sighting becomes one period that starts on `on`. The period ends only when a later sighting drops the capacity; a later file that is not there, or a later sighting that still holds it, leaves `valid_to` and `valid_to_basis` null, and only moves `last_observed`. Sightings fold by `on`, not by the order pasted. An observed sighting after a stated end is returned in `contradictions` for a steward and does not reopen the period. A rule that is not JSON, not one object, with no `sightings` list, a sighting that is not an object, a basis other than observed or stated, a `held` flag that is not true, false or null, a time with no timezone, or no `assertion_id` returns `{"refused": "..."}`. The file does not import `link_masters.py`.

## Comments
