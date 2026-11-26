# Try Link two masters

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/link_masters.py` only. The person pastes claims, state, entities, as-of time, and types. The page calls `project` with those arguments. Do not call `types_of`. Do not read `rules/reference`. A link does not create a master.

Invented pass: pasted endpoints that resolve emit one link. A pasted claim with no start time returns the engine's wait.

## Checklist

- [x] `link_masters.py` is the only production file this ticket adds. `tests/unit/test_rules_try_link_masters.py` is new. 2026-11-25 21:54 ET
- [x] Resolved ends emit one link. `tests/unit/test_rules_try_link_masters.py`. 2026-11-25 21:54 ET
- [x] A missing start waits. `tests/unit/test_rules_try_link_masters.py`. 2026-11-25 21:54 ET
- [x] `types_of` is not called. `tests/unit/test_rules_try_link_masters.py`. 2026-11-25 21:54 ET
- [x] Learning → skill: none. The family is one call to the existing `project`. 2026-11-25 21:54 ET

## Answer

`link_masters` shows the title "Link two masters" and five inputs: the claims, the state, the entities, the as-of time and the link types, each pasted as JSON (the as-of time as text). The rule box holds the link one stating record makes, as JSON: `type`, `target_key` (the key the other master's record is bound under in the state), `valid_from`, `valid_to` and `scope`. Try writes that link into each pasted claim as its one relationship, calls `edgar_warehouse.mdm.relationships.project(claims, state, entities, as_of, types)` and returns `{"links": [...], "reviews": [...]}`. The state is `{"bindings": ..., "canonical": ...}`.

Both ends resolved and accepted: one link with its stated period, and no review. A claim with no `valid_from` and no `effective_at` in its `source_meta` is set aside with the review `unknown_relationship_start`; no link is emitted. A rule with no `target_key`, or one the state does not bind, is set aside with the review `unresolved_endpoint` and `missing: ["target"]`; no link is emitted and no end is made up. A link does not create a master: an end whose master is not `accepted` is set aside as `unresolved_endpoint_identity`. A rule or paste that is not JSON, a claim that already holds `relationships`, a key the rule does not take, a state without `bindings` or `canonical`, and anything the engine refuses (a bad time, a type with rules it cannot run, a master with no `kind`) each return `{"refused": "..."}`. `types_of` is not called and no `rules/` file is read.

## Comments

- The ticket says the person pastes "types" with the claims; the rule box holds the link and the types are the fifth input, so the short words of ticket 26 (`type`, `target_key`, `valid_from`, `valid_to`) name keys of the rule box.
