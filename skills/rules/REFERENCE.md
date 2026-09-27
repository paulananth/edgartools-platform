# Rules file reference

What a `rules/sources/<source>/source.yaml` file may say, and how Clean MDM
reads it (`edgar_warehouse/mdm/clean/adapters.py`, `normalize`).

## The file

```yaml
source: <source>                     # the folder name, e.g. acme.registry or gleif
bookkeeping: {...}                   # the Bookkeeping skill's section; leave it alone
bronze:
  family: <bronze family>            # the main captured-file family (no code reads it yet)
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

| What happened | Code | Default |
|---|---|---|
| Outside the approved scope | `outside_approved_company_scope` | does not block |
| A kind MDM does not take yet | `unsupported_identity_kind` | does not block |
| A valid reporting exception | `reported_parent_exception` | does not block |
| Held back by a classification rule | `classification_deferred`, `classification_entity_undetermined` | blocks until the operator rules otherwise |
| A relationship type not mapped | `unsupported_relationship_type` | blocks; ask the operator |
| The policy has not activated the verdict | `classification_not_activated` | blocks: the policy is wrong |
| A defect: `invalid_*`, `missing_*`, `ambiguous_relationship_period`, `unsupported_relationship_endpoint`, `unsupported_exception_category` | | always blocks |

The three "does not block" reasons are the record's decision (native GLEIF
operation); list each one a contract can raise. For any other reason, ask.

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
  approves it.

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
| `kind_field`, `kind_values` | The path holding the source's category, and the kind for each category the source accepts, e.g. `CORP: company`. |
| `probable_kind_values` | What a record in another category probably is. It sorts the record without making an identity. |
| `classification` | Instead of a kind: the Mastering Policy rule that decides it: `kind`, `rule_id`, `version`. |
| `identifiers` | `namespace: path`, e.g. `lei: firm.lei`. |
| `identifier_formats` | `namespace: format`, from `FORMATS`. |
| `fields` | `mdm_field: path`. Use the names MDM already has for the kind (for Company, `COMPANY_NAMED_FIELDS` in `edgar_warehouse/mdm/clean/store.py`). |
| `fields.address` | `components:` with any of `street`, `street2`, `city`, `region`, `postcode`, `country`, each a path. `street2` may be `lines: <path>`, where the path holds a list of `{"$": text}` lines. |
| `field_shape` | `nullable_text`: every field is text or empty. |
| `relationships` | A list. Each has `type` (or `type_field` + `type_values`), `target_key` (paths), `target_source` (the other end's source code), `valid_from`, `valid_to` and `properties` (paths), and `scope`: fixed text, `<Provider> <relationship family>` (for example `ACME ownership`), not a path. Name each property after its source field with a `source_` prefix, so it cannot be mistaken for an MDM value. |
| `profiles` | A role profile: `role`, `authority`, `registration`, `jurisdiction`, `valid_from`, `valid_to`, `fields`. |
| `provenance` | `name: path` kept with each record. Only values that stay the same across captures (the source's own record); capture hashes, run ids and sync times stay beside the record. |
| `source_record_provenance` | `true`: keep the record key and adapter version as provenance. |
| `matching` | `name: path` values that the matching rules compare. They are kept with the record, outside its fields. |
| `retain_deferred` | `true`: keep a record MDM cannot take yet, with its reason. |
| `native_member` | For a source parsed by native code, the member this contract maps. |

## Merge rules

`rules/merge/kinds/<kind>.yaml` ranks the sources per kind (the first listed
wins every field it fills) and holds the matching rules. Its comments record
which of a source's values fills a field that two sources share. Adding a source to a field's ranks, adding a
field or adding a kind changes what MDM decides. Each one needs the operator's
ruling and approval. Every source whose records are of a kind must be in that
kind's `defaults.sources`, or its batch fails: adding it is such a change.
A relationship record becomes a link only once a matching rule joins its
record to the kind's records.

Not expressible yet, so log them: a publication-level contract (a reader's
list of approved identifiers, or the files that make one release), a
source placeholder that means "none", a kind taken from a record in another
file.

## Worked examples

Every file under `rules/sources/` is a worked example. Read them all before
writing a new one.
