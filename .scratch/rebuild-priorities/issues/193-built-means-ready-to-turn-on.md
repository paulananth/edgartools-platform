# 193: A built source is ready to turn on

Priority: 193. Map: [Rebuild priorities](../map.md). Opened 2026-11-04 21:15 ET (operator, 2026-11-04: "this is idiotic when you build it
you need all of this once proved it is just turn on and go make this rule in the skill").

Type: task. Status: open. Blocked by: none.

## Question

Activating a source in a new store should be save, record proof, approve, activate, load, with nothing to prepare. Today
the proof lives in the Rules Database of the store where the test ran, so a new store (`local-test-server`, 2026-11-04)
had every rules version as a draft and no proof, and each source would need its own test again. What does a built source
carry so that any store can turn it on at once?

## Parts

- [x] The rule is in the skill (2026-11-04 21:15 ET): data-onboarding SKILL.md, "Built means ready to turn on", and the switch-on mode names it
- [x] ~~The proof and the approval evidence of each built source are kept with it~~ replaced by the operator's ruling (2026-11-04 21:26 ET: "you dont need proof to activate once the rules are finalized"; asked: "Rules merged on main"): rules merged on `main` are final, and `rules approve --finalized <merge>` approves them on the operator's words with no test run, then `rules activate`. Migration 007 (Rules Database: `finalized_ref`; the trigger accepts the approval and the activation with no proof), `Rules.approve(finalized=)`, `finalized_holds` in the processing authority and in the run-start gate (`Bookkeeping.start`), `rules approve --finalized`; tests `test_rules_finalized_on_main_are_approved_and_activate_with_no_test_run` and `test_a_version_without_a_finalized_reference_still_needs_its_test_evidence` on PostgreSQL 16 (84 Rules and Bookkeeping integration tests pass). Not changed: live acquisition still needs the acquisition proof of a real run (the provider-request permission, separate from activating the rules); the MySQL Rules schema keeps its proof rule, as it did for the silver exemption (migration 006)
- [ ] Every source's run inputs are named in its rules (the facts and files its target needs, how each is produced, where its captures are); `sec.company` needs a Name Count file, a catalog capture run, an observation time and a load mode today, and nothing in the rules says how they are made
- [ ] Learning → skill
