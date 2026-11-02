# 161: The catalog shows each source's and entity's profile and says when it is stale

Priority: 161. Map: [Rebuild priorities](../map.md). Opened 2026-11-01 20:43 ET, from the catalog review (operator, 2026-11-01: "update the profile findings with each source and entity, profile must update when changed"; "add it to the correct openmetadata context").

Type: task. Status: open. Blocked by: 160 (both edit the catalog plan and the source files).

## Question

Where does OpenMetadata hold a profile, and can the publisher write each source's and entity's profile there and report when a changed profile has not been published?

## Parts

- [ ] Test the native table profile on the local server: `PUT /api/v1/tables/{id}/tableProfile` with the row count and column count from `profile.yaml`; read it back with `GET /api/v1/tables/{fqn}/tableProfile/latest`
- [ ] A test states the profile text: each source schema and each kind table says its parts, row counts when profiled, keys and the date of the approved profile, from `profile.yaml` only (counts and names, never values); a source with no `profile.yaml` says "not profiled yet"
- [ ] A test states that `rules catalog check` reports "profile changed, publish again" when `profile.yaml` and the live catalog differ
- [ ] `overlap_guard.sh` fails when a changed `profile.yaml` leaves the catalog plan's profile text behind
- [ ] `catalog.py` writes them; the three review axes; PR
- [ ] Publish and read back
- [ ] ~~Profile the 10 sources that have no `profile.yaml`~~ deferred: needs their captured files and its own tickets (one per source)
- [ ] Learning → skill: `skills/openmetadata/SKILL.md` (where a profile shows) and `skills/data-profiling/SKILL.md` (a changed profile is published again)
