# Accept short words for Link two masters

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/link_masters_full.py` only. A missing end stays the engine's wait. No end is invented from a later file. This file can merge before ticket 25. The page ignores it until `link_masters.py` exists.

- link type → `type`
- other master's key → `target_key`
- link starts → `valid_from`
- link ends → `valid_to`

## Checklist

- [x] `link_masters_full.py` is the only production file this ticket adds. `tests/unit/test_rules_try_link_masters_full.py` is new. 2026-11-25 23:51 ET
- [x] The resolved-ends case written in these words matches ticket 25. `tests/unit/test_rules_try_link_masters_full.py`. 2026-11-25 23:51 ET
- [x] A missing end is not invented. `tests/unit/test_rules_try_link_masters_full.py`. 2026-11-25 23:51 ET
- [x] Learning → skill: none. The words rename four keys of the link rule. 2026-11-25 23:51 ET

## Answer

`link_masters_full.py` declares the four words with their stored keys and `explain(rule)`. Show the full rule takes the link as JSON, replaces each word by its stored key, and returns `{"lines": [the words used, with their stored keys], "document": the link with stored keys}`. `scope` keeps its stored key, and a stored key typed in place of its word is accepted unchanged. The document is checked with the same `link_of` the family's Try uses, so a value that is not text is refused. A word the file does not know, a word beside its own stored key, a link that is not JSON and a link that is not one object each return `{"refused": "..."}`; the unknown-word refusal lists the words this file accepts.

The four-word link in the tests (`link type` `ISSUED_BY`, `other master's key` `C1`, `link starts` and `link ends` as instants) shows the same document as ticket 25's resolved-ends rule and Try emits the same one link. With no `link ends` the document has no `valid_to` and the link's period stays open. With no `other master's key` the document has no `target_key` and Try returns the engine's `unresolved_endpoint` review with `missing: ["target"]`, no link.

## Comments
