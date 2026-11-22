# Accept short words for Read the file

Type: task
Status: open
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

- [ ] `read_file_full.py` is the only file this ticket adds
- [ ] The shown document, tried through the engine, matches the R1 row in ticket 04
- [ ] A bare `join` or `number` is refused with the accepted words
- [ ] The page does not show this file before ticket 04's run file exists
- [ ] Learning → skill

## Comments

