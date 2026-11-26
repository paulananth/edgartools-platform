# Accept short words for Read the file

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/read_file_full.py` only. A short rule in the words below becomes a complete read document. Show the full rule prints the stored key beside each word. A bare stored key from this list is refused, with the words this file accepts. `format` and the size limits come from the paste, inside the engine's existing ceilings.

This file can merge before ticket 04. The page ignores it until `read_file.py` exists.

- exact decimal → `value`, decimals kept as text
- keep JSON → `value`
- fixed → `const`
- if → `choose` on a column
- first that counts → `coalesce`
- join text → `join` (texts, not rows)
- keep the last → `steps` (the result is the last call)
- read inside → `project` on a column
- row number → `ordinal`
- supplied fact → `context`
- in the list → `member`
- one value for the key → `member_value`
- code table → `lookup`
- in the caller's list → `in_lookup`
- in this fixed list → `in_set`
- shape → `test`
- key exists → `test` kind `present`
- text is there → check `required`
- skip the row → `on_fail: defer`
- refuse the file → `on_fail: reject`
- how many at this path → check `count`
- start is earlier → check `before`
- which list → `choose` on iteration
- no rows → `empty`
- zip arrays → `parallel`
- headers and cells → `matrix`
- child rows → `nest`
- floating-point → `number` (not money)

`trim`, `replace`, `regex_replace`, `regex_extract`, `case`, and `unicode` stay as stored keys because the word matches the action.

## Checklist

- [x] `read_file_full.py` is the only production file this ticket adds. `tests/unit/test_rules_try_read_file_full.py` is new. 2026-11-25 21:52 ET
- [x] The shown document, tried through the engine, matches the R1 row in ticket 04. `tests/unit/test_rules_try_read_file_full.py`. 2026-11-25 21:52 ET
- [x] A bare `join` or `number` is refused with the accepted words. `tests/unit/test_rules_try_read_file_full.py`. 2026-11-25 21:52 ET
- [x] The page does not show this file before ticket 04's run file exists. `tests/unit/test_rules_try_read_file_full.py`. 2026-11-25 21:52 ET
- [x] Learning → skill: none. The words are a table the file reads. 2026-11-25 21:52 ET

## Answer

A short rule is a read document that may use the words in the list where a stored key goes. Show the full rule returns `{"lines": [...], "document": {...}}`: the words the rule used, each with its stored key, and the same document with every word replaced. Call words are replaced under `columns`, `select` and `assertions`; iteration words under `each`; check words in `check`; outcome words in `on_fail`. "exact decimal" adds `decimals: text` and `big_numbers: text`; "key exists" adds `kind: present`. A stored key from the list typed bare, such as `join` or `number`, is refused with the word to type and every word the file accepts. A key that is not a call keeps its name (the `context` block under `read`, or a column named `context`). The document is built only if `SourceEngine` loads it, so `format` and the limits come from the paste inside the engine's ceilings.

## Comments

