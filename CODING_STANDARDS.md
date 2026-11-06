# Coding standards

Read during review. Each rule here is one a reviewer enforces on a diff.

- **Engine-only SQL lives in `edgar_warehouse/mastering/store.py`, and only when measured.** Mastering
  works on any database: standard SQL first, and an engine-only statement needs its measured cost
  in the PR.
- **A long run holds no transaction open.** One read held across a replay stops deleted rows being
  cleaned, so each page has its own read.
- **Write a row once.** An insert followed by an update of the same row leaves one dead row per record.
- **A new package reaches a wheel**, or `tests/unit/test_wheels_ship_every_package.py` names why not.
