# Every skill works lean: the seven wastes

Priority: 115. Map: [Rebuild priorities](../map.md).

Type: task (skills). Status: done (#1109 merged 2026-10-19 08:40 ET). Blocked by: none.

## Operator ruling

- 2026-10-19: "You have done proving runs 100s of times why do you need more runs how do you record for that make all skills understand 7 wastes and eliminate any of the waste from each skill", then "Do you understand 7 wastes of lean process".

## Checklist

- [x] The seven wastes in the hub skill (`skills/data-platform/SKILL.md`, "The seven wastes"), each with its form here and what to do instead; "Carry a proof forward": a version whose rules moved since its last proof, each change proven by its own merged PR, records that proof with those changes named, no new run (2026-10-19 08:25 ET)
- [x] mdm-engineering "Choose the cheapest proof" gains that row; data-onboarding's "run a step again" rule carries a proven change's proof forward (2026-10-19 08:25 ET)
- [x] Every other skill points to the seven wastes under its title (12 skills) (2026-10-19 08:25 ET)
- [x] data-onboarding: the stale "Unfinished live pipelines" history cut to what is open (2026-10-19 08:25 ET)
- [x] Each skill read for its own waste and cut in place (2026-10-19 08:28 ET):
  - bookkeeping: plan and validate skipped for an active, unchanged target (over-processing); a feed only for live acquisition; a history note cut
  - change-journal: plan and validate only when the journal or an envelope version changes
  - data-operations: a proof carried forward instead of a new test; a run over captured files names no feed
  - refining-rules: test is the cheapest proof, recorded forward when it covers the change (it said "re-run")
  - data-quality: the on_fail table decides under the standing rule approval; a question only where it cannot (it asked one per check: waiting)
  - data-modeling: an open question holds only the part it decides (it stopped the turn: waiting)
  - data-onboarding: the full installed proof only when the change needs it; no proving run when the last proof covers the source; stale pipeline history cut
  - data-platform: stale qualification history cut to the evidence versions carry forward
  - mdm-engineering, data-profiling, sql-writer, data-scientist, data-engineering-fundamentals: read; no waste beyond the pointer (data-profiling already profiles once; its narration section is the operator's)
- [x] Three-axis review (2026-10-19 08:30 ET): GoF: "carry a proof forward" was stated five times and already drifting (now one owner, mdm-engineering's last proof row, the others link to it); bookkeeping and RUN.md still required a feed (now feed only for live acquisition). Standards and Spec: how a carried proof is recorded (`record-proof` checks the digest: a new proof file, written out in the owner row); the standing rule approval had reached only data-quality (APPROVE.md and COMPLETION.md now record a passing version under it; overrules, new kinds and switch-on still ask); data-quality's hard stops contradicted its new section (fixed); data-engineering-fundamentals answers from its own file only (pointer removed). Merges after #1108, whose feed-less runs these skills describe
- [x] PR, CI, merge (after #1108): #1109 merged 2026-10-19 08:40 ET (checked 2026-10-21 21:02 ET)
- [x] Learning → skill: this ticket is the skill change, #1109 (bookkeeping, change-journal, data-modeling, data-onboarding and others) (checked 2026-10-21 21:02 ET)

## Answer

Every skill works lean (the seven wastes). Merged in #1109 (2026-10-19 08:40 ET).
