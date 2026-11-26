# Prepare the MDM record

Type a short contract, press Show the full rule to see the stored keys beside your words, and press Try to prepare an invented row with it. This page fixes the entity type: every row of the source is that one entity type. The invented examples below were run on the try page's "Prepare the MDM record" family.

## Words and stored keys

| Word you type | Stored key | What it holds |
| --- | --- | --- |
| entity type | `kind` | the one entity type every row of the source is |
| record key | `record_key` | the row's own key: a list of paths in the row |
| identifier | `identifiers` | the identifiers the row carries, as a name and the path that holds it |
| lookup only | `cross_references` | an id kept for lookup that does not match by itself |

The words go where a stored key goes in the contract's `adapter`. `version`, `reading`, `schema_version` and the format keys keep their names. A stored key from the table, typed bare, is refused with the word to type and the words the page accepts.

"entity type rule" is not a word here. A contract that contains `classification`, which names an entity type rule, is refused before the row is prepared, and the refusal names the page "Prepare a record whose entity type comes from a rule".

## An invented row

The row:

```json
{"id": "R1", "ident": "ID-100", "tax": "TX-7", "name": "Example Works"}
```

The source code is `example.records.v1`. The publication:

```json
{"publication_key": "p1", "revision": 1, "artifact_sha256": "0000000000000000000000000000000000000000000000000000000000000000", "member": "m"}
```

Your short contract, with four words:

```json
{"schema_version": "1", "adapter": {"version": "example-v1",
  "entity type": "company", "record key": ["id"],
  "identifier": {"example_id": "ident"}, "lookup only": {"tax_id": "tax"},
  "reading": {"read": {"format": "json", "limits": {"max_bytes": 4096, "max_records": 1},
    "tables": {"mapped": {"each": ".", "columns": {
      "fields": {"object": {"fields": {"name": {"value": {"path": "name", "path_mode": "literal", "null_if_blank": true}}}}},
      "matching": {"object": {"fields": {}}}}}}}}}}
```

Show the full rule prints these lines, then the same contract with the stored keys (`kind`, `record_key`, `identifiers`, `cross_references`):

```json
[{"word": "entity type", "stored": "kind"}, {"word": "record key", "stored": "record_key"}, {"word": "identifier", "stored": "identifiers"}, {"word": "lookup only", "stored": "cross_references"}]
```

## What Try returns

Pasting the full contract with the row, the source code and the publication above returns the prepared record:

```json
{"source_code": "example.records.v1", "record_key": "R1", "publication_key": "p1", "revision": 1,
 "schema_version": "1", "effective_at": null, "kind": "company",
 "subject": "6e9085099d48039118b7a4dc2f718326dc5252789b624038acb4ca1e519f72b4",
 "fields": {"name": {"op": "value", "value": "Example Works"}},
 "identifiers": {"example_id": "ID-100"}, "profiles": [], "relationships": [],
 "provenance": {"artifact_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
                "member": "m", "record_key": "R1", "adapter_version": "example-v1"},
 "cross_references": {"tax_id": "TX-7"},
 "assertion_id": "7b22169fe4c9eb5e41754a7494e5a3d4865730c352598904550ba43092225100"}
```

The entity type is `company`, the record key is `R1`, and the identifier is `ID-100`. The `tax_id` stays in `cross_references`: it is kept for lookup and does not match the row to another by itself.

## A row with no key

The same contract with the `id` taken out of the row:

```json
{"ident": "ID-100", "tax": "TX-7", "name": "Example Works"}
```

returns the engine's refusal and nothing else:

```json
{"refused": "The record is set aside: missing_record_identity"}
```

A paste the engine cannot read also returns `{"refused": "..."}`: a contract or publication that is not JSON, a contract with no `adapter`, or one that lacks a part the preparation reads, such as `record_key`.
