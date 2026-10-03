# Configured reading

Use this reference when writing a captured JSON contract. It describes the
implemented engine grammar; a source version is approved through the normal
Rules workflow after its test run.

## Parallel arrays

A JSON document may hold columns as arrays, rather than a list of objects.
Declare the object path, anchor array and output field names:

```yaml
read:
  format: json
  limits: { max_bytes: 33554432, max_records: 100000 }
  tables:
    rows:
      each:
        parallel:
          path: records
          anchor: id
          fields: { id: id, name: name }
          lengths: equal
      columns:
        id: { text: { path: id } }
        name: { text: { path: name, trim: false, null_if: [""] } }
```

`path` locates one object; `"."` means the document. `anchor` and every
`fields` value are array paths relative to that object. Output field names
use letters, digits and underscores. Row order is anchor order, and
`ordinal` starts at 1. `from: document` reads a column's path against the
original document, so envelope facts need not be duplicated into every row.

- `lengths: equal` (the default) refuses arrays with different lengths,
  including an absent field when the anchor has rows.
- `lengths: anchor` emits exactly the anchor's number of rows, pads absent
  or shorter fields with null, and ignores longer fields' trailing values.
  Use it only when that behavior is part of the source contract.
- An absent object yields no rows. An absent/empty anchor yields no rows
  when the other arrays satisfy the declared length policy. A present scalar,
  null or array where an object is required is refused. A scalar or null
  where an array is required is refused, including one-element cases.
- The record limit is checked before expanding rows. Existing record
  checks can defer rows; their raw evidence is the aligned record with
  exactly the declared fields, not the complete original document.

The parser supports parallel arrays in one JSON document. JSON Lines, CSV
and XML retain their existing path iteration. The source worker's immutable
input reference keeps the original artifact and its hash available.

## Source text

`text` trims surrounding whitespace by default. `trim: false` preserves it.
`null_if` compares against the resulting text; token trimming also follows
`trim`. For a source whose empty string is absent but whitespace is evidence,
use `trim: false, null_if: [""]`. `ignore_case` retains its ASCII case
comparison and requires `null_if`.

## Qualification boundary

The generic primitive and the installed worker protocol are tested
independently. The partial filing projection case compares accession and
form fields only. Company/Person classification, address interpretation,
reference lookups, aggregation, full assertion IDs and source refusals need
complete equivalence proof before retiring a source reader. See the current
source-completion checklist; a passing primitive test is not that proof.
