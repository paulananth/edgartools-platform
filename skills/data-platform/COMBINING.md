# Combine configured readings

Use `source.combine` between configured reading and MDM preparation when
records need keyed collections or joins across captured artifacts. The worker
uses declared column names and immutable reading receipts; it has no loader,
provider, classification or database dependency.

## Inputs and configuration

A standalone input manifest is an object with `version: 1`, a `contract`
receipt (`uri`, `sha256`), and `readings`: a mapping from logical names to
reading receipts. Each receipt holds a version-1 inline or version-2 partitioned
configured reading. Partition receipts are authenticated within the same
aggregate input byte and row budgets as inline readings. Contiguous source
ranges, declared table names and EOF counts are checked before combining.
Original artifact/context receipts and row order are retained; storage
partitions do not create new source identities. Both forms supply tables and
an empty `deferred` list. Unresolved
reading deferrals block combination; resolve them explicitly before this step.

The contract is a JSON object with this shape (shown as YAML for review):

```yaml
execution: {profile: source.combine}
combine:
  max_rows: 100000
  groups:
    forms:
      source: references
      table: filings
      key: cik
      value: form
      mode: collect
      order_by: [form]
      distinct: true
      skip_null_values: true
      checks: {capture: approved-capture}
      where: {}
  tables:
    companies:
      source: primary
      table: companies
      checks: {capture: approved-capture}
      where: {}
      joins:
        forms: {group: forms, key: cik, on_missing: empty, replace: false}
```

All shown keys are required. Replace sample names, capture values and limits
with the measured feed's approved facts. Store the JSON contract as a pinned
artifact; this profile does not accept a YAML artifact. Its schema is separate
from the `source.read` contract. A Rules-approved pipeline pins both via its
frozen units.

- `source` is one declared reading name or an ordered list of 1–8 distinct
  declared names. Rows are traversed in that name order, then artifact and
  row order. Use a list to collect across separately verified readings.
- Logical names, tables, columns, groups and output fields use letters,
  digits and underscores, start with a letter or underscore, and have at
  most 64 characters.
- `checks` asserts exact JSON values on every row, **before** filtering or
  skipping null keys. A mismatch rejects the whole combination. `where`
  selects rows whose columns equal the declared exact values; `{}` selects
  all rows. Missing check/filter columns fail. Each mapping has at most
  32 entries.
- Group keys are exact text or integers, with no conversion: integer `1`
  and text `"1"` are different identities; boolean/structured keys fail.
  Null group keys are skipped. Group `value` is a column or `.` for the
  complete row. Missing columns fail. `skip_null_values` decides whether
  to skip null values; empty-string interpretation belongs in the reading
  contract (for example `text.null_if`), not the collector.
- `order_by` lists at most eight columns. Each must have one exact scalar
  type across selected group rows; nulls and mixed types fail. Sort is
  ascending and stable. An empty list retains reading artifact and row
  order. `collect` returns a list; `distinct: true` keeps the first occurrence
  of each exact JSON value after sorting. `first`/`last` select a single
  value; they require `distinct: false`.
- `collect_flat` requires list values and concatenates exactly one level.
  Nested lists and objects remain typed values. Distinct comparison uses exact
  canonical JSON, so false, integer zero and floating zero remain distinct.
  Null whole values obey `skip_null_values`; null items inside lists remain.
  Before deduplication, the total flattened element count across all selected
  keys in each group must not exceed `max_rows`. An empty list contributes no
  elements, while every duplicate still counts against this bound.
- Optional `sort_values: true` sorts the collected JSON values
  after flattening/deduplication. It is valid only for `collect` and
  `collect_flat`, and must be a boolean. Omission preserves existing value
  order; `order_by` still orders source rows before collection. Values must
  have one exact scalar type (text, integer, float or boolean), with no nulls;
  mixed types or structured values refuse. Sorting is natural within that
  type, so prefix form names sort as `S-8`, then `S-8 POS`.
- Joins preserve the base row and use the declared base key. `on_missing:
  empty` produces `[]` for either collection mode or null for first/last; `error` refuses
  an unmatched key (including null). Existing fields require `replace: true`
  to overwrite; with false, a collision rejects the combination.
- Bounds: 1–8 named readings, at most 32 groups, 1–16 output tables and
  at most 32 joins per output. Each reading is at most 32 MiB, all readings
  together at most 64 MiB, and input **and** output rows each respect
  `max_rows` (1–100,000). Counts include every input table. Combined output
  is at most 32 MiB. Partition work explicitly when a limit is exceeded;
  validation and output-budget failures occur before any destination write.

## One installed pipeline

For a predecessor reading, the combination unit's input is
`{"from": {"step": "read", "key": "<unit key>"}}`. Its frozen keys contain:

- `combine_contract_uri` and `combine_contract_sha256`: the contract receipt
  fields as nonempty text;
- `reading_name`: the name assigned to the resolved predecessor reading;
- Optional `readings_uri` and `readings_sha256` together: a pinned JSON mapping
  of up to seven additional names to reading receipts. Omit both when there
  are no additional readings. The predecessor name must not collide with an
  additional name. Every unit key value is nonempty text; receipts belong in
  pinned artifacts, rather than structured unit keys.

The combination worker materializes a content-addressed scope document under
`combine-inputs/` beside its output. This binds the contract and **all** reading
receipts. Its reading artifact's `input` points to that real document. A change
to a contract or auxiliary reading therefore changes downstream MDM input
identity; no receipt is invented for bytes at another URI. The verifier
rebuilds and verifies the scope document and exact combined output.

Declare step dependencies read → combine → prepare → merge. The combine step
uses operation `source.combine`, declares domain check `source.combined`, and
has its own output lease. Preparation takes the combine step's output through
its `from` reference. Use the same submitted run ID and, in dependency order:

```bash
edgar-warehouse workers work source.combine <run_id> --limit 100
edgar-warehouse workers verify source.combine <run_id> --reports <uri> --limit 100
```

Work uses the worker Bookkeeping login; verification uses the separate verifier
login. Repeat bounded work/verify until every combination unit verifies, then
continue preparation and merge. Finalize only after every declared step has
verified. Existing Rules proof and operator approval requirements apply.

## Qualification boundary

The installed PostgreSQL 16 combined-records trial reads two artifacts,
orders/deduplicates their aliases, combines them with the primary rows, then
prepares and merges them with independent verifiers and destination fencing.
It retains the original installed trials.

Company comparison tests qualify form/ticker collection and address selection
against the retained functions, including capture mismatch refusals. The
address values are explicit fixture inputs: **raw address derivation, census
joins, complete provenance and full Company mastering remain unqualified**.
This profile does not authorize deletion of retained Company/GLEIF readers or
activation of a source Rules version.

Offline evidence in [PR #819](https://github.com/paulananth/edgartools-platform/pull/819)
records exact recent-form comparisons on 1,000 distinct receipt-pinned main
captures (107,197 filing rows). This exercised source.read and source.combine
workers/verifiers directly, not the installed full Company pipeline. Its
`pagination_qualified` and `full_company_mastering` flags remain false.

`skip_empty_text: true` is optional for `collect` and `collect_flat` groups.
It excludes only the empty string. Whitespace, false, zero, empty lists/maps
and null retain their existing policies. The default is false. Flattened
input elements still count toward the declared budget before this exclusion
or deduplication. Use this with ranked catalog ticker collections to preserve
the landing rule that excludes empty ticker text without changing source ranks.
