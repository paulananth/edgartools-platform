# Engine rules reference: the source-expression primitives

Each column expression of a `read` block is exactly one call, and calls can contain other calls. This file lists every call the source engine accepts. Examples are fragments to place beneath a column name; the [primer](engine-rules-primer.md) explains how reading, checks and lookups use them, and the engine's own [expression validator and evaluator](../crates/source-contract/src/lib.rs) owns every argument and limit.

## Read or construct a value

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

## Conditions

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

## Reference lookups and membership

| Primitive | Example fragment | Function |
| --- | --- | --- |
| `lookup` | `{lookup: {reference: statuses, column: label, key: {text: {path: status}}, on_missing: "null"}}` | Exact lookup in `read.references`; missing may return null or error. |
| `member` | `{member: {lookup: scope, key: {text: {path: id}}}}` | Boolean membership in a declared immutable set. |
| `member_value` | `{member_value: {lookup: aliases, key: {text: {path: id}}, on_many: error}}` | Return the unique value in a declared pair set; never choose an arbitrary ambiguous value. |
