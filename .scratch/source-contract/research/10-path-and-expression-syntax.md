# Research 10 — Path and expression syntax other engines use

Ticket: [10-research-path-and-expression-syntax](../issues/10-research-path-and-expression-syntax.md)
Map: [source-contract](../map.md) · Feeds: [ticket 04 Q1](../issues/04-decide-the-read-and-transform-primitives.md)
Date: 2026-09-21. Method: each tool's own specification, documentation, PyPI page or source repository (URLs below), plus this repo's code (`path:line`, relative to the repo root). No request was made to sec.gov, GLEIF or AWS. No code was run.
Where a source was checked but did not answer a question, this file says **unverified** instead of guessing.

## Summary

1. **(a) Path syntax — recommend our own restricted dotted path**, the same form Clean MDM's `adapter` already uses (`edgar_warehouse/mdm/clean/adapters.py:33-39`): literal keys joined by `.`, no wildcards, no filters, no functions, no quoting. It reads GLEIF's awkward keys as written (`LEI.$`, `Entity.LegalName.@xml:lang`), which JSONPath and JMESPath can only reach with bracket or quote escapes. XML is read through one declared XML-to-tree rule (text in `$`, attributes in `@name`, the convention the GLEIF JSON Golden Copy already uses), so **one path form covers XML and JSON**. Each dotted path has an exact RFC 6901 JSON Pointer twin, which the runner uses in error messages.
2. **(b) Repeating groups — recommend an explicit `each:` block, never a wildcard inside a path.** A single object always counts as a one-item list and a missing group gives zero rows (Airbyte's record selector does the same wrap). Filtering (`where: has:`) and `ordinal` are keys of that block. Aggregating a group into one string is a `join:` primitive with an `each:` argument.
3. **(c) Transform-call style — recommend one YAML mapping per column, `primitive: {arguments}`**, and a `steps:` list for chains. No expression language, no templates, no Jinja: every branch is a YAML key the JSON Schema can check. `default:` is required on every primitive that reads a path, because this repo uses three different "absent" values.
4. **Rejected as the authoring surface:** jq, JSONata, Bloblang, VRL, JOLT, JMESPath and Airbyte's Jinja interpolation (each puts logic inside a quoted string, against Q4's rule); full XPath (XML only, large, attributes not selectable in the Python standard library); JSON Pointer as the *authoring* form (no multi-value selection). JSON Pointer stays as the error-location format.
5. **Two findings for ticket 04 Q0:** PyYAML, the only YAML library the project declares (`pyproject.toml:22`), is "a complete YAML 1.1 parser" — it cannot give Q0's strict YAML 1.2; ruamel.yaml is a YAML 1.2 loader. And YAML 1.2 reserves `@`, so a path that **starts** with `@` (`"@id"`) must be quoted in the contract.

---

## 1. Scoring table

Scale per cell: **good / fair / poor**, with the reason. The six criteria are the ticket's (`issues/10-…md:29-42`).

| Candidate | 1 Readable | 2 Agent-safe (spec, well known) | 3 Precise (missing, null, object-vs-list, XML attrs, order) | 4 Testable (suite, per-line test, error location) | 5 Local-file / Python under `uv` | 6 Fits this repo |
|---|---|---|---|---|---|---|
| **Plain dotted paths** (K8s `fieldPath`, dbt/Soda/GX column names, Reltio, Clean MDM `value()`) | good: one way to write a path | fair: no shared spec; each tool defines its own small form | fair: whatever we write down; Clean MDM's form silently returns `None` at a list | good: trivially unit-tested; errors are ours to shape | good: no library needed | **good**: identical to `adapter` paths |
| **Airbyte** `field_path` + record selector + Jinja | fair: path is clear, Jinja strings are not | fair: schema published, Jinja is well known but Airbyte's variables are product-specific | fair: `*` iterates, single object wrapped as a list; Jinja semantics are Python's | fair: acceptance tests run a Docker image; no per-line test | poor: needs the Airbyte CDK | poor: logic in Jinja strings breaks Q4 |
| **JSON Pointer** (RFC 6901) | good: one spelling | good: IETF standard | good for one value; no wildcard; error handling left to the application | good: `jsonpointer` package; used by JSON Schema errors | good: `jsonpointer` 3.1.1 | fair: `/a/b` differs from `a.b`; no repeating groups |
| **JSONPath** (RFC 9535) | fair: several spellings (`.a`, `['a']`) | good: IETF standard | good: nodelists, null ≠ missing, no auto-wrap, object order unspecified | **good**: official Compliance Test Suite | good: `jsonpath-rfc9535` 1.0.0, tested against the suite | fair: `$`, `@xml:lang` need bracket quoting; JSON only |
| **JMESPath** | fair: projections and pipes need study | good: spec + compliance tests; widely known (AWS CLI) | fair: missing and null both `null`; projections silently drop nulls | good: `jmespath.test` suite; `ParseError` gives a column | good: `jmespath` 1.1.0 already in `uv.lock` (via botocore) | poor: quoting for `$`/`@…`; logic in strings |
| **XPath** (W3C 3.1; stdlib ElementTree subset) | fair: well known for XML, verbose | good: W3C Recommendation | good for XML: empty sequence, document order, `@attr` | fair: W3C error codes; stdlib subset has no error codes | fair: stdlib subset, or `elementpath` 5.1.4 | poor: XML only; stdlib cannot return attributes |
| **jq** | poor: dense pipelines | fair: manual only, no separate spec | fair: `.foo` on an array is an error; `//` treats `false` as absent | fair: CLI-testable; no conformance suite found | fair: `jq` 1.12.0 wraps C jq | poor: a program in a string |
| **JSONata** | fair | fair: docs only; reference implementation in JS | fair: singleton sequences unwrap, missing gives "nothing" | fair: Python port reuses the JS test repo | fair: `jsonata-python` 0.7.0 (pre-1.0) | poor: a program in a string; JSON only |
| **Bloblang** (Redpanda Connect) | fair | poor: product docs only | fair: explicit `catch`/`or` | fair: Redpanda Connect unit tests | poor: Go only (no Python implementation found) | poor |
| **VRL** (Vector) | good for code | poor: product docs only | good: fallible calls must be handled at compile time | fair: Vector config tests | poor: Rust; no Python implementation found (**unverified** beyond the docs) | poor |
| **JOLT** | poor: specs are JSON trees with `&`/`@` symbols | poor: javadoc and tests only | fair: `cardinality` handles ONE/MANY | fair: unit-test examples | poor: Java only | poor |

---

## 2. Per-tool notes, with sources

### Plain dotted paths

- **Kubernetes `fieldPath`** is written `metadata.name` or `metadata.labels['<KEY>']`, but it is **a fixed list of supported fields, not a general path language** ([Downward API](https://kubernetes.io/docs/concepts/workloads/pods/downward-api/), "Available fields"). Lesson: a small, closed form is enough when the host system defines what can be reached.
- **dbt** declares columns as `columns: - name: <column_name>` with an optional `quote:` flag; the page shows no nested-field syntax ([dbt columns](https://docs.getdbt.com/reference/resource-properties/columns)).
- **Soda** (v4 contracts) declares `columns: - name: …`; nested JSON/STRUCT values are reached with `column_expression:` in **the warehouse's own SQL dialect** (example `employee.data->>'id'`), and "Soda does not normalize SQL syntax across data sources" ([Soda contract language reference](https://docs.soda.io/reference/contract-language-reference), "Column expression").
- **Great Expectations** passes a plain column name: `ExpectColumnValuesToNotBeNull(column="transfer_amount")` ([GX missingness](https://docs.greatexpectations.io/docs/reference/learn/data_quality_use_cases/missingness/)); no nested path shown.
- **Reltio** filters use "a dot-delimited path to the property", e.g. `attributes.Name`, `attributes.Education.Degree`, with functions `equals(…)`, `missing(…)`, `exists(…)` ([Reltio filtering entities](https://docs.reltio.com/en/developer-resources/entity-management-apis/entity-management-apis-at-a-glance/entities-api/get-entity/filtering-entities)).
- **Clean MDM** (this repo): `value(row, path)` splits on `.`, walks dicts, and returns `None` when it meets anything that is not a dict, including a list (`edgar_warehouse/mdm/clean/adapters.py:33-39`). Live paths: `"_origin.sha256"`, `"last_sync_run_id"` (`edgar_warehouse/mdm/clean/company_source.py:54-58`).

What they share: the reviewer reads a column name or a short dotted path, and nothing else. None of them defines repeating groups in the path; data-quality tools work on flat tables.

### Airbyte declarative (low-code) connectors

- `field_path` is "a list of strings"; `*` iterates array elements; "if the path resolves to a single object rather than an array, that object gets wrapped in an array" ([record selector](https://docs.airbyte.com/platform/connector-development/config-based/understanding-the-yaml-file/record-selector)). Navigation uses the `dpath` library (same page).
- `record_filter` and `AddFields` use **Jinja2** strings such as `"{{ record['created_at'] < stream_slice['start_time'] }}"` (same page; [string interpolation](https://docs.airbyte.com/platform/connector-development/config-based/advanced-topics/string-interpolation)). The interpolation page says nothing about sandboxing (**unverified** either way).
- The manifest is validated against a published JSON Schema, `declarative_component_schema.yaml` ([YAML reference](https://docs.airbyte.com/platform/connector-development/config-based/understanding-the-yaml-file/reference)).
- Tests: unit, integration and connector-agnostic acceptance tests; the acceptance suite "runs its tests against the connector's Docker image" with `acceptance-tests-config.yml` and pytest ([Testing connectors](https://docs.airbyte.com/platform/connector-development/testing-connectors)). There is no documented way to test one mapping line alone.

Take from Airbyte: the path as data, the explicit single-object-to-list rule, and a published JSON Schema. Leave: Jinja in strings.

### JSON Pointer — RFC 6901

- Syntax: "a sequence of zero or more reference tokens, each prefixed by a '/'"; `~` is written `~0` and `/` is written `~1` ([RFC 6901 §3](https://www.rfc-editor.org/rfc/rfc6901#section-3)).
- Array tokens are digits without leading zeros, or `-` for "after the last element" ([§4](https://www.rfc-editor.org/rfc/rfc6901#section-4)).
- If a reference does not resolve, "evaluation … fails"; the RFC "does not define how errors are handled" ([§4, §7](https://www.rfc-editor.org/rfc/rfc6901#section-7)).
- **No wildcard and no multi-value selection** — so it cannot express a repeating group.
- Python: `jsonpointer` 3.1.1 (Mar 2026, BSD, Production/Stable) ([PyPI](https://pypi.org/project/jsonpointer/)).
- It is also the location format of JSON Schema tooling: Python `jsonschema` errors carry `path`/`absolute_path` ("the path to the offending element within the instance"), `json_path`, `schema_path` and `validator` ("the name of the failed keyword") ([jsonschema errors](https://python-jsonschema.readthedocs.io/en/stable/errors/)).

### JSONPath — RFC 9535

- Results are nodelists; a valid query never errors at run time: "A syntactically valid segment MUST NOT produce errors when executing the query" ([RFC 9535 §2.3.1.2](https://www.rfc-editor.org/rfc/rfc9535#section-2.3.1.2)). No match gives an empty nodelist.
- "JSON null is treated the same as any other JSON value, i.e., it is not taken to mean 'undefined' or 'missing'" ([§2.6](https://www.rfc-editor.org/rfc/rfc9535#section-2.6)).
- No auto-wrap: indexing a non-array selects nothing.
- Object wildcard order is not stipulated "since JSON objects are unordered" ([§2.3.2.2](https://www.rfc-editor.org/rfc/rfc9535#section-2.3.2.2)); array order is kept.
- Five functions only: `length`, `count`, `match`, `search`, `value`, with a well-typedness check ([§2.4](https://www.rfc-editor.org/rfc/rfc9535#section-2.4)).
- Shorthand names must start with a letter, `_` or non-ASCII (`member-name-shorthand = name-first *name-char`, [§2.5.1.1](https://www.rfc-editor.org/rfc/rfc9535#section-2.5.1.1)). So GLEIF's `$` and `@xml:lang` need `$.LEI['$']` and `$.Entity.LegalName['@xml:lang']`.
- JSON only; XPath is cited as inspiration.
- **Compliance Test Suite**: `cts.json` built from `tests/`, with a `cts.schema.json`, testing RFC 9535 ([jsonpath-compliance-test-suite](https://github.com/jsonpath-standard/jsonpath-compliance-test-suite)). Test count and the list of passing implementations: **unverified** (not on the page).
- Python: `jsonpath-rfc9535` 1.0.0 (Nov 2025, MIT, Production/Stable): "We follow RFC 9535 strictly and test against the JSONPath Compliance Test Suite" ([PyPI](https://pypi.org/project/jsonpath-rfc9535/)). It raises `JSONPathSyntaxError`; whether it carries a position is **unverified**.

### JMESPath

- A missing identifier returns `null`; slicing a non-array returns `null` ([spec](https://jmespath.org/specification.html), "Identifiers", "Slices"). So **missing and null are the same**.
- Projections: "if any subsequent expression after a wildcard expression returns a null value, it is omitted from the final result list" (spec, "Wildcard Expressions"). A projection over owners would silently lose rows with no value, which would shift an `ordinal`.
- Pipes stop projections (spec, "Pipe Expressions"). A fixed built-in function list (`abs` … `values`); no user-defined functions in the spec. Order of `values()`/object wildcards is undefined.
- Identifiers that do not match `[A-Za-z_][A-Za-z0-9_]*` "must be quoted" (spec, "Identifiers" ABNF): GLEIF paths become `LEI."$"`, `Entity.LegalName."@xml:lang"`.
- Errors: `syntax`, `invalid-type`, `invalid-value`, `unknown-function`, `invalid-arity`; the spec does not require a location.
- Compliance tests: [jmespath/jmespath.test](https://github.com/jmespath/jmespath.test) (`given` / `cases` / `expression` / `result` or `error`).
- A community fork adds `let`, arithmetic and ternaries through JEPs and "is not a formal standard" ([jmespath-community/jmespath.spec](https://github.com/jmespath-community/jmespath.spec)) — so agents may produce syntax that one library accepts and another rejects.
- Python: `jmespath` 1.1.0 (Jan 2026, MIT, maintained by aws/jamesls), ships `tests/compliance`, supports custom functions ([PyPI](https://pypi.org/project/jmespath/)). `ParseError` prints "Parse error at column %s, token …" ([exceptions.py](https://raw.githubusercontent.com/jmespath/jmespath.py/develop/jmespath/exceptions.py)). In this repo it is **only a transitive dependency** of botocore (`uv.lock:13`, package at `uv.lock:1177`), not a declared one.

### XPath (W3C) and Python's ElementTree subset

- XPath 3.1 is a W3C Recommendation of 21 March 2017 ([XPath 3.1](https://www.w3.org/TR/xpath-31/)). Paths return sequences in document order; no match is the empty sequence; `@name` abbreviates the attribute axis (§3.3.5). Errors have codes `err:XPST…` (static), `XPDY…` (dynamic), `XPTY…` (type) (§2.3). An element's string value is defined by the XDM data model, which this file did not fetch (**unverified** wording).
- Python's `xml.etree.ElementTree` offers "limited support for XPath expressions … a full XPath engine is outside the scope of the module". Its `find`/`findall` **return elements only**; attributes are read with `Element.get()` ([ElementTree docs](https://docs.python.org/3/library/xml.etree.elementtree.html), "XPath support").
- The ownership parser uses exactly that subset: `root.findall("./reportingOwner")` (`edgar_warehouse/parsers/ownership.py:88`), `fn.get('id', '')` for `@id` (`:85`, `:307`), and "all descendant text" through `itertext()` (`:283-289`).
- Full XPath in Python: `elementpath` 5.1.4 (Aug 2026, MIT) — XPath 1.0 to 3.1 over ElementTree or lxml ([PyPI](https://pypi.org/project/elementpath/)). Its README does not state a W3C QT3 test-suite result: **unverified**, not assumed.

### jq

- `.foo` gives the value "or null otherwise"; on an array it errors ("Cannot index array with string"); `?` is `try`; `a // b` treats both `false` and `null` as absent ([jq manual](https://jqlang.org/manual/)). The `//` rule would turn a real `false` flag into a default.
- No separate specification is referenced; no XML.
- Python: `jq` 1.12.0 (Jul 2026, BSD-2), bindings to C jq 1.8.2 ([PyPI](https://pypi.org/project/jq/)).

### JSONata

- "a lightweight query and transformation language for JSON data. Inspired by the 'location path' semantics of XPath 3.1" ([overview](https://docs.jsonata.org/overview)). No formal spec is referenced beyond the docs.
- A path to nothing gives "nothing"; a single value "is treated as equivalent to an array containing that single value" ([path operators](https://docs.jsonata.org/path-operators)). This auto-unwrap is convenient but hides the object-or-list difference.
- Python: `jsonata-python` 0.7.0 (Jul 2026, Apache-2.0), a port of the reference implementation that uses the reference test repo as a submodule ([PyPI](https://pypi.org/project/jsonata-python/)). Pass count: **unverified**.

### Bloblang (Redpanda Connect)

- "a language designed for mapping data of a wide variety of forms"; assignments look like `root.foo = this.bar…`; errors are recovered with `catch`, nulls with `or` ([Bloblang about](https://docs.redpanda.com/redpanda-connect/guides/bloblang/about/)).
- Tested with Redpanda Connect unit tests or `rpk connect blobl`. The page mentions only a Go API; no Python implementation was found.

### VRL (Vector Remap Language)

- "VRL programs are fail safe, meaning that a VRL program won't compile unless all errors thrown by fallible functions are handled" ([VRL reference](https://vector.dev/docs/reference/vrl/)). This is the strongest error design seen, but it lives in Rust inside Vector; the docs describe no Python implementation.

### JOLT

- "JSON to JSON transformation library written in Java where the 'specification' for the transform is itself a JSON document"; transforms `shift`, `default`, `remove`, `sort`, `cardinality` (ONE/MANY) ([bazaarvoice/jolt](https://github.com/bazaarvoice/jolt)). The rules are documented in javadoc and tests, not a spec. Java only.

---

## 3. Missing value, null, object-versus-list, XML attributes

This repo already has **three different "absent" results** for Form 3/4/5 (research 02, A.2 finding 2):

- absent text gives `""` (`ownership.py:283-289`);
- absent numbers and dates give `None`;
- absent flags give `False` (`:314-317`);
- `officer_title` gives `None` through `or None` (`:123`).

GLEIF uses `None` everywhere (research 02, B.2).

| Candidate | Missing key | JSON `null` | Single object where a list is expected | XML attributes |
|---|---|---|---|---|
| Clean MDM `value()` | `None` | `None` (same as missing) | `None` at any list (`adapters.py:36-37`) | n/a |
| Airbyte `field_path` | not stated on the page | not stated | **wrapped in a list** | n/a |
| JSON Pointer | evaluation fails; handling is up to the application | a value | n/a (no multi-select) | only as a key such as `/@id` |
| JSONPath | empty nodelist | a value, distinct from missing | no wrap; array selectors select nothing | only as a key (`['@id']`) |
| JMESPath | `null` | `null` (same) | index on non-list gives `null`; projections drop nulls | only as a quoted key |
| XPath | empty sequence | n/a | n/a (element sequences) | `@id`, native |
| jq | `null`; error on an array | `null`; `//` also treats `false` as absent | error without `?` | n/a |
| JSONata | "nothing" | a value | **auto-wrap / unwrap** | n/a |

Conclusions:

- **No candidate matches the repo's per-type defaults.** So every primitive that reads a path needs an explicit `default:`, as research 02 already said. The engine must keep "missing" and JSON `null` apart internally (RFC 9535's rule), and let `default` apply to missing only.
- **Object-or-list must be decided outside the path.** GLEIF's `gleif:Geocoding` is an object in about 57 records and a list in 48 (research 02, B.1). Airbyte and JSONata wrap; JSONPath and JMESPath do not. The contract should wrap, always, in one place: the `each:` block.
- **XML attributes only exist natively in XPath.** Every JSON language sees them only if the reader turns them into keys. GLEIF's JSON Golden Copy already does this: text in `"$"`, attributes in `"@name"` (research 02, B.0). BadgerFish is the common name for this convention; its original site was not checked, so no standard is claimed for it here.

---

## 4. Recommendations

### (a) Path syntax: restricted dotted path over one canonical tree

**Rule.** A path is literal keys joined by `.`. No wildcard, no index, no filter, no function, no quoting. The JSON Schema enforces it with a pattern such as `^[^.\s]+(\.[^.\s]+)*$`. A key that contains a dot is not supported; if a source ever needs one, that is a versioned spec change, not a second spelling.

**Same form as Clean MDM**, with two stricter rules for the read step:

- reaching a list in the middle of a path is an **error with a location** ("path crosses a repeating group; use `each`"), not a silent `None` as in `adapters.py:36-37`;
- missing and JSON `null` are kept apart; `default:` applies only to missing.

**Same form, different tree.** The `adapter`'s `value()` walks one **flat silver row** (live paths `_origin.sha256`, `last_sync_run_id`, `company_source.py:54-58`). The read paths walk the **Bronze Artifact tree**. That is why the adapter never needs `each`, and why research 02 (B.2, last paragraph) makes a flat silver table the thing that lets the unchanged adapter work. "Same form" means the same spelling rules, not the same paths.

**XML becomes the same tree.** The `xml` reader turns each element into an object:

- text goes in `$`;
- attributes go in `@name`;
- a child that appears once is an object, and one that repeats is a list, in document order;
- declared namespace prefixes are kept as `prefix:Name`, matching GLEIF's `gleif:Geocoding`.

So `ownershipDocument` and the GLEIF JSON are read with the same path form. The one XML-specific need is edgartools' "all descendant text" (`ownership.py:283-289`, used for `footnote` text at `:85`). That is a **primitive** (`text_all`), not a path feature. It needs the reader to keep child order, which the rule above does.

**Error location** uses RFC 6901: `a.b.$` is reported as `/a/b/$` in the data, next to the contract's own line and JSON Schema keyword (`jsonschema`'s `absolute_path` and `validator`). This serves acceptance check 9 ("names the line and rule").

Examples (from research 02):

```yaml
# Form 3/4/5 — XML, relative to one <reportingOwner>
owner_cik:      { int:  { path: reportingOwnerId.rptOwnerCik.$, default: null } }
owner_name_raw: { text_all: { path: reportingOwnerId.rptOwnerName, default: "" } }
is_director:    { flag: { path: reportingOwnerRelationship.isDirector.$, true_set: ["1", "Y", "true", "True", "TRUE"], default: false } }

# GLEIF Level 1 — JSON Golden Copy
lei:                 { text: { path: LEI.$, default: null } }
legal_name_language: { text: { path: Entity.LegalName.@xml:lang, default: null } }
conformity_flag:     { text: { path: Extension.gleif:conformity.gleif:conformityflag.$, default: null } }
```

YAML note: `@` is a reserved indicator in YAML 1.2 ([spec §5.3](https://yaml.org/spec/1.2.2/#53-indicator-characters)), so a plain scalar cannot **start** with it. `Entity.LegalName.@xml:lang` is fine; a path that is only `@id` must be written `"@id"`. The JSON Schema error for this case should say so.

### (b) Repeating groups: an explicit `each:` block

**Rule.** A table's row source is `each: <path>`:

- a single object counts as a one-item list;
- a missing group gives zero rows;
- `where: { has: [...] }` filters items before `ordinal` is numbered;
- paths inside the block are relative to the item;
- a value from outside the item is reached with `from: document`.

Aggregating a group into one value uses `join:` with its own `each:`. The output text is built from a `parts:` list, not a template string.

```yaml
# Form 3/4/5 — one row per kept nonDerivativeTransaction (research 02, A.1)
sec_ownership_non_derivative_txn:
  each: nonDerivativeTable.nonDerivativeTransaction
  where: { has: [transactionAmounts, ownershipNature, postTransactionAmounts] }
  columns:
    txn_index:             { ordinal: {} }                       # 1-based, after `where`
    owner_index:           { const: { value: 1 } }
    reporting_owner_count: { count: { each: reportingOwner, from: document } }
    transaction_shares:    { number: { path: transactionAmounts.transactionShares.value.$, default: null } }  # reads <value> only; today's code reads all descendant text (ownership.py:283-289) — a deliberate change, pinned by a test
    transaction_date:      { date_prefix: { path: transactionDate.value.$, default: null } }

# Form 3/4/5 — document footnotes joined onto each owner row: "[F1] text | [F2] text"
filing_footnote_text:
  join:
    each: footnotes.footnote
    from: document
    parts: [ { const: { value: "[" } }, { text: { path: "@id", default: "" } }, { const: { value: "] " } }, { text_all: { path: ".", default: "" } } ]
    separator: " | "
    default: ""

# GLEIF — object-or-list address lines, joined
legal_address_additional_lines:
  join:
    each: Entity.LegalAddress.AdditionalAddressLine
    parts: [ { text: { path: $, default: "" } } ]
    separator: "\n"
    default: null
```

The `"."` path means "the item itself". It is the one reserved path value and should appear in the JSON Schema as an explicit `const`, not as a pattern exception.

Why not `nonDerivativeTable.nonDerivativeTransaction[*]` in the path? Because then the row grain, the filter and the ordinal rule are hidden inside one string. JMESPath shows the danger: its projections drop nulls, which silently changes positions. Research 02 (A.1) already shows `txn_index` depends on the filter (test `tests/unit/test_ownership_parser.py:554`).

### (c) Transform-call style: `primitive: {arguments}` and `steps:`

**Rule.** A column is one of two forms:

- a single call, `name: { <primitive>: { <arguments> } }`;
- a chain, `name: { steps: [ <call>, <call>, … ] }`, where each step after the first takes the previous value as input.

Primitive names and arguments are closed enums in the JSON Schema, so an unknown primitive or a misspelled argument fails validation with a line and keyword. How versions are written (`name@version`) is ticket 04's decision and is left out of these examples.

```yaml
# Form 3/4/5 officer_title (research 02, A.2): text; if it contains "see remarks", use the remarks; "" → null
officer_title:
  steps:
    - text: { path: reportingOwnerRelationship.officerTitle.$, default: "" }
    - when: { contains: "see remarks", ignore_case: true,
              then: { text: { path: remarks.$, from: document, default: "" } } }
    - empty_to_null: {}

# Form 3/4/5 address_is_care_of: text → upper → strip spaces → starts with "C/O"
address_is_care_of:
  steps:
    - text: { path: reportingOwnerAddress.rptOwnerStreet1.$, default: "" }
    - upper: {}
    - strip_spaces: {}
    - starts_with: { value: "C/O" }

# Form 3/4/5 security_title: SEC's "<value> [F1,F2]" convention as one named primitive
security_title: { value_with_footnotes: { path: securityTitle, default: "" } }

# GLEIF timestamp
initial_registration_date: { timestamp: { path: Registration.InitialRegistrationDate.$, default: null } }
```

There is no string that the engine must parse as code. `contains: "see remarks"` is a literal, and the branch is the `when` key.

**Cross-source lookup (rule C-J, 9 of 58 Form 3/4/5 columns).** `lookup` returns a record `{found, artifact_sha256, payload}` (research 02, A.3). It is declared once as a row-level value, and columns read it through `ref:` plus `get:`/`len:`. The `path:` inside `get:` is **the same dotted path language**, walking the lookup's result record instead of the artifact. It is still one path form, and "which tree" is always named by the step before it (`ref:`), never by a prefix in the path string.

```yaml
lookups:
  owner_submissions: { lookup: { source: submissions_main, key: owner_cik, key_format: cik10, select: newest, missing: null } }
columns:
  owner_submissions_present: { steps: [ { ref: { lookup: owner_submissions } }, { get: { path: found, default: false } } ] }
  owner_submissions_sha256:  { steps: [ { ref: { lookup: owner_submissions } }, { get: { path: artifact_sha256, default: "" } } ] }
  owner_entity_type:         { steps: [ { ref: { lookup: owner_submissions } }, { get: { path: payload.entityType, default: "" } } ] }
  owner_ticker_count:        { steps: [ { ref: { lookup: owner_submissions } }, { len: { path: payload.tickers, default: 0 } } ] }
```

`select: newest` copies today's behaviour. Whether it becomes `as_of(...)` is research 02's open point 1, not decided here.

### How each line is tested

- **One fixture, one expected row.** A parse test case names a committed fixture artifact (a trimmed Form 4 XML, or a 2-record GLEIF JSON) and the expected row for the columns it checks. The runner evaluates each column's call alone, so a failure names the column, its contract line and expected versus actual (acceptance check 9).
- **Per-primitive tests live in the engine**, once: each primitive gets a table of (input value, arguments, expected output). The contract tests only choices that belong to the source: paths, defaults and group filters.
- **Pin the traps with test cases.**
  - One GLEIF record where `AdditionalAddressLine` is a single object and one where it is a list.
  - One Form 4 with a transaction that the `where:` filter drops, so `txn_index` stays 1-based after the filter.
  - One `transactionShares` element with a `footnoteId` child. Research 02 (A.2 finding 1) shows `value.$` and all-descendant-text differ only when `footnoteId` has text.
- **Error cases are tests too.** A wrong path must produce the error "path crosses a repeating group" with the RFC 6901 location and the contract line. A test asserts that message.

### The local edit → re-run loop

1. Edit `sources/<source>/contract.yaml` in an editor. The editor validates it against the published JSON Schema while typing; yaml-language-server takes a `# yaml-language-server: $schema=<path>` modeline, supports JSON Schema drafts 04 to 2020-12, and defaults to YAML 1.2 ([yaml-language-server](https://github.com/redhat-developer/yaml-language-server)).
2. Run one local command (acceptance check 8), e.g. `uv run <runner> check sources/<source>`. It:
   - loads the file as strict YAML 1.2;
   - validates it against the JSON Schema;
   - runs the parse cases against the committed fixtures;
   - prints any failure as `contract.yaml:LINE  <column>  <rule>` followed by expected and actual values.
3. Nothing leaves the laptop: the fixtures and the bronze files are local files, and the runner refuses network access (acceptance check 4).

Python pieces that fit this loop:

- `jsonschema` is resolved in `uv.lock` (4.26.0 at `uv.lock:1186`), but only through altair (`uv.lock:154`), not as a declared dependency.
- The YAML loader must give line numbers for check 9. PyYAML nodes carry `start_mark` line and column ([PyYAML docs](https://pyyaml.org/wiki/PyYAMLDocumentation)), but see risk 1 below.
- The XML reader can stay on the standard library ElementTree the parser uses today (`ownership.py:37`); no XPath engine is needed, because paths run over the canonical tree.

---

## 5. Risks, and what is rejected and why

### Risks

1. **YAML 1.2 versus the declared loader.** PyYAML is "a complete YAML 1.1 parser" ([PyYAML](https://pyyaml.org/wiki/PyYAML)), and it is the only YAML library in `pyproject.toml:22`. Ticket 04 Q0 requires strict YAML 1.2. ruamel.yaml "is a YAML 1.2 loader/dumper package" (0.19.1, Jan 2026, single maintainer) ([PyPI](https://pypi.org/project/ruamel.yaml/)). Its line and column API was not confirmed from that page (**unverified**). Ticket 04 must pick the loader. Strict 1.2 also limits **key** spelling: an unquoted key `true`, `false` or `null` resolves to a non-string and cannot become a canonical-JSON object key. So argument names such as `true_set` must never be bare YAML keywords, and the JSON Schema should reject them.
2. **Our own path form has no external spec.** Agents know JSONPath and JMESPath better than "our dotted path". Two things limit this risk: the form is tiny (a key list joined by dots), and the JSON Schema pattern rejects `[`, `*`, `?` and `|`, so an invented JSONPath habit fails validation at once instead of misreading data.
3. **The XML-to-tree rule is ours.** Mixed content (text between child elements) loses its interleaving in `$`. SEC ownership values are leaf text, and `text_all` covers the footnote case (`ownership.py:85`). A source with real mixed content would need a custom step or a new primitive. Namespaces need a declared prefix map in the reader.
4. **Single-versus-list in XML is invisible to the tree.** An element that appears once becomes an object. That is why `each:` always wraps, and why no path may cross a list.
5. **Verbosity.** The `parts:` and `steps:` forms are longer than `"[{@id}] {$}"` or a jq pipe. This is accepted on purpose: each part is checked by the schema, and each can be tested.

### Rejected

- **jq, JSONata, Bloblang, VRL, JMESPath and Airbyte Jinja as the authoring surface.** Each writes branching and computation inside a quoted scalar. JSON Schema cannot check what that string does. That breaks Q4's "no logic hidden in strings" and weakens check 9's "names the line and rule". Some also have local reasons:
  - Bloblang, VRL and JOLT have no Python implementation.
  - jq's `//` treats `false` as absent.
  - JMESPath projections drop nulls.
  - The JMESPath community fork makes its syntax ambiguous for agents.
- **XPath** (full, or the ElementTree subset). It is XML only, so GLEIF JSON would need a second path language. The standard library cannot return attributes as results. Full XPath adds a large engine (`elementpath`) whose conformance claim is unverified.
- **JSONPath (RFC 9535)** as the authoring form. It is the best-specified candidate: an IETF standard, a compliance suite, and a strict Python implementation. But GLEIF keys need bracket quoting (`$.LEI['$']`), it has two spellings for every step, and wildcards would bring repeating groups back into strings. **Keep it in reserve**: if a later source needs a real filter inside a path, RFC 9535 is the standard to adopt, not an invented extension.
- **JSON Pointer** as the authoring form. It has no multi-value selection (RFC 6901), and `/a/b` differs from the `adapter`'s `a.b`. It is kept as the error-location format, because JSON Schema tooling already reports locations that way.
- **Airbyte's list-of-segments path** (`["data", "*", "record"]`). It is precise, but it is a second way to write what `adapter` writes as `a.b.c`, and its `*` puts groups back into the path.
