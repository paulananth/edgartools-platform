# Rules file reference

What a `rules/sources/<source>/source.yaml` file may say, and how Clean MDM
reads it (`edgar_warehouse/mdm/clean/adapters.py`, `normalize`).

## The file

```yaml
source: <provider>.<dataset>          # the folder name, e.g. acme.registry
bronze:
  family: <bronze family>            # where the captured files live
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
      completeness: <plain words: what one publication covers>
      adapter: {...}                 # below
```

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
| `fields` | `mdm_field: path`. The field names come from `rules/merge/kinds/<kind>.yaml`. |
| `fields.address` | `components:` with any of `street`, `street2`, `city`, `region`, `postcode`, `country`, each a path. `street2` may be `lines: <path>` for a list of lines. |
| `field_shape` | `nullable_text`: every field is text or empty. |
| `relationships` | A list. Each has `type` (or `type_field` + `type_values`), `target_key` (paths), `target_source` (the other end's source code), `scope`, `valid_from`, `valid_to`, `properties`. |
| `profiles` | A role profile: `role`, `authority`, `registration`, `jurisdiction`, `valid_from`, `valid_to`, `fields`. |
| `provenance` | `name: path` kept with each record, to trace it back to its file. |
| `source_record_provenance` | `true`: keep the record key and adapter version as provenance. |
| `matching` | `name: path` values that the matching rules compare. They are kept with the record, outside its fields. |
| `retain_deferred` | `true`: keep a record MDM cannot take yet, with its reason. |
| `native_member` | For a source parsed by native code, the member this contract maps. |

## Merge rules

`rules/merge/kinds/<kind>.yaml` gives each field's source ranks (which source
wins) and the matching rules. Adding a source to a field's ranks, adding a
field or adding a kind changes what MDM decides. Each one needs the operator's
ruling and approval.

## Worked examples

Every file under `rules/sources/` is a worked example. Read them all before
writing a new one.
