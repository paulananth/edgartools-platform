# Summarize every row

Type a short rule, press Show the full rule to see the stored modes beside your words, and press Try to summarize invented rows with it. The invented examples below were run on the try page's "Summarize every row" family.

## Words and stored keys

A word goes where a group's `mode` goes inside the `reduce` block.

| Word you type | Stored key | What the group returns for each key |
| --- | --- | --- |
| how many rows | `count` | how many rows have the key |
| distinct values | `members` | how many different values the rows file, and the values themselves |
| most frequent | `most` | the value the most rows file, and how many rows file it |

A stored key from the table, typed bare, is refused with the word to type and the three words the family accepts. "how many at this path" belongs to reading a file, not to summarizing rows, so it is refused too. The bounds and the group columns come from your paste.

## An invented set of rows

Three rows share the key `K1`. Two of them file the value `Alpha`.

Your short rule, with the three words:

```json
{"reduce": {"max_rows": 100, "max_input_bytes": 4096, "max_state_bytes": 4096, "max_keys": 10,
  "max_members": 10, "max_output_rows": 10, "max_output_bytes": 4096,
  "groups": {
    "rows": {"source": "main", "table": "rows", "keys": ["key"], "mode": "how many rows",
             "count": "frequency", "sample": null, "sample_limit": 0},
    "distinct": {"source": "main", "table": "rows", "keys": ["key"], "mode": "distinct values",
                 "member": "holder", "count": "count", "sample": "sample", "sample_limit": 5},
    "most": {"source": "main", "table": "rows", "keys": ["key"], "mode": "most frequent",
             "member": "holder", "count": "filed", "sample": "value", "sample_limit": 0}}}}
```

Show the full rule prints these lines, then the same document with `mode` set to `count`, `members` and `most`:

```json
[{"word": "how many rows", "stored": "count"}, {"word": "distinct values", "stored": "members"}, {"word": "most frequent", "stored": "most"}]
```

The rows box holds a group name and its rows. Each group here reads the same three rows:

```json
{"rows": [{"key": "K1", "holder": "Alpha"}, {"key": "K1", "holder": "Beta"}, {"key": "K1", "holder": "Alpha"}],
 "distinct": [{"key": "K1", "holder": "Alpha"}, {"key": "K1", "holder": "Beta"}, {"key": "K1", "holder": "Alpha"}],
 "most": [{"key": "K1", "holder": "Alpha"}, {"key": "K1", "holder": "Beta"}, {"key": "K1", "holder": "Alpha"}]}
```

## What Try returns

Pasting the full document and those rows returns:

```json
{"groups": {"rows": [{"key": "K1", "frequency": 3}],
            "distinct": [{"key": "K1", "count": 2, "sample": [{"holder": "Alpha"}, {"holder": "Beta"}]}],
            "most": [{"key": "K1", "filed": 2, "value": "Alpha"}]}}
```

Three rows, two different values, and `Alpha` filed twice.

## The tie

With only the first two rows, `Alpha` and `Beta` once each, no one value is filed most often. The most frequent value is blank (`null`), and `filed` is 1, the most rows any one value has:

```json
{"groups": {"rows": [{"key": "K1", "frequency": 2}],
            "distinct": [{"key": "K1", "count": 2, "sample": [{"holder": "Alpha"}, {"holder": "Beta"}]}],
            "most": [{"key": "K1", "filed": 1, "value": null}]}}
```

A row whose value is `null` files no value and votes for none. A rule that is not JSON or has no `reduce` block, a plan the engine refuses, rows that are not a JSON object of lists of rows, and a row with a key that is not text each return `{"refused": "..."}` and nothing else.
