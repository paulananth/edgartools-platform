# Portable pipeline orchestration and production support skills

Status: implemented and locally validated; publishing the review handoff.

## Parts

- [x] Inspect current code and rebase the dedicated skill branch — 2026-10-29 06:53 ET: fresh Codex worktree rebased onto ca67e441; shared dirty checkout untouched; read-only inventory identifies missing scheduler/dispatcher/workflow builder.
- [x] Record settled orchestration responsibilities — 2026-10-29 06:53 ET: per-pipeline schedules; AWS and local Docker proof; configured dependency order/concurrency; independent work continues after failure; overlapping triggers coalesce through existing control; Bookkeeping owns state/recovery and Change Journal owns receipts. New sources route to owning skills for complete pipeline/mastering build and test before scheduled admission.
- [x] Record production-support requirements — 2026-10-29 06:53 ET: job/CPU/memory/log monitoring, efficiency insights, 5-whys or appropriate RCA; architecture and security experts must be consulted for a holistic diagnosis; only preapproved bounded runbook actions execute automatically.
- [x] Research cost-effective high-performance execution against primary sources, with architecture and security consultation — 2026-10-29 06:55 ET: two cited research notes cover measured container sizing, throughput/concurrency, retry-adjusted Spot economics, native architecture qualification, telemetry scope, trust boundaries and bounded existing-runbook actions; no deployment or benchmark result is claimed.
- [x] Settle the remaining material operator choices one question at a time and confirm shared scope before implementation — 2026-10-29 18:16 ET: operator confirmed cost minimization within deadlines, bounded alert/review invocation and the full two-skill/agent scope.
- [x] Create source-neutral orchestration and production-support skills plus the appropriate agent definitions, with existing capability gaps stated precisely — 2026-10-29 18:16 ET: two discoverable skills and three canonical Luna/low TOML roles; project discovery links; no runtime or global-configuration mutation.
- [x] Validate skill behavior, packaging/discovery and agent configuration without deploying live infrastructure — 2026-10-29 18:16 ET: both skill validators; source-neutrality lint (86 initial passes plus corrected case passing on testmon rerun); two independent forward tests; TOML parsing and fresh CLI role-name discovery; two wheel builds and isolated installed-bundle copy with 23 relative links checked.
- [x] Review Standards, Spec and GoF and qualify declared local validation — 2026-10-29 18:16 ET: independent review below; business-calendar finding corrected; no code refactor or deployment claim.
- [ ] Publish the scoped result in a PR and verify its checked head.
- [x] Learning → skill — 2026-10-29 18:16 ET: pipeline-orchestration owns schedule/calendar, control boundaries and platform qualification; production-support owns bounded investigations, mandatory expert review, action authority and retry-adjusted cost guidance. Verified by forward tests and skill validation; existing shared skills untouched.

## Scope boundary

The requested deliverables are reusable skills and agent definitions. Creating
these artifacts does not itself install timers, collect production telemetry,
activate sources or deploy infrastructure. Existing permissions and supported
commands govern those actions when invoked. No additional execution state store,
checkpoint system or shutdown protocol belongs here.

## Settled optimization objective

Choose the lowest total cost that meets each pipeline's configured deadline
and correctness requirements. Include startup, storage/data transfer and
interruption/retry overhead in the comparison. Faster execution alone does not
justify higher cost when the configured deadline is already met.

## Review

### Standards

New skills are source-neutral and remain in the bundled skills tree. No existing
runtime's files were edited. The overlap guard passed before publication.
Instructions preserve provider access, source activation and deployment gates.
Project agent links expose the canonical bundled TOML definitions without copying
prompts; only these three ignored-path links are explicitly added to Git.

### Spec

The two skills cover per-pipeline schedules, approved-platform lifecycle,
configuration-first new-source routing, existing-source evidence reuse,
coalescing/failure isolation, resource economics, bounded alert/review invocation,
and job/CPU/memory/log RCA with both expert consultations. Existing control owns
state and recovery. No universal scheduler, deploy builder, monitoring integration
or platform runtime has been implemented or qualified by this instruction change.

Independent scenarios correctly held an unqualified new source and a missing
workflow builder, reused existing-source evidence conditionally, and returned an
incomplete incident diagnosis with no restart when telemetry/expert evidence was
missing and logs contained an instruction injection. Business-day schedules now
require an explicit calendar and holiday policy.

### GoF

The pattern-selector consult and available gof-refactor-reviewer method support
leaving execution code intact: these are new instruction/configuration artifacts,
not evidence of repeated code branching. Existing discovery and bundle install
already accept additional skills; adding adapter classes, a state machine or a
registry would add cost without proving a required gap. Platform-specific guidance
is disclosed in one reference; canonical role prompts are linked, not duplicated.

## Qualification limits

Local validation proves instruction behavior, syntax, relative links, wheel
contents/copy and role-name visibility in a fresh Codex CLI context. It does not
prove IAM enforcement, production telemetry, alert wiring, AWS/Docker execution,
source activation, cost savings or a hot reload in an existing session. Custom
agent instructions inherit parent permissions; restricted credentials/tools and
a read-only parent are required for operational use. CI remains a merge gate.
