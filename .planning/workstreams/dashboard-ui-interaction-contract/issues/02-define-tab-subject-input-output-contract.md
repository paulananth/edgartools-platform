# Define tab subject-input and observable-output contract

Type: grilling (HITL)
Status: resolved
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

### Accepted: successful subject-tab result

For `results`, render the resolved issuer identity, a visible bounded row count,
the tab's bounded data table, and an “Open in Company 360” drill-through when
the rows identify an issuer. This applies to Company 360, Fundamentals, and
Insider Watch.

### Accepted: mode-stable subject interaction

The shared Subject Input has the same resolution behavior in Agent View and
Explore. The rendered result states its active mode and readiness state; it
never silently switches mode to make a query succeed.

### Accepted: ADV interaction

ADV retains its adviser/fund resolver and entity identity but renders the same
four observable states: `results`, `no_coverage`, `no_match`, and
`unavailable`. ADV results do not drill through to Company 360 unless a future
explicit issuer relationship supports that navigation.

### Accepted: non-subject tabs

Summary and Pipeline retain their own non-subject controls. They expose the
same visible outcome vocabulary where it applies (`results`, `no_coverage`,
`unavailable`), but Pipeline status is never evidence for data completeness,
agent readiness, or the success of another tab.

## Answer

| Tab | Input | Results | No coverage | No match | Unavailable |
| --- | --- | --- | --- | --- | --- |
| Company 360 | Shared Subject Input | Resolved issuer, bounded Company 360 surfaces | Resolved issuer with the unavailable surface named | Resolver-only | Resolved issuer when available, safe retry copy |
| Fundamentals Screener | Shared Subject Input plus screen filters | Resolved issuer, row count, bounded factors, Company 360 drill-through | Resolved issuer plus “No financial coverage is available” | Resolver-only | Resolved issuer when available, safe retry copy |
| Insider Watch | Shared Subject Input plus ownership filters | Resolved issuer, row count, bounded transactions, Company 360 drill-through | Resolved issuer plus no covered transactions | Resolver-only | Resolved issuer when available, safe retry copy |
| ADV Explorer | Adviser/fund identifier | Bounded adviser/fund results | Explicit unavailable coverage | No active adviser/fund match | Safe retry copy |
| Summary | Native summary controls | Bounded summary result | Explicit unavailable coverage | Not applicable | Safe retry copy |
| Pipeline | Native pipeline controls | Bounded operational result | Explicit unavailable coverage | Not applicable | Safe retry copy |

The shared Subject Input is mode-stable: it resolves identically in Agent View
and Explore and labels the active mode/readiness without silently switching.
The interaction tests assert these visible states; they do not assert a
pipeline run, data completeness, or release readiness.
