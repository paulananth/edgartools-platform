# Person and link quality rules

Type: task (configuration, then code for the run report)
Status: open
Blocked by: 03, 14

## Question

Build ticket 03's checks:
- Person's critical checks in `rules/sources/sec.submissions.person/quality.yaml`, with tests on names with accents, apostrophes, degrees and footnote marks;
- the link checks, with the Person link engine (ticket 14);
- the three run report checks, reported and never blocking. This needs code: the GoF consult first.

The quality versions change, so each needs a test run and the operator's approval.
