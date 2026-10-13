# SEC Company on the engine

Type: task (code)
Status: done (2026-10-13 17:31 ET): SEC Company is read on the engine from the raw capture and company_source.py and loaders/ are retired (Issue 20 L4, #905, #909; the mastering target #928-#930)
Blocked by: 15

## Question

Move SEC Company reading (`company_source.py`, the landing loaders) onto the engine:
- the 10 scalar lookups first (Codex's demonstrated case: keep the blank-value contract);
- then classification, address conversion, filing-array expansion and Company grouping. These go into configuration where the engine can state them, and stay as declared custom steps where it can't.

Prove equivalence on the pinned capture before retiring code. The source version changes, so it needs a test run and the operator's approval.
