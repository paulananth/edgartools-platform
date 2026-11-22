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

## Not yet specified

None for this list. A ticket that learns a new rule records it in that ticket's Learning line.

## Out of scope

- Rewriting the files under `rules/`.
- Replacing the Rust source engine, the quality engine, or the mastering engine.
- Adopting another rules runtime.
- Switching a stored draft on. Approve and activate stay where they are.
