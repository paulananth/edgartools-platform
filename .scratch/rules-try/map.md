# Try one rule

Label: `wayfinder:map`

## Destination

A person hand-writes one rule, supplies the input and the expected output, and the page shows the full rule, tries it, and can store the draft. The engines stay. Files under `rules/` stay until a later effort. Each ticket in `issues/` is one pull request.

## Notes

- Do ticket 01 first. After it merges, tickets 02 through 37 can each be done alone. Ticket 38 waits for 01 and 37 because it also edits the primer.
- Ticket 01 is the only ticket that creates more than one file. Every other ticket adds or replaces the one file it names.
- The page command is `edgar-warehouse rules try`. The buttons are Try, Show the full rule, Keep a copy, and Store this draft.
- Examples in the tickets are invented.
- The remaining work is handed to Claude in [HANDOFF-claude.md](HANDOFF-claude.md). One open ticket, one pull request.

## Decisions so far

- The 38 tickets in `issues/` are the approved breakdown (2026-11-21). One ticket, one file, except ticket 01.
- Plain words live only in that family's `*_full.py`. The stored key is shown beside the word. A bare misleading key is refused.
- "attach" is the typed word in two families. The page title tells them apart. Each full-rule file refuses the other family's words.
- Identity consolidation stays on `rules test`. The page does not offer a word for it.
- Source priority chooses a field value. It does not decide that two masters are the same subject.
- Ticket 01 opens the try page. A family is the file `bench_families/<name>.py`. Store this draft refuses until its own ticket.
- Ticket 02: Keep a copy writes the case JSON to the path the person names. No path is not confirmed and is not written. A path under `rules/` is refused. Store this draft still refuses.
- Ticket 03: Store this draft calls `Rules.save` under the `version` in the pasted rule and keeps the case beside that draft. A rule with no version is not stored. The draft is not switched on.
- Ticket 04: `read_file` takes the read document as the rule, the file text and the lookup lists as inputs, and returns what `SourceEngine.read` returns. The folder test checks that every family declares a page.
- Ticket 05: a short read rule is a read document that may use the listed words for a stored key. Show the full rule returns the words used with their stored keys and the full document, which the engine must load. A bare stored key from the list is refused with the word to type.
- Ticket 06: `docs/rules-try/read_file.md` records each word, its stored key, the invented R1 file and the output Try returns for it.
- Ticket 07: `group_rows` takes the combination contract as the rule and the input tables as JSON, checks the contract with the combine worker's check, and returns what `combine_tables` returns, with the worker's `canonical` as the equality.
- Ticket 08: `group_rows_full` replaces the words for a group's `mode` (list the values, one flat list, first row, last row, exactly one row, and in a reduction how many rows, distinct values, most frequent) and the table key `attach` (`joins`, grouped rows joined to a row). A bare stored key is refused with the word to type. "how many at this path" and the words of Attach a source record are refused and name their family.
- Ticket 09: `docs/rules-try/group_rows.md` lists the nine words with their stored keys and records the R1 case run on the family: aliases `["A","B"]`.
- Ticket 11: `whole_set_full` accepts three words for a group's `mode`: how many rows (`count`), distinct values (`members`), most frequent (`most`). A bare stored mode and "how many at this path" are refused.
- Ticket 13: `check_record` takes the quality block as the rule, the fields and the matching input as inputs, and returns what `quality.apply` returns; a failed `exception` check returns `{"held out": "quality_<id>", "on_fail": "exception"}`. The test uses "is present" only; an in-reference check is not tried.
- Ticket 14: `check_record_full.py` takes a quality block whose `test` and `on_fail` use five words (is present, in the pinned code set, hold the record out, keep off matching, count the failure) and shows the same block with the stored keys. A stored key typed bare is refused with the word to type and the words the file accepts.
- Ticket 16: `entity_type` takes the classification rule as the rule, the record and the doc as inputs, and returns what `classify` decides: `{"entity type": ...}` or `{"held back": "deferred"}`. A rule with no `otherwise` step is the engine's refusal.
- Ticket 17: `entity_type_full` has the words `field is one of`, `these fields are empty`, `name tokens match` (`token_match@2`, with its own long word for `token_match@1`), `held back`, `probable entity type` and `otherwise`. A bare stored key is refused naming the word to type.
- Ticket 18: `docs/rules-try/entity_type.md` records the words and the empty-ticker case: an empty `ticker` is held back (`deferred`), a ticker with the `OPERATING` category is a `company`, and a rule with no `otherwise` step is refused.
- Ticket 22: `attach_record` takes the policy as the rule and the records, the masters that exist (with the values each holds) and the bound list as inputs. It calls `plan_record_matches`, answers the lookup from the pasted masters, and names each record's outcome: attach, create a master, or send to review. A rule that merges two masters is refused.
- Ticket 23: `attach_record_full` replaces the five words (same identifier, how many that identifier allows, attach, create a master, send to review) with their stored keys, refuses a bare stored key, refuses a word for combining two existing masters (that stays on `rules test`), and refuses the words of Group and attach rows and Read the file.
- Ticket 25: `link_masters` takes the one link a stating record makes as the rule (`type`, `target_key`, `valid_from`, `valid_to`, `scope`); the claims, state, entities, as-of time and link types are the inputs, and Try returns the links and reviews `mdm.relationships.project` returns. A claim with no start waits as `unknown_relationship_start`; an end that is not named or not bound waits as `unresolved_endpoint`.
- Ticket 26: `link_masters_full` names four keys of the link rule: link type → `type`, other master's key → `target_key`, link starts → `valid_from`, link ends → `valid_to`. A missing end is not invented, and a missing other master stays the engine's `unresolved_endpoint` wait.
- Ticket 27: `docs/rules-try/link_masters.md` records the four words, the emitted `ISSUED_BY` link between two invented masters, and the missing-start wait (`unknown_relationship_start`, no link), from a run of tickets 25 and 26.
- Ticket 37: the primer's opening points to `docs/rules-try/` and the try command. The primitive catalog stays in the primer until ticket 38.

## Not yet specified

None for this list. A ticket that learns a new rule records it in that ticket's Learning line.

## Out of scope

- Rewriting the files under `rules/`.
- Replacing the Rust source engine, the quality engine, or the mastering engine.
- Adopting another rules runtime.
- Switching a stored draft on. Approve and activate stay where they are.
