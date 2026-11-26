# Check one record

Type a short quality block, press Show the full rule to see the stored keys beside your words, and press Try to check one invented record with it. The invented examples below were run on the try page's "Check one record" family, which calls `quality.apply`.

## Words and stored keys

| Word you type | Stored key | Where it goes |
| --- | --- | --- |
| is present | `present@1` | a check's `test` |
| hold the record out | `exception` | a check's `on_fail` |
| keep off matching | `withhold` | a check's `on_fail` |
| count the failure | `flag` | a check's `on_fail` |

`version`, the check ids, the paths such as `fields.name`, and the arguments come from your paste. A stored key from the table, typed bare, is refused with the words the family accepts. This guide has no in-reference check; "is present" is the only test it uses.

## An invented record

The record's fields:

```json
{"name": "Example Works"}
```

A second record with no name:

```json
{}
```

Your short rule:

```json
{"version": "example-quality-v1",
 "checks": [{"id": "name_required", "test": "is present", "value": "fields.name",
             "on_fail": "hold the record out", "args": {}}]}
```

Show the full rule prints these lines, then the same block with the stored keys:

```json
[{"word": "is present", "stored": "present@1"}, {"word": "hold the record out", "stored": "exception"}]
```

```json
{"version": "example-quality-v1", "checks": [{"id": "name_required", "test": "present@1", "value": "fields.name", "on_fail": "exception", "args": {}}]}
```

## What Try returns

Pasting the full block with the first record and no matching input returns what `apply` returns, one entry per check:

```json
{"version": "example-quality-v1", "checks": {"name_required": {"kind": "present@1", "failure_action": "exception", "rows_checked": 1, "rows_failed": 0}}}
```

The same block with the record that has no name is held out. The reason is `quality_` and the check id, and `exception` is shown beside "held out":

```json
{"held out": "quality_name_required", "on_fail": "exception"}
```

With `on_fail` set to `keep off matching` (`withhold`), the same record is not held out. The value stays and no matching rule may use it:

```json
{"version": "example-quality-v1", "checks": {"name_required": {"kind": "present@1", "failure_action": "withhold", "rows_checked": 1, "rows_failed": 1}}, "withheld": ["fields.name"]}
```

With `count the failure` (`flag`), the failure is only counted:

```json
{"version": "example-quality-v1", "checks": {"name_required": {"kind": "present@1", "failure_action": "flag", "rows_checked": 1, "rows_failed": 1}}, "flags": ["name_required"]}
```

A paste the quality engine cannot read (a block with no `version`, an unknown test, an `on_fail` that is not one of the three) returns `{"refused": "..."}` and nothing else.
