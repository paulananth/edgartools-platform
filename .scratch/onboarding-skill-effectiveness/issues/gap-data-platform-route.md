# Capability gap: the data-platform route is not executable

Type: task
Status: claimed
Priority: P0
Blocked by: none
Labels: wayfinder:task
Map: [Make source-onboarding skills effective](../map.md)

## Question

Where is the function that takes a source's configuration and retained evidence and returns one next action and its owner?

## Evidence

Ticket 05's three approved scenarios need that function. The route exists only as text in [Start here](../../../skills/data-platform/SKILL.md#start-here-route-the-work) and [Resume](../../../skills/data-platform/RESUME.md). No module accepts invented configuration and returns Data Onboarding, Data Operations, Refining Rules, or the first unfinished owner.

Ticket 05 forbids adding source-specific runtime behavior inside that verification task. This separate issue is the capability gap it identified; any implementation here must remain generic across sources.

## Required behavior

One generic function, shared by every source. Inputs are invented configuration and retained artifacts: rules file present or absent, delivery changed or not, live-rule change or repeat run, and a Resume record whose hashes match or differ. Output is one owner and one next action. A completed phase whose recorded hashes match is not selected again.
## Acceptance checklist

- [x] Define one pure, source-neutral routing interface over normalized configuration and retained resume evidence; verified by the route behavior tests (2026-11-23 21:43 ET).
- [x] Implement the three operator-approved route scenarios and resume selection: matching completed phases are skipped; the first unfinished or invalidated phase is selected. Overlapping change flags stop for Data Platform clarification, per the existing Start here stop rule (2026-11-23 21:43 ET).
- [x] Expose the route through `edgar-warehouse plan route` and document its use in Data Platform's entrypoint; verified by CLI tests and the wheel-inclusion check (2026-11-23 21:43 ET).
- [x] Run affected checks: route behavior **10 passed**, wheel inclusion **1 passed**, skill genericity and path checks **157 passed** (2026-11-23 21:43 ET).
- [ ] Publish this ticket's scoped change on its own branch and PR; verify the merged head.
- [x] Learning → skill: Data Platform's entrypoint now routes from normalized config and retained evidence through the executable command (2026-11-23 21:43 ET).
