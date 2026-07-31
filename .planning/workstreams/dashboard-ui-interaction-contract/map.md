# Dashboard UI Interaction Contract

## Destination

Specify one observable, subject-oriented input/output contract and a UI interaction
test matrix for every dashboard tab, so a symbol such as `AAPL` has a consistent,
testable outcome without depending on a pipeline run or release readiness.

## Notes

- This is a dashboard usability and interaction-testing workstream. It is separate
  from the production-release dashboard acceptance artifact and from data-completeness
  or pipeline validation.
- A **Subject Input** accepts a ticker, company name, or CIK. A **Subject Resolution**
  returns either one canonical CIK or a bounded set of disambiguation choices.
- Company 360, Fundamentals Screener, and Insider Watch share the Subject Input.
  Summary and Pipeline remain non-subject tabs; ADV retains its adviser/fund resolver.
- The canonical SEC company-ticker snapshot must be exposed through a bounded
  dashboard read view. It is the source for ticker resolution; the empty
  `TICKER_REFERENCE` export must not make an otherwise resolvable ticker disappear.
- Each tab must return one observable output state: `results`, `no_coverage`,
  `no_match`, or `unavailable`. `no_coverage` is not `no_match` and is never
  reported as a pipeline failure.
- UI interaction tests must exercise the rendered tab input and output state,
  separately from SQL contract tests and release-evidence checks.

## Decisions so far

- [Use a bounded canonical SEC ticker resolver](issues/01-decide-canonical-subject-resolver.md)
  — confirmed: `AAPL` resolves through the canonical SEC ticker snapshot rather
  than the currently empty `TICKER_REFERENCE` export.
- [Define tab subject-input and observable-output contract](issues/02-define-tab-subject-input-output-contract.md)
  — subject tabs share a mode-stable resolver and every tab exposes explicit
  `results`/`no_coverage`/`no_match`/`unavailable` output semantics; Summary and
  Pipeline stay non-subject.
- [Select the rendered dashboard UI test seam](issues/03-select-rendered-ui-test-seam.md)
  — use Streamlit AppTest plus a deterministic fake Snowpark session for widget
  interaction assertions; retain fake-Streamlit policy tests, and reserve a
  browser only for explicitly authorized live acceptance.

## Not yet specified


## Out of scope

- Repairing or backfilling fundamentals, ticker-export, or other pipeline data.
- Release-readiness attestation, agent-grade promotion, and pipeline execution.
