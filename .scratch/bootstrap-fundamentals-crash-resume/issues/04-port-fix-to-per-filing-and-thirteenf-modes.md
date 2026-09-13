# 04 — Port the durable-marker fix to `per-filing` and `thirteenf` modes

**Type:** task

**Status:** open

## Question

`run_bootstrap_fundamentals_per_filing` and `run_bootstrap_thirteenf`
(`fundamentals_ingest.py`) share `entity-facts`'s exact structural shape —
same entry point (`bootstrap_fundamentals.py`), same end-of-task-only
`_publish_silver_database_if_remote` publish, same per-CIK loop pattern —
so Ticket 03's fix plausibly ports unchanged. Confirm each mode's own
per-CIK write/skip logic (candidate-manifest handling, release-mode
semantics) doesn't conflict with the new marker before assuming a
mechanical port, then apply it.

## Blocked by: 03

## Answer

(not yet resolved)
