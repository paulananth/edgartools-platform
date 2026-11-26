# Accept short words for Fold sightings into periods

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/link_periods_full.py` only. Words name a dated sighting and the period that results. No invented end. This file can merge before ticket 28. The page ignores it until `link_periods.py` exists.

## Checklist

- [x] `link_periods_full.py` is the only production file this ticket adds. `tests/unit/test_rules_try_link_periods_full.py` is new. 2026-11-25 21:56 ET
- [x] The sighting case written in those words matches ticket 28. `tests/unit/test_rules_try_link_periods_full.py`. 2026-11-25 21:56 ET
- [x] No end is invented from a missing later file. `tests/unit/test_rules_try_link_periods_full.py`. 2026-11-25 21:56 ET
- [x] Learning → skill: none. The words are a table the file reads. 2026-11-25 21:56 ET

## Answer

A short rule is ticket 28's rule, one JSON object with a `sightings` list, that may use the words below where a stored key goes. Show the full rule returns `{"lines": [...], "document": {...}}`: the words the rule used, each with its stored key, and the same sightings with every word replaced. The document folds, through `edgar_warehouse.mdm.relationships.fold_sightings`, to the same period as ticket 28's.

| Word | Stored key |
| --- | --- |
| seen on | `on` |
| still held | `held` (true holds the capacity; false or null drops it) |
| how known | `basis` (observed or stated) |
| filing id | `assertion_id` |
| filing | `subject` |
| starts | `valid_from` (a period) |
| start known by | `valid_from_basis` (a period) |
| ends | `valid_to` (a period) |
| end known by | `valid_to_basis` (a period) |
| last seen | `last_observed` (a period) |
| left for a steward | `contradictions` (the second answer of the fold) |

`title` keeps its name, because the word matches the field. A stored key typed bare in a sighting (`on`, `held`, `basis`, `assertion_id`, `subject`) is refused with the word to type and every word the file accepts. The period words and an end are not typed into a sighting: an end (`ends`, `end known by`, `valid_to`, `valid_to_basis`) is refused with the reason that it comes only from a later sighting that drops the capacity, and a missing later file leaves it empty. A word that is not in the table, a sighting missing `seen on`, `how known` or `filing id`, a basis other than observed or stated, a `held` flag that is not true, false or null, and a time with no timezone each return `{"refused": "..."}`. The file does not import `link_periods.py`, so the page ignores it until that file exists.

## Comments
