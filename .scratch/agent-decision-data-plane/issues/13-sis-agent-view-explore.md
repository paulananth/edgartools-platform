# 13 — Streamlit-in-Snowflake Agent View vs Explore

**What to build:** Existing Streamlit-in-Snowflake app gains a mode toggle: **Agent View** reads only Decision Contract objects; **Explore** may use broader gold queries but is labeled not-for-agent so humans do not confuse free SQL with the trading contract.

**Blocked by:** 10 — Subject Feature Screen; 11 — Subject Bundle Read.

**Status:** resolved

- [x] Mode toggle is visible and sticky enough for a session
- [x] Agent View cannot run unlabeled free gold joins outside the contract
- [x] Explore Mode is explicitly labeled not agent contract / not Trading Decision input
- [x] Same CIK can be inspected in both modes for audit comparison
