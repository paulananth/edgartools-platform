# Research the path and expression syntax other engines use

Type: research
Status: resolved (2026-09-21)
Blocked by: none

## Question

Ticket 04 Q1 must pick how a Source Contract says where a value is in a
Bronze Artifact, and how it writes a transform. The operator's criteria
(2026-09-21): **easy to understand for a human reviewer and for an agent,
precise, easy to test, and the whole thing works with local files** — a
contract is a local file, edited and re-run locally against local Bronze
Artifacts and fixtures, with no service.

From primary sources (each tool's own documentation, specification or
source), compare at least:

- plain dotted paths: Kubernetes `fieldPath`, dbt / Soda / Great
  Expectations column references, Reltio attribute paths;
- Airbyte's declarative YAML connector (low-code CDK): `field_path`,
  record selector, transformations, interpolation, and its own tests;
- JSON Pointer (RFC 6901), JSONPath (RFC 9535), JMESPath, XPath;
- transform languages: jq, JSONata, Benthos/Redpanda Connect Bloblang,
  Vector VRL, JOLT.

Score each against the criteria:

1. **Readable**: can a reviewer tell what a line does without running it?
   One way to write each thing, or several?
2. **Agent-safe**: is there a formal specification, and is it widely known
   (so agents produce correct syntax rather than inventing it)?
3. **Precise**: is its behaviour fully specified — missing value, null,
   object-versus-list, XML attributes, ordering?
4. **Testable**: is there a conformance test suite or reference
   implementation; can a single line be unit-tested; how does it report an
   error (with a location)?
5. **Local-file friendly**: validates and runs offline from a file; editor
   support through JSON Schema; a Python implementation usable under `uv`.
6. **Fits this repo**: consistency with Clean MDM's `adapter` dotted paths
   (`edgar_warehouse/mdm/clean/adapters.py:33-39`), XML and JSON both,
   no logic hidden in strings (Q4's rule), strict YAML 1.2 (ticket 04 Q0).

End with a recommendation for (a) the path syntax, (b) how repeating groups
are written, and (c) how a transform is written (primitive-call style), each
with an example taken from Form 3/4/5 and GLEIF (see
[research/02](../research/02-parse-needs-inventory.md)).

## Answer

[research/10](../research/10-path-and-expression-syntax.md). Eleven syntaxes
scored against the six criteria. Recommended: **(a)** a restricted dotted
path — literal keys joined by `.`, no wildcard, index, filter, function or
quoting, enforced by a JSON Schema pattern — over one canonical tree (XML
text in `$`, attributes in `@name`, the shape GLEIF's JSON already has);
crossing a list mid-path is an error with an RFC 6901 location, and missing
is kept apart from `null`. **(b)** repeating groups only through an explicit
`each:` block (single object = one-item list, missing = zero rows, `where:
has:` before `ordinal`, `from: document` for outer values; `join:` with a
`parts:` list for aggregation). **(c)** one YAML mapping per column,
`primitive: {arguments}`, or a `steps:` chain; every path-reading primitive
takes an explicit `default:`; the C-J lookup is `lookup` + `ref` + `get`.
Rejected: jq, JSONata, Bloblang, VRL, JMESPath and Airbyte Jinja (logic in
strings), XPath (XML only), JSON Pointer for authoring (no groups);
JSONPath RFC 9535 held in reserve. **For Q0**: the declared PyYAML is a
YAML 1.1 parser, so strict YAML 1.2 needs ruamel.yaml (line/column API
unverified); a path starting with `@` must be quoted; `jsonschema` is only
a transitive dependency today.
