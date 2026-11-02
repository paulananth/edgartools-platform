# 161: The catalog shows each source's and entity's profile and says when it is stale

Priority: 161. Map: [Rebuild priorities](../map.md). Opened 2026-11-01 20:43 ET, from the catalog review (operator, 2026-11-01: "update the profile findings with each source and entity, profile must update when changed"; "add it to the correct openmetadata context").

Type: task. Status: resolved. Blocked by: none (160 merged).

## Question

Where does OpenMetadata hold a profile, and can the publisher write each source's and entity's profile there and report when a changed profile has not been published?

## Parts

- [x] Test the native table profile on the local server (tested 2026-11-01 21:45 ET: the PUT and the `tableProfile/latest` read-back work; I first wrote invented numbers onto a real catalog table, then deleted that profile by its timestamp and checked the table was empty again; the skill now says to use a throwaway table). Original wording: `PUT /api/v1/tables/{id}/tableProfile` with the row count and column count from `profile.yaml`; read it back with `GET /api/v1/tables/{fqn}/tableProfile/latest`
- [x] A test states the profile text (`test_a_profiled_source_says_so_and_an_unprofiled_one_says_not_yet`, `test_a_kind_table_says_which_profile_feeds_it_or_not_yet`, 2026-11-01 21:45 ET). Original wording: each source schema and each kind table says its parts, row counts when profiled, keys and the date of the approved profile, from `profile.yaml` only (counts and names, never values); a source with no `profile.yaml` says "not profiled yet"
- [x] A test states that `rules catalog check` reports (`test_publish_writes_the_profile_and_check_says_when_it_is_stale`; live: 22 differences before a publish, matched after, 2026-11-01 21:45 ET). Original wording: "profile changed, publish again" when `profile.yaml` and the live catalog differ
- [ ] ~~`overlap_guard.sh` fails when~~ deferred, no guard to write: the catalog plan is generated from `profile.yaml` on every run, so the repository cannot hold stale profile text. Staleness exists only against a live server, which only `rules catalog check` can see. Original wording: a changed `profile.yaml` leaves the catalog plan's profile text behind
- [x] `catalog.py` writes them (2026-11-01 21:45 ET); the three review axes; PR
- [x] Publish and read back: `check` matched; the OpenFIGI silver tables carry their profile; every other source says "Not profiled yet" (2026-11-01 21:45 ET)
- [ ] ~~Profile the 10 sources that have no `profile.yaml`~~ deferred: needs their captured files and its own tickets (one per source)
- [x] Learning → skill: `skills/openmetadata/SKILL.md` (where a profile shows) and `skills/data-profiling/SKILL.md` (a changed profile is published again)
  - `skills/openmetadata/SKILL.md` names the profile API and the throwaway-table rule; `skills/data-profiling/SKILL.md` step 6 publishes and checks (2026-11-01 21:45 ET).
  - Narrowed from the plan: the description text names the dataset, its parts and the profile and approval dates; the row counts are in the native profile, and the keys stay in the silver table descriptions that were already published.
