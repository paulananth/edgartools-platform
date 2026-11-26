# Group and attach rows

Type a short rule, press Show the full rule to see the stored keys beside your words, and press Try to combine invented tables with it. The invented examples below were run on the try page's "Group and attach rows" family.

## Words and stored keys

| Word you type | Stored key | Where it goes |
| --- | --- | --- |
| list the values | `collect` | a group's `mode` |
| one flat list | `collect_flat` | a group's `mode` |
| first row | `first` | a group's `mode` |
| last row | `last` | a group's `mode` |
| exactly one row | `one` (two matching rows are refused, even when they hold equal values) | a group's `mode` |
| how many rows | `count` | a group's `mode` in a reduction |
| distinct values | `members` | a group's `mode` in a reduction |
| most frequent | `most` (no value when two tie) | a group's `mode` in a reduction |
| attach | `joins` (grouped rows are joined to a row) | the key that holds an output table's joins |

The five row words go in a `combine` block, and the three whole-set words go in a `reduce` block. A word in the other block is refused. "attach" here means grouped rows are joined to a row; it does not bind a source record. A stored key from the table, typed bare, is refused with the word to type and the words the family accepts. "how many at this path" is a word of Read the file and is refused here. The words of Attach a source record ("same identifier", "how many that identifier allows", "create a master", "send to review") are refused here too.

## An invented case

The input tables, a reading name, a table name, and its rows:

```json
{"primary": {"records": [{"id": "R1"}]},
 "extra": {"names": [{"id": "R1", "alias": "B"}, {"id": "R1", "alias": "A"}]}}
```

Your short rule, with two words:

```json
{"execution": {"profile": "source.combine"},
 "combine": {"max_rows": 1000,
  "groups": {"aliases": {"source": "extra", "table": "names", "key": "id", "value": "alias",
                         "mode": "list the values", "order_by": ["alias"], "distinct": true,
                         "skip_null_values": true, "checks": {}, "where": {}}},
  "tables": {"records": {"source": "primary", "table": "records", "checks": {}, "where": {},
                         "attach": {"aliases": {"group": "aliases", "key": "id",
                                                "on_missing": "empty", "replace": false}}}}}}
```

Show the full rule prints these lines, then the same document with the stored keys:

```json
[{"word": "list the values", "stored": "collect"}, {"word": "attach", "stored": "joins"}]
```

In the full document the group's `mode` is `collect` and the table holds `joins` where it held `attach`.

## What Try returns

Pasting the full document and the tables above returns:

```json
{"tables": {"records": [{"id": "R1", "aliases": ["A", "B"]}]}}
```

Row `R1` carries its two aliases, ordered. This join does not decide that two records are the same subject.

With `mode` set to `exactly one row` and two names rows for `R1` that both hold `A`, Try returns `{"refused": "Group one requires exactly one value per key"}`. A paste the engine cannot read returns `{"refused": "..."}` and nothing else. The rule box takes a combination contract (`execution` and `combine`); a reduction contract is a different family, "Summarize every row".
