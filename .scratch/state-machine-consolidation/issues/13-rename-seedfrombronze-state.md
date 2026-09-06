Type: grilling
Status: open

**Spawned by:** user note during [Ticket 11](11-decide-bronze-seed-silver-gold-default-path-fate.md)'s live AWS cutover (2026-09-06), while renaming the outer machine `bronze_seed_silver_gold` -> `one_click_data_refresh`.

## Question

`one_click_data_refresh`'s (formerly `bronze_seed_silver_gold`'s) head state, `SeedFromBronze`, is the one remaining internal state name that wasn't given a business-friendly name in the earlier BatchSilver/GoldRefresh -> "Clean and Merge Filings"/"Publish Business Data" rename this session. Pick a business-friendly replacement name (ASD-STE100-style, matching the sibling states' naming convention) and apply it the same way: `deploy-aws-application.sh`'s `seed_from_bronze` state dict key/`Next`-pointers, `install.sh`'s prose, CLAUDE.md/CONTEXT.md live architecture references, and any test asserting the literal state name.

Same scope-narrowing discipline as the earlier rename applies: confirm via grep exactly which files reference `SeedFromBronze` as a live state name before touching anything, and leave historical/frozen records (`.planning/`, `.scratch/`, `docs/release-readiness/`, CLAUDE.md's dated 5-whys narratives) untouched.

## Answer

_(pending)_
