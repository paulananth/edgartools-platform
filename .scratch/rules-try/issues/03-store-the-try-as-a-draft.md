# Store the try as a draft

Type: task
Status: resolved
Label: ready-for-agent
Blocked by: 01

## What to build

Replace `bench_store.py` only. Store this draft calls `Rules.save` under the version label the person types and keeps the case beside that draft. The rule is not switched on. Do not call approve or activate. Do not import a family.

`Rules.save` was named in the Bookkeeping spec and was not a method. This ticket adds it in `edgar_warehouse/rules/db.py`, because the button cannot call a method that is not there. The version label is the `version` string in the pasted rule. The page and the command have nowhere else to type one, and this ticket does not add a flag.

## Checklist

- [x] `bench_store.py` stores the draft. `db.py` gained `Rules.save` because that method was not in the code. The try command's note now says Store this draft opens the Rules Database. The map records that decision. (2026-11-22 08:40 ET: `tests/unit/test_rules_try.py`, 23 passed; `tests/storage_adapters/test_rules_runtime.py`, 3 passed on PostgreSQL and 3 passed on MySQL)
- [x] The draft is stored under the typed version label. The label is the `version` string in the pasted rule, compared exactly, including case. A rule with no version is not stored and the database is not opened. A label longer than 128 characters is refused as too long and is not truncated. (2026-11-22 08:40 ET: the same unit file; case distinction on PostgreSQL and MySQL in the adapter test)
- [x] The case is kept beside that draft. Storing the same body again leaves the first case. A different body under that version is refused. (2026-11-22 08:40 ET: the same unit file and the adapter test)
- [x] Approve and activate are not called. The stored status stays draft, and the runtime login cannot change or delete the row. (2026-11-22 08:40 ET: the adapter test on both engines)
- [x] Learning → skill: `skills/data-platform/STORES.md` now lists the draft table beside `rules_used` and the registry

## Answer

Store this draft reads `version` from the pasted rule and calls `Rules.save`. That method stores the rule's canonical JSON and its SHA-256 as an immutable draft, and stores the case beside it. The label is compared exactly, including case. The status stays draft. A pasted rule with no version is refused and nothing is stored. A label longer than 128 characters is refused as too long.

## Comments

