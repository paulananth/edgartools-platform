# Try Attach a source record

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Add `bench_families/attach_record.py` only. The person pastes the policy, assertions, identities, and the bound list. The page calls `plan_record_matches`. Outcomes on the page: attach, create a master, send to review. The stored words `bind` and `mint` appear beside attach and create a master. Do not call `propose`. Do not open a database.

Invented pass: one invented identifier with one pasted master returns attach. The same identifier with two pasted masters returns send to review.

Known leftover: the same identifier-declaration import as ticket 16. This ticket does not add a database read.

## Checklist

- [x] `attach_record.py` is the only production file this ticket adds. `tests/unit/test_rules_try_attach_record.py` is new. 2026-11-25 21:56 ET
- [x] One pasted master returns attach. `tests/unit/test_rules_try_attach_record.py`. 2026-11-25 21:56 ET
- [x] Two pasted masters return send to review. `tests/unit/test_rules_try_attach_record.py`. 2026-11-25 21:56 ET
- [x] `propose` is not called and no database connection is opened. `tests/unit/test_rules_try_attach_record.py`. 2026-11-25 21:56 ET
- [x] Learning → skill: none. The family is two calls to the existing source engine, and ticket 22's text names the plan. 2026-11-25 21:56 ET

## Answer

`attach_record` shows the title "Attach a source record" and three inputs: the records (assertions) as JSON, the masters that exist (identities, each with `entity_id`, `kind` and `holds`: a namespace and the values it holds) as JSON, and the bound list (records already attached) as JSON. The rule box holds the policy as JSON. Try calls `edgar_warehouse.rules.source_engine.plan_record_matches`, answers its lookup from the pasted masters, and calls `link_matching_records` from the same module, since the plan alone names no outcome. It returns `looked_up` (the plan's lookup), `outcomes` and `no_outcome`. An outcome is `attach` (stored `bind`, with the master), `create a master` (stored `mint`, with a master named `new-master-1` for the try) or `send to review` (stored `review`, with the engine's reason). A record with no outcome says why: already attached, no rule applies, or waits for a master. One pasted master returns attach; two pasted masters holding the same value return send to review with `ambiguous_identifier`. A rule whose `on_several` is `merge` is refused, since combining existing masters stays on `rules test`. A policy that is not a JSON object or lacks `kinds` or `automatic_rules`, a paste that is not JSON or not the listed shape, and a batch the engine refuses each return `{"refused": "..."}`. `propose` is not called and no database is opened. The value forms come from `edgar_warehouse.mdm.identifier_types`, the known leftover from ticket 16.

## Comments
