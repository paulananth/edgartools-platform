# Ongoing data operations skill

Status: research and skill documentation complete; runtime automation is not
implemented by this ticket. Operator requests research of existing skills and a named
ongoing skill for available-source processing, load sizing, Bookkeeping and
Change Journal coordination, and source-file changes. Acquisition remains AWS-owned.

## Parts

- [x] Isolate work and inspect current skills/runtime ownership. Dedicated `codex/data-operations-skill-20261017` at `f0a8709f`; existing data-platform, Bookkeeping, Journal, changed-file selector and package installer inspected. 2026-10-17 13:03 ET.
- [x] Research external skill alternatives against primary sources; record bounded-search findings and links. Six actual skill texts examined, two CLI searches; findings in `docs/research/data-operations-skill-landscape.md`. 2026-10-17 13:07 ET.
- [x] Create `data-operations` as a recurring operational coordinator, with resource sizing, readiness/change decisions, recovery and a maintained runbook. Skill Creator validation passed; unavailable runtime features explicitly identified. 2026-10-17 13:07 ET.
- [x] Add discovery pointers and verify bundle inclusion, links and real CLI examples without altering global skills or shared stores. Actual offline wheel, isolated installer checks, all new links/commands valid; 17 affected tests passed in 2.50 s, nine unchanged deselected. 2026-10-17 13:07 ET.
- [x] Exercise realistic scenarios independently: unchanged/renamed files, incomplete deliveries, active leases, capacity pressure and pending Journal delivery. Independent agent preserved ownership/pins, selected renamed inputs safely, bounded concurrency and watch, and withheld completion for pending receipts; no defects found. See VERIFICATION.md. 2026-10-17 13:07 ET.
- [x] Review Standards, Spec and GoF; record validation and remaining runtime gaps. Three independent reviews found no actionable issues; VERIFICATION.md separates instruction/package evidence from live qualification. 2026-10-17 13:07 ET.
- [x] Learning → skill: new `data-operations`, recurring loop and RUNBOOK.md. Ongoing load management uses existing durable owners rather than introducing a scheduler or parallel control store; renamed keys remain eligible under today's selector. 2026-10-17 13:07 ET.

## Scope

New skill and supporting runbook, primary-source research, and short routing
pointers. No runtime changes, provider requests, source activation, source data
processing, global skill replacement, infrastructure changes or schema changes.
Company's existing readiness/activation gap is retained, not claimed fixed by
writing a skill. The skill supports authorized recurring operation when invoked;
it does not install a resident agent or autonomous scheduling service.
