# Review findings 5 and 6: GLEIF batch size and missing former names

Type: task (AFK)
Status: open
Blocked by: none

## Question

These come from the 2026-09-30 database review (`docs/specs/database-design-review-2026-09-30.md`):
- **Finding 5:** size GLEIF batches by bytes, under the 16 MiB cap; 1,000 records came to 43 MB.
- **Finding 6:** the Name Census should treat a missing former-names member as none.

Both are small code fixes with a GoF consult, tests and a PR.
