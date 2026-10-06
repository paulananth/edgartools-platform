# 04 Relationship context view and onboarding

Type: task. Phase: A. Blocked by: 01a. Map: [map](../map.md). Plan: [plan](../plan.md).

## Checklist

- [x] GoF consult: types as data justified (type tables changed in 4 of 6 commits, each new type 2-5 edits); one record per type read by plain lookups, golden test first, extract only _ultimate_parents; one algorithm validated by name 2026-10-06 07:49 ET
- [ ] mdm.relationship_context
- [ ] Relationship onboarding for any typed relationship
- [ ] Recursive parent chain matches the source
- [x] Operator ruling: relationship types as data ("Types as data (Recommended)", 2026-10-06 07:30 ET); production keeps the current policy until the new digest is approved (added 2026-10-06 07:30 ET) (policy digest becomes 1e38238f…03da4; peeled, it is 6978715f…08ae5, the active one) 2026-10-06 07:55 ET
- [x] Golden test first: the rules' types reproduce the code table exactly; relationship ids and projections unchanged (added 2026-10-06 07:30 ET) (tests/mdm/test_clean_relationship_types.py: the rules file and TYPES_V0 equal the frozen table) 2026-10-06 07:55 ET
- [x] rules/merge/relationships.yaml (one entry per type: end kinds, profile roles, capacities, hierarchy, one parent, ultimate parent, cycles), loaded into the policy and split back by write_policy; validated as strictly as kinds (added 2026-10-06 07:30 ET) (files.policy loads it, write_policy writes it back; check_types refuses 8 kinds of malformed type) 2026-10-06 07:55 ET
- [x] project() reads types from the policy; the code table and the type lists in project() are gone (added 2026-10-06 07:30 ET) (merge passes types_of(policy); a policy without the section uses TYPES_V0 so production is unchanged; a new type declared only in data is mastered, tested) 2026-10-06 07:55 ET
- [x] Inline test policies carry the types (read from the rules file) (added 2026-10-06 07:30 ET) (not needed: a policy without the section keeps TYPES_V0; the 11 inline policies pass unchanged) 2026-10-06 07:55 ET
- [ ] Rules for the view written in the agent-context spec: one row per period, role = capacity, derived links flagged, retired links left out (added 2026-10-06 07:30 ET)
- [ ] Migration 006: mdm.relationship_context and a parent-chain function with a hop limit and a cycle guard; populated-store test; COMMENT ON everything (added 2026-10-06 07:30 ET)
- [ ] Chain check that can fail: the direct-parent chain ends at the stated ultimate parent (synthetic fixture in CI; a one-off check on a local slice of the real relationship files, recorded) (added 2026-10-06 07:30 ET)
- [ ] data-onboarding REFERENCE.md: how to onboard a new relationship type (guard first) (added 2026-10-06 07:30 ET)
- [ ] ~~Remove TYPES_V0~~ follow-up: once the operator approves policy 1e38238f…03da4 and it is active, every policy carries the section (added 2026-10-06 07:55 ET)
- [ ] Review, PR, CI, merge on word
