# Run the cold-onboarding trial

Type: task
Status: closed (2026-09-22) — check 5 accepted as partly met
Blocked by: 08

## Question

Check 5. Give a fresh agent with no project context only the spec and one
example contract, and a source it has never seen. Record: whether it
onboards the source, how often it read engine code or asked a question
(target zero), files changed, contract length, and time. Anything it had to
ask becomes a spec fix before the destination is declared reached.

## Answer

Three rounds, each with a new fresh agent in a sandbox outside the repository,
where the runner was present only as compiled bytecode. Full report:
[trial/README.md](../trial/README.md).

- **All three onboarded their source to `version proven`**, with no engine
  read and no read outside the sandbox:
  - SEC company profiles, twice (123 and 133 lines);
  - SEC Form ADV advisers, CSV, 17,413 filings (164 lines).
- **They logged 17, 13 and 14 questions. Of those, 14, 9 and 8 were spec
  gaps**, classified one by one in [classification.md](../trial/classification.md).
  Every gap is written into `docs/specs/source-contract/spec.md`, but round
  3's fixes have not been tried by a fresh agent. Round
  3 changed source on purpose to test generality; its gaps were narrower
  (vocabulary, dates, CSV) than round 1's (how paths read JSON).
- Five runner lags were found by the trial and fixed in the prototype, and
  three runner bugs were found by its review.
- Method limits: the task text carried hints beyond the spec
  ([prompts.md](../trial/prompts.md)), and round 2 reused round 1's source.
- **Check 5 is partly met.** The target was zero questions and no round
  reached it.

## Decision

Operator, 2026-09-22: **accept check 5 as partly met; no fourth round.** The
evidence is the trend (14 → 9 → 8 gaps, narrowing from how the language reads
data to vocabulary and source-specific conventions) and three proven sources
with no engine reads. Round 3's spec fixes stay untried by a fresh agent; the
real engine's first new source is the next test of them.
