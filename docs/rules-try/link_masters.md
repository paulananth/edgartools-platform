# Link two masters

Type a short link, press Show the full rule to see the stored keys beside your words, and press Try to project the link between two invented masters. The invented examples below were run on the try page's "Link two masters" family.

## Words and stored keys

| Word you type | Stored key | Where it goes |
| --- | --- | --- |
| link type | `type` | the rule box |
| other master's key | `target_key`, the key the other master's record is bound under in the state | the rule box |
| link starts | `valid_from` | the rule box |
| link ends | `valid_to` | the rule box |

`scope` keeps its stored key. A stored key typed in place of its word is accepted unchanged. A word the page does not know is refused with the words it accepts. A missing `link ends` is not filled in: the link stays open. A missing `other master's key` is not guessed: the link waits.

## What you paste

The rule box holds the link one stating record makes. Five inputs hold everything else:

| Input | What it is |
| --- | --- |
| claims | The stating records, as JSON: a subject key and its assertion id. The link from the rule box is written into each claim. |
| state | `bindings` (subject key to binding) and `canonical` (binding to master). |
| entities | Each master's `kind` and `status`. |
| as_of | The as-of time, with its time zone. |
| types | The link types, as JSON: a type code and the kinds it joins (`from`, `to`). |

Try calls `edgar_warehouse.mdm.relationships.project` with those and returns the links and the reviews. A link does not create a master: an end that is not an accepted master waits.

## An emitted link

The inputs:

```json
{"claims": {"S1": {"assertion_id": "a1", "source_meta": {}}},
 "state": {"bindings": {"S1": "b1", "C1": "b2"}, "canonical": {"b1": "E1", "b2": "E2"}},
 "entities": {"E1": {"kind": "security", "status": "accepted", "profiles": []},
              "E2": {"kind": "company", "status": "accepted", "profiles": []}},
 "as_of": "2026-01-01T00:00:00+00:00",
 "types": {"ISSUED_BY": {"from": ["security"], "to": ["company"]}}}
```

Your short link, with four words:

```json
{"link type": "ISSUED_BY", "other master's key": "C1",
 "link starts": "2020-01-01T00:00:00+00:00", "link ends": "2022-01-01T00:00:00+00:00"}
```

Show the full rule prints these lines, then the same link with the stored keys:

```json
[{"word": "link type", "stored": "type"}, {"word": "other master's key", "stored": "target_key"},
 {"word": "link starts", "stored": "valid_from"}, {"word": "link ends", "stored": "valid_to"}]
```

```json
{"type": "ISSUED_BY", "target_key": "C1", "valid_from": "2020-01-01T00:00:00+00:00", "valid_to": "2022-01-01T00:00:00+00:00"}
```

Both ends resolve to accepted masters of the right kinds, so Try returns one link and no review:

```json
{"links": [{"type": "ISSUED_BY", "source_id": "E1", "target_id": "E2", "scope": "", "derived": false,
            "relationship_id": "eb7dbfd039189949fd1992a155306ef0e3c3ab769b69d69c44289fd07cef7b68",
            "last_seen": null,
            "periods": [{"valid_from": "2020-01-01T00:00:00+00:00", "valid_to": "2022-01-01T00:00:00+00:00",
                         "valid_from_basis": "stated", "valid_to_basis": "stated"}],
            "evidence": [{"assertion_id": "a1", "source_subject": "S1", "target_subject": "C1"}]}],
 "reviews": []}
```

## The missing-start wait

The same inputs with a short link that has no `link starts`:

```json
{"link type": "ISSUED_BY", "other master's key": "C1"}
```

The claim states no start and its `source_meta` has no `effective_at` to stand in for one, so the engine emits no link. It returns the claim as a review with the reason `unknown_relationship_start`:

```json
{"links": [],
 "reviews": [{"reason": "unknown_relationship_start", "assertion_id": "a1",
              "relationship": {"type": "ISSUED_BY", "target_subject": "C1"}, "subject": "S1"}]}
```

Put `"effective_at": "2024-01-01T00:00:00+00:00"` in the claim's `source_meta` and the same rule emits the link with `valid_from` `2024-01-01T00:00:00+00:00` and `valid_from_basis` `observed`.

A missing end waits the same way. With no `other master's key`, or a key the state does not bind, Try returns no link and the review `unresolved_endpoint` with `"missing": ["target"]`. No end is taken from a later file.

A paste the engine cannot read returns `{"refused": "..."}` and nothing else.
