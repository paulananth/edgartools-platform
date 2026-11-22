# Engine rules primer, grouped by function

Rules describe how captured evidence becomes rows, master identities and
relationships. They are configuration interpreted by existing code, not an
arbitrary programming language. This primer explains the supported families
and gives invented examples; linked references own the complete argument and
limit contracts.

## Find the function you need

| Function | Rule location / interpreter | Start here |
| --- | --- | --- |
| Open a captured file | `read` / source engine | [1. Reading](#1-reading-files-and-choosing-rows) |
| Read or construct a value | `read.tables.<table>.columns` / source engine | [2. Values](#2-extracting-and-constructing-values) |
| Clean text | Expression `transforms` / source engine | [3. Text](#3-normalizing-text) |
| Select, assert or defer | Document/table rules / source engine | [4. Conditions and checks](#4-conditions-filtering-and-source-checks) |
| Look up reference or companion data | References and lookup sets / source engine | [5. Lookups](#5-reference-lookups-and-membership) |
| Group, join or count across inputs | `combine` or `reduce` / native kernels and workers | [6. Combination](#6-combining-and-aggregating-records) |
| Map rows into MDM | Dataset Contract `adapter` / MDM preparation and normalization | [7. Mapping](#7-mapping-records-into-mdm) |
| Fix or check MDM input | Source `quality.yaml` / quality engine | [8. Quality](#8-mdm-data-quality) |
| Decide kind and identity | Kind policy rules / mastering engine | [9. Matching](#9-classification-and-identity-matching) |
| Choose authoritative field values | Kind defaults, field and group rules / mastering engine | [10. Survivorship](#10-choosing-field-values-survivorship) |
| Build links, hierarchies and role periods | Adapter assertions + pinned RDM type rules / mastering engine | [11. Relationships](#11-relationships-hierarchies-and-profiles) |
| Run work, land Silver and expose metadata | Target configuration and registered workers | [12. Workflow](#12-workflow-silver-and-metadata-rules) |

The vocabulary below was checked against the source at
`90ef96a77` and the accompanying examples against the current checkout.
Support for a rule does not establish that a particular source is qualified,
activated or deployed. Examples labeled **fragment** require the enclosing
contract, registered kinds, reference pins or pipeline inputs described there.

## 1. Reading files and choosing rows

The source engine reads captured bytes; it does not fetch a URL. A `read` block
declares format, container, shape, limits, iteration and columns.
`root` checks an XML root; `required` lists paths that must exist before table
iteration. Those artifact checks differ from per-row `checks`.

| Format | Typical use |
| --- | --- |
| `json` | Whole documents, objects and arrays. |
| `jsonl` | One JSON record per line. |
| `xml` | Root-checked XML; names, attributes and repeated elements. |
| `csv`, `tsv` | Header-based rows; TSV treats quotes as ordinary characters. |
| `html` | Visible text blocks and table rows, with page/table position metadata. |
| `parquet` (worker-framed) | The source worker frames Parquet rows and projects them through JSON rules; not direct eager Rust parsing. |

Containers include plain input, ZIP member selection and, for XML, an SGML
submission envelope. ZIP member patterns must select exactly one unencrypted
member. CSV/TSV/HTML can explicitly declare UTF-8 or Windows-1252 decoding.
`read.format: parquet` is supported through the worker framing path, while the
direct/eager Rust reader does not parse Parquet.
Streaming JSON, XML, delimited and Parquet paths have their own worker contracts;
do not substitute a `SourceEngine.read()` call for their authenticated EOF gate.

### A complete small reading example

Input:

```json
{"records":[{"id":"R1","name":"  Example Works  ","quantity":"12"}]}
```

Contract:

```yaml
read:
  format: json
  limits: {max_bytes: 4096, max_records: 10}
  tables:
    records:
      each: records
      columns:
        id: {text: {path: id}}
        name: {text: {path: name}}
        quantity: {integer: {path: quantity}}
```

Result: `records` contains `{"id":"R1","name":"Example Works","quantity":12}`.
Use `each: .` for one row from the document itself. Paths are relative to the
current item; supported expressions can use `from: document` for the envelope.
XML scalar text uses `$` and attributes use `@name`. A repeated intermediate
path needs explicit iteration; it does not silently choose one item.

### Iteration functions

| Form | Function / example fragment |
| --- | --- |
| Path | `each: records` visits the named records. |
| `parallel` | `each: {parallel: {path: records, anchor: id, fields: {id: id, name: name}, lengths: equal}}` zips column arrays; `anchor` is an explicit alternative length policy. |
| `matrix` | `each: {matrix: {headers: fields, rows: data}}` turns header/cell arrays into records. Explicit compatibility policies govern unequal lengths, duplicate/coerced headers and invalid rows. |
| `objects` | `each: {objects: {path: catalog, on_invalid: empty}}` visits object values in captured order. |
| `entries` | `each: {entries: {path: catalog, key_field: code, value_field: body}}` exposes literal keys and typed values; optional `keys` restricts the requested keys. |
| `values` | `each: {values: {path: items}}` visits array values, including arrays exposed by `entries`. |
| `nest` | `each: {nest: {each: records, keep: {id: parent_id}, then: items}}` visits child rows and carries outer `id` into child `parent_id`; collisions refuse. |
| `project` | `each: {project: {value: {value: {path: record}}, on_null: empty}}` emits one derived row or no row for null. |
| `choose` | `each: {choose: {condition: {test: {path: records, kind: array}}, then: records, else: {empty: {}}}}` chooses an iteration layout. |
| `empty` | `each: {empty: {}}` deliberately emits no rows. |

`take` selects a prefix; `select` filters that prefix. Neither bypasses full
input safety checks. `ordinal: selected` counts retained rows; the default
ordinal follows source positions. Context declares typed caller facts, such as
the capture's business date; immutable receipts bind them to the input.

Reference: [Configured source extraction](../skills/data-platform/READING.md)
and [iteration implementation](../crates/source-contract/src/iteration.rs).

## 2. Extracting and constructing values

Each column expression is exactly one call. Calls can contain other calls.
This section and sections 4–5 cover all **28 source-expression primitives**.
Examples in these tables are fragments to place beneath a column name.

| Primitive | Example | Meaning |
| --- | --- | --- |
| `text` | `{text: {path: name, trim: true, null_if: ["", UNKNOWN]}}` | Read text, trim, optionally change case and handle declared null tokens. |
| `value` | `{value: {path: payload, type: object}}` | Preserve typed JSON rather than stringify it. Optional null/type policies reject incompatible shapes. |
| `integer` | `{integer: {path: quantity, on_invalid: error}}` | Convert to exact signed 64-bit integer; independently declare invalid-value and overflow handling. |
| `number` | `{number: {path: score}}` | Existing floating-point conversion. Supported, but unsuitable for this repository's exact business decimals. |
| `date` | `{date: {path: effective_date, kind: calendar}}` | Return a calendar date; default `kind: instant` requires a timezone-bearing instant and normalizes it to UTC. |
| `const` | `{const: {value: example}}` | Supply a scalar literal; it is not a typed JSON object/array constructor. |
| `context` | `{context: {name: business_date}}` | Read a declared typed caller/header fact. |
| `ordinal` | `{ordinal: {}}` | Return the current row's one-based ordinal. |
| `object` | `{object: {fields: {id: {text: {path: id}}}, omit_nulls: true}}` | Construct an object; optional `base` preserves existing fields and refuses collisions. |
| `sequence` | `{sequence: [{text: {path: id}}, {text: {path: name}}]}` | Construct a typed list, preserving null entries. |
| `concat` | `{concat: [{text: {path: id}}, {const: {value: ":"}}, {ordinal: {}}]}` | Build text from text/integer parts; any null part makes the result null. |
| `pluck` | `{pluck: {value: {value: {path: items}}, fields: [id]}}` | Collect named text fields from objects in a list; skip missing/null fields. |
| `join` | `{join: {path: lines, item_path: $, separator: ", ", max_items: 100, skip_empty: true}}` | Join an array of projected texts; not a relational join. |
| `project` | `{project: {value: {value: {path: payload}}, then: {text: {path: name}}}}` | Evaluate an expression against a derived typed document. |
| `transform` | `{transform: {value: {text: {path: name}}, transforms: [{case: upper}]}}` | Apply a text recipe to an expression result; preserve null. |
| `steps` | `{steps: [{text: {path: id}}, {text: {path: name}}]}` | Evaluate calls in order and return the final result; **not** a value pipeline between calls. |
| `custom` | `{custom: {step: epoch_microseconds@1, inputs: {value: {text: {path: timestamp}}}}}` | Call an explicitly registered versioned function; unknown functions refuse at contract load. |

### Exact numbers and missing values

For financial decimals, use typed JSON preservation, for example
`{value: {path: amount, decimals: text, big_numbers: text}}`. A JSON number
`2.50` becomes exact text `"2.50"` for a decimal consumer. Do not round it
through `number`. These policies require the supported whole-document JSON/JSONL
path; streaming restrictions are explicit in the reading reference.

An `integer` conversion supports configurable overflow/invalid handling and
`as: boolean`, but some numeric input conversions truncate. Do not assume
integer conversion validates that a source fraction was an integer. Preserve
the source value and explicitly handle representability before publication.

An absent value, explicit null, empty text, zero and false are different states.
`const: {value: false}` has historical **text** conversion; use a native boolean
from `test`, `equal`, `member`, typed context or `value` for conditions.

References: [expression validator and evaluator](../crates/source-contract/src/lib.rs),
[typed JSON](../crates/source-contract/src/value.rs),
[registered custom steps](../edgar_warehouse/rules/steps.py).

## 3. Normalizing text

Recipes run in order, after ordinary text trim/case and before null-token
handling. The complete transform vocabulary is:

| Operation | Example | Function |
| --- | --- | --- |
| `unicode` | `{unicode: nfkd}` | Compatibility decomposition. |
| `strip_combining` | `{strip_combining: true}` | Remove combining marks. |
| `case` | `{case: upper}` | Unicode uppercase in a recipe. |
| `trim` | `{trim: true}` | Remove surrounding supported whitespace. |
| `replace` | `{replace: {from: "&", to: " AND "}}` | Literal replacement. |
| `regex_replace` | `{regex_replace: {pattern: "[^A-Z0-9]+", with: " "}}` | Bounded Rust-regex replacement; replacement text is literal. |
| `regex_extract` | `{regex_extract: {pattern: "ID: ([0-9]+)", group: 1}}` | Extract a capture group, empty when no match. |
| `pad` | `{pad: {left: "[", right: "]"}}` | Surround text. |
| `remove_prefix` | `{remove_prefix: "THE "}` | Remove one exact prefix. |
| `tokens` | `{tokens: {STREET: ST}}` | Replace whole whitespace-separated tokens. |
| `lines` | `{lines: [{trim: true}, {case: upper}]}` | Apply a recipe to each line and drop empty results. |
| `slice` | `{slice: {start: 0, end: 3}}` | Slice Unicode characters from the start. |
| `keep_last` | `{keep_last: 3}` | Keep the final characters. |
| `drop_last` | `{drop_last: 3}` | Remove the final characters. |

Example fragment:

```yaml
normalized_name:
  text:
    path: name
    transforms:
    - unicode: nfkd
    - strip_combining: true
    - case: upper
    - replace: {from: "&", to: " AND "}
    - regex_replace: {pattern: "[^A-Z0-9]+", with: " "}
    - trim: true
```

`"  Café & Sons  "` becomes `"CAFE AND SONS"`. This is a matching aid, not
proof that two names identify the same subject. Regex lookaround and
backreferences are unsupported. Text, regex work and recipe counts are bounded.
Reference: [text recipe implementation](../crates/source-contract/src/text_transform.rs).

## 4. Conditions, filtering and source checks

### Conditional expression primitives

| Primitive | Example fragment | Function |
| --- | --- | --- |
| `test` | `{test: {path: name, kind: text}}` | Native shape/presence/truth check. Kinds: `truthy`, `missing`, `present`, `'null'`, `not_null`, `array`, `object`, `text`. |
| `equal` | `{equal: {left: {integer: {path: count}}, right: {const: {value: 2}}}}` | Compare typed values without coercing text to integer. |
| `overlap` | `{overlap: {left: {value: {path: codes}}, right: {sequence: [{const: {value: A}}]}}}` | True when text lists share a value; null if either operand is null. |
| `coalesce` | `{coalesce: {values: [{value: {path: preferred}}, {value: {path: fallback}}], skip: "null"}}` | First retained value; `falsey` additionally skips zero, false and empty containers/text. |
| `choose` | `{choose: {condition: {test: {path: active, kind: truthy}}, then: {text: {path: name}}, else: {const: {value: null}}}}` | Execute one branch; condition must be boolean/null. |
| `recover` | `{recover: {value: {value: {path: name, type: text}}, codes: [value_type], fallback: {const: {value: null}}}}` | Catch only declared `value_type`/`join_shape` failures, not corruption, contract or resource failures. |
| `found` | `{found: {path: name, transforms: [{trim: true}]}}` | True when transforming a text leaves a nonempty result. |
| `first_found` | `{first_found: {path: block, from: document, within: 20, transforms: [{trim: true}]}}` | First nonempty transformed text, useful for HTML blocks. |

`read.assertions` rejects an entire artifact before reading its tables. A
table's `select` instead omits rows. A table's `checks` can defer a bad row or
reject the artifact. These outcomes are not interchangeable.

```yaml
# Fragment under read:
assertions:
- test: {test: {path: '.', kind: object}}
  reason: Expected an object document
```

All seven source-check names are listed below. Each names `on_fail: defer` or
`reject` and a reason (the specialized `lei` check has its own reason handling).
Optional `when: {column: status, equals: ACTIVE}` limits applicability.

| Check | Example fragment | Pass condition |
| --- | --- | --- |
| `required` | `{check: required, column: id, on_fail: defer, reason: missing_id}` | Selected text exists. |
| `in_set` | `{check: in_set, column: status, values: [ACTIVE], on_fail: defer, reason: unsupported_status}` | Selected text belongs to the declared list. |
| `in_lookup` | `{check: in_lookup, column: id, lookup: scope, on_fail: defer, reason: outside_scope}` | Selected text belongs to the caller's membership set. |
| `absent` | `{check: absent, path: error, on_fail: reject, reason: error_present}` | The named path is absent. |
| `count` | `{check: count, path: items, equals: 2, on_fail: reject, reason: wrong_count}` | Missing path counts as 0, a list by its length, and a selected scalar/element as 1; compare that count with `equals`. |
| `before` | `{check: before, column: start, until: end, on_fail: defer, reason: invalid_period}` | When both columns are text instants, start is strictly before end; a missing/nontext endpoint does not fail this check, so add required checks where needed. |
| `lei` | `{check: lei, column: identifier, on_fail: defer}` | Specialized identifier validation succeeds. |

These source checks differ from MDM's versioned quality checks in section 8.
`test.present` accepts an existing JSON null; source `required` is a text-value
check. Consult the [source check evaluator](../crates/source-contract/src/lib.rs)
before substituting one for the other.

## 5. Reference lookups and membership

The remaining three expression primitives distinguish small frozen dimensions,
membership and key/value lookup:

| Primitive | Example fragment | Function |
| --- | --- | --- |
| `lookup` | `{lookup: {reference: statuses, column: label, key: {text: {path: status}}, on_missing: "null"}}` | Exact lookup in `read.references`; missing may return null or error. |
| `member` | `{member: {lookup: scope, key: {text: {path: id}}}}` | Boolean membership in a declared immutable set. |
| `member_value` | `{member_value: {lookup: aliases, key: {text: {path: id}}, on_many: error}}` | Return the unique value in a declared pair set; never choose an arbitrary ambiguous value. |

Example declarations under `read`:

```yaml
references:
  statuses:
    A: {label: Active}
lookup_sets:
  scope: {max_values: 100, max_bytes: 4096, max_value_bytes: 64}
  aliases: {max_values: 100, max_bytes: 4096, max_value_bytes: 64, pairs: true}
```

The caller supplies membership/pair values through authenticated lookup
receipts. A frozen reference is not a mutable database query. Reference-code
meaning and approved versions remain governed in RDM.
Reference: [lookup sets and receipts](../skills/data-platform/READING.md#indexed-membership-and-scope-receipts).

## 6. Combining and aggregating records

Use `source.combine` for keyed grouping and joins across authenticated source
extracts; per-row derivation belongs in reading expressions.

| Function | Modes / options | Example result |
| --- | --- | --- |
| Collect values | `collect`, `distinct`, `order_by`, `skip_null_values` | Alias rows A, B, A become `[A, B]` after declared distinct collection. |
| Flatten one level | `collect_flat`, optional `sort_values` | `[B, A]` and `[A]` become `[A, B]` with distinct sorting. |
| Choose a row/value | `first`, `last`, `one` | `one` refuses two matching rows even when they hold equal values. |
| Join grouped results | Base `key`, `group`, `on_missing`, `replace`, optional nested `path` | Attach each record's collected aliases without changing its source identity. |
| Validate or restrict | `checks`, `where`, output `drop` | Require a capture marker, select exact values, remove helper keys. |
| Complete-set reduction | `count`, `members`, `most` | Count rows; count distinct members; or choose the most-filed member, returning null on a tie. |

Combination example (a complete configuration shape; receipt inputs are separate):

```yaml
execution: {profile: source.combine}
combine:
  max_rows: 1000
  groups:
    aliases:
      source: extra
      table: names
      key: id
      value: alias
      mode: collect
      order_by: [alias]
      distinct: true
      skip_null_values: true
      checks: {}
      where: {}
  tables:
    records:
      source: primary
      table: records
      checks: {}
      where: {}
      joins:
        aliases: {group: aliases, key: id, on_missing: empty, replace: false}
```

With primary row `{"id":"R1"}` and names `{"id":"R1","alias":"B"}`,
`{"id":"R1","alias":"A"}`, output is
`{"id":"R1","aliases":["A","B"]}`. This join does not decide identity.

`reduce` is a separate contract with required aggregate byte/row/state/key/member
limits. `members` can subtract an `exclude` group or retain a constrained `last`
value; `most` counts frequencies. Finish only after every input authenticates
and reaches EOF. Materialized `combine` is not a disk-spilling SQL engine.
Reference: [Combination and reduction](../skills/data-platform/COMBINING.md).

## 7. Mapping records into MDM

A Dataset Contract identifies source records and maps them to accepted model
concepts. Its `adapter` can configure:

- Record/publication identity, format validation and effective time.
- Fixed kind, category-to-kind mappings, or a declared classification rule.
- Matching identifiers, separately declared lookup-only cross-references and
  their formats. An identifier of another subject belongs to that subject.
- A `reading` with one `mapped` table and `fields`/`matching` object columns.
- Relationship assertions, role profiles and stable source provenance.
- Retained deferrals and the explicitly allowed nonblocking reason list.

Mapping fragment under an otherwise complete Dataset Contract:

```yaml
adapter:
  version: example-record-v1
  record_key: [id]
  kind: company
  effective_at: updated_at
  retain_deferred: true
  source_record_provenance: true
  reading:
    read:
      format: json
      tables:
        mapped:
          each: .
          columns:
            fields:
              object:
                fields:
                  name: {value: {path: name, path_mode: literal, type: text, null_if_blank: true}}
            matching: {object: {fields: {}}}
```

The `company` kind must already exist. The snippet deliberately does not invent
an approved identity identifier. The adapter reading exposes source paths for
stewards; computed mapping expressions such as `choose` are restricted there,
even when supported in an earlier source-reading step. Adding an engine
expression does not make it valid in every configuration location.

Reference: [Dataset Contract reference](../skills/data-onboarding/REFERENCE.md#adapter),
[adapter implementation](../edgar_warehouse/mdm/adapters.py).

## 8. MDM data quality

`sources/<source>/quality.yaml` applies fixes first, then checks on mapped input.
It is a separate file, folded into the registered Dataset Contract by the loader.

| Check | Function / example arguments |
| --- | --- |
| `present@1` | Required value; no arguments. |
| `in_set@1` | Allowed values: `{values: [ACTIVE, CLOSED]}`; empty passes. |
| `pattern@1` | Full regex match: `{regex: '[A-Z]{2}'}`; empty passes. |
| `lei_check_digit@1` | Specialized LEI shape/checksum validation. |
| `identifier_check_digit@1` | Checksum for a declared identifier: `{identifier: example_id}`; requires that identifier definition. |
| `placeholder@1` | Exclude stand-ins: `{values: [UNKNOWN, NONE]}`; also detects all-zero placeholders. |
| `registered_agent_address@1` | Detect address markers: `{markers: ["C/O"]}`. |
| `in_reference@1` | Validate against a pinned reference version: `{table: approved_codes, sha256: PINNED_DIGEST}`. |
| `in_hierarchy@1` | Validate a code's parent against that version: add `{field: fields.parent_code}` to the reference arguments. |

| Fix | Function / example arguments |
| --- | --- |
| `blank_values@1` | `{field: fields.name, values: [UNKNOWN]}` clears declared stand-ins. |
| `name_state_marker@1` | `{name: fields.name, target: fields.state_of_incorporation}` moves a recognized suffix marker into an empty target. |
| `standardize_address@1` | `{field: fields.address, into: matching.address}` creates a matching copy, preserving the displayed source address. |

Example fragment for an existing Dataset Contract `example.records.v1`:

```yaml
version: example-quality-v1
quality:
  example.records.v1:
    checks:
    - id: name_required
      test: present@1
      value: fields.name
      on_fail: exception
      args: {}
```

`exception` keeps the record out of merging as `quality_name_required`; declare
that reason in the contract's nonblocking list. `withhold` retains a value but
excludes it from matching; `flag` only counts the failure. None means “silently
fix it.” Silver has a distinct specification/check path; do not assume MDM input
checks automatically govern all Silver rows.
Authority: [quality checks and fixes](../edgar_warehouse/mdm/quality.py).

## 9. Classification and identity matching

These are **versioned policy primitives**, not source expressions. Rules select
the supported primitive and its arguments; code owns the implementation.

| Rule family | Function |
| --- | --- |
| `classification` | Ordered record tests choose an allowed kind or deferred verdict. |
| `binding` | Find compatible holders by approved identifiers; follow declared missing/conflict outcomes. |
| `name_binding` | Compare qualified candidate pairs using declared name/place evidence and population counts. |
| `exact_name_binding` | Use a supported exact key such as `name_id@1`, `name_place_id@1` or `issuer_symbol_id@1`; retain explicit holder scope and creation/review policy. |

| Function | Supported primitives |
| --- | --- |
| Determine kind from evidence | `evidence_present@1`, `field_in_set@1`, `token_match@1`, `token_match@2`, `values_overlap@1`, `name_shape@1`, `fields_all_empty@1` |
| Bind by approved identifier | `identifier_match@1`, `identifier_cardinality@1`, `kind_equal@1` |
| Qualified name-pair matching | `gleif_entity_eligible@1`, `holds_no_other_lei@1`, `waterfall_pass@1` — existing specialized compatibility operations, not universal fuzzy-matching primitives. |

Classification fragment within a rule's `steps` (the rule envelope, declared
source, emitted verdicts, proof and activation are separate):

```yaml
- step: "1"
  verdict: company
  when:
  - primitive: field_in_set@1
    args: {field: entity_type, values: [CORPORATION]}
- step: "otherwise"
  verdict: deferred
  otherwise: true
```

Steps are ordered; conditions within a step combine conjunctively. Prefer
configured value lists or separate steps where supported rather than inventing
an inline `OR`, SQL or arbitrary Python predicate.

Identifier-binding fragment, requiring an existing Identifier Contract for
`example_id` whose approved creating sources include `example.register.v1`:

```yaml
rule_id: example-issued-id
version: example-issued-id-v1
family: binding
source: example.register.v1
applies_to_verdict: company
emits: [bind]
on_no_match: mint
when:
- primitive: identifier_match@1
  args: {namespace: example_id}
- primitive: identifier_cardinality@1
  args: {namespace: example_id}
```

Identifier declarations under `rules/identifiers/` define shape, case,
stand-ins and optional check-digit family. Supported checksum families include
`mod 97-10`, `mod 11-2`, `mod 11-10`, `mod 37-36`, `luhn`, the three documented
letter/value Luhn variants, `damm`, and the documented weighted-sum family.
They supply a versioned identifier format and normalizer. Existing fixed
normalizers also cover conformed text, legal-form-preserving names and historical
identifier formats; aliases resolve to registered names, not arbitrary code.

Matching may bind a record, create under an allowed creation rule, wait or
raise review. Binding a record to a master, consolidating two existing masters
and choosing field winners are separate permissions. A lookup-only identifier
or name similarity never grants consolidation by itself.

References: [primitive registry](../edgar_warehouse/mdm/primitives.py),
[identifier declarations](../skills/data-onboarding/REFERENCE.md#identifier-types),
[mastering semantics](../skills/mdm-engineering/MASTERING-STANDARD.md).

## 10. Choosing field values: survivorship

A kind's source priority determines which eligible contribution fills each
field. It does not decide which records represent the same entity.

```yaml
# Fragment of rules/merge/kinds/<kind>.yaml:
defaults:
  sources: [example.register.v1, example.directory.v1]
  allow_unknown_effective: true
fields:
  address:
    sources: [example.directory.v1, example.register.v1]
    clear_sources: [example.directory.v1]
    max_age_days: 365
```

The register wins ordinary fields when it has eligible values; the directory
wins address under its override. Freshness and unknown-effective policy govern
eligibility. Only declared sources may clear a field. Conflicting alternatives
remain explainable beside the winning source.

Profile-field priorities and recorded steward overrides have separate inputs.
The owner recognizes `field_group`/`field_groups` as authority-bearing keys, but
that recognition alone does not prove an executed grouping behavior; this
primer does not present them as a qualified grouping feature. Use the
[field-rule owner](../crates/source-contract/src/field_values.rs) for exact shapes;
there is no arbitrary “most recent row always wins” rule.

## 11. Relationships, hierarchies and profiles

Adapter relationships declare type, endpoints/source keys, scope, dates and
properties. `each` repeats links; `find` locates related evidence. Optional
`ends`, `interval` and `status` rules control incomplete or invalid claims.
For capacity-based types, `on`, `held` and optional title produce dated sightings
that fold into periods. Role profiles carry role/authority/registration,
jurisdiction, dates and fields; they do not create new identities automatically.

The Mastering Policy pins the RDM `mdm-relationship-types` version. Its codes
govern allowed kinds/profiles, hierarchy/cycle behavior, one-parent constraints,
ultimate-parent and capacity semantics. A type declaration is not evidence that
a relationship exists.

Example fragment, assuming the type and both endpoint sources are configured:

```yaml
relationships:
- type: DIRECT_PARENT
  target_source: example.register.v1
  target_key: [parent_id]
  scope: Example ownership
  valid_from: relationship_start
  valid_to: relationship_end
  time_format: date
```

`DIRECT_PARENT` is illustrative, not a claim that this type code exists. Register
and approve an appropriate supported type before using it. Missing endpoints
and ambiguous dates remain explicit; do not guess them from a similar name.
Reference: [relationship mappings and type rules](../skills/data-onboarding/REFERENCE.md#relationship-types).

## 12. Workflow, Silver and metadata rules

These configure the platform around the expression engine:

- **Bookkeeping targets:** dependencies, units, inputs, execution profiles and
  domain checks connect registered workers. A typical shape is
  `source.read → source.combine → mdm.prepare → mastering.merge`, with Silver
  steps where required. Profiles/check names must exist in this build.
- **Source inputs:** receipt hashes, context and lookup receipts bind the exact
  evidence. Processing identity determines whether the Change Journal recognizes
  an unchanged input. A changed rule can require processing again.
- **Silver specifications:** declare table grain, key, exact types, master-link
  lookups and checks. They do not create MDM matching authority.
- **Reference pins:** select immutable published RDM code-set versions used by
  quality, matching, relationship and classification configuration.
- **Mapping Documents and catalog:** generated views explain rules, fields,
  quality requirements, pipelines and lineage. Editing catalog metadata does
  not change execution rules.

Use [Bookkeeping](../skills/bookkeeping/SKILL.md),
[Data Operations](../skills/data-operations/SKILL.md),
[the Silver specification procedure](../skills/data-onboarding/SKILL.md),
and [catalog guidance](../skills/data-catalog/SKILL.md) for their exact contracts.

## Validate before using an example

YAML uses the repository's JSON-compatible value rules: quote ambiguous values
and date strings, avoid duplicate keys, anchors and aliases, and use descriptive
versions. Native rule validation refuses unknown primitives and validates
unselected branches before execution. Missing data is not permission to suppress
a broken contract, corrupted input or resource-bound failure.

Start with invented local bytes and explicit expected outputs. Check the owning
contract, then generate/reconcile its Mapping Document, run the affected proof
and follow the existing approval/activation gates. This primer creates no new
rule or activation and authorizes no provider requests.

For existing-rule changes, follow
[MDM Engineering → refining rules](../skills/mdm-engineering/REFINING-RULES.md);
for a new feed, follow [Data Onboarding](../skills/data-onboarding/SKILL.md).
