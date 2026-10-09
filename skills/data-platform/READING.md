# Configured reading

Use this reference when writing a captured JSON contract. It describes the
implemented engine grammar; a source version is approved through the normal
Rules workflow after its test run.

## Streamed JSON record projection

### Full-source archive attestation

For native publication verification, `workers.source_attestation.attest_zip`
uses the same configured stream policy and native readers without retaining
projected partitions. Declare the raw record and source ordinal columns:

```yaml
attestation:
  table: level1
  record_column: record
  ordinal_column: source_index
```

This boundary authenticates a private compressed snapshot, requires one
unencrypted ZIP member and the pinned exact record count, and checks CRC,
expanded length and original-source EOF. It hashes every configured raw record,
including records outside the mastering scope; table selection is removed only
from a private contract copy. Callbacks produce provisional evidence. A returned
report is required before committing any callback result.

Publisher authority and XML header references must be authenticated separately.
GLEIF's publication binding supplies them from its pinned manifest. The generic
boundary interprets no GLEIF fields and grants no identity or binding authority.
Use `source.read` for Bookkeeping-managed partition publication and verification;
the callable attestation boundary is not a separate execution profile.

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
take the eager path. A source's active parsing is retired only under its own ticket.

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
`equal` returns a boolean from two expressions, without coercing their types:

```yaml
- test:
    equal:
      left: {integer: {path: RecordCount.$}}
      right: {context: {name: publication_count}}
  reason: Header count must equal the input-bound publication count
```

Both `left` and `right` are required and evaluate before comparison. Integer,
float, text and boolean values remain distinct; null equals null. Lists compare
in order and maps compare their typed fields without depending on key order.
Use `value` or typed context for boolean values: the existing `const` boolean
conversion produces text. Explicitly parse source counts with `integer` before
comparing them to integer context. Nested calls still validate before reading.
The existing `const` primitive renders boolean literals as text; such a value
refuses with `assertion_condition`.
Expressions, context names, references and custom steps are validated when
the contract loads. The expression inventory also enables exact numeric and
Python JSON formatting policies inside assertions. Assertions run even when
every table is empty and cannot defer records. The source worker writes no
reading output on rejection; the existing parser and byte limits still apply.

A contract may require an object document, require a member to be an object
when present, take a row only from an object member, or convert a looked-up
code with Python text semantics to keep a historical mapping of nontext codes.
These are configuration choices of one contract, not defaults for others.

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

### Typed dictionary values

For JSON mappings, `value` also accepts `type` (`text`, `integer`, `number`,
`boolean`, `object`, `array`), `nullable` (default true), `trim`, and
`null_if_blank` (both default false). Wrong types or forbidden nulls refuse
with `value_type`; booleans never count as numbers. Blank/trim policies use
Python whitespace, including U+001C–U+001F. Nonblank strings retain their
original spelling unless trimming is declared.

Declare `path_mode: literal` when each intermediate must be a JSON object.
A scalar or list intermediate is missing; `$` is an ordinary dictionary key,
not a scalar-text alias. Literal paths have no filters. Default `tree` mode
keeps the established document path grammar. Explicit typed values under
reserved `$`/`@` keys retain their actual types.

### Joined text and nullable objects

Use generic `join` for an ordered array of projected text:

```yaml
street2:
  join:
    path: Entity.LegalAddress.AdditionalAddressLine
    path_mode: literal
    item_path: $
    item_type: object
    separator: "\n"
    trim: true
    skip_empty: true
    null_if_empty: true
    max_items: 100000
```

`path`, `item_path`, `separator`, and `max_items` are required. Missing/null
arrays return null; other non-array inputs or non-text projections refuse
with `join_shape`. Optional `item_type` is `object` or `text`; it checks each
raw item before projection. `from: document` selects the original document.
`max_items` is 1–100,000 and counts raw entries before omission. The separator
is at most 128 UTF-8 bytes; joined output is at most 1 MiB. Limit failures
use `join_limit`. Empty output returns text unless `null_if_empty` is true.

`object` accepts `omit_nulls: true` to omit declared null fields and
`null_if_empty: true` to return null for an empty result. Both default false.
Base fields retain their nulls; collision checks still precede omission.

A source's bundled `*-fields.yaml` recipes demonstrate these operations. Freeze
the entire reading under the Dataset Contract's `adapter.reading` before
qualification. The generic record mapper validates all expressions before
selective evaluation, then evaluates fields and matching at their existing
MDM normalization points. Compare exact assertions, quality, deferrals and
failure order with the retained oracle; approve changed contract digests as
new Rules versions before activation. Configuration and execution-limit
failures stop the run. Record shape failures retain their declared deferral.
Installed fixture publication/recovery and bounded captured parity are
separate from full semantic corpus and complete population proof.

For the generic record mapping bridge, optional top-level `input_fields`
declares the JSON input view as 1–128 distinct ASCII root identifiers, each
at most 128 characters. Only existing declared roots enter serialization;
missing roots stay missing. Selected values retain their types and must be
JSON values. This lets unrelated foreign metadata, such as Parquet timestamps,
remain outside field parsing without coercing it to text. Validate the full
reading and check that every mapped value path is covered by the declared
roots.
This option affects the record bridge; artifact `source.read` already consumes
serialized input and continues reading its declared paths directly.

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

A source read block that preserves a complete document (unknown fields,
structural evidence, nested history) does not activate a Rules version, and
raw-column qualification does not by itself replace a source's joins, address
derivation or full mastering.

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

Put this expression under a table's `columns`. `object` requires `fields`;
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
unchanged. This does not supply a source's catalog or census joins or qualify
its full preparation; compare those operations and assertion identities before
retiring the retained reader. Prove it by assembling fixture records from
explicit fields and verifying them through preparation and the kind's actual
MDM contract.

Optional `base` is an expression returning one JSON object. Its fields and
exact types are retained; declared `fields` add metadata. A non-object base
refuses with `object_base`, and a field collision refuses with
`object_field_conflict`. There is no implicit overwrite. All expressions in
`base` participate in validation and feature/context inventory, including
unselected branches.

```yaml
name_evidence:
  object:
    base: {value: {path: entry}}
    fields:
      census: {const: {value: APPROVED_CANONICAL_CENSUS_SHA256}}
```

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
    entity:
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

### Ordered text transformations

When a join key requires Unicode decomposition or replacements, use
`text.transforms` before considering a custom step. It runs after ordinary
trim/case conversion and before `null_if`, in the order written. Non-text
defaults pass through unchanged. Set `trim: false` when the recipe owns trimming.

Operations are single-key mappings:

- `unicode: nfkd`: compatibility decomposition using pinned Unicode 15.0 tables.
- `strip_combining: true`: remove characters with nonzero canonical combining class.
- `case: upper`: native Unicode uppercase.
- `trim: true`: strip Unicode whitespace and Python's ASCII U+001C–U+001F separators.
- `replace: {from: "&", to: " AND "}`: literal non-overlapping replacement.
- `regex_replace: {pattern: "[^A-Z0-9]+", with: " "}`: Rust regex replacement;
  replacement text is literal, including `$`. Lookaround and backreferences are refused.
- `pad: {left: " ", right: " "}`: append declared surrounding text.
- `remove_prefix: "THE "`: remove one exact leading prefix.

Bounds: 1–64 operations; each argument at most 4,096 UTF-8 bytes;
regex compilation and DFA caches each capped at 1 MiB, nesting at 32;
input and every intermediate text at most 1 MiB. Across a contract, at most
128 distinct recipes, 1,024 operations and 32 regexes. Each regex replacement charges
the remaining search window before finding its next match, with an 8 MiB
cumulative window budget; repeated searches refuse with `text_transform_work_limit`.
This conservative budget can also refuse many matches in long benign strings.
Growth refuses with
`text_transform_limit`. Contracts compile regexes once, including expressions
in unselected branches. Literal reference rows and defaults remain data.

For Name Census keys, start with each source's bundled `name-key.yaml`
(see Examples). Run the recipes on authenticated captured
current/former names; compare exact retained keys and prove a deliberate
recipe fault changes them. Record capture, contract, oracle and actual native
binary hashes. Recipe parity completes the name-key step only; census population,
classification, provenance, installed mastering/replay/recovery and active
consumer replacement remain independent requirements.

Bounds: at most 16 reference tables, 10,000 keyed rows per table, 32 columns
per row and 100,000 cells in total. Names/keys are nonempty text of at most
128 UTF-8 bytes; text cells are at most 4,096 bytes. Structured, tagged,
nonfinite and out-of-range integer cells are refused. Duplicate YAML keys
are refused by the contract parser. These are small dimension tables, not
large artifact joins or permission to raise source-worker budgets.

Compare every code of a frozen reference, with explicit lowercase and
whitespace variants, to the retained converter it replaces. Complete address,
reference provenance and assertion equivalence remain source retirement gates.

## Qualification boundary

The generic primitive and the installed worker protocol are tested
independently. A partial projection case compares only the fields it names.
Classification, address interpretation,
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

Text and calendar qualification does not cover numeric flags,
classification, mastering, reference joins or complete
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

This syntax qualifies the content fields it reads only. Artifact metadata, complete
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

A fixture and its pinned comparison cover caller provenance and the content
they select. They do not complete classification, paginated history,
reference joins, other sources or complete malformed source equivalence. Keep the full retirement gates open until those pass.

## Indexed membership and scope receipts

Use `member` when a record must be selected against a large, immutable set
of exact text keys. Declare the set and its bounds in the reading contract:

```yaml
read:
  format: json
  lookup_sets:
    scope: {max_values: 100000, max_bytes: 33554432, max_value_bytes: 16384}
  tables:
    rows:
      each: '.'
      select:
        member: {lookup: scope, key: {value: {path: code}}}
      columns:
        code: {value: {path: code}}
```

The key is an ordinary expression, including an explicit text transform when
needed. Membership is exact: no trimming, case change or type coercion. Null
returns false; nontext keys refuse. The named set must be declared even in a
branch that is never selected. Both branches validate, while evaluation stays
lazy. This declaration also bounds supplied sets used by `in_lookup`; legacy
undeclared eager membership retains its existing semantics.

Declare at most 16 sets, with nonempty names of at most 128 UTF-8 bytes.
Each set declares positive `max_values` (at most 1,000,000), `max_bytes`
(at most 64 MiB), and `max_value_bytes` (at most 16,384). Supplied names must
exactly match the declarations, including for empty input. Raw counts and
UTF-8 bytes are bounded before duplicate removal; aggregate raw key bytes
across sets must not exceed 64 MiB. The native reader freezes and indexes
values once before callbacks. They belong in lookup receipts, not scalar
context or oversized frozen reference tables.

The `source.read` **worker input manifest** uses version 3 for these receipts;
this is distinct from the pipeline's run manifest:

```json
{"version":3,"contract":{"uri":"s3://bucket/contract.yaml","sha256":"<hash>"},
 "artifacts":[{"input":{"uri":"s3://bucket/captured.json","sha256":"<hash>"},
               "context":{"uri":"s3://bucket/context.json","sha256":"<hash>"},
               "lookups":{"uri":"s3://bucket/lookups.json","sha256":"<hash>"}}]}
```

Both context and lookup receipts are required. Use an empty `values` object
in the context document when no context is declared. The lookup receipt names
strict JSON of at most 64 MiB:

```json
{"version":1,"input":{"uri":"s3://bucket/captured.json","sha256":"<hash>"},
 "sets":{"scope":["A","B"]}}
```

`input` must equal the captured receipt's complete URI and hash. `sets` must
hold exactly the declared names, each with a text array. The worker validates
these documents before opening source bytes; its verifier independently
replays the reading with the same receipts. Output retains lookup evidence,
even when selection yields no rows. JSON streaming supports these indexed
sets; XML streaming currently refuses them explicitly. Eager configured reads
retain their declared-format support.

A consumer must bind lookup evidence into its output identity. The configured
combiner supports this: its scope hashes the complete reading receipts, so
identical rows under different lookup receipts remain distinct for downstream
preparation and publication. Direct MDM preparation of a lookup-bearing
reading refuses until its identity contract supports that evidence. Declare
a combine step before preparation for this route; never discard the receipt.

Construct the set from verified upstream population evidence and pin its
receipt in the worklist. Authentication proves the supplied bytes and input
binding; it does not prove that the set is complete or that a supplied count
was derived correctly. Compare complete source populations and retain their
provenance before retiring an active consumer. A sampled reading or successful
EOF on a repackaged prefix does not qualify the original whole source.

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

A configured address comparison can freeze place reference rows into the
contract, preserve raw street and region text, derive country from the
approved ISO reference and keep region only for subdivisions. This proves
raw address derivation separately from census, complete provenance, pagination
and full mastering; those remain required before parser retirement.

### A main document with continuation pages

A source's `source.yaml` may declare a generic `source.read` block for its main
document that emits one table per part (the record, its repeated items, its
addresses). Fields keep their captured types; repeated items use the
parallel-array, date, numeric and first-N rules; places use frozen reference rows.

Use a version-2 source input manifest. Each artifact has `input` and `context`
receipts. The context document binds explicit caller facts (the record key,
capture run, raw object id, load mode, sync time, any item limit) to that exact
input receipt; the worker verifies their binding and the native engine their
types. An input hash does not independently prove a supplied capture identifier
or observation time: the acquisition or census provenance gates must prove those.

Join the resulting tables with a declared `source.combine` contract, then use
`mdm.prepare` to write immutable input batches. The read block alone is neither
a source activation nor complete mastering.

Read each captured continuation page with its own contract at the raw page
root, bound to the page receipt, with no item-limit context. Do not invent a
wrapper the page does not have. Capture every page the pinned main document
names, read pages in bounded groups, combine them with the main reading, then
combine the per-record lists with `collect_flat` and `sort_values: true`. See
[Combination](COMBINING.md) for list and element-budget semantics. Same-date
captures plus version and hash evidence prove captured bytes and declared page
coverage; they do not prove Bookkeeping producer success.

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

`each.entries` exposes both a literal key and its typed value:

```yaml
each:
  entries: {path: entries, key_field: map_key, value_field: entry}
```

The two fields must be distinct ASCII identifiers of 1–64 characters. Keys
such as `a.b`, `@id` or `$` remain literal values in `map_key`; `entry`
retains arrays, objects, booleans, numbers and null. Captured key order and
raw-count limits are preserved. `on_invalid: empty` is explicit; the default
refuses a missing or non-object input.

Choose a layout through `each.choose` with `condition`, `then` and `else`.
The condition is an ordinary expression evaluated against the document;
branches are iteration calls or paths. Boolean true selects `then`, false or
null selects `else`, and other types refuse. Both branches validate before
reading; only the selected branch reads the document. Nesting is capped at
eight calls. Context/reference/custom names in all conditions must resolve.

`each: {empty: {}}` returns zero rows without inspecting the document or
evaluating columns. Use it as an `each.choose` branch when an eligibility
condition excludes a record. Arguments must be an empty mapping; both choose
branches still validate. This avoids relying on a supposedly absent path
that captured data could contain.

`test: {path: code, kind: truthy}` returns a native boolean without text
coercion or materializing a subtree. Kinds are `truthy`, `missing`, `null`,
`not_null`, `array`, `object` and `text`; optional `from: document` tests the original
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

A catalog contract can declare every captured layout of a catalog and its
legacy skip, fallback and text rules with these generic calls. Receipt context
supplies catalog run, source name and sync time. Group a repeated value by the
record key with `order_by: [source_rank]`, `distinct: true`,
`skip_empty_text: true` and a catalog-run row check; keep the record's own
capture-run check on base rows. Both finite malformed-case and physical capture
qualification must pass before adoption. Byte, header, row, numeric and Unicode
safety boundaries remain explicit, so finite parity does not imply universal
arbitrary-input parity. No source activation, producer success or complete
mastering follows from successful catalog reading.

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
matches a historical decoder's narrower negative boundary.
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
qualified, including combining and preparation. Before a streamed source's
cutover, verify complete archive/member authentication and metadata and prove
publication/replay through EOF. JSON framing tests do not qualify XML or
retire a source's active parsing.

## An approved scope in a streamed template

A streamed template declares its framing, explicit numeric and record limits,
a pinned publication count and a receipt-bound source ordinal. Populate its
scope reference (`read.references.<scope>`) with the reviewed identifiers as
`{<id>: {selected: true}}` before submission; an empty map is a template, not
an approved cohort. Source scope is a frozen reference table in the same
contract receipt as selection. `record` keeps typed source fields for MDM
interpretation; `source_index` is one-based. Compare provenance with any
historical zero-based ordinal explicitly before runtime adoption.

Archive framing parity and a captured-sample performance measurement do not
by themselves prove installed configured projection, producer publication,
XML parity or complete mastering. Complete those checks before replacing a
source's active runtime or activating its Rules.

## Configured XML record framing

For a large XML envelope, declare `read.stream.framing: xml_records`.
`read.format: json` describes the normalized record presented to the existing
table interpreter. The stream declares `xml` with exactly `namespace`, `root`,
`header`, `container`, `record` and nullable `record_wrapper`. Envelope elements
and records must use the declared namespace. The header precedes the single
record container; repeated/misplaced elements and incomplete EOF refuse.

Declare `header_read` as a separate ordinary JSON read block with the same
context declaration as the record read. Its configured assertions run before
the first record, including an empty container. Header deferrals refuse the
source. Use input-bound context and pinned reference cells for publication
metadata; the framer supplies no source-specific metadata policy. Generate the
one-based ordinal context internally as for JSON framing. The optional
`expected_records_context` checks the full source count after EOF.

XML framing uses the same compressed/expanded bytes, record/depth/count,
partition and private spool bounds as JSON framing. Omit the JSON-only
`wrapper`, `min_integer` and `record_encoding` fields. Normalized records use
compact Python JSON byte accounting. XML may declare `read.stream.max_header`
(1..32 MiB) separately for normalized header/envelope nodes; omission defaults
to `max_record`. Match `header_read.limits.max_bytes` to the intended header
projection bound. Increasing `max_header` never increases normalized record
limits or the raw per-record buffering allowance (`max_record` + 65,536 bytes).
Attributes retain expanded namespace
names (`@{URI}local`); children in the declared namespace use local names;
foreign children retain `{URI}local`. Repeated children become lists and
leading stripped text becomes `$`; tail text is ignored. Namespace scopes,
XML line endings, attribute whitespace and character references are normalized.
DTD, undeclared entities, invalid XML names/characters, processing instructions
inside captured nodes and malformed declarations refuse the source.

`SourceEngine.stream_xml_records` projects normalized records in Rust and
receives a separate configured header engine. The worker stages all partitions
privately until every input reaches valid EOF, ZIP CRC and count checks. Retry
and independent verification use the same configured source boundary. Complete
captured XML parity, installed mastering and active consumer replacement
remain required before an old XML parser can be removed.

## Member templates and publication headers

A source folder may bundle one template per member and format. Read them
through `rules.files.load` from the installed `rules.files.ROOT`; copy and pin
the result before submitting `source.read`. They are qualification templates,
not activated source Rules. Their selection keeps complete source records and
original one-based ordinals. Both endpoints of a relationship must belong to
the approved scope. Scope selection makes no identity or binding decision and
does not replace the later MDM checks.

Populate the XML `header_read.references` from authenticated publication
metadata: `content_dates` and `delta_starts` key normalized UTC ISO instants
(`+00:00`, seconds or six fractional digits); `record_counts` keys the exact
decimal header text; `file_content` keys the publication mode and supplies
`valid: true` plus boolean `requires_delta`. Other reference cells supply
`valid: true`. Full publication requires absent/empty `DeltaStart`; delta
publication requires its pinned predecessor time. Empty header references
refuse the source. Duplicate, malformed or mismatching fields fail before any
record can be published. Header date comparison accepts equivalent timezone
spellings by using the existing `date` expression.

Bind `publication_count` to each exact input receipt using the version-2
source input manifest. Pin the same publisher count in the header reference;
the worker compares the complete framed count at EOF before publication.
The creator must derive both pins from the same publication. Each XML member template configures the generic `equal` assertion
above to compare header count directly to context count; independently pinned
header references must also agree with the authenticated publication metadata. Also keep API `publish_date`
separate from XML `ContentDate`: captured members can have different content
timestamps within one publication slot. Pin authenticated capture-header
evidence explicitly when the download API does not supply that field.
JSON has no XML header: its CDF version, content time, mode and predecessor
evidence must come from the authenticated publisher manifest. A count observed
by a decoder is structural evidence and cannot substitute for that metadata.
Read the format's source structures as captured; XML and JSON may represent
singleton lists or attributes differently, so do not infer cross-format raw
record equality from their common member name.

## Reuse an authenticated census

For census reuse, import the approved JSON through `Artifacts.put` so its
artifact SHA matches the canonical census digest used in evidence. Bind that
SHA to every placeholder in the source's census contract before freezing it. Optional `execution.input_sha256s` pins every
input artifact in manifest order (one or two lowercase SHA-256 values).
Both source.read worker and verifier check these pins before reading or
publishing, including when the source yields no rows. The standalone native
engine does not enforce execution pins.

Read the captures through the source's census main contract, then combine with
its census combine contract as described in COMBINING.md. Census version,
normalizers, FULL publication and optional cascade version must match the
contract; unexpected reserved metadata collisions refuse. Constants are
scalar values; use scalar assertions for metadata fields and `test`/`equal`
for typed boolean conditions.

This reuses approved global counts. Constructing the complete census,
qualifying its current source population and proving installed mastering
remain separate completion requirements.

## Typed values that may be single or repeated

Use `each.values` for a JSON member that can hold one value or an array:

```yaml
read:
  format: json
  limits: {max_bytes: 1048576, max_records: 1000}
  tables:
    names:
      each: {values: {path: names}}
      select: {test: {path: '.', kind: text}}
      columns:
        name: {value: {path: '.', type: text, trim: true, null_if_blank: true}}
```

A missing member or empty array yields no rows. Null, numbers, booleans and
objects are single values; selection chooses which types to retain. Arrays
retain element order and exact types. The record bound counts every source
value before selection or `take`; an oversized array is refused even when
nothing would be selected. `test.kind: text` tests the original JSON type
without numeric or boolean coercion. Nested `choose` expressions can select
an object's `$` text member or a scalar text value explicitly.

Bundled census contracts use these primitives for census name extraction and
canonical keys: they project eligibility and legal keys selectively and read
registration only for a wanted legal key. Preserve the caller's column order.
Empty falsey containers yield no names; truthy non-object containers refuse.
Skipped records must not evaluate name counts or registration. Qualification
disables custom steps and includes paired faults that prove refusal order.
Holder aggregation and cascade decisions remain in the census implementation.
Whole-source census construction, complete source provenance and installed
population qualification are still required before removing that implementation.

## Examples

The sources this repository reads today, and where each rule above is applied.

### Recipes and contracts

- GLEIF's bundled `*-fields.yaml` recipes demonstrate the joined-text and
  nullable-object operations; the SEC Company `fields.yaml` recipe demonstrates
  the `input_fields` boundary.
- The SEC Company main contract requires an object document and an object
  `addresses` member when present; a business member gives a row only when it is
  an object; its place lookup converts the selected SEC code with Python text
  semantics, keeping the historical mapping of nontext codes to unknown places.
- The Person source read block keeps the complete submissions document. Company
  raw-column qualification does not yet replace its catalog and census joins,
  address derivation or full mastering.
- The installed object-records trial assembles the two raw Person fixture records
  and verifies them through preparation and the actual Person MDM contract.
- Name Census keys: `sec.submissions.company/name-key.yaml` and
  `gleif/name-key.yaml` keep legal forms and unify their spelling; the SEC recipe
  removes the trailing state suffix before normalizing.
- All 309 SEC place codes and their lowercase and whitespace variants are
  compared to the retained jurisdiction converter.
- The partial filing projection case compares accession and form fields only.
  The 18-column filing fixture covers caller provenance and selected recent
  filing content.
- The Company draft `catalog.yaml` groups `ticker` by CIK over both captured
  catalog layouts; runtime custom ticker parsing is retired and its oracle is
  test-only.
- `min_integer: -9223372036854775807` matches the historical GLEIF decoder.
- Active GLEIF JSON and XML retirement was unfinished when this was written.

### The SEC Company main document

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


### The GLEIF Level 1 JSON template

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


### The GLEIF member templates

The bundled `sources/gleif/` folder contains `level1`, `relationships` and
`reporting-exceptions` templates for both `json` and `xml`. Read them through
`rules.files.load` from the installed `rules.files.ROOT`; copy and pin the
result before submitting `source.read`. They are qualification templates,
not activated source Rules. Their selection preserves complete source
records and original one-based ordinals. Both relationship endpoints must
belong to the approved scope. Scope selection makes no identity or binding
decision and does not replace the later MDM checks.


### Census contracts

- Census reuse binds the census SHA into `sources/sec.submissions.company/census.yaml`;
  Company captures are read through `census-main.yaml` and combined with
  `combine-census.yaml`.

The bundled `gleif/census-record.yaml` and
`sec.submissions.company/census-filer.yaml` use these primitives for census
name extraction and canonical keys. `gleif/census-identity.yaml` projects
eligibility and legal keys selectively; `gleif/census-update.yaml` reads
registration only for a wanted legal key. Preserve the caller order: census
category, LEI, legal key, wanted-key timestamp, other names; cascade LEI,
category, mapped quality, names. Empty falsey containers yield no names;
truthy non-object containers refuse. Skipped records must not evaluate name
counts or registration. Qualification disables custom steps and includes
paired faults that prove refusal order. Holder aggregation and
cascade decisions remain in the census implementation. Whole-source census
construction, complete source provenance and installed population qualification
are still required before removing that implementation.

## Bounded Parquet framing and sparse object entries

The `source.read` worker accepts `read.format: parquet`. Arrow frames projected
rows as JSON `rows`; configured Rust expressions produce the output tables.
The physical Parquet receipt remains the source identity. Optional
`read.parquet.columns` declares 1..128 distinct input columns; omitted means all.
`distinct: true` deduplicates exact projected rows, preserving first occurrence.
A declared `take: 1..1000` frames the first source rows as a bounded sample.
Without `take`, framing consumes every projected row through EOF. Dates become
ISO text; unsupported scalars and nonfinite numbers refuse. No provider logic
runs in framing. Do not omit fencing columns when projecting/deduplicating.

Materialized execution may declare `execution.max_input_bytes` (1..256 MiB).
Otherwise the existing 32 MiB physical limit applies. `read.limits` bounds the
framed/decoded document and emitted records independently; the output remains
bounded. Streamed framing declares its own physical bounds and refuses this
materialized option. A bounded preparation template may retain a 64 MiB
physical limit, 32 MiB framed JSON and 100,000 distinct projected rows. Larger
projected inputs require partitioning; this is a bounded preparation contract.

`each.entries` optionally declares `keys: [literal, keys]`, at most 1,000 distinct
text keys of at most 4,096 bytes each. The reader authenticates and parses the
complete input document before projecting those entries, preserving source
object order and literal punctuation. Missing keys emit nothing. `max_records`
then bounds selected entries; omitting `keys` preserves whole-object iteration.
An empty key list still validates document shape and assertions.

## Examples: configured preparation caller

`mdm prepare-clean-company` now binds immutable configured Parquet reading and
combination contracts, reuses the authenticated frozen census and verifies each
worker before publishing its existing bundle. It retains complete worker
inputs/contracts/outputs and proof beside the original pinned members. Readback
requires the approved inventory report and reproduces the configured outputs.
The independent `mdm name-census` caller remains active; this change does not
qualify a new census construction or full population mastering.
