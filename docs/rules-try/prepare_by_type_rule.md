# Prepare a record whose entity type comes from a rule

Type a short contract that names an entity type rule, paste the policy that holds the rule, press Show the full rule to see the stored keys beside your words, and press Try to prepare an invented row. The row receives the entity type the rule decides. The invented examples below were run on the try page's "Prepare a record whose entity type comes from a rule" family.

## Words and stored keys

| Word you type | Stored key | What it holds |
| --- | --- | --- |
| entity type rule | `classification` | the rule that decides the entity type: the entity type's block in the policy, the rule id and the rule version |
| entity type | `kind` | inside the entity type rule, the policy block that holds the rule |
| record key | `record_key` | the row's own key: a list of paths in the row |
| identifier | `identifiers` | the identifiers the row carries, as a name and the path that holds it |
| lookup only | `cross_references` | an id kept for lookup that does not match by itself |

The words go where a stored key goes in the contract's `adapter`. `version`, `rule_id`, `reading`, `schema_version` and the format keys keep their names. A stored key from the table, typed bare, is refused with the word to type and the words the page accepts. A contract that states an entity type (`kind` or `kind_field`) beside the entity type rule is refused: it states one or the other.

This is the only page that accepts "entity type rule". A contract with a fixed entity type and no `classification` is refused, and the refusal names the page "Prepare the MDM record".

## An invented row

The row:

```json
{"id": "R1", "ident": "ID-100", "name": "Example Works", "category": "operating"}
```

The source code is `example.records.v1`. The publication:

```json
{"publication_key": "p1", "revision": 1, "artifact_sha256": "0000000000000000000000000000000000000000000000000000000000000000", "member": "m"}
```

The policy holds the rule in the `company` block. Step 1 decides `company` for a row whose `category` is `operating`; step 2 is the catch-all that decides nothing. `automatic_rules` switches the `company` verdict on:

```json
{"automatic_rules": [{"kind": "company", "family": "classification", "rule_id": "example-rule", "rule_version": "1", "verdict": "company"}],
 "kinds": {"company": {"rules": [{"rule_id": "example-rule", "version": "1", "family": "classification",
   "emits": ["company", "deferred"],
   "steps": [{"step": "1", "verdict": "company",
              "when": [{"primitive": "field_in_set@1", "args": {"field": "category", "values": ["operating"]}}]},
             {"step": "2", "verdict": "deferred", "otherwise": true}]}]}}}
```

Your short contract, with four words:

```json
{"schema_version": "1", "adapter": {"version": "example-v1",
  "entity type rule": {"entity type": "company", "rule_id": "example-rule", "version": "1"},
  "record key": ["id"], "identifier": {"example_id": "ident"},
  "reading": {"read": {"format": "json", "limits": {"max_bytes": 4096, "max_records": 1},
    "tables": {"mapped": {"each": ".", "columns": {
      "fields": {"object": {"fields": {"name": {"value": {"path": "name", "path_mode": "literal", "null_if_blank": true}}}}},
      "matching": {"object": {"fields": {}}}}}}}}}}
```

Show the full rule prints these lines, then the same contract with the stored keys:

```json
[{"word": "entity type rule", "stored": "classification"}, {"word": "entity type", "stored": "kind"}, {"word": "record key", "stored": "record_key"}, {"word": "identifier", "stored": "identifiers"}]
```

The adapter in the full contract holds `"classification": {"kind": "company", "rule_id": "example-rule", "version": "1"}`, `"record_key": ["id"]` and `"identifiers": {"example_id": "ident"}`.

## What Try returns

Pasting the full contract with the row, the source code, the publication and the policy above returns the prepared record:

```json
{"source_code": "example.records.v1", "record_key": "R1", "publication_key": "p1", "revision": 1,
 "schema_version": "1", "effective_at": null, "kind": "company",
 "subject": "6e9085099d48039118b7a4dc2f718326dc5252789b624038acb4ca1e519f72b4",
 "fields": {"name": {"op": "value", "value": "Example Works"}},
 "identifiers": {"example_id": "ID-100"}, "profiles": [], "relationships": [],
 "provenance": {"artifact_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
                "member": "m", "record_key": "R1", "adapter_version": "example-v1",
                "classification": {"rule_id": "example-rule", "version": "1", "step": "1"}},
 "assertion_id": "b3748e9abeefd9096292b9a39fdfa3bb66c3aa8f96d12f12a7f19c72e9305256"}
```

The entity type is `company` because step 1 of the pasted rule decided it, and the record keeps the rule id, the version and the step that did.

A row whose `category` is `other` reaches the catch-all, which decides no entity type, and returns:

```json
{"refused": "The record is set aside: classification_deferred (rule example-rule, version 1, step 2, verdict deferred)"}
```

The same row as the first one, with an empty `automatic_rules`, is not switched on and returns:

```json
{"refused": "The record is set aside: classification_not_activated (rule example-rule, version 1, step 1, verdict company)"}
```

A rule the policy does not hold, or holds at another version, or holds for another source, is refused with the engine's reason. A paste the engine cannot read returns `{"refused": "..."}` and nothing else.
