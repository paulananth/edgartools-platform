# 02 RDM database, publish, MDM pin, migrate reference YAML

Type: task. Phase: B. Blocked by: 01a, Codex retirement merged. Map: [map](../map.md). Plan: [plan](../plan.md).

## Rulings

- 2026-10-07 06:39 ET: operator invoked "/implement ticket 02", starting this phase B ticket before Codex's old-parser retirement merged.
- 2026-10-07: operator asked whether RDM is friendly to agents, then "make rdm be friendly to agents need semantic layer hints": added `rdm list`, `rdm describe`, `rdm draft --file`, and two tables frozen with each version, `code_set_usage` (where the codes' values live, how to compare them) and `code_set_hint` (meaning, use_when, avoid_when, example_question).
- 2026-10-07 06:47 ET: operator said "approved" to the data model, as shown:
  - the seven RDM tables from the spec (§2.1) (two more, `code_set_usage` and `code_set_hint`, came with the semantic-layer ruling above);
  - the place-code table's `place` becomes the label, and `iso` an `exact` crosswalk row to the outside standard `iso-3166`;
  - `type` becomes a `broad` crosswalk row to a new 4-code set `sec-place-types`, not parent codes;
  - one current published version per code set is held by a unique index, not the `btree_gist` exclusion constraint;
  - this PR leaves the YAML and the Mastering Policy (digest 1e38238f…03da4) unchanged. Switching the policy to pin the version is a separate approval, with the mastering counts from both runs.

## Checklist

- [ ] ~~Re-read main for Codex's final design~~ deferred to the policy pin switch: Codex's retirement has not merged (PR #834 open); this PR touches none of Codex's paths (added 2026-10-07 06:47 ET)
- [x] Data model shown with the data-modeling skill's lens and approved by the operator ("approved") 2026-10-07 06:47 ET
- [x] GoF consult: copy the migration loop; no shared runner (each store's changes were its own roles and grants) 2026-10-07 06:45 ET
- [x] rdm migrations from zero: tables, comments on everything, immutability after publish, approval needs name and words, one current published version (`tests/integration/test_rdm_postgres.py` on PG16) 2026-10-07 07:10 ET
- [x] Draft, approve, publish (code paths, cycle refusal, sha256 of the canonical form, previous version closed), canonical JSON Lines files beside the version (silver writer is ticket 06) (integration tests) 2026-10-07 07:10 ET
- [x] `edgar-warehouse rdm diff` (spec §5): added, removed, relabelled, moved codes (integration test) 2026-10-07 07:10 ET
- [x] Import the place-code YAML as `sec-place-codes` version 1 (plus `sec-place-types`), and rebuild the YAML's `codes` map exactly from it (309 codes; unit and integration tests) 2026-10-07 07:10 ET
- [x] Spec status line says approved (#825); the spec records the unique index, the `type` crosswalk, the canonical form's crosswalk rows, the commands and the semantic layer 2026-10-07 07:10 ET
- [x] Tests on a populated version (all 309 codes): migrate from zero, publish, immutability, cycle refusal, supersede, diff (9 RDM tests pass on local PG16; affected unit/mdm tests pass, the 15 architecture failures are the same on main: no `jq` on this machine) 2026-10-07 07:10 ET
- [x] Agent-friendly: `rdm list`, `rdm describe` (bounded 8 KB), `rdm draft --file`, usage and hint tables; data-profiling SKILL.md says how an agent drafts a code set 2026-10-07 07:10 ET
- [ ] ~~Lookup and search of codes (`rdm.code_context`, `edgar-warehouse context <code set>`)~~ deferred to [05](05-agent-context-views-and-command.md), its RDM part (added 2026-10-07 07:10 ET)
- [ ] MDM pins version + sha256: separate operator approval, with mastering counts embed vs pin (added 2026-10-07 06:47 ET)
- [ ] Contract-embedded tables gain the pin: handoff to Codex (spec §7) (added 2026-10-07 06:47 ET)
- [ ] YAML removed only after the pin's counts match (spec §7)
- [x] Review (Standards, Spec, GoF): GoF no findings; fixed: the database checks a publish supersedes the newest published version; level names are in the pin; a failed import writes nothing; draft fields are checked (a misspelled one is refused); a code set's words never change; the drafter cannot approve; `describe` stays within 8 KB; publishes of one set are serialised; files are written before the commit and `--out` is required; `rdm retire` and `rdm verify`; tighter grants; spec wording. A wrong sha256 written by hand is caught by `rdm verify`, not by the database (it cannot compute the canonical form) (10 RDM tests pass) 2026-10-07 07:16 ET
- [ ] PR, CI, merge on word
