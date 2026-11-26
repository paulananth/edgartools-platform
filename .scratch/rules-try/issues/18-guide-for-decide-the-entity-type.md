# Guide for Decide the entity type

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `docs/rules-try/entity_type.md` only. Words and the empty-ticker case. Do not edit another guide. No test.

## Checklist

- [x] `docs/rules-try/entity_type.md` is the only production file this ticket adds. No test. 2026-11-25 22:43 ET
- [x] The guide has the empty-ticker case. Its Try output was run on the `entity_type` family. 2026-11-25 22:43 ET
- [x] Learning → skill: none. The guide records output; it teaches no new rule. 2026-11-25 22:43 ET

## Answer

`docs/rules-try/entity_type.md` lists each word beside its stored key (`field_in_set@1`, `fields_all_empty@1`, `token_match@2`, `token_match@1`, `deferred`, `probable_kind`, `otherwise`), shows an invented short rule with the empty-ticker case, what Show the full rule prints for it, and what Try returns: `{"held back": "deferred"}` for the empty ticker, `{"entity type": "company"}` for a ticker with the `OPERATING` category, and the engine's refusal for a rule with no `otherwise` step. The output comes from running `classification.classify` through the `entity_type` family.

## Comments

