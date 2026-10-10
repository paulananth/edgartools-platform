# Rules file reference

What a `rules/sources/<source>/source.yaml` file may say, and how Clean MDM
reads it (`edgar_warehouse/mdm/clean/adapters.py`, `normalize`).

## The file

```yaml
source: <source>                     # the folder name, e.g. acme.registry or gleif
bookkeeping: {...}                   # the Bookkeeping skill's section; leave it alone
bronze:
  family: <bronze family>            # the main captured-file family; name any other in a comment
mdm:
  <source_code>:                     # e.g. acme.registry.firms.v1; one per record type
    contract:
      provider: <who publishes it>
      family: <bronze family>
      schema_version: <the record shape the mapping reads>
      record_key: <plain words: what identifies one record>
      publication_key: <plain words: what identifies one publication>
      effective_time: <plain words: when a record takes effect, or unknown>
      semantics: <patch: a record changes only what it says; absence never retires>
      completeness: <plain words: what one publication covers; optional>
      nonblocking_deferred_reasons: [...]   # optional, below
      publication_families: [...]           # optional, below
      adapter: {...}                        # below
```

The folder name is the source's name: lowercase, dotted. When the repo
already names the source, or its reader names the folder, keep that name.
One folder may hold several source codes, one per file or record type, when
one reader reads them all.

## Defaults

Start every contract from these, and change one only with a reason written
beside it:

```yaml
adapter:
  retain_deferred: true           # keep a record MDM cannot take yet, with its reason
  source_record_provenance: true  # keep the record key and adapter version with each fact
  field_shape: nullable_text      # every field is text or empty
  provenance:                     # never capture hashes, run ids or sync times: they stay beside the record
    native_record: <key>          # only if the reader keeps the source's own record under a key
```

When the files arrive as releases the reader numbers and verifies, also set
`publication_families` (for a full release, the family the reader names).

## Blocking and non-blocking

A record set aside for a reason in `nonblocking_deferred_reasons` does not
stop its batch; any other reason stops the batch until a person resolves it.
Only an expected, explained exclusion is non-blocking: a record outside the
approved scope, or of a kind MDM does not take yet. **A defect always
blocks:** a bad identifier (a failed check digit), a malformed record, a
missing key. Never list a defect as non-blocking.

The reason codes the code raises today:

| What happened | Code | List it as non-blocking? |
|---|---|---|
| Outside the approved scope | `outside_approved_company_scope` | yes |
| A kind MDM does not take yet | `unsupported_identity_kind` | yes |
| A valid reporting exception | `reported_parent_exception` | yes |
| A data quality exception: a critical data element is missing | `quality_<id>` | yes, always (operator, 2026-09-28) |
| Held back by a classification rule | `classification_deferred`, `classification_entity_undetermined` | yes (operator, 2026-09-27: "never stop the run") |
| A relationship type not mapped yet | `unsupported_relationship_type` | yes (operator, 2026-09-27); each run reports a count by type, so a new type is seen |
| The policy has not activated the verdict | `classification_not_activated` | no: it means the policy is wrong |
| A defect: `invalid_*`, `missing_*`, `ambiguous_relationship_period`, `unsupported_relationship_endpoint`, `unsupported_exception_category` | | never, unless the operator rules one defect non-blocking for one contract (the records still never merge; they wait for a steward); quote the ruling in a comment beside the list |

A contract that lists no reason blocks on every one. The "yes" reasons are
decided (a source's native operation; the operator for relationship types and
classification hold-backs): list
each one a contract can raise. For any other reason, ask.

## Full files and changes

`semantics: patch` means a record changes only what it says, and a record
missing from a file retires nothing. This holds even for a source that
publishes full files: MDM never retires an identity because a file left it
out. Say in `completeness` whether each file is complete or holds changes
only. A reader may require an exact `schema_version`; when it checks one,
use that value.

## Names that are part of every record's identity

`schema_version` and `adapter.version` are written into every record MDM
keeps from this source, and a source code is fixed once it is registered.
`schema_version` names the record shape the mapping reads; a reader may
require it to equal `adapter.version`. So:
- name each one once, for example `acme-firm-record-v1`;
- never reuse a name for different content;
- a change to a registered source is a new version, and the operator
  approves it. A change to a record key, the publication key or the
  identifiers needs a new source code instead: the engine refuses it within
  one source code (`PROTECTED_ADAPTER_PARTS` in
  `edgar_warehouse/mdm/clean/store.py`). Cross-references never decide which
  record is which, so adding one is a new version, not a new source code.

## Optional envelope keys

| Key | Meaning |
|---|---|
| `nonblocking_deferred_reasons` | Reasons a record is set aside that do **not** block its batch, for example records outside the approved scope, or of a kind MDM does not take yet. Any other reason blocks the batch until a person resolves it. List only reasons you expect and can explain. |
| `publication_families` | For a source whose files arrive as numbered native publications: the families this contract accepts, for example a full release. |

## Values

The loader reads JSON values exactly:
- An unquoted `null`, `true`, `false` or JSON number is that value.
- Any other unquoted value that YAML would read as something else (`yes`,
  `no`, `010`, `2026-09-25`, an empty value) is refused, with its line. Quote
  it.
- Every other value, and every key, is text.
- Duplicate keys, anchors, aliases, tags and a second document are refused.

`files.dumps(value)` writes YAML that reads back exactly.

## Paths

A path is dotted keys into one record: `firm.address.postcode`,
`firm.legal_name`. A missing key gives no value. Map from the record as the
source's parser produces it, not from the raw file, when a parser exists.

## `adapter`

| Key | Meaning |
|---|---|
| `version` | The mapping's own version name, e.g. `acme-firm-record-v1`. |
| `record_key` | A list of paths that together identify one record. |
| `record_key_format` | A named format from `FORMATS` (`sec_cik`, `lei`), checked and normalized. |
| `kind` | Every record is this kind (from `KINDS`). |
| `kind_field`, `kind_values` | The path holding the source's category, and the kind for each category the source accepts, e.g. `CORP: <kind>`. |
| `probable_kind_values` | What a record in another category probably is. It sorts the record without making an identity. |
| `classification` | Instead of a kind: the Mastering Policy rule that decides it: `kind`, `rule_id`, `version`. |
| `identifiers` | `namespace: path`, e.g. `lei: firm.lei`. |
| `identifier_formats` | `namespace: format`, from `FORMATS`. |
| `cross_references` | `namespace: path`: an id kept so any document can be looked up by it, **never used to join records** (operator, 2026-09-26: "lookup only"). Matching and binding read `identifiers` only. Name it for what it is (`tax_id`, or `<source>_<id>` for a source's own copy of another register's id); registration refuses a namespace that is also one of `identifiers`, or one a binding rule matches on (the kind's merge rules name them). An empty value is left out. An id of another kind of entity goes on that kind's contract, not here. Look one up with `mdm.cross_reference_lookup(namespace, value)`; `mdm.cross_reference` lists them all. |
| `cross_reference_formats` | `namespace: format`, from `FORMATS`, for a cross-reference. |
| `name_id` (a cross-reference) | **Only when the records carry no id another source shares.** Map the name: `cross_references: {name_id: <name path>}`, `cross_reference_formats: {name_id: name_id@1}`. The format keeps every token of the name (a share class or series number stays), so one name gives one id in every source, and `mdm.cross_reference_lookup('name_id', <id>)` finds the records named so. Lookup only, like any cross-reference. Measure it first with the data-profiling skill's `match_names.py` (operator, 2026-10-06: "no id exists you just need to create a id using name"). |
| `fields` | `mdm_field: path`. Use the names MDM already has for the kind (its field list in code, or, for a kind with none, its consumer spec; see Examples). |
| `fields.address` | `components:` with any of `street`, `street2`, `city`, `region`, `postcode`, `country`, each a path. `street2` may be `lines: <path>`, where the path holds a list of `{"$": text}` lines. Only `address` takes components; every other field is one path. |
| `field_shape` | `nullable_text`: every field is text or empty. |
| `relationships` | A list. Each has `type` (or `type_field` + `type_values`), `target_key` (paths), `target_source` (the other end's source code), optional `source_key` and `source_source` when the link starts at another record than the one stating it (a relationship record that starts at another record of the same source), `valid_from`, `valid_to` and `properties` (paths), and `scope`: fixed text, `<Provider> <relationship family>` (for example `ACME ownership`), not a path. Name each property after its source field with a `source_` prefix, so it cannot be mistaken for an MDM value. The `type` must be declared in `rules/merge/relationships.yaml` (below). A path reads one value; for a list, `each: <path>` makes one link per item, its paths starting `item.` (an item with no target key makes no link), and `find: {<name>: {in: <path>, where: {<path>: <text>, a list of texts (any of them), or {path: <path>}}}}` adds the first item of another list whose `where` paths all match, read under `<name>.`; a `where` path through a nested list matches when any element does, and no match leaves `<name>.` paths empty. Neither name may be a field of the record; a mapping that breaks this, or a `find` without `in` and `where`, stops the run. |
| `profiles` | A role profile: `role`, `authority`, `registration`, `jurisdiction`, `valid_from`, `valid_to`, `fields`. |
| `provenance` | `name: path` kept with each record. Only values that stay the same across captures (the source's own record); capture hashes, run ids and sync times stay beside the record. |
| `source_record_provenance` | `true`: keep the record key and adapter version as provenance. |
| `matching` | `name: path` values that the matching rules compare. They are kept with the record, outside its fields. A value may also be a whole address, written as `fields.address` is (`components:`), for example a second address kept for matching beside the one MDM shows. Data quality fixes and checks can read it (`matching.<name>`). |
| `retain_deferred` | `true`: keep a record MDM cannot take yet, with its reason. |
| `native_member` | For a source parsed by native code, the member this contract maps. |

## Relationship types

`rules/merge/relationships.yaml` declares every relationship type MDM masters
(operator, 2026-10-06: "Types as data"). It is part of the Mastering Policy, so
a change to it is a new policy version, approved by its digest. A new type
needs no code change:

```yaml
types:
  <TYPE_NAME>:
    from: [<kind>, ...]          # the kinds at the start (the child, for a parent link)
    to: [<kind>, ...]            # the kinds at the end
    from_profile: <role>         # optional: a role profile the start must hold over the period
    to_profile: <role>           # optional: the same for the end
    capacities: [<name>, ...]    # optional: a person's link in a capacity, dated by sightings
    hierarchy: true              # optional: the links form parent chains
    cycles: invalid | review     # a hierarchy: a cycle's links are held back, or kept and reviewed
    one_parent: true             # optional, a hierarchy: one parent at a time per scope
    ultimate_parent: accounting-chain-v1   # optional, a hierarchy: derive each record's ultimate parent
```

`check_policy` refuses a type it could not run: an unknown kind or key, a
hierarchy that does not say what its cycles do, an unknown ultimate-parent
algorithm. Agents read every mastered link through `mdm.relationship_context`,
and a parent chain through `mdm.relationship_chain(entity, type, max_hops)`.

## Reading MDM's context

`edgar-warehouse context` reads what MDM already holds, read only, as JSON of
at most 8 KB. Use it before proposing a kind, an identifier or a relationship
type, and cite what it showed in your question to the operator.

- `edgar-warehouse context <kind> --search "<words>"`: entities whose name
  matches, best first.
- `edgar-warehouse context <kind> <namespace>:<value>`: the one entity carrying
  that identifier (or cross-reference id, lookup only), with its fields, each
  field's winning source, and its source records.
- `edgar-warehouse context relationship <entity id> --hops 2`: its links, both
  ways.
- `--as-of <time>` reads what was true then; `--as-at <time>` what MDM had
  recorded by then, for entities and for relationships (links as recorded
  then, of those holding now; names as MDM holds them now, said in
  `trust.current_parts`). Follow `next_step` in each answer.

What each kind and relationship type means is in
`rules/context/definitions.yaml`. A new kind or relationship type adds its
line there in the same PR; a test fails until it does.

## Merge rules

`rules/merge/kinds/<kind>.yaml` ranks the sources per kind (the first listed
wins every field it fills) and holds the matching rules. One field may have
its own rule, `fields.<name>`: it takes `defaults` and changes any part of
it, such as `sources` (its own order), `clear_sources` (who may empty it),
`max_age_days` or `allow_unknown_effective`: one source may win one field
while another wins the rest (Examples). Its comments record
which of a source's values fills a field that two sources share. Adding a
source to a kind's ranks, adding a field or adding a kind changes what MDM
decides. Each one needs the operator's
ruling and approval. Every source whose records are of a kind must be in that
kind's `defaults.sources`, or its batch fails: adding it is such a change.
A relationship record becomes a link only once a matching rule joins its
record to the kind's records. A matching rule on an identifier names one
namespace, and only one that has an Identifier Contract in a kind file
(`identifiers`); a new joining identifier is its contract and its rule, with
no code (operator, 2026-10-09: "Read the list from the rules").

Not expressible yet, so log them: a publication-level contract (a reader's
list of approved identifiers, or the files that make one release), a kind
taken from a record in another file. A source placeholder that means "none"
is now a data quality fix (`blank_values@1`, below).

## Data quality

`rules/sources/<source>/quality.yaml` holds the checks and fixes run on each
record after the mapping and before the merge
(`edgar_warehouse/mdm/clean/quality.py`):

```yaml
version: <quality version name>       # e.g. acme-firm-quality-v1; a change is a new name
quality:
  <source_code>:                      # a Dataset Contract of this source
    fixes:                            # run first, in order
    - id: <lower_case_id>
      fix: <fix>@<n>
      args: {...}
    checks:                           # run after the fixes, on the fixed values
    - id: <lower_case_id>
      test: <test>@<n>
      value: <path>                   # fields.<name>, fields.address.<part> or matching.<name>
      on_fail: exception | withhold | flag
      args: {...}
```

The loader puts each entry into its contract as `contract.quality` (with the
file's `version`), so the contract's digest and one approval cover both. Do
not write `quality` inside `source.yaml`: the loader refuses it.

| `on_fail` | What happens |
|---|---|
| `exception` | For a missing critical data element. The record is set aside as `quality_<id>`: it never merges and never stops the run, and waits as an open exception until it is fixed or ignored. List `quality_<id>` in the contract's `nonblocking_deferred_reasons`; registration refuses the contract otherwise. |
| `withhold` | The value stays on the record, but no matching rule uses it (`provenance.quality.withheld`). |
| `flag` | Only counted. |

Checks:

| Test | Args | Passes when |
|---|---|---|
| `present@1` | | the value is filled |
| `in_set@1` | `values` | the value is empty or one of `values` |
| `pattern@1` | `regex` | the value is empty or matches all of `regex` |
| `lei_check_digit@1` | | the value is a 20-character ISO 17442 identifier whose check digits pass (mod 97-10) |
| `placeholder@1` | `values` | the value, letters and digits only, is not one of `values` and not all zeros |
| `registered_agent_address@1` | `markers` | no marker is in the address's street lines |
| `in_hierarchy@1` | `table`, `sha256`, `field` (the path of the record's parent code) | the value or its parent is empty, the value is not a code of `table`, or the record's parent is the parent `table` gives the code (a pinned RDM version with a hierarchy); a code at the top with a parent given fails |
| `in_reference@1` | `table`, `sha256` | the value is empty or a code of the reference data the Mastering Policy pins as `table` (`merge/reference-pins.yaml`, a published RDM version); `sha256` must be that pin |

Fixes (each keeps the original under `provenance.quality.fixes`):

| Fix | Args | What it does |
|---|---|---|
| `blank_values@1` | `field`, `values` | a value in `values` becomes empty, so it reads as unknown |
| `name_state_marker@1` | `name`, `target` | a state tag at the end of a name (`/XX`) fills an empty `target` |
| `standardize_address@1` | `field`, `into` | writes a matching copy of the address to `into` (`matching.<name>`): upper case, USPS street words, no suite or floor, a 5-digit ZIP. The address MDM shows is not changed; it counts as a fix only when the copy differs |

A fix that corrects a value (`blank_values@1`, `name_state_marker@1`) changes
the field MDM shows and merges on; the original stays on the record. A test
or fix not in these tables is new code: log it for a ticket.

## Mapping Documents

`edgar-warehouse rules mapdoc write|diff|check [--only <source or kind>]`
works from the rules files alone, with no database.

| Workbook | Sheets |
|---|---|
| `rules/sources/<source>/MAPPING.xlsx` (only a source with an `mdm` section) | Source, Fields (MDM field or matching only), Identifiers, Critical data elements (a `present@1` check with `on_fail: exception`), Data quality, Who wins, Notes |
| `rules/merge/kinds/<kind>.xlsx` | Kind, Preferred sources, Who wins each field, Classification, Matching rules (each condition in plain words), Notes |

Every row names its rules path. A list longer than 12 values shows as a
count. Critical data elements are the checks with `on_fail: exception`. Notes (Note, About, Who, When) is kept on `write`. A new workbook
starts it with the comments in its rules files. `diff` prints each changed
cell, and `check` fails on any.

## The Data Catalog

`edgar-warehouse rules catalog plan|publish [--root <rules>]` works from
the rules files alone. `plan` prints the catalog as JSON; `publish` makes
the OpenMetadata catalog equal to it, with `OPENMETADATA_URL` and
`OPENMETADATA_TOKEN` (a bot's token: Settings > Bots). It is one database
service, `edgartools-rules`:

| Database | Schema | Tables | Columns |
|---|---|---|---|
| `sources` | one per source | one per feed, one per Dataset Contract | a feed: the keys naming a captured file; a dataset: each source path it reads, with its use (identifier, record key, MDM field, matching only, kind) |
| `mdm` | `clean` | one per kind | each MDM field: the datasets that fill it in order (the first with a value wins) and the rule |

Lineage runs from a feed to the datasets that read its files, and from a
dataset to its kind, column by column (an address's parts all feed one
field; matching-only paths feed none). A dataset's critical data elements
are in its description. The service description carries a sha256 of every
rules file, so a reader can tell which rules it shows. `publish` creates or
updates what the rules name and hard-deletes, inside `edgartools-rules`
only, the tables, schemas and lineage they no longer name; publishing the
same rules again changes nothing.

A catalog server on a laptop: `docker compose -f
infra/openmetadata/docker-compose.yml up -d`, then http://localhost:8585.

## Examples (worked)

Every file under `rules/sources/` is a worked example. Read them all before
writing a new one.

The examples above in plain words, from today's sources:

- Fields: Company's are `FIELDS` in `edgar_warehouse/mdm/clean/company_source.py`;
  Person's are in its consumer spec, `docs/specs/person/consumer.md`.
- Joining identifiers: `cik`, the one Identifier Contract today; a ticker on a company's record belongs
  to the security's contract.
- A link starting at another record: a GLEIF relationship record starts at its
  child's Level 1 record. A matching address: GLEIF's headquarters address
  beside the legal address MDM shows.
- One field's own sources: `fields: {address: {sources: [gleif.level1.v1,
  sec.submissions.company.v1]}}` makes GLEIF win the address while SEC wins
  every other field.
- A native operation: GLEIF's. A state tag: SEC's `/DE`. An ISO 17442
  identifier: the LEI.
