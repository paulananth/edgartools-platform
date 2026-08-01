# Make daily-incremental optional input routing total

Type: task
Status: claimed
Blocked by: none

## Question

How must the `daily_incremental` state machine preserve and route optional
operator input so an ordinary `{}` execution and explicit repair overrides both
reach the full downstream chain?

## Direct evidence

The production execution
`daily-incremental-ticket03-1785413694` ran from 2026-07-30 12:14:56 UTC to
2026-07-31 01:35:12 UTC. `Stage0CompanyIdentity` and `RunWarehouseTask` both
completed, and the warehouse container exited 0. The execution then failed in
`ForceCheck` with `States.Runtime` because `$.force` was absent:

```text
Invalid path '$.force': The choice state's condition path references an invalid value.
```

The deployed definition and current `main` both use `BooleanEquals` on
`$.force` without an `IsPresent` guard. `RunWarehouseTask` also replaces the
state input with the ECS result, so an explicitly supplied `force` value would
not survive to the later choice.

## Required work

- Preserve the original optional execution input across `RunWarehouseTask`, or
  explicitly carry the required operator fields through its result boundary.
- Make `ForceCheck` and `FirmRosterForceCheck` total for absent, false, true,
  malformed, and preserved explicit values; ordinary `{}` input must select the
  non-forced path without a runtime error.
- Apply the same rule to duplicated state-machine definitions where the same
  optional-input contract exists; do not fix only one generated definition.
- Add architecture tests that execute the generated Choice semantics for `{}`
  and explicit `force` inputs and prove later states see the intended value.
- Keep malformed operator input fail-closed with a named validation disposition
  rather than silently treating an invalid value as false.
- Bind manual evidence to the deployed definition revision and show the full
  chain advances beyond both force choices.

## Done when

Focused tests and one immutable-Release-Candidate execution prove ordinary
`{}` input and explicit repair inputs route deterministically through the ADV
and firm-roster stages without `States.Runtime`, while malformed input fails
before workload execution with an operator-readable reason.

## Answer

The generated contract must validate `force` before any ECS workload, normalize
an omitted value to `false`, reject a present non-boolean value through the
named `InvalidForceInput` fail state, preserve the normalized operator envelope
through every task before the ADV choices, and make both `ForceCheck` and
`FirmRosterForceCheck` independently total for absent, false, true, and
malformed values. The same contract applies to both the `daily_incremental` and
`load_history` definition builders.

## Progress

- 2026-07-31: Implemented the total optional-input contract and generated-Choice
  behavior tests in PR #319. Local focused verification passed 66 tests; the
  complete unit + architecture suite passed with the `mdm-runtime` extra; all
  GitHub CI checks passed. PR #319 merged to `main` as
  `47005767bc9efcc677e346ab06ca53c9bb00ad0b`.
- Production resolution evidence remains pending. Keep this ticket `claimed`
  until the scheduler/alarms release candidate is deployed with the verified
  deployer principal and immutable executions prove both ordinary `{}` and
  explicit repair routing beyond the ADV and firm-roster choices.
