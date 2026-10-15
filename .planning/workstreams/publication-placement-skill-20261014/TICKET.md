# Correct publication placement in the platform skill

Status: in progress. Source baseline: main82f4e5ce.
Scope: correct existing capability wording, with no runtime or approval change.
Found while completing codex/rust-python-database-boundaries; current AGENTS.md
requires a skill issue to have its own branch and PR.

- [x] Confirm contract2 native preparation and contract3 SQL payload_text against current source/migrations — migration018 and payloads.payload_bytes/prepare checked, with migration020's view update; 2026-10-14 22:00 ET.
- [x] Correct only the platform skill's publication placement paragraph after the shared-path ownership guard passes — prospective shared-path guard and final two-file guard passed; only the Master paragraph changes; 2026-10-14 22:00 ET.
- [x] Verify skill command resolution, exact documentation/source agreement and a clean diff —24 platform command examples resolve,0 unresolved; focused role-skill test passed in1.84s; source assertions, diff check and public PR-body credential scan clear; 2026-10-14 22:00 ET.
- [ ] Publish this dedicated skill branch and a reviewable PR with evidence.
- [x] Learning → skill — skills/data-platform/SKILL.md, Master publication paragraph: the existing native port covers contract2; contract3 uses SQL-built payload_text; all publication paths preserve committed-hash authentication. Verified against current source without adding a capability or changing approval; 2026-10-14 22:00 ET.
