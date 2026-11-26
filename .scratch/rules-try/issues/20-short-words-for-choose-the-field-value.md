# Accept short words for Choose the field value

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/field_value_full.py` only. This file can merge before ticket 19. The page ignores it until `field_value.py` exists.

- source order → `defaults.sources`
- this field's order → `fields.<name>.sources`
- may blank the field → `clear_sources`
- ignore older than → `max_age_days`

## Checklist

- [x] `field_value_full.py` is the only production file this ticket adds. `tests/unit/test_rules_try_field_value_full.py` is new. 2026-11-26 00:50 ET
- [x] The directory-then-register case written in these words matches ticket 19. `tests/unit/test_rules_try_field_value_full.py`. 2026-11-26 00:50 ET
- [x] A bare `sources`, `clear_sources` or `max_age_days` is refused with the word to type and the accepted words, and no word attaches a record or joins two masters. `tests/unit/test_rules_try_field_value_full.py`. 2026-11-26 00:50 ET
- [x] The page does not show this file before ticket 19's run file exists. `tests/unit/test_rules_try_field_value_full.py`. 2026-11-26 00:50 ET
- [x] Learning → skill: none. The words are a table the file reads. 2026-11-26 00:50 ET

## Answer

A short policy is a policy with a `kinds` block that may use four words where a stored key goes. In an entity type's block: "source order" is `defaults.sources`, "may blank the field" is `defaults.clear_sources`, "ignore older than" is `defaults.max_age_days`. Inside `fields.<name>`: "this field's order" is `sources`, "may blank the field" is `clear_sources`, "ignore older than" is `max_age_days`. Show the full rule returns `{"lines": [...], "document": {...}}`: the words used with the stored path each became, and the same policy with every word replaced. The directory-then-register case in these words, tried on `field_value`, gives the same fields as the stored keys: `address` from the directory and `name` from the register. A bare `sources`, `clear_sources` or `max_age_days` is refused with the word to type and every accepted word, because the stored key does not say whether it is for every field or one field. "source order" typed under a field, and "this field's order" typed for the entity type, are refused naming the right word. A word typed twice for one place, a list that is not source names, and a day count that is not a number are refused. The produced policy is checked by calling `select_fields` with no claims for each entity type, so a policy the engine refuses is refused here; an unknown key, such as a word that would attach a record or decide two masters are one subject, is refused by that check. Keys that are not words (`version`, `allow_unknown_effective`) keep their names.

## Comments

