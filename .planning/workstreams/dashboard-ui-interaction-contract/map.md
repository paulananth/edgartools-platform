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
- UI interaction acceptance must exercise the built, deployed Streamlit app
  through an authenticated browser. Mocked Snowpark data and fake Streamlit
  widgets are not valid evidence for this workstream; existing unit tests may
  remain as code checks but cannot satisfy UI acceptance.
- The acceptance suite has two real layers: (1) connection integration tests
  run against a configured Snowflake connection and actual deployed/query
  objects without a browser; (2) browser E2E tests drive the deployed Streamlit
  app. Neither layer uses fake data or a mocked Snowpark session.

## Decisions so far

- [Use a bounded canonical SEC ticker resolver](issues/01-decide-canonical-subject-resolver.md)
  — confirmed: `AAPL` resolves through the canonical SEC ticker snapshot rather
  than the currently empty `TICKER_REFERENCE` export.
- [Define tab subject-input and observable-output contract](issues/02-define-tab-subject-input-output-contract.md)
  — subject tabs share a mode-stable resolver and every tab exposes explicit
  `results`/`no_coverage`/`no_match`/`unavailable` output semantics; Summary and
  Pipeline stay non-subject.
- [Reject simulated dashboard UI acceptance](issues/03-select-rendered-ui-test-seam.md)
  — user direction supersedes the earlier AppTest recommendation: only a real
  built/deployed Streamlit app exercised through an authenticated browser can
  prove the interaction contract.

## Not yet specified


## Out of scope

- Repairing or backfilling fundamentals, ticker-export, or other pipeline data.
- Release-readiness attestation, agent-grade promotion, and pipeline execution.
