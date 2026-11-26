# Read the file

Type a short rule, press Show the full rule to see the stored keys beside your words, and press Try to read an invented file with it. The invented examples below were run on the try page's "Read the file" family.

## Words and stored keys

| Word you type | Stored key | Where it goes |
| --- | --- | --- |
| exact decimal | `value`, decimals and big numbers kept as text | a column |
| keep JSON | `value` | a column |
| fixed | `const` | a column |
| if | `choose` | a column |
| first that counts | `coalesce` | a column |
| join text | `join` (texts, not rows) | a column |
| keep the last | `steps` (the result is the last call) | a column |
| read inside | `project` | a column |
| row number | `ordinal` | a column |
| supplied fact | `context` | a column |
| in the list | `member` | a column |
| one value for the key | `member_value` | a column |
| code table | `lookup` | a column |
| shape | `test` | a column |
| key exists | `test` with kind `present` | a column |
| floating-point | `number` (not money) | a column |
| which list | `choose` | `each` |
| no rows | `empty` | `each` |
| zip arrays | `parallel` | `each` |
| headers and cells | `matrix` | `each` |
| child rows | `nest` | `each` |
| text is there | check `required` | `checks` |
| in the caller's list | check `in_lookup` | `checks` |
| in this fixed list | check `in_set` | `checks` |
| how many at this path | check `count` | `checks` |
| start is earlier | check `before` | `checks` |
| skip the row | `on_fail: defer` | `checks` |
| refuse the file | `on_fail: reject` | `checks` |

`trim`, `replace`, `regex_replace`, `regex_extract`, `case` and `unicode` keep their stored keys, since the word matches the action. `format` and the size limits come from your paste. A stored key from the table, typed bare, is refused with the words the family accepts.

## An invented file

The file:

```json
{"records":[{"id":"R1","name":"  Example Works  ","quantity":"12"}]}
```

Your short rule, with two words:

```json
{"read": {"format": "json", "limits": {"max_bytes": 4096, "max_records": 10},
  "tables": {"records": {"each": "records",
    "columns": {"id": {"text": {"path": "id"}}, "name": {"text": {"path": "name"}},
                "quantity": {"integer": {"path": "quantity"}}},
    "checks": [{"check": "text is there", "column": "id", "on_fail": "skip the row", "reason": "missing_id"}]}}}}
```

Show the full rule prints these lines, then the same document with the stored keys:

```json
[{"word": "text is there", "stored": "required"}, {"word": "skip the row", "stored": "defer"}]
```

The check in the full document is `{"check": "required", "column": "id", "on_fail": "defer", "reason": "missing_id"}`.

## What Try returns

Pasting the full document, the file above and no lookup lists returns:

```json
{"tables": {"records": [{"id": "R1", "name": "Example Works", "quantity": 12}]}, "deferred": []}
```

A file with no `id` on a row would put that row in `deferred` with the reason `missing_id`, not in `tables`. A paste the engine cannot read returns `{"refused": "..."}` and nothing else.
