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
- [ ] The proof and the approval evidence of each built source are kept with it (counts only, beside the source) and a new store records them with the commands it already has (`rules record-proof --proof-uri`, `rules approve --proof --evidence --root`): check on one source that a fresh store goes from draft to active with no test run, and write the one command that does it for every source in the sequence
- [ ] Every source's run inputs are named in its rules (the facts and files its target needs, how each is produced, where its captures are); `sec.company` needs a Name Count file, a catalog capture run, an observation time and a load mode today, and nothing in the rules says how they are made
- [ ] Learning → skill
