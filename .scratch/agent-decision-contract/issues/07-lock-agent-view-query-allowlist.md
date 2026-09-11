# Lock Agent View query allowlist on Streamlit-in-Snowflake

Type: grilling
Status: open
Blocked by: 05, 06

## Question

How does the existing Streamlit-in-Snowflake app enforce Agent View versus
Explore so Agent View cannot run unlabeled free gold joins?

Decide:

1. Allowlist of `EDGARTOOLS_DECISION` objects Agent View may query.
2. How Explore is labeled not-for-agent / not Trading Decision input.
3. Whether the same CIK can be opened in both modes in one session.
4. What Agent View shows when the contract is not READY (empty, display
   not-ready reason, or error).

Predecessor: [SiS Agent View vs Explore](../../agent-decision-data-plane/issues/13-sis-agent-view-explore.md)
is closed as product shape; this ticket binds it to the live app and
contract objects.
