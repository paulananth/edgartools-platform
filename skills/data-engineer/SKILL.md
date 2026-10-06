---
name: data-engineer
description: Move captured files through the workers and run control that already exist, and stop when a profile does not resolve. Use when the operator wants captured files read, combined, prepared, merged, or published, or wants a run inspected or resumed.
---

# Data engineer

The boundary is [REQUIREMENTS.md](REQUIREMENTS.md). Read it before running anything. The runtime split is in [the runtime account](../../docs/research/claude-codex-runtimes-2026-10-06.md).

This skill moves captured data. It does not decide structure and it does not approve a rules version.

**Hand off when:**

- the feed has no rules file yet: [data-onboarding](../data-onboarding/SKILL.md)
- the question is what a part is: [data-modeling](../data-modeling/SKILL.md)
- a live mapping, quality check, or matching rule should change: [refining-rules](../refining-rules/SKILL.md)
- the files have not been profiled: [data-profiling](../data-profiling/SKILL.md)
- the question is what the data shows: [data-scientist](../data-scientist/SKILL.md)
- a defect must become a check: [data-quality](../data-quality/SKILL.md)
- the step is a custom parse the engine cannot state: [data-platform](../data-platform/SKILL.md) Mode 6, then stop for a pull request

The parse and master order, the setup, and the logins are in [data-platform](../data-platform/SKILL.md). Contract grammar is in [READING.md](../data-platform/READING.md). Combination is in [COMBINING.md](../data-platform/COMBINING.md). Do not copy those files and do not edit them. Run control is [bookkeeping](../bookkeeping/SKILL.md). Delivery recovery is [change-journal](../change-journal/SKILL.md).

## Hard stops

| Never | Instead |
|---|---|
| Approve a version or switch one on | Follow data-onboarding [APPROVE.md](../data-onboarding/APPROVE.md) and let the operator decide |
| Invent a command or a profile | `workers describe` must resolve it. If it does not, report the gap |
| Run a step another way because its worker is missing | Record unfinished implementation and stop that step |
| Retire a reader or activate a source from a qualification note | [READING.md](../data-platform/READING.md) says which proofs are still open |
| Edit the source engine, READING.md, COMBINING.md, or PR #834 | Those paths belong to Codex |
| Load silver or RDM by a new command | Neither writer exists. Say so |
| Request `sec.gov`, or print a secret | Use captured files and the variables the other skills name |

## Workflow

1. **Name the source and the feed.** If either is missing, ask once and stop.
2. **Check the install and the binding.**

   ```bash
   edgar-warehouse doctor
   edgar-warehouse plan resolve-feed --source <source> --feed <feed>
   ```

   `doctor` must be ok before a run. `resolve-feed` returns the Rules digest and the targets. It does not authorize the run.
3. **Describe every profile the pipeline declares** before work starts:

   ```bash
   edgar-warehouse workers describe <profile>
   ```

   A profile that does not resolve is a blocker. Do not substitute another command.
4. **Run the declared steps** in the order data-platform gives, on the `run_id` from `rules run` in that skill. For each profile that resolved:

   ```bash
   edgar-warehouse workers work <profile> <run_id> --limit 100
   edgar-warehouse workers verify <profile> <run_id> --reports <uri> --limit 100
   ```

   Repeat until that profile's units are verified. `--limit 100` bounds one invocation. It does not prove the step finished. Use the worker login for work and the verifier login for verify, as data-platform states.
5. **Inspect or resume** with bookkeeping. Do not restate its recover procedure.

   ```bash
   edgar-warehouse bookkeeping status <run-id> --limit 100
   edgar-warehouse bookkeeping resume <run-id>
   ```

   After resume, run the workers again. Journal delivery goes to change-journal.
6. **Report** the run id, which profiles verified, and every profile or target that is still unfinished. Company full mastering and GLEIF archive and XML retirement stay unfinished until their own proofs say otherwise. Do not call a partial read a completed mastering.
