# Choose the field value

Type a short policy, press Show the full rule to see the stored keys beside your words, and press Try to choose the field values for invented claims with it. The invented examples below were run on the try page's "Choose the field value" family. The page calls `select_fields` and does not read a policy file.

Source priority chooses which claim fills a field. It never decides that two masters are the same subject: you name the subjects that already are one, and the policy only ranks their claims.

## Words and stored keys

| Word you type | Stored key | Where it goes |
| --- | --- | --- |
| source order | `defaults.sources` | the entity type's block: the order for every field |
| this field's order | `fields.<name>.sources` | one field under `fields` |
| may blank the field | `clear_sources` | the entity type's block (every field) or one field |
| ignore older than | `max_age_days` | the entity type's block (every field) or one field |

`source order` and `this field's order` list source names, first source first. `may blank the field` lists the sources that may clear the field; a clear from any other source is set aside for review. `ignore older than` is a number of days: a claim effective earlier than that, counting back from the as-of time, is not eligible. A field's own words override the entity type's.

A stored key from the table, typed bare (`sources`, `clear_sources`, `max_age_days`), is refused with the word to type and the words the family accepts, since the stored key does not say whether it is for every field or one field. A key that is not a word, such as `version` or `allow_unknown_effective`, keeps its name.

## The inputs

The rule box holds the policy. The page asks for:

- Entity type: the name of the block under `kinds`.
- Subjects: a JSON list of the subject keys whose claims are compared.
- Claims: a JSON object of subject key to that subject's fields. Each field carries `assertion_id`, `effective_at`, `op`, `record_key`, `source_code` and `value`.
- Steward overrides: a JSON list, empty for none.
- As-of time, with a time zone.
- Policy digest: any text. A policy with a `kinds` block records the digest of the entity type's own rules instead.

## Directory first for address, register first for the rest

The claims, for two subjects of the entity type `example_company`:

```json
{"S1": {"fields": {"name": {"assertion_id": "R1-a", "effective_at": "2026-09-01T00:00:00+00:00", "op": "value", "record_key": "R1", "source_code": "example.register.v1", "value": "Example Works"},
                    "address": {"assertion_id": "R1-a", "effective_at": "2026-09-01T00:00:00+00:00", "op": "value", "record_key": "R1", "source_code": "example.register.v1", "value": "1 Register Way"}}},
 "S2": {"fields": {"name": {"assertion_id": "D1-a", "effective_at": "2026-09-01T00:00:00+00:00", "op": "value", "record_key": "D1", "source_code": "example.directory.v1", "value": "EXAMPLE WORKS LTD"},
                    "address": {"assertion_id": "D1-a", "effective_at": "2026-09-01T00:00:00+00:00", "op": "value", "record_key": "D1", "source_code": "example.directory.v1", "value": "2 Directory Road"}}}}
```

Your short policy, with two words:

```json
{"kinds": {"example_company": {
  "source order": ["example.register.v1", "example.directory.v1"],
  "fields": {"address": {"this field's order": ["example.directory.v1", "example.register.v1"]}}}}}
```

Show the full rule prints these lines, then the same policy with the stored keys:

```json
[{"word": "source order", "stored": "defaults.sources"}, {"word": "this field's order", "stored": "fields.address.sources"}]
```

```json
{"kinds": {"example_company": {
  "defaults": {"sources": ["example.register.v1", "example.directory.v1"]},
  "fields": {"address": {"sources": ["example.directory.v1", "example.register.v1"]}}}}}
```

## What Try returns

Pasting the full policy, the entity type `example_company`, the subjects `["S1", "S2"]`, the claims above, no overrides, the as-of time `2026-09-22T00:00:00+00:00` and the digest `digest-1` returns the chosen fields, the profiles and the reviews. The address comes from the directory and the name from the register; the claim that lost stays beside the winner under `conflicts`:

```json
{"fields": {
  "address": {"value": "2 Directory Road", "cleared": false,
    "winner": {"assertion_id": "D1-a", "effective_at": "2026-09-01T00:00:00+00:00", "op": "value", "record_key": "D1", "source_code": "example.directory.v1", "value": "2 Directory Road"},
    "policy_digest": "9619cb14aaa26db3f17352e033396254449eccfa79af5333d959ea2daf261439",
    "conflicts": [{"assertion_id": "R1-a", "effective_at": "2026-09-01T00:00:00+00:00", "op": "value", "record_key": "R1", "source_code": "example.register.v1", "value": "1 Register Way"}]},
  "name": {"value": "Example Works", "cleared": false,
    "winner": {"assertion_id": "R1-a", "effective_at": "2026-09-01T00:00:00+00:00", "op": "value", "record_key": "R1", "source_code": "example.register.v1", "value": "Example Works"},
    "policy_digest": "9619cb14aaa26db3f17352e033396254449eccfa79af5333d959ea2daf261439",
    "conflicts": [{"assertion_id": "D1-a", "effective_at": "2026-09-01T00:00:00+00:00", "op": "value", "record_key": "D1", "source_code": "example.directory.v1", "value": "EXAMPLE WORKS LTD"}]}},
 "profiles": [], "reviews": []}
```

A steward override for a field wins over both claims and adds a review, `override_source_disagreement`, when a claim disagrees. A paste the engine cannot read, such as a policy that is not JSON or an as-of time with no time zone, returns `{"refused": "..."}` and nothing else.
