# Configured reading

Use this reference when writing a captured JSON contract. It describes the
implemented engine grammar; a source version is approved through the normal
Rules workflow after its test run.

## Streamed JSON record projection

For a captured single-wrapper array, `source.read` can authenticate the entire
input into a private bounded snapshot, then project each object through the
ordinary configured engine. Declare `read.stream` and use one execution worker:

```yaml
execution: {profile: source.read, workers: 1, max_artifacts: 1}
read:
  format: json
  limits: {max_bytes: 4096, max_records: 100}
  context:
    source_index: {type: integer}
  stream:
    wrapper: records
    container: none
    max_input_bytes: 65536
    max_bytes: 65536
    max_record: 4096
    max_records: 100
    max_depth: 64
    min_integer: -9223372036854775808
    record_encoding: python
    ordinal_context: source_index
    partition_bytes: 4096
    partition_records: 2
    max_partitions: 10
    max_spool_bytes: 65536
    max_output_rows: 100
  tables:
    rows:
      each: .
      columns:
        value: {value: {path: n}}
        source_index: {context: {name: source_index}}
```

Every stream field is required. `container` is `none` or `zip`; ZIP requires
one unencrypted file, verifies its CRC through EOF and enforces the expanded
byte limit. `max_input_bytes` bounds the authenticated snapshot (at most 1 GiB);
`max_bytes` bounds expanded bytes (at most 16 GiB). Private spool storage is
capped at 1 GiB and each partition at 8 MiB. `max_record` applies the explicitly selected
native or Python compact JSON encoding. Recursive object key order is retained
before projection. `read.limits` bounds each projected record, and assertions
run on each record. Ordinary `ordinal` expressions refer to rows within that
record; `ordinal_context` supplies the one-based source record index and cannot
be overridden by caller context. Use null when no source index is needed.
Context is validated even for empty arrays. An optional
`expected_records_context` names a declared integer context field holding the
publication's exact record count. Bind that context receipt to the captured
input. The worker checks its range before opening the source and compares it
with the full EOF count before publishing any partitions. Selected output rows
may be fewer than source records; the publication count always counts every
framed source record.

Record projection runs in Rust through the ordinary table interpreter;
Python receives projected readings, retains private partitions and orchestrates
verification. Approved custom expressions keep their registered step boundary.
This avoids converting and serializing every raw record through Python.

Projected tables and deferred records accumulate in private partitions.
Partition count, bytes, record count, aggregate spool bytes and output rows
are independently bounded. Every input must authenticate and reach valid EOF
before any partition is written. The version-2 reading index names immutable
content-addressed partitions, their byte sizes, source ordinal ranges and
declared table names (at most 64 distinct names).
The verifier rebuilds them from the original receipts and compares their
exact bytes without writes. A later output-write failure may leave immutable
partitions for retry; the index is written last.

`source.combine` and `mdm.prepare` accept both inline and partitioned readings.
They authenticate every partition and enforce aggregate consumer byte and row
budgets before writing output. Partitions retain the original artifact/context
identity and row order; they do not create additional MDM batches. Consumers
materialize the selected tables within their existing 32 MiB input budget,
so a full archive needs configured selection before this boundary. Finish
installed source/population proof before activating a streamed source.
Direct `SourceEngine.read` rejects stream contracts so they cannot silently
take the eager path. Active GLEIF JSON/XML retirement remains unfinished.

## Document assertions

Use `read.assertions` when the captured document must pass a shape or
expression check before any table is read:

```yaml
read:
  format: json
  assertions:
  - test: {test: {path: '.', kind: object}}
    reason: The captured document must be an object
  tables:
    records:
      each: records
      columns:
        record: {value: {path: '.'}}
```

An assertion names `test` (one ordinary expression) and `reason` (nonempty
text, at most 4,096 UTF-8 bytes). At most 32 assertions run in declared order,
after parsing and before required paths or table iteration. `true` passes;
`false` or null rejects the whole artifact with `assertion_failed` and the
declared reason. Any other result rejects with `assertion_condition`.
Use `test`, boolean context or boolean reference cells for an assertion result.
The existing `const` primitive renders boolean literals as text; such a value
refuses with `assertion_condition`.
Expressions, context names, references and custom steps are validated when
the contract loads. The expression inventory also enables exact numeric and
Python JSON formatting policies inside assertions. Assertions run even when
every table is empty and cannot defer records. The source worker writes no
reading output on rejection; the existing parser and byte limits still apply.

The Company main contract requires an object document and an object
`addresses` member when present. A business member contributes a row only
when it is an object. Its place lookup explicitly converts the selected SEC
code with Python text semantics, preserving the historical mapping of
nontext codes to unknown places. These are configuration choices, not
defaults for other contracts.

## Complete JSON records

Use `value` to retain nested JSON evidence and original scalar types:

```yaml
read:
  format: json
  limits: {max_bytes: 33554432, max_records: 1}
  tables:
    submissions:
      each: .
      columns:
        record: {value: {path: .}}
```

`value` accepts JSON or JSON Lines only. It preserves objects, arrays, null,
boolean, text, exact signed/unsigned 64-bit integers and finite floats.
An absent path returns null; an empty array remains an empty array, and an
empty object remains an object. Dot paths use the existing path grammar;
`from: document` selects the original document inside a table iteration.
Crossing an unselected repeating group still fails with `repeated_path`.
Numbers outside the exact integer range fail with `value_number_range`,
rather than silently rounding into a different record. Existing byte,
nesting, UTF-8 and finite-number safety checks remain. This is a declared
numeric boundary, not universal equivalence with Python's arbitrary integers.

For `mdm.prepare`, declare `record_column: record` in the unit's keys when the
selected table holds complete records in a column. Every selected value must
be an object. Preparation writes those exact objects as JSON Lines; its
verifier rebuilds the same selection. Without `record_column`, the entire
table row remains the record. A missing/null/list/scalar selection fails
before output files are written. Reading outputs are bounded to the source
verifier's 128 MiB budget; MDM preparation reads at most 32 MiB and refuses
records files above 16 MiB or a manifest above 32 MiB before writing. Partition
large inputs explicitly; source reading has no MDM-specific budget.
No field renaming or classification happens
in this worker; MDM uses its registered Dataset Contract and pinned policy.

The Person source read block preserves the complete submissions document,
including unknown fields, structural evidence and nested filing history.
It does not activate a Rules version. Company raw-column qualification does
not yet replace its catalog/census joins, address derivation or full mastering.

## Constructed records

`object` assembles a nested record from explicit field expressions:

```yaml
record:
  object:
    fields:
      cik: {integer: {path: cik}}
      evidence: {value: {path: evidence}}
      origin:
        object:
          fields:
            run: {context: {name: run}}
            row: {ordinal: {}}
```

Put this expression under a table's `columns`. `object` names `fields` only;
fields is a mapping of at most 128 entries with nonempty text names of at
most 128 UTF-8 bytes. An empty mapping produces an empty object. Each field
is one supported expression; it evaluates in the same document, item,
context and ordinal as the containing column. Null remains an explicit
field value. Child refusals propagate to the existing artifact/record
handling; there is no partial constructed record or implicit fallback.
Nested context and reference calls are validated before reading; nested
integer, value and Python text policies enable the same exact numeric and
format handling as top-level calls. Literal const/default/reference data
never enables a feature. Existing scalar `const` behavior is unchanged.

Use `record_column: record` in `mdm.prepare` to send the constructed object
unchanged. This does not supply Company catalog/census joins or qualify its
full preparation; compare those operations and assertion identities before
retiring the retained reader. The installed object-records trial assembles
the two raw Person fixture records from explicit fields and verifies them
through preparation and the actual Person MDM contract.

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

## Frozen reference tables

Reference data needed during reading belongs in `read.references`, embedded
in the frozen contract so the source worker and verifier read identical data.
It is separate from the caller-supplied membership sets used by `in_lookup`.
No mutable path or callback is consulted.

```yaml
read:
  format: json
  references:
    places:
      DE: {iso: US-DE}
      XX: {iso: null}
  tables:
    company:
      each: .
      columns:
        jurisdiction:
          lookup:
            reference: places
            column: iso
            key: {text: {path: stateOfIncorporation, case: upper}}
            on_missing: "null"
```

`lookup` uses an exact text key produced by its nested expression. Null or
an absent key returns null by default; `on_missing: error` rejects the artifact
with `lookup_missing`. An explicitly null cell is a successful lookup even in
error mode. Non-text, non-null keys fail with `lookup_key`; convert them
explicitly when the source requires it. References and every named column
are validated at contract load, including unused expressions and empty inputs.
Cells retain null, boolean, signed 64-bit integer, finite float or text types.
There is no implicit default, string conversion or key case conversion.

`text.case` is `preserve` by default, or explicit `upper`/`lower` using native
Unicode case conversion. Conversion follows trimming and precedes `null_if`;
case changes must be declared for both the value and null tokens when needed.
Unicode compatibility is qualified for the source's inputs; this is not a
claim of Python compatibility across every Unicode version.

Bounds: at most 16 reference tables, 10,000 keyed rows per table, 32 columns
per row and 100,000 cells in total. Names/keys are nonempty text of at most
128 UTF-8 bytes; text cells are at most 4,096 bytes. Structured, tagged,
nonfinite and out-of-range integer cells are refused. Duplicate YAML keys
are refused by the contract parser. These are small dimension tables, not
large artifact joins or permission to raise source-worker budgets.

All 309 SEC place codes and explicit lowercase/whitespace variants are
compared to the retained jurisdiction converter. Complete Company address,
reference provenance and assertion equivalence remain source retirement gates.

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
assertion/failure equivalence. The unused historical landing API and loader modules are retired from the runtime; frozen oracles under `tests/support` remain for qualification. Active MDM preparation, provenance and full population/recovery still need replacement and proof.

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

## Fallback and conditional values

`coalesce` selects a typed value without a custom step:

```yaml
coalesce:
  values: [{value: {path: stateOrCountry}}, {value: {path: countryCode}}]
  skip: falsey
```

Both keys are required; `values` has 1–16 expressions. `skip: "null"`
skips null only; `skip: falsey` also skips false, numerical zero and empty
text, lists and objects. Whitespace text remains a value. Return the first
retained value, or null when all are skipped. Evaluation stops at that value.

`choose` names `condition`, `then` and `else`, each an expression. The condition
must return boolean or null: true selects `then`; false/null selects `else`;
other types refuse with `choose_condition`. Only the selected branch executes.
Use boolean values from `value`, context or a reference lookup. Existing
`const` boolean conversion remains unchanged and produces text.

All calls in every branch still validate at contract load, including nested
context/reference names, custom implementations and feature restrictions.
Lazy evaluation skips runtime field access; it does not approve invalid calls.

A `lookup` may declare `trim: true` (Python Unicode whitespace, including
U+001C–U+001F) and `case: upper`/`lower`/`preserve` on its
text key. These run **after** the key expression, including fallback. Defaults
remain exact matching (`trim: false`, `case: preserve`). Null keys follow the
existing missing policy, and other types refuse. This order matters when a
whitespace-only preferred value should resolve as unknown rather than select
a fallback.

The configured Company address comparison freezes SEC place rows into the
contract. It preserves raw street/region text, derives country from the
approved ISO reference, and keeps region only for subdivisions. This proves
raw address derivation separately from census, complete provenance, pagination
and full Company mastering; those remain required before parser retirement.

### Company main-document reading

`rules/sources/sec.submissions.company/source.yaml` now declares a generic
`source.read` block for its main submissions document. It emits `company`,
`filings` and `addresses` tables. Company fields retain their captured types;
filings use the qualified parallel-array, date, numeric and first-N rules;
business addresses use the frozen SEC place reference rows.

Use a version-2 source input manifest. Each artifact has `input` and `context`
receipts. The context document binds its values to that exact input receipt:
`cik` (integer), `sync_run_id`, `raw_object_id`, `load_mode`, `last_synced_at`
(text), and `recent_limit` (integer or null). These are explicit caller facts;
the worker verifies their binding and the native engine verifies their types.
An input hash does not independently prove a supplied capture identifier or
observation time: the acquisition/census provenance gates must prove those.

Join the resulting tables with a declared `source.combine` contract, then use
`mdm.prepare` to write immutable input batches. The current Company target
still uses retained preparation until census, ticker catalog, pagination,
classification/provenance and installed full-population replay are qualified.
The read block alone is neither a source activation nor complete mastering.

For a captured continuation page, use the packaged
`rules/sources/sec.submissions.company/pagination.yaml` contract. It reads
column arrays at the raw page root and emits all eighteen filing fields;
it has no recent-limit context. Bind `cik`, `sync_run_id`, `raw_object_id`
and `load_mode` to the page receipt. `raw_object_id` retains the caller's
publication context; the independent `input` receipt identifies the exact
page bytes. Do not invent a `filings` wrapper before configured reading.

Capture all filenames declared by the pinned main document. Read pages in
bounded pairs, combine up to seven page readings with the main reading,
then combine the resulting per-Company form lists with `collect_flat` and
`sort_values: true`. This preserves complete page scope through immutable
reading receipts while keeping each work unit bounded. See
[Combination](COMBINING.md) for list and element-budget semantics.
Same-date S3 captures plus version/hash evidence prove captured bytes and
declared page coverage; they do not prove Bookkeeping producer success.

## Header-driven JSON matrices

Use `each: {matrix: {headers: fields, rows: data}}` for a JSON document with
an array of header names and an array of row arrays. Paths may be nested.
Both arguments are required; unknown arguments and non-JSON formats refuse.
By default, headers must be 1..128 distinct names of at most 128 ASCII letters, digits or
underscores. Every row must be an array of exactly the header length. Missing
arrays, duplicate headers and malformed rows refuse the artifact. Ordinary
column expressions read each cell by its header name, preserving typed values;
`ordinal` retains the row's original position. Document/context expressions
remain available. Full row-count and shape checks run even when `take` selects
only a prefix; materialization is bounded by the artifact and record limits.

Optional matrix policies are explicit: `lengths: zip` maps only matching
header/cell pairs, `duplicates: last` keeps the last assigned value with the
first assigned key position, `headers_coerce: python` converts supported JSON
headers with Python text semantics (including null as `None`), and
`on_invalid_row: skip` ignores non-array rows. Defaults remain equal lengths,
unique simple text headers and rejected malformed rows. Python header coercion
allows zero headers and arbitrary header text, bounded to 128 headers and
128 UTF-8 bytes per name. Full input count remains bounded before skipping.

## Object entries and conditional iteration

`each: {objects: {path: '.', on_invalid: empty}}` iterates a JSON object's
values in captured key order. Default invalid-object behavior is `reject`;
`empty` explicitly returns no rows for missing, scalar or array input. Input
entry count includes values later excluded by selection.

Choose a layout through `each.choose` with `condition`, `then` and `else`.
The condition is an ordinary expression evaluated against the document;
branches are iteration calls or paths. Boolean true selects `then`, false or
null selects `else`, and other types refuse. Both branches validate before
reading; only the selected branch reads the document. Nesting is capped at
eight calls. Context/reference/custom names in all conditions must resolve.

`test: {path: ticker, kind: truthy}` returns a native boolean without text
coercion or materializing a subtree. Kinds are `truthy`, `missing`, `null`,
`not_null`, `array` and `object`; optional `from: document` tests the original
document. Null includes absent values; `missing` distinguishes absence from
explicit null. Quote `'null'` in YAML so the kind is text. Truth follows the captured JSON type: zero, false, null and
empty text/containers are false; whitespace text is true.

A table may declare `select: <expression>` to exclude rows before column
conversion and record checks. True retains a row; false/null excludes it;
other values refuse. Selection runs after `take`, which still bounds the
input prefix. Default `ordinal: source` reports iterator position;
`ordinal: selected` counts retained selection rows, including rows that a
later record check defers. Deferred/error locations keep source positions.
Selection expressions see source positions. For permissive matrix iteration,
non-array rows skipped by that iterator do not have a row position.

The Company draft `catalog.yaml` declares both captured catalog layouts and
legacy skip/fallback/text rules, using these generic calls. Receipt context
supplies catalog run, source name and sync time. Group `ticker` by CIK with
`order_by: [source_rank]`, `distinct: true`, `skip_empty_text: true` and a
catalog-run row check. Keep the separate Company capture-run check on base
rows. Both finite malformed-case and physical capture qualification must
pass before adoption. Runtime custom ticker parsing is retired; its historical
oracle is test-only. Byte/header/row/numeric/Unicode safety boundaries remain
explicit, so finite parity does not imply universal arbitrary-input parity.
No source activation, producer success or complete Company mastering follows
from successful catalog reading.

## Large JSON array framing foundation

For a captured document shaped as one object containing one named array,
`source_engine.stream_json_array` reads object records incrementally through
the native binding. Its callback receives the typed record and zero-based
ordinal. Only successful return supplies an EOF receipt; callbacks prepare
candidates and must not commit, publish or authenticate partial records.
Duplicate keys, extra wrapper keys, non-object records, nonfinite numbers,
depth overflow, integer overflow and trailing data refuse the input.

`max_record` bounds the compact encoded record. Raw records and transport
reads permit 65,536 additional bytes of buffering headroom, including
whitespace. `max_bytes` bounds the whole expanded stream. Signed 64-bit
integers are supported; an explicit `min_integer: -9223372036854775807`
matches the historical GLEIF decoder's narrower negative boundary.
Choose `record_encoding='python'` to apply the historical compact Python
JSON byte limit. Default `native` measures native JSON spelling. These can
accept different records at a tight float byte boundary even when their
decoded values are identical; the policy must be pinned before cutover.

`Artifacts.verified_stream(ref, max_bytes=...)` authenticates a complete
private disk snapshot before allowing any parser reads. It bounds memory
through 64 KiB reads, bounds snapshot disk usage explicitly, and closes the
snapshot on success or failure. Use a compressed-byte cap when snapshotting
an archive, then a separate expanded-byte cap while parsing its member.

The configured worker mode is described under **Streamed JSON record
projection** above. Its installed projection and partition verifier are
qualified, including combining and preparation. Before GLEIF cutover,
verify complete archive/member authentication and metadata and prove
publication/replay through EOF. JSON framing tests do not qualify XML or
retire active GLEIF parsing.

## GLEIF Level 1 JSON qualification template

The bundled `gleif/level1-json.yaml` template declares ZIP framing, explicit
historical numeric/record limits, pinned publication count and a receipt-bound
source ordinal. Populate `read.references.approved_scope` with the reviewed
LEIs as `{LEI: {selected: true}}` before submission; the supplied empty map is
a template, not an approved cohort. Source scope is a frozen reference table
in the same contract receipt as selection. `record` retains typed source
fields for MDM interpretation; `source_index` is one-based. Compare provenance
with the historical zero-based ordinal explicitly before runtime adoption.

The complete archive framing parity result and the captured-sample performance
measurement do not by themselves prove installed configured projection,
producer publication, XML parity or complete Company mastering. Complete those
checks before replacing the active GLEIF runtime or activating source Rules.
