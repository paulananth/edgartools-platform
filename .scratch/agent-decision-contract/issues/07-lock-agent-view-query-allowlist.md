# Lock Agent View query allowlist on Streamlit-in-Snowflake

Type: grilling
Status: resolved
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

## Comments

- Q7 (2026-09-11): Agent View allowlist is **issuer contract only**:
  feature screen, issuer bundle (unavailable keys included), contract
  status, display status, subject resolver. Not manager bundle, not
  standalone holders/auditor views, not gold tables.
- Q8 (2026-09-11): Explore has a required persistent banner. The Agent View
  allowlist still blocks gold. Banner is the label, not the only control.
- Q9 (2026-09-11): same CIK may stay selected when switching Agent View and
  Explore in one session.
- Q10 (2026-09-11): when not READY, Agent View shows display `not_ready`
  with a reason. Ready views stay empty. No gold fallback. Not a hard error.

## Answer

Agent View queries **issuer Snowflake Decision Contract objects only**:
feature screen, issuer bundle (including `unavailable` keys), contract
status, display status, subject resolver. Not manager bundle, not
standalone holders/auditor views, not gold tables.

Explore keeps a required persistent banner. The allowlist, not the banner,
blocks gold in Agent View. The same CIK may stay selected across modes.

When the contract is not READY, Agent View shows display `not_ready` plus
a reason. Ready views return no tradeable payload. That is not an
Agent-Grade Read.
