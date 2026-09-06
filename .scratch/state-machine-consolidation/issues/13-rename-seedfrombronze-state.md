Type: grilling
Status: resolved (2026-09-06)

**Spawned by:** user note during [Ticket 11](11-decide-bronze-seed-silver-gold-default-path-fate.md)'s live AWS cutover (2026-09-06), while renaming the outer machine `bronze_seed_silver_gold` -> `one_click_data_refresh`.

## Question

`one_click_data_refresh`'s (formerly `bronze_seed_silver_gold`'s) head state, `SeedFromBronze`, is the one remaining internal state name that wasn't given a business-friendly name in the earlier BatchSilver/GoldRefresh -> "Clean and Merge Filings"/"Publish Business Data" rename this session. Pick a business-friendly replacement name (ASD-STE100-style, matching the sibling states' naming convention) and apply it the same way: `deploy-aws-application.sh`'s `seed_from_bronze` state dict key/`Next`-pointers, `install.sh`'s prose, CLAUDE.md/CONTEXT.md live architecture references, and any test asserting the literal state name.

Same scope-narrowing discipline as the earlier rename applies: confirm via grep exactly which files reference `SeedFromBronze` as a live state name before touching anything, and leave historical/frozen records (`.planning/`, `.scratch/`, `docs/release-readiness/`, CLAUDE.md's dated 5-whys narratives) untouched.

## Answer

Renamed to **Initialize From Bronze** (user-confirmed via a quick 3-option
check-in). Applied across `deploy-aws-application.sh` (the state dict key,
both `Next`-pointers, and both `Comment` strings), `install.sh`'s one live
stage-description line (its separate historical "Known gaps" block was
deliberately left with the old name, matching the precedent already
established for the earlier BatchSilver/GoldRefresh rename),
`batch_silver_resume.py`'s docstring, and two test files'
docstrings/assertions (`test_ticket20_release_state_machine.py`,
`test_batch_silver_resume.py`). `/gof-refactor-reviewer` consulted before
committing per the repo's hard rule — verdict: nothing to flag, pure
rename, zero structural change. Full suite green: 2201 passed, 5 skipped,
identical before and after.

This state name is internal JSON content within the already-deployed
`edgartools-prod-one-click-data-refresh` machine (no new AWS object,
unlike Ticket 11's outer-machine rename) — takes effect on the next
ordinary redeploy of that machine, no separate create-new/delete-old
cutover needed.
