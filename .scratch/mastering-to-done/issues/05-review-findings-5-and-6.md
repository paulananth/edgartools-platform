# Review findings 5 and 6: GLEIF batch size and missing former names

Type: task (AFK)
Status: in progress (Claude, branch `claude/mastering-05-review-fixes`)
Blocked by: none

## Question

These come from the 2026-09-30 database review (`docs/specs/database-design-review-2026-09-30.md`):
- **Finding 5:** size GLEIF batches by bytes, under the 16 MiB cap; 1,000 records came to 43 MB.
- **Finding 6:** the Name Census should treat a missing former-names member as none.

Both were planned as small code fixes. Finding 6 is fixed here; finding 5 has no code in the repo to change and moved to ticket 06.

## Checklist

- [x] Finding 6: GoF consult (leave the structure; only `census_filers` reads the member). A test fails first: `test_a_capture_with_no_former_names_counts_as_none`. `census_filers` now reads a missing former-name member as none, with `former_name_member_sha256` null.
  - `tests/mdm/test_clean_company_source.py` and `test_clean_name_census.py`: 56 passed.
  - testmon over `tests/mdm` and `tests/unit`: 43 passed.
  - `tests/integration/test_company_only_postgres.py`: 2 passed in 152 s.
  - 2026-10-02 12:20 ET
- [ ] ~~Finding 5: size GLEIF batches by bytes~~ deferred to ticket 06: No code in the repo builds GLEIF batches: the proof-run scripts write them into the native manifest, and `mdm.save_batch` already refuses a request over 16 MiB with a clear error. The switch-on run in ticket 06 builds the batches, so it sizes them there and measures them after the #772 review fix.
- [x] Three-axis review. 2026-10-02 12:35 ET
  - GoF: leave it.
  - Spec: finding 6 met and the finding 5 deferral accurate; the comment now says only old captures (before #764) lack the member.
  - Standards: no hard finding; the long line is split. The duplicated table lookup is left until a second member becomes optional.
- [ ] PR, CI; merge on the operator's word
