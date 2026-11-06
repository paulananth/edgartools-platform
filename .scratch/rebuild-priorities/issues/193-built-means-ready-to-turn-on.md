# 193: A built source is ready to turn on

Priority: 193. Map: [Rebuild priorities](../map.md). Opened 2026-11-04 21:15 ET (operator, 2026-11-04: "this is idiotic when you build it
you need all of this once proved it is just turn on and go make this rule in the skill").

Type: task. Status: resolved. Blocked by: none.

## Question

Activating a source in a new store should be save, record proof, approve, activate, load, with nothing to prepare. Today
the proof lives in the Rules Database of the store where the test ran, so a new store (`local-test-server`, 2026-11-04)
had every rules version as a draft and no proof, and each source would need its own test again. What does a built source
carry so that any store can turn it on at once?

## Parts

- [x] The rule is in the skill (2026-11-04 21:15 ET): data-onboarding SKILL.md, "Built means ready to turn on", and the switch-on mode names it
- [x] ~~The proof and the approval evidence of each built source are kept with it~~ replaced by the operator's ruling (2026-11-04 21:26 ET: "you dont need proof to activate once the rules are finalized"; asked: "Rules merged on main"): rules merged on `main` are final, and `rules approve --finalized <merge>` approves them on the operator's words with no test run, then `rules activate`. Migration 007 (Rules Database: `finalized_ref`; the trigger accepts the approval and the activation with no proof), `Rules.approve(finalized=)`, `finalized_holds` in the processing authority and in the run-start gate (`Bookkeeping.start`), `rules approve --finalized`; tests `test_rules_finalized_on_main_are_approved_and_activate_with_no_test_run` and `test_a_version_without_a_finalized_reference_still_needs_its_test_evidence` on PostgreSQL 16 (84 Rules and Bookkeeping integration tests pass). Not changed: live acquisition still needs the acquisition proof of a real run (the provider-request permission, separate from activating the rules); the MySQL Rules schema keeps its proof rule, as it did for the silver exemption (migration 006)
- [x] The approvals are in git (2026-11-04 21:48 ET: operator, "the rules must also be in git"; asked: "The approvals (Recommended)"): `rules/approvals.yaml` lists each rules document's digest with the operator's exact words ("approved all rules", 2026-11-04), the merge (PR 1428) and who; `rules load` approves every saved version whose digest is listed (`edgar_warehouse/rules/approvals.py`), `rules approvals check` and `write`; 16 documents listed; tests `tests/unit/test_rules_approvals.py` (5) and `test_rules_load_approves_the_versions_the_approvals_file_lists` on PostgreSQL 16
- [x] Every source's run inputs are named in its rules: each target declares them under `run` (`facts`, `files`); `skills/data-onboarding/scripts/run_inputs.py` lists them per source and target with the comments that say how each is produced, and says when no comment does (3 tests, `tests/unit/test_run_inputs.py`; run on the rules: `gleif` and `iapd.adv` and `sec.nport.security` are described, `sec.company`'s four facts and its Name Count only in part) (2026-11-05 18:57 ET).
- [x] `sec.company`'s five run inputs are described in a comment above its `mastering` target, each from how the steps use it; `run_inputs.py sec.company` prints them; only comments changed, `rules approvals check` reports nothing missing (2026-11-05 19:16 ET).
- [x] The silver spec is registered by the load: `Loader.register_silver` runs `silver register` for each table a `silver.land` step names, as the stores' migration login, for the silver runtime login read from the worker env, before anything is submitted; the same spec changes nothing. 4 tests in `tests/unit/test_rules_loading.py` fail without the change and pass with it; run against the real stores it reported both `sec.registration` tables registered and changed nothing (2026-11-05 19:18 ET).
- [x] The capture bridge: `skills/data-operations/scripts/capture_receipts.py <folder>` writes `receipts.jsonl` for a `provider.capture` folder and never replaces one; 3 tests; on the real registration capture it wrote the same 732 receipts as the hand-written file (2026-11-05 19:18 ET).
- [x] Learning → skill: `data-onboarding` (a load registers silver itself; write each run input's origin above the target; `run_inputs.py`), `data-operations` ("Load a capture": silver registration and `capture_receipts.py`).
