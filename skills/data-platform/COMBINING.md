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

### Incremental authenticated traversal

For reductions that must traverse partitioned readings without retaining all
decoded rows, the runtime supplies `source_readings.iter_load(receipt,
artifacts, max_bytes=..., max_rows=...)`. It yields a header, original artifact
index, one artifact chunk and cumulative bytes. The header names `version`,
the original `reading` receipt and, when present, its `contract` receipt.
An inline reading yields one chunk per original artifact (one or two). A partitioned
reading retains its input/context/lookup receipts and current `partition`
range/receipt on each chunk; its tables contain only that partition's rows.
The header's reading receipt binds the complete index, including all partition
receipts. Consumers must bind that original receipt into reduction identity.
An empty
source still yields its original identity and declared empty tables.
Its partition marker is null; inline events have no partition marker.
Yielded metadata is isolated from private traversal: editing returned evidence
cannot change a later authenticated receipt or declared schema.

The incremental index is bounded to 32 MiB and each partition to 8 MiB.
The materializing loader retains its caller's existing index limit. Explicit byte and
row budgets apply across every table, deferral, partition and artifact.
Complete contiguous range and EOF accounting are checked before traversing
an artifact's content. Each partition's exact hash, byte count and schema are
checked before its rows are yielded. Iteration must finish successfully before
publishing anything: later corruption can invalidate an already yielded
private prefix. Closing or abandoning an iterator is not successful EOF.
Consumers must resolve deferrals and explicitly opt in to lookup receipts
only when all those receipts participate in output identity.

The iterator supplies traversal. Use a declared reduction contract for
complete-set aggregation. The existing `combine` contract below retains its
original materializing row/byte limits.

### Bounded complete-set reduction

Use `execution: {profile: source.combine}` and `reduce` in place of `combine`.
Pin the contract as JSON and use the same input manifest and verification check.
Declare all limits: `max_rows` (1..40,000,000), `max_input_bytes`
(1..16 GiB), `max_state_bytes` (1..256 MiB), `max_keys` and `max_members`
(each 1..10,000,000), `max_output_rows` (1..100,000), and
`max_output_bytes` (1..32 MiB). Choose measured limits for the approved scope.
Input limits cover every supplied reading, artifact, partition and table,
including unselected rows. State limits cover all groups together. State bytes
measure canonical UTF-8 key/member/value payload; key/member counts separately
bound Python object overhead. They are not an RSS measurement or disk spill.

`groups` names 1..32 output tables. Each group requires one declared `source`,
`table` (one name or an ordered list of 1..8 distinct names), `keys`
(1..8 distinct text columns), `mode`, `count` (new output
column), `sample` and `sample_limit` (0..1,000). Text keys are exact; missing,
null and nontext values refuse. Normalize them in the reading contract.

- `mode: count` counts every selected row, including duplicates; require
  `sample: null` and `sample_limit: 0`.
- `mode: members` requires `member`, a text column, and a distinct named
  `sample` column. Count unique members per key. Optional `last` names a text
  column retained from the last source occurrence of that specific key/member,
  including empty text. It is neither a maximum nor a global member timestamp.
  Optional `last_null` explicitly replaces null with the declared text; missing
  columns and other nontext values still refuse.
  Multiple tables share the same member set and traverse declared table order
  within each artifact chunk. Duplicate membership across tables counts once.
  `last` requires one table: unions lack original source ordinals, so a last
  occurrence across tables could otherwise depend on partition boundaries.
- Optional `exclude` names another member group with identical key columns
  and no exclusion of its own. Subtract its complete member set after all
  inputs finish. Counts remain uncapped; samples contain the lexically first
  `sample_limit` surviving members. Sample objects retain the declared member
  and optional last column names. Exclusion uses every member, not its sample.

Output tables retain key columns plus the declared count/sample fields; keys
and members sort lexically. Every supplied reading must authenticate and
exhaust successfully, with no deferrals, before the worker writes its scope or
result. A late corrupted partition invalidates all provisional reduction state.
Original reading receipts participate in the combined scope identity, including
their original input/context/lookup evidence. Verification reconstructs exact
bytes through the pinned contract. Successful reduction does not prove upstream
population completeness or downstream matching parity; qualify those separately
before replacing an active caller.

### Materialized collections and joins

The contract is a JSON object with this shape (shown as YAML for review):

```yaml
execution: {profile: source.combine}
combine:
  max_rows: 100000
  groups:
    forms:
      source: references
      table: items
      key: record_key
      value: form
      mode: collect
      order_by: [form]
      distinct: true
      skip_null_values: true
      checks: {capture: approved-capture}
      where: {}
  tables:
    records:
      source: primary
      table: records
      checks: {capture: approved-capture}
      where: {}
      joins:
        forms: {group: forms, key: record_key, on_missing: empty, replace: false}
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
  value; they require `distinct: false`. `one` also requires exactly one
  selected value per key; duplicate rows refuse even when identical.
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
  empty` produces `[]` for either collection mode or null for first/last/one; `error` refuses
  an unmatched key (including null). Existing fields require `replace: true`
  to overwrite; with false, a collision rejects the combination.
- Optional join `path` declares 1–8 identifier fields from the output root
  to the destination leaf. Joins run in increasing path depth, so parents
  exist before children regardless of canonical JSON key order. Equal-depth
  joins retain contract order. Intermediate objects are copied before edits;
  null parents become objects, scalar parents refuse. Leaf collisions obey
  `replace`. `on_missing: skip` leaves the row untouched for an absent answer.
- Optional output-table `drop` removes at most 64 distinct named columns after
  all joins. Missing columns refuse. Use it to remove declared helper keys.
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

A shipped blueprint is qualified only for what its fixtures cover (main
records, continuation pages, catalog shapes, address conversion, then
independently verified combination and MDM preparation). **Complete mastering
provenance and full installed population, replay and recovery stay unqualified
until proved for that source.** This profile does not authorize deletion of a
source's retained readers or activation of a source Rules version. Offline
comparisons on captured samples exercise the workers and verifiers directly,
not the installed full pipeline; record which qualification flags stay false.

`skip_empty_text: true` is optional for `collect` and `collect_flat` groups.
It excludes only the empty string. Whitespace, false, zero, empty lists/maps
and null retain their existing policies. The default is false. Flattened
input elements still count toward the declared budget before this exclusion
or deduplication. Use this with ranked catalog collections to keep a landing
rule that excludes empty text without changing source ranks.

## Preparation blueprints

A source may bundle a `combine.yaml` that joins its main reading, its
continuation pages and its catalog readings (each from its own bundled reading
contract). Preserve every input's independently verified reading receipt. Each
capture must belong to its approved capture run.

1. From authenticated capture manifests, replace every approved-run placeholder
   check value in a copy of the blueprint. Pin the resulting JSON combination
   contract. Finish when every check equals its approved manifest run ID, and the
   immutable contract receipt is recorded in the creator's frozen unit.
2. If main-derived capture completeness proves zero continuation pages, set
   the group's source list to `[main]` and omit `pages` from readings.
   Otherwise include every required page through its verified reading receipt.
   Finish when the immutable capture scope accounts for every main-derived
   page; never substitute a fabricated empty page for missing capture evidence.
3. Run the configured read → combine → prepare steps and their independent
   verifiers as above. Finish this composition step only when all three
   receipts verify, the combined scope pins every reading role (or the
   verified no-pages variant), and prepared rows reproduce the same collections.

State what the blueprint keeps (sort order, distinctness, which value wins per
key), which empty values it excludes, and what a missing collection becomes.
Capture checks run before any row filtering or key skip. The composition is an
input to the remaining census, classification and provenance qualification;
keep the active route until the installed population and replay/recovery gates
pass.

## Census evidence

Bind the approved canonical census SHA into the source's census combine
contract and use its matching census reading contract; replace capture and
catalog run placeholders with the approved runs. Supply the full readings the
source's `combine.yaml` uses, plus a reading named `census`. Census groups use
`one` and pin each row's census digest. Name evidence joins by the configured
name key; optional cascade evidence joins by the record key. Missing name
evidence yields null, while a cascade answer can create a cascade-only object.
The helper name key is dropped before MDM preparation.

Compare complete prepared rows with the retained census helper, including
missing/empty evidence and cascade-only cases. Authenticate the full census
input even when its tables are empty. Approval of its construction, complete
mastering provenance, installed population, replay and recovery must be
proved before retiring active semantic consumers.

## Examples

### Qualification on 2026-10-02

The shipped Company blueprint has raw-JSON fixture qualification for main
records, continuation pages, both ticker-catalog shapes and business-address
conversion, followed by independently verified combination and MDM preparation.
Census lookup/composition has exact fixture and pinned-census qualification.
**Complete mastering provenance and full installed Company
population/replay/recovery remain unqualified.**
This profile does not authorize deletion of retained Company/GLEIF readers or
activation of a source Rules version.

Offline evidence in [PR #819](https://github.com/paulananth/edgartools-platform/pull/819)
records exact recent-form comparisons on 1,000 distinct receipt-pinned main
captures (107,197 filing rows). This exercised source.read and source.combine
workers/verifiers directly, not the installed full Company pipeline. Its
`pagination_qualified` and `full_company_mastering` flags remain false.

### The SEC Company preparation blueprint

Use the bundled `sources/sec.submissions.company/combine.yaml` with readings
from the bundled main `source.yaml`, `pagination.yaml` and `catalog.yaml`.
The four reading names are `main`, `pages`, `catalog_exchange` and
`catalog_tickers`. Preserve every input's independently verified reading
receipt. Both catalog captures must belong to the approved catalog run; main
and all derived pages must belong to the approved Company capture run.

1. From authenticated capture manifests, replace every
   `APPROVED_COMPANY_CAPTURE_RUN` and `APPROVED_CATALOG_CAPTURE_RUN` check value
   in a copy of the blueprint. Pin the resulting JSON combination contract.
   Finish when every check equals its approved manifest run ID, and the
   immutable contract receipt is recorded in the creator's frozen unit.
2. If main-derived capture completeness proves zero continuation pages, set
   the forms group's source list to `[main]` and omit `pages` from readings.
   Otherwise include every required page through its verified reading receipt.
   Finish when the immutable capture scope accounts for every main-derived
   page; never substitute a fabricated empty page for missing capture evidence.
3. Run the configured read → combine → prepare steps and their independent
   verifiers as above. Finish this composition step only when all three
   receipts verify, the combined scope pins all four reading roles (or the
   verified no-pages variant), and prepared rows reproduce the same collections.

The blueprint preserves naturally sorted distinct filing forms, catalog
tickers ordered by `(source_rank, ticker)` across both captures, and the last
configured business address per CIK. Empty ticker/form text and null values
are excluded explicitly. Missing collections become `[]`; a missing business
address becomes null. Capture checks run before any row filtering or key skip.

This composition is an input to the remaining census/classification/provenance
qualification. Keep the active Company route until the installed empty-store
6,414 Company / 3,052 CIK+LEI population and replay/recovery gates pass.

### The SEC Company census evidence

Bind the approved canonical census SHA into `combine-census.yaml` and use
its matching reading contract `census.yaml`; replace capture/catalog run
placeholders with the approved runs. Supply the full main/page/catalog
readings used by `combine.yaml`, with main captures read through
`census-main.yaml`, plus a reading named `census`. Both census groups use
`one` and pin each row's census digest. Name evidence joins by the configured
SEC name key; optional cascade evidence joins by integer CIK under
`name_census.cascade`. Missing name evidence yields null, while a cascade
answer can create a cascade-only object. The helper name key is dropped
before MDM preparation.

Compare complete prepared rows with the retained census helper, including
missing/empty evidence and cascade-only cases. Authenticate the full census
input even when its tables are empty. Approval of its construction, complete
mastering provenance, installed population, replay and recovery must be
proved before retiring active semantic consumers.
