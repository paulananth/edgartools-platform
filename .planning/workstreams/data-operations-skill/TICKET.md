# Ongoing data operations skill

Status: [PR #1049](https://github.com/paulananth/edgartools-platform/pull/1049) published; CI genericity fix in progress. Runtime automation
is not implemented by this ticket. Operator requests research of existing skills and a named
ongoing skill for available-source processing, load sizing, Bookkeeping and
Change Journal coordination, and source-file changes. Acquisition remains AWS-owned.

## Parts

- [x] Isolate work and inspect current skills/runtime ownership. Dedicated `codex/data-operations-skill-20261017` at `f0a8709f`; existing data-platform, Bookkeeping, Journal, changed-file selector and package installer inspected. 2026-10-17 13:03 ET.
- [x] Research external skill alternatives against primary sources; record bounded-search findings and links. Six actual skill texts examined, two CLI searches; findings in `docs/research/data-operations-skill-landscape.md`. 2026-10-17 13:07 ET.
- [x] Create `data-operations` as a recurring operational coordinator, with resource sizing, readiness/change decisions, recovery and a maintained runbook. Skill Creator validation passed; unavailable runtime features explicitly identified. 2026-10-17 13:07 ET.
- [x] Add discovery pointers and verify bundle inclusion, links and real CLI examples without altering global skills or shared stores. Actual offline wheel, isolated installer checks, all new links/commands valid; 17 affected tests passed in 2.50 s, nine unchanged deselected. 2026-10-17 13:07 ET.
- [x] Exercise realistic scenarios independently: unchanged/renamed files, incomplete deliveries, active leases, capacity pressure and pending Journal delivery. Independent agent preserved ownership/pins, selected renamed inputs safely, bounded concurrency and watch, and withheld completion for pending receipts; no defects found. See VERIFICATION.md. 2026-10-17 13:07 ET.
- [x] Review Standards, Spec and GoF; record validation and remaining runtime gaps. Three independent reviews found no actionable issues; VERIFICATION.md separates instruction/package evidence from live qualification. 2026-10-17 13:07 ET.
- [x] Add configuration promotion and skill-location guidance requested in the follow-up; reuse the existing lifecycle and approvals, identify release-transfer/runtime gaps. Final independent promotion scenario distinguishes exact source evidence, mismatched merge versions and missing readiness; no unsafe action. 2026-10-17 13:35 ET.
- [x] Synchronize with main, verify the final packaged documentation and promotion scenarios, and review Standards/Spec/GoF before publishing. Rebased onto `8d9772ae`; all 26 named affected tests passed in 5.38 s with testmon, final wheel/install/link/command checks passed and three final reviews clean. 2026-10-17 13:35 ET.
- [x] Publish the PR and verify its reviewed head and description. PR #1049 is open against main at reviewed head `43018acf`, with the requested promotion guidance and clean documentation-sync check; this checklist-only commit follows. CI status is reported separately; no merge or source deployment is part of this request. 2026-10-17 13:37 ET.
- [x] Reproduce CI's generic-skill failure in the existing parameterized test and identify the source-specific statement that caused it. CI job `117460084439` reported one failed / 702 passed; local exact existing case failed at RUNBOOK.md:41 in 0.11 s because its promotion section named a specific master kind. 2026-10-17 13:43 ET.
- [x] Keep the reusable promotion guidance generic and retain source status in the work record; verify all affected skill checks and final packaging, with Standards/Spec/GoF review. All 97 named genericity/skill checks passed in 2.70 s; actual rebuilt wheel and isolated installations verified; three focused independent reviews clean. No test, runtime or CI configuration changed. 2026-10-17 13:43 ET.
- [ ] Push the correction and verify the full PR CI outcome without weakening checks.
- [x] Learning → skill: new `data-operations`, recurring loop and RUNBOOK.md. Ongoing load management uses existing durable owners rather than introducing a scheduler or parallel control store; renamed keys remain eligible under today's selector. 2026-10-17 13:07 ET. RUNBOOK.md now directs source-specific readiness status to its operational record, preserving generic instructions; existing genericity tests included in final qualification. 2026-10-17 13:43 ET.

## Scope

New skill and supporting runbook, primary-source research, and short routing
pointers. No runtime changes, provider requests, source activation, source data
processing, global skill replacement, infrastructure changes or schema changes.
Company's existing readiness/activation gap is retained, not claimed fixed by
writing a skill. The skill supports authorized recurring operation when invoked;
it does not install a resident agent or autonomous scheduling service.
