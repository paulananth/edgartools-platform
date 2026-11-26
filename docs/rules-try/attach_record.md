# Source record binding: attach a source record

This is the "Attach a source record" page of `edgar-warehouse rules try attach_record`. It is about source record binding: a record from a source is attached to a master that already holds one of its identifier values, becomes a new master when none holds it, or goes to review when the choice is not clear. It does not group rows (that page is "Group and attach rows", where "attach" means grouped rows are joined to a row), and it does not combine two existing masters (that decision stays on `rules test`).

Type a short policy, press Show the full rule to see the stored keys beside your words, and press Try to see what each record does. The invented examples below were run on the try page's "Attach a source record" family.

## Words and stored keys

| Word you type | Stored key | Where it goes |
| --- | --- | --- |
| same identifier | `identifier_match@1` | a rule's `when`, as the `primitive` |
| how many that identifier allows | `identifier_cardinality@1` | a rule's `when`, as the `primitive` |
| attach | `bind` | `verdict` in `automatic_rules`, and the rule's `emits` |
| create a master | `mint` | `on_no_match` |
| send to review | `review` | `on_several`, and `on_conflict` |

`wait` (for `on_no_match`) and `first` (for `on_conflict`) say what they do and keep their stored keys, as does `review`, and the other record tests keep theirs. A bare `bind`, `mint`, `identifier_match@1` or `identifier_cardinality@1` is refused with the word to type and the words the family accepts. A word for combining two existing masters, such as `merge`, `combine the masters` or `consolidate`, is refused and points to `rules test`; so is a rule whose `on_several` is `merge`. The words of "Group and attach rows" and "Read the file" are refused and name their page.

## What you paste

- The rule box holds the policy: the `automatic_rules` that approve a rule, and the `kinds` with each kind's rules and identifier declarations.
- Records: a JSON list of records, each with `subject`, `assertion_id`, `source_code`, `kind`, `revision` and `identifiers`.
- Masters that exist: a JSON list, each with `entity_id`, `kind` and `holds` (a namespace and the values the master holds). Leave it empty for none.
- Records already attached: a JSON list of subjects. Leave it empty for none.

Try calls `plan_record_matches` for the values to look up, answers that lookup from the pasted masters, and names each record's outcome. A master is a master of its kind: a master of another kind that holds the value sends the record to review.

## An invented policy

The identifier is an invented ticker, `EXMPL`, from the source `example.listings`. Your short policy, with the words:

```json
{"automatic_rules": [{"kind": "security", "family": "binding", "rule_id": "example-listing-ticker",
                      "rule_version": "1", "verdict": "attach"}],
 "kinds": {"security": {
   "rules": [{"rule_id": "example-listing-ticker", "version": "1", "family": "binding",
              "applies_to_verdict": "security",
              "when": [{"primitive": "same identifier", "args": {"namespace": "ticker"}},
                       {"primitive": "how many that identifier allows", "args": {"namespace": "ticker"}}],
              "emits": ["attach"], "on_no_match": "create a master", "on_several": "send to review"}],
   "identifiers": {"ticker": {"normalizer": "normalize_identifier@ticker-v1", "consolidates": true,
                              "sources": ["example.listings"], "claim": {"forward": 1, "reverse": null}}}}}}
```

Show the full rule prints one line for each word used:

```json
[{"word": "attach", "stored": "bind"}, {"word": "create a master", "stored": "mint"}, {"word": "send to review", "stored": "review"}, {"word": "same identifier", "stored": "identifier_match@1"}, {"word": "how many that identifier allows", "stored": "identifier_cardinality@1"}]
```

It then prints the same policy with `verdict` and `emits` as `bind`, `on_no_match` as `mint`, `on_several` as `review`, and the two primitives as `identifier_match@1` and `identifier_cardinality@1`. Paste that full policy in the rule box for Try.

The record is the same in both cases below:

```json
[{"subject": "R1", "assertion_id": "A-R1", "source_code": "example.listings", "kind": "security",
  "revision": 1, "identifiers": {"ticker": ["EXMPL"]}}]
```

## The one-master case

One master exists and holds `EXMPL`:

```json
[{"entity_id": "M1", "kind": "security", "holds": {"ticker": ["EXMPL"]}}]
```

Try returns:

```json
{"looked_up": {"ticker": ["EXMPL"]}, "outcomes": [{"subject": "R1", "outcome": "attach", "stored": "bind", "master": "M1"}], "no_outcome": []}
```

## The two-master case

Two masters, `M1` and `M2`, both hold `EXMPL`:

```json
[{"entity_id": "M1", "kind": "security", "holds": {"ticker": ["EXMPL"]}},
 {"entity_id": "M2", "kind": "security", "holds": {"ticker": ["EXMPL"]}}]
```

Try returns:

```json
{"looked_up": {"ticker": ["EXMPL"]}, "outcomes": [{"subject": "R1", "outcome": "send to review", "stored": "review", "reason": "ambiguous_identifier"}], "no_outcome": []}
```

The record is not attached to either master. Whether the two masters are one subject is not decided here.

## When no master holds the value

With no master pasted, Try returns:

```json
{"looked_up": {"ticker": ["EXMPL"]}, "outcomes": [{"subject": "R1", "outcome": "create a master", "stored": "mint", "master": "new-master-1"}], "no_outcome": []}
```

`new-master-1` is a name the try gives the new master. A record that no rule applies to, that is already in the bound list, or that waits for a master (`on_no_match` is `wait`) is listed under `no_outcome` with the reason. A paste the engine cannot read returns `{"refused": "..."}` and nothing else. No database is opened.
