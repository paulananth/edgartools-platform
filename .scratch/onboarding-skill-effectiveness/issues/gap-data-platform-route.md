# Capability gap: the data-platform route is not executable

Type: task
Status: resolved
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
- [x] Publish this ticket's scoped change on its own branch and PR; affected checks passed locally. [PR #2089](https://github.com/paulananth/edgartools-platform/pull/2089) (2026-11-23 21:46 ET).
- [x] Learning → skill: Data Platform's entrypoint now routes from normalized config and retained evidence through the executable command (2026-11-23 21:43 ET).

## Answer

The route was text-only. `route_next_action` now returns one owner/action pair from normalized configuration and retained run evidence. An absent `source.yaml` routes to Data Onboarding; otherwise matching completed resume phases are skipped, and the first unfinished or hash-invalidated phase is selected. Live-rule-only changes route to Refining Rules; delivery-only changes and repeat runs route to Data Operations. If both change signals are present, Data Platform asks the operator to disambiguate.

`edgar-warehouse plan route --request <file>` (or `--request -`) exposes the pure function as JSON output. It does not load data, contact providers, approve rules or switch on a version. The [Data Platform entrypoint](../../../skills/data-platform/SKILL.md#start-here-route-the-work) documents the normalized request fields and handoff.

The interface uses no GoF pattern: one deterministic route function has no configurable handler chain or alternative algorithms to justify Chain of Responsibility, State or Strategy indirection.

The [route planner pull request](https://github.com/paulananth/edgartools-platform/pull/2089) includes the implementation and evidence. Local checks passed: route behavior 10, wheel inclusion 1, skill genericity/path checks 157.
