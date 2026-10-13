# Person and link quality rules

Priority: 10, tier 2, the recreation proof. Map: [Rebuild priorities](../map.md). Moved from `.scratch/mastering-to-done/issues/18-person-and-link-quality-rules.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

Type: task (configuration, then code for the run report)
Status: open
Blocked by: mastering-to-done 03, mastering-to-done 14

## Question

Build ticket 03's checks:
- Person's critical checks in `rules/sources/sec.submissions.person/quality.yaml`, with tests on names with accents, apostrophes, degrees and footnote marks;
- the link checks, with the Person link engine (ticket 14);
- the three run report checks, reported and never blocking. This needs code: the GoF consult first.

The quality versions change, so each needs a test run and the operator's approval.
