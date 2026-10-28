# 146: Convert a populated native MDM store to governed storage

Priority: 146. Map: [Rebuild priorities](../map.md). Opened 2026-10-28 12:43 ET.

Type: task. Status: in progress (Claude, branch `claude/t146-mdm-data-migration`).
Blocked by: none. Unblocks ticket 120's switch-on in `company-on`.
Operator, 2026-10-28: "how to get Securities running in a store: build a data
migration so today's code can upgrade company-on - approved".

## Why

Since #1159 (2026-10-24) MDM installs governed storage (`mdm_store` tables,
protocol 6) and refuses a populated native store ("Populated native MDM requires a
qualified data migration; use a fresh prepared store"); #1190 retired the native
callers. Codex's PRs left the conversion out of scope; no plan exists for it.

## Found (2026-10-28 12:43 ET, `company-on`'s MDM, counts only)

Only the native layout (64 `mdm` tables; no `mdm_store`). Rows: 19,280 source
readings (and stage records), 15,564 masters (Company 2,433, Fund 12,937, Person
194), 15,789 decisions, all `bind` with their `entity_id`, 886 records set aside,
29,751 cross-references, 3 policies; no relationships, no detail versions.

## Design (advisor, 2026-10-28)

Replay, not a table-to-table copy: masters derive from source readings and
decisions. Read the native store's readings (revisions and times) and its bind
decisions, and apply them in order through today's Merge Stage (`apply(...,
decisions=...)`) into a new governed database on the same server, under today's
policy. Hard checks: the same master ids, the same binding per source record, no
decision lost, the readings set aside again. Differences from rule changes since
are counted by field, not failed. Never write the native database: build beside
it, verify, then swap names, keeping the native one for rollback. An owner-only,
resumable command beside `rebuild-name-index`; `migrate()`'s refusal stays.

## Parts

- [x] Inventory and design (2026-10-28 12:43 ET): above
- [x] A replayed bind keeps its master id in a fresh governed store (the seam) (2026-10-28 13:07 ET): already proven by `test_configured_master_kinds` (a caller identity and bind keep their id); the native shapes (rule-authored binds, a later bind onto an earlier master, a set-aside record) by `tests/integration/test_mdm_conversion.py`
- [x] Found (2026-10-28 13:07 ET): each native batch kept its whole command in `mdm.batch.effects` (77 batches: 19,280 readings, 15,789 decisions, 15,564 new masters, 886 set aside, `as_of`), so the conversion applies those commands again, in order; nothing is rebuilt or guessed
- [x] Found (2026-10-28 13:07 ET): today's code refuses the native policy's inline relationship types (ticket 132's pinned code set replaced them). The conversion swaps that one section for today's pin and refuses if a kept type is defined differently; 16 of the 17 types are identical, `HOLDS` was dropped and no native reading reports one (the only links: 48 `SUCCESSOR_ENTITY`). Advisor: each batch keeps its own policy, never today's, so the conversion is not a rule change
- [x] GoF consult (2026-10-28 13:07 ET): a new module beside the Merge Stage, its only caller; no existing code changes shape (Rule 0: leave it)
- [x] The command (2026-10-28 13:07 ET): `edgar-warehouse mdm convert-native` (owner-only; `NATIVE_MDM_DATABASE_URL` read in a read-only transaction, `MDM_DATABASE_URL` a fresh governed store); a rerun skips saved batches by their ids
- [x] Tests (2026-10-28 13:07 ET): `tests/integration/test_mdm_conversion.py` 3 passed (ids kept, bindings kept, no decision lost, a set-aside record, the native database unchanged, a second run changes nothing, a stopped run resumes); `tests/mdm/test_conversion_policy.py` 3 passed; `tests/unit/test_mdm_cli_commands.py` 11 passed
- [x] Probe (2026-10-28 13:35 ET): `company-on`'s native tables converted into a disposable store in 20 min: 77 batches, 19,280 readings, 15,789 decisions, 15,564 masters, 886 set aside, equal to the inventory; 3 policies, 14 Dataset Contract readings carried; `HOLDS` the one type dropped. The process was then killed (signal 9, cause not found) in the checks, so the checks run in their own process on `company-on`
- [x] Three-axis review, PR, CI green, merge (2026-10-28 13:23 ET): GoF leave it (noted: `--limit` restarted from the oldest batch, fixed); Standards: the same `--limit` bug, read-only by session, one short native read a batch, a docstring for the whole reads, fixed; Spec: the checks now fail the command (`passed`, exit 1), every record present, field differences counted by field, a type added since accepted, fixed. #1205 merged 13:23 ET, 20 of 20 checks
- [x] Convert `company-on`; counts against the inventory; the swap, with the native database kept (2026-10-28 14:21 ET): the swap at 13:36 ET (backup first; `mdm` renamed `mdm_native`, read-only, the runtime, verifier and governance roles' connect revoked; a fresh governed `mdm`). The conversion 13:37–13:57 ET (19.5 min, peak 1.8 GB): 77 batches, 19,280 readings, 15,789 decisions, 15,564 masters, 886 set aside, equal to the inventory; 3 policies and 14 Dataset Contract readings carried, `HOLDS` dropped. The checks, 27 s: 15,564 masters kept, none added; 19,280 records present with the same binding; no decision lost; no field differs; passed
- [x] Found (2026-10-28 14:21 ET): the checks were killed (signal 9) twice before their first page of masters. A consumer page reads each master with its batch's whole saved request (77 requests, 2,553 MB, the largest 141 MB), once per row. Fixed in the checks: they read the current master records only (`iter_type`), conversion tests 9 passed. The consumer page itself is [ticket 147](147-consumer-page-carries-the-batch-request.md)
- [x] Three-axis review of the checks' read (2026-10-28 14:22 ET): GoF leave it (noted on ticket 147: the adapter built by hand at eight call sites); Spec: the checks unchanged (same keys, same bodies, now in the checks' own transaction), ticket 147 corrected (the request's hash check, 200 masters a statement); Standards: the whole read named in the docstring, one `_adapter` for both commands, the comment points at ticket 147; paging past 400 masters proved live (15,564 masters, about 39 pages, every count exact). Tests 20 passed
- [ ] PR, CI, merge of the checks' read
- [ ] Ticket 120's switch-on in `company-on`, and its loads (hours: say the time first)
- [ ] Learning → skill
