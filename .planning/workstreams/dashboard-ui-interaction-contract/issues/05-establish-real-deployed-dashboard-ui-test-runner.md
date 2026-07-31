# Establish real deployed dashboard UI test runner

Type: task (HITL)
Status: open
Blocks: 04-implement-dashboard-subject-resolver-and-ui-contract-tests

## Question

How will the project build and deploy an isolated Streamlit dashboard target,
run real non-browser connection integration tests, authenticate an automated
browser without storing credentials in the repository, and retain evidence for
the subject-input/output matrix?

## Constraint

The user rejected simulated UI acceptance. Fake Streamlit, fake Snowpark, and
unit-level output assertions may not be used to prove dashboard interaction.

Two real suites are required:

1. **Snowflake connection integration** — run through the configured Snowflake
   connection against the real deployed/query objects, with actual data and no
   browser.
2. **Browser E2E** — exercise the deployed Snowflake Streamlit app through an
   authenticated browser session.

The suites have different seams and evidence but share the same subject-input/
output matrix. Neither is a pipeline or release-readiness test.
