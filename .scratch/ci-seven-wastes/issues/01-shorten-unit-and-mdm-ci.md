# Shorten Unit and MDM CI without reducing behavior coverage

Type: task
Status: claimed

## Scope

Operator: create a fresh branch, investigate the slow Unit and MDM CI job and
optimize using the seven wastes. Preserve the full test inventory and required
database acceptance. New test scenarios require operator approval before code.

## Parts

- [ ] Measure recent successful CI runs, separating startup, build and execution.
- [ ] Profile the existing affected tests and identify the root cause.
- [ ] Review the relevant code and change history using the GoF method.
- [ ] Apply the smallest measured optimization; preserve behavior coverage.
- [ ] Verify locally within five minutes per invocation and compare CI results.
- [ ] Review Standards, Spec and GoF; publish a PR with evidence.
- [ ] Learning → skill: none identified yet.

## Baseline

At base e8df6ebd3, run 44800864333 executes 2,989 passed, one skipped in
398.83 seconds; dependency installation takes 47 seconds. Runs 44797779761
and 44792230764 spend 538 and 563 seconds in the test step, with 69 and
77 seconds installing dependencies. Runner startup is seconds, not minutes.

## Investigation

Ranked hypotheses: repeated profiling work; oversized fixtures; process startup;
uncached Rust builds. Measure individual test durations before choosing a fix.
