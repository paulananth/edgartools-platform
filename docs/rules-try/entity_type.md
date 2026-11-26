# Decide the entity type

Type a short classification rule, press Show the full rule to see the stored keys beside your words, and press Try to decide the entity type of an invented record with it. The invented examples below were run on the try page's "Decide the entity type" family. Try calls `classification.classify`, which returns the verdict of the first step whose tests all hold.

## Words and stored keys

| Word you type | Stored key | Where it goes |
| --- | --- | --- |
| field is one of | `field_in_set@1` | a test's `primitive` |
| these fields are empty | `fields_all_empty@1` | a test's `primitive` |
| name tokens match | `token_match@2` | a test's `primitive` |
| name tokens match with any ampersand | `token_match@1` | a test's `primitive` |
| held back | `deferred` (no master is created) | a step's `verdict`, and `emits` |
| probable entity type | `probable_kind` (a queue label, not a master) | a step that holds a record back |
| otherwise | `otherwise` | the step that catches every record no earlier step took |

`name tokens match` counts an ampersand as a word only when the list holds `AND`. `name tokens match with any ampersand` counts it for every list. A stored key from the table, typed bare, is refused with the word to type and every word the family accepts.

`evidence_present@1`, `values_overlap@1` and `name_shape@1` keep their stored keys, since the key says what the test does. The `args` of each test, the kind names (`company`, `person`, and the rest), `entity_undetermined` and the step names keep what you type. A `probable entity type` goes only on a step that holds a record back; the engine refuses one on a step that decides an entity type.

## An invented empty-ticker case

The record has an empty `ticker`. The doc is empty, since the rule names no list.

```json
{"ticker": "", "category": "OPERATING"}
```

Your short rule, with three words. The first step holds back a record whose `ticker` is empty. The second decides `company` when `category` is `OPERATING`. The last catches the rest:

```json
{"rule_id": "example-entity-type", "version": "example-entity-type-v1", "family": "classification",
 "emits": ["company", "held back"],
 "steps": [
   {"step": "1", "verdict": "held back",
    "when": [{"primitive": "these fields are empty", "args": {"fields": ["ticker"]}}]},
   {"step": "2", "verdict": "company",
    "when": [{"primitive": "field is one of", "args": {"field": "category", "values": ["OPERATING"]}}]},
   {"step": "3", "verdict": "held back", "otherwise": true}]}
```

Show the full rule prints these lines, then the same rule with the stored keys:

```json
[{"word": "held back", "stored": "deferred"}, {"word": "these fields are empty", "stored": "fields_all_empty@1"},
 {"word": "field is one of", "stored": "field_in_set@1"}, {"word": "otherwise", "stored": "otherwise"}]
```

In the full rule, `emits` is `["company", "deferred"]`, step 1 has `"verdict": "deferred"` and `"primitive": "fields_all_empty@1"`, step 2 has `"primitive": "field_in_set@1"`, and step 3 has `"verdict": "deferred"`.

## What Try returns

Pasting the full rule and the record above returns the stored verdict beside "held back":

```json
{"held back": "deferred"}
```

A record with a ticker and the `OPERATING` category, `{"ticker": "EXMP", "category": "OPERATING"}`, skips step 1, takes step 2 and returns the entity type:

```json
{"entity type": "company"}
```

A record with a ticker and another category, `{"ticker": "EXMP", "category": "OTHER"}`, takes no step but the last and returns `{"held back": "deferred"}`. A step whose verdict is `entity_undetermined` returns `{"held back": "entity_undetermined"}`. Try shows the verdict; it does not show a `probable entity type`.

A rule with no `otherwise` step is refused by the engine:

```json
{"refused": "Classification rule example-entity-type has no catch-all step: exactly one otherwise step is required"}
```

A rule, record or doc that is not a JSON object, a test the engine does not know, and a list the rule names that the doc does not hold each return `{"refused": "..."}` and nothing else.
