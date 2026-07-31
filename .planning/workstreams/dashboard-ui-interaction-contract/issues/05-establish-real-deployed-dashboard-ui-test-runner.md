# Establish real deployed dashboard UI test runner

Type: task (HITL)
Status: open
Blocks: 04-implement-dashboard-subject-resolver-and-ui-contract-tests

## Question

How will the project build and deploy an isolated Streamlit dashboard target,
authenticate an automated browser without storing credentials in the repository,
and retain browser evidence for the subject-input/output matrix?

## Constraint

The user rejected simulated UI acceptance. Fake Streamlit, fake Snowpark, and
unit-level output assertions may not be used to prove dashboard interaction.
The runner must exercise a deployed Snowflake Streamlit app with actual browser
rendering and authenticated user interaction.
