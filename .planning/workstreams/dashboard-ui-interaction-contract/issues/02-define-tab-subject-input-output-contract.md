# Define tab subject-input and observable-output contract

Type: grilling (HITL)
Status: claimed
Assignee: Codex
Blocks: 04-implement-dashboard-subject-resolver-and-ui-contract-tests

## Question

For Company 360, Fundamentals Screener, Insider Watch, ADV Explorer, Summary,
and Pipeline, which inputs are accepted and which exact rendered output state
must appear for resolved data, absent coverage, no match, and unavailable data?

## Confirmed direction

Company 360, Fundamentals Screener, and Insider Watch share the Subject Input.
Summary and Pipeline remain non-subject tabs. ADV retains its adviser/fund
identifier input. The remaining decision is the precise visible output for each
of the four states.

### Accepted: resolved subject without tab coverage

When a Subject Input resolves (for example `AAPL` → Apple, CIK 320193) but a
tab has no rows, render `no_coverage` with the resolved issuer identity and a
tab-specific message such as “No financial coverage is available.” It must not
render `no_match`, an agent-readiness error, or a pipeline failure.

### Accepted: unresolved subject

For a symbol, issuer name, or CIK that the Subject Resolver cannot resolve,
every subject-capable tab renders `no_match` and no result table. The message is
“No SEC company matched '<input>'. Try ticker, company name, or CIK.”

### Accepted: technical failure after resolution

When subject resolution or a tab query fails technically, render `unavailable`.
If resolution succeeded, preserve the issuer identity and show a message such as
“Apple (CIK 320193) resolved, but this tab is temporarily unavailable. Retry
later.” Do not expose connector details, render an empty table, or use pipeline
or release-readiness wording.
