# Fold sightings into periods

Type a short rule, press Show the full rule to see the stored keys beside your words, and press Try to fold the invented sightings into periods. The rule box holds the sightings: the fold has no other setting. The invented examples below were run on the try page's "Fold sightings into periods" family.

## Words and stored keys

| Word you type | Stored key | Where it goes |
| --- | --- | --- |
| seen on | `on` | a sighting: the date the filing says the capacity was held or dropped |
| still held | `held` | a sighting: true holds the capacity; false or null drops it |
| how known | `basis` | a sighting: `observed` or `stated` |
| filing id | `assertion_id` | a sighting |
| filing | `subject` | a sighting |
| starts | `valid_from` | the period that comes out |
| start known by | `valid_from_basis` | the period that comes out |
| ends | `valid_to` | the period that comes out |
| end known by | `valid_to_basis` | the period that comes out |
| last seen | `last_observed` | the period that comes out |
| left for a steward | `contradictions` | the second answer of the fold |

`title` keeps its stored key, since the word matches the field: it is a dated detail of the period. A stored key from the table, typed bare in a sighting, is refused with the word to type and every word the file accepts. The period words are not typed into a sighting. An end is refused in particular: a period ends only at a later sighting that drops the capacity, and a missing later file leaves the end empty.

## An invented sighting

Your short rule, with one dated sighting:

```json
{"sightings": [{"seen on": "2024-01-15T00:00:00+00:00", "still held": true, "how known": "observed",
                "filing id": "a1", "filing": "filing-1"}]}
```

Show the full rule prints these lines, then the same sightings with the stored keys:

```json
[{"word": "seen on", "stored": "on"}, {"word": "still held", "stored": "held"}, {"word": "how known", "stored": "basis"}, {"word": "filing id", "stored": "assertion_id"}, {"word": "filing", "stored": "subject"}]
```

```json
{"sightings": [{"on": "2024-01-15T00:00:00+00:00", "held": true, "basis": "observed", "assertion_id": "a1", "subject": "filing-1"}]}
```

## What Try returns

Pasting the full sightings returns the period the relationship held:

```json
{"periods": [{"valid_from": "2024-01-15T00:00:00+00:00", "valid_from_basis": "observed", "valid_to": null, "valid_to_basis": null, "last_observed": "2024-01-15T00:00:00+00:00", "titles": []}], "contradictions": []}
```

The sighting opened the period on its date, so `valid_from` is that date with the basis `observed`. Nothing ended it, so `valid_to` and `valid_to_basis` are null.

## A missing later file does not invent an end

A second sighting on `2024-03-15T00:00:00+00:00` that still holds the capacity (`"still held": true`, filing id `a2`) leaves the period open and moves `last_observed` to that date:

```json
{"periods": [{"valid_from": "2024-01-15T00:00:00+00:00", "valid_from_basis": "observed", "valid_to": null, "valid_to_basis": null, "last_observed": "2024-03-15T00:00:00+00:00", "titles": []}], "contradictions": []}
```

Silence, a later filing that is not there, never ends a period. A later sighting with `"still held": false` does:

```json
{"periods": [{"valid_from": "2024-01-15T00:00:00+00:00", "valid_from_basis": "observed", "valid_to": "2024-03-15T00:00:00+00:00", "valid_to_basis": "observed", "last_observed": "2024-01-15T00:00:00+00:00", "titles": []}], "contradictions": []}
```

## A sighting after a stated end

If the dropping sighting is `"how known": "stated"` and a later observed sighting (here filing id `a3` on `2024-06-15T00:00:00+00:00`) holds the capacity again, the period stays ended and the fold leaves the later sighting for a steward:

```json
{"periods": [{"valid_from": "2024-01-15T00:00:00+00:00", "valid_from_basis": "observed", "valid_to": "2024-03-15T00:00:00+00:00", "valid_to_basis": "stated", "last_observed": "2024-01-15T00:00:00+00:00", "titles": []}], "contradictions": [{"stated_end": "2024-03-15T00:00:00+00:00", "on": "2024-06-15T00:00:00+00:00", "assertion_id": "a3", "subject": "filing-3"}]}
```

## Refusals

A paste the fold cannot read returns `{"refused": "..."}` and nothing else. Typing `ends` in a sighting returns:

```json
{"refused": "An end is not typed. It comes from a later sighting that drops the capacity ('still held' false); a missing later file leaves it empty. Words this file accepts: seen on, still held, how known, filing id, filing, starts, start known by, ends, end known by, last seen, left for a steward."}
```
