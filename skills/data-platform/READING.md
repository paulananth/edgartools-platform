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
- `on_invalid_object: empty` explicitly returns no rows when the object path
  reaches a scalar, null or array. It does not excuse invalid arrays inside
  a valid object. The default is `reject`.
- `strings: characters` permits a string wherever an array is declared,
  indexing Unicode code points in order. Padding/length checks still follow
  `lengths`; null, numbers, booleans and objects remain invalid arrays.
  The default is `reject`. Character expansion is bounded by the anchor
  safety limit and the number of fields actually used.
- `on_empty_anchor: ignore_fields` with `lengths: anchor` produces no rows
  without inspecting fields when the anchor is empty. The default,
  `validate_fields`, preserves shape checks even for an empty anchor.
  `ignore_fields` is invalid with `lengths: equal`.
- `objects: indexed` explicitly permits object sequences: the number of
  keys supplies their length, but integer indexing cannot address JSON's
  string keys. An empty object pads as a zero-length field; a selected index
  below a nonempty object's length fails with `parallel_index`, including
  an object with a string key `"0"`. The default is `reject`.
- `validation: selected` with `lengths: anchor` expands and accesses only
  the first `take` rows. When no row is selected it skips field access,
  including invalid unused fields. The **full anchor** still supplies the
  record safety limit and the declared document record-count check. Null,
  boolean and numeric anchors remain invalid even with `take: 0`.
  The default, `all`, preserves validation of all declared fields and
  expansion of the full anchor before first-N selection. `selected` is
  invalid with `lengths: equal`.
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

For a JSON source that defines Python-style text conversion, declare
`coerce: python` in `text` (or the text input of `date`). Booleans become
`True`/`False`; finite floats use Python 3.12 notation; JSON integers retain
their exact value as integers; containers use Python repr with original
object insertion order, nested `None`, quote selection and Unicode 15.0
printability. Null still uses the expression's default. Apply trim and
null tokens after conversion. The default, `coerce: scalar`, retains the
existing scalar-only behavior and lowercase boolean text. Python coercion
requires JSON or JSON Lines; it is implemented in Rust without a Python
callback or source loader. It does not expand the existing finite-number,
UTF-8, nesting or byte safety limits.

Declare these policies only after comparing both outputs and failures with
the source contract. They do not authorize a source version or retire its
reader. The original seven cases and the 450-case anchor/field/first-N
matrix match retained acceptance and output rows with these explicit
policies. Matching refusal decisions does not assert identical exception
classes. Complete malformed-source equivalence remains a separate gate.

## Qualification boundary

The generic primitive and the installed worker protocol are tested
independently. The partial filing projection case compares accession and
form fields only. Company/Person classification, address interpretation,
reference lookups, aggregation, full assertion IDs and source refusals need
complete equivalence proof before retiring a source reader. See the current
source-completion checklist; a passing primitive test is not that proof.

## Calendar dates

The existing `date` call defaults to a timezone-bearing instant normalized to
UTC. To read a calendar date without interpreting a time or zone, declare:

```yaml
filing_date:
  date:
    path: filingDate
    kind: calendar
    prefix_length: 10
    basic_suffix: ignore
    on_invalid: null
```

Calendar mode accepts ISO calendar dates (`YYYY-MM-DD` or `YYYYMMDD`) and ISO
week dates (`YYYY-Www-D`, `YYYYWwwD`, or the corresponding week without a day,
which means Monday). Years are 1–9999. It returns `YYYY-MM-DD` text. Missing,
null or empty values return the declared `default`, otherwise null.

`prefix_length` is optional and must be an integer 1–32; it counts Unicode
characters before parsing. No whitespace is trimmed. Invalid dates fail the
artifact with `invalid_value` by default. Explicit `on_invalid: null` (or the
quoted string `"null"`) returns null instead; `on_invalid: error` keeps the
failure. These two options require `kind: calendar`; instant behavior stays
unchanged. Root document iteration is written `each: .`.

SEC filing text/calendar qualification does not cover numeric flags,
classification, Company or Person mastering, reference joins or complete
assertion/failure equivalence. The old loaders remain until those are proved.

`basic_suffix` defaults to `reject`. Calendar-only `basic_suffix: ignore`
reproduces the Python 3.12 loader exception: after prefix truncation, a
ten-character ASCII value whose first eight characters form a valid basic calendar
or week date ignores its final two characters (for example `20240229T0`).
Declare this compatibility behavior only when replacing a reader that used it.

## Exact integers and integer-derived booleans

```yaml
size:
  integer: {path: size, on_invalid: null}
is_xbrl:
  integer: {path: isXBRL, as: boolean, default: false, on_invalid: default}
```

`integer` defaults to signed 64-bit integer output. Integer text supports a
leading ASCII sign, surrounding Unicode whitespace, Unicode 15.0 decimal
digits and underscores between digits. Decimal/scientific text is invalid.
Native JSON booleans become 0/1; native finite JSON floating values truncate
toward zero. Original JSON numeric spellings are retained for this expression,
so an integer never passes through floating point first. Existing text/number
calls keep their original representation and behavior.

`as: boolean` returns a native boolean after integer conversion: 0.9 is false,
1.9 is true. Arbitrary-size integer text (up to 4,300 digits) and finite JSON
floats can be tested for zero without a signed 64-bit output boundary.

Missing/null values use `default` (otherwise null). Present invalid values
follow `on_invalid`: `error` (default), `null`, or `default`. Integer overflow
follows the independently declared `on_overflow` with the same three choices;
its default error code is `integer_overflow`. Conversion never saturates.
Boolean output has no integer output to overflow, so it refuses `on_overflow`.
Defaults must match the declared output type. Structured values are invalid;
repeating intermediate paths still fail closed. JSON syntax, nesting and
finite-number checks remain the existing parser's checks, and the artifact
retains its byte/record limits.

This syntax qualifies filing content fields only. Artifact metadata, complete
classification and source/mastering equivalence remain required before reader
or loader retirement.

## Artifact context and first-N rows

When output fields come from caller facts, declare their types separately from
captured document paths:

```yaml
read:
  format: json
  context:
    caller_id: {type: integer}
    capture_label: {type: text, max_bytes: 128}
    first_n: {type: integer, nullable: true}
  tables:
    rows:
      each: records
      take: {context: {name: first_n}}
      columns:
        id: {context: {name: caller_id}}
        capture: {context: {name: capture_label}}
        name: {text: {path: name}}
```

Provide every declared context key exactly once. Types are `text`, signed
64-bit `integer`, and native `boolean`; there is no coercion. Null requires
`nullable: true`. Text defaults to at most 4,096 UTF-8 bytes; `max_bytes` may
lower that limit. Declare at most 32 keys, each at most 64 ASCII letters,
digits or underscores. Unknown fields, missing fields, wrong types and bounds
fail with `invalid_context`. A context expression names a declared field;
that field also works as a custom step's input. Document paths keep reading
the original captured bytes.

`take` accepts a context field declared as integer (optionally nullable), or
`{const: {value: N}}`. Null selects all rows; positive N selects the first N;
zero and negative N select none. Byte, shape, full source record-count and
safety-limit checks still run. Selected rows retain their original ordinals,
and their record checks run normally. `take` is selection, not a larger
safety allowance.

For `source.read`, use input version 2 when context is required:

```json
{"version":2,"contract":{"uri":"s3://bucket/contract.yaml","sha256":"<hash>"},
 "artifacts":[{"input":{"uri":"s3://bucket/captured.json","sha256":"<hash>"},
               "context":{"uri":"s3://bucket/context.json","sha256":"<hash>"}}]}
```

The context receipt names immutable JSON, at most 32 KiB:

```json
{"version":1,"input":{"uri":"s3://bucket/captured.json","sha256":"<hash>"},
 "values":{"caller_id":320193,"capture_label":"approved capture","first_n":null}}
```

Its `input` must equal the artifact's exact URI and hash. Build the context
from approved caller facts and pin it in the execution worklist. A hash proves
bytes and binding; Rules approval supplies authority for those facts. The
worker and independent verifier reread both receipts. Reading output retains
version 1 and adds the context receipt to each artifact. MDM preparation uses
both input and context hashes for record, batch and publication identity, so
different context for the same captured bytes remains separate. Version-1
source inputs remain valid for contracts without required context.

The 18-column filing fixture and pinned comparison cover caller provenance
and selected recent filing content. They do not complete Company/Person
classification, paginated history, reference joins, GLEIF or complete malformed
source equivalence. Keep the full retirement gates open until those pass.
