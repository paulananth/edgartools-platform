# Phase 1: Production Readiness Inventory And Launch Gate Contract - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-06-13
**Phase:** 1-Production Readiness Inventory And Launch Gate Contract
**Areas discussed:** Launch blocker rules, Evidence bundle format, Production source of truth, Preflight and spend boundary, Data issue routing

---

## Launch Blocker Rules

| Question | Options Presented | User's Choice |
|----------|-------------------|---------------|
| What blocker policy should Phase 1 use? | Strict gate; Runtime-only blockers; Evidence-first blockers; Other | Strict gate |
| How should Phase 1 classify incomplete upstream workstream closeout? | Launch blocker; Warning only; Case-by-case; Other | Launch blocker |
| How should Phase 1 treat known deploy hazards with documented workarounds? | Block until guarded; Warning with workaround; Must fix code first; Other | Block until guarded |
| How should Phase 1 classify missing production artifacts or live proof? | Blocker until proven; Warning until Phase 2; Placeholder allowed; Other | Blocker until proven |
| Should any condition be allowed to pass as warning-only in Phase 1? | Only non-launch-impacting cleanup; No warnings; Broad warnings; Other | Only non-launch-impacting cleanup |
| What does an explicit waiver need to include? | Owner, reason, expiry, residual risk; Owner and reason only; No waivers; Other | No waivers |
| How should Phase 1 handle secret-safety failures in evidence or runbooks? | Hard blocker with scrub required; Block only committed secrets; Warning with redaction follow-up; Other | Hard blocker with scrub required |
| What evidence is required to mark a blocker fixed? | Re-run proof plus non-secret summary; Code/doc change only; Operator attestation; Other | Re-run proof plus non-secret summary |

**Notes:** User selected strict launch gating throughout. Launch blockers must be fixed, not waived.

---

## Evidence Bundle Format

| Question | Options Presented | User's Choice |
|----------|-------------------|---------------|
| What should Phase 1 produce as the primary launch-readiness artifact? | Gate matrix + evidence folder; Single runbook document; Minimal inventory only; Other | Gate matrix + evidence folder |
| How detailed should command evidence be? | Command + non-secret result summary; Full sanitized output; Pass/fail only; Other | Command + non-secret result summary |
| Which files should downstream planners expect Phase 1 to create? | Matrix + four evidence files; Matrix + many layer files; Matrix only; Other | Matrix + four evidence files |
| How should unresolved items be represented? | Blocking rows in the matrix; Separate blocker register; Inline notes only; Other | Blocking rows in the matrix |
| Should Phase 1 evidence files include planned commands that cannot run yet? | Yes, marked NOT_RUN with blocker reason; No; Separate future commands section; Other | No |
| Should Phase 1 include screenshots for dashboard evidence? | Optional but useful; Required; No screenshots; Other | Optional but useful |
| How should evidence handle generated JSON like infra/aws-*-application.json? | Summarize only; Include sanitized excerpts; Link only; Other | Summarize only |

**Notes:** Evidence files record commands that actually ran or were verified. Planned blocked commands are matrix blockers.

---

## Production Source Of Truth

| Question | Options Presented | User's Choice |
|----------|-------------------|---------------|
| What should Phase 1 treat as authoritative for production readiness? | Live discovery first; Manifests first; Operator-provided values first; Other | Live discovery first |
| How should Phase 1 treat a missing infra/aws-prod-application.json? | Launch blocker until live/deploy evidence exists; Warning only; Ignore it; Other | Launch blocker until live/deploy evidence exists |
| What environments should Phase 1 distinguish in the gate matrix? | Dev proof vs prod proof; Prod only; Dev-to-prod parity; Other | Dev proof vs prod proof |
| Which production identifiers should Phase 1 require before planning execution? | Account/connection/image refs; Account and Snowflake only; None yet; Other | Account/connection/image refs |

**Notes:** Production proof is required even when dev evidence exists.

---

## Preflight And Spend Boundary

| Question | Options Presented | User's Choice |
|----------|-------------------|---------------|
| What must happen before Phase 1 allows any AWS Step Functions execution or expensive Snowflake work? | Local gates first; Status-only first; Operator discretion; Other | Local gates first |
| Should --status-only checks be allowed before all gates are green? | Yes, pure read-only status is allowed; No; Only with approval; Other | Yes, pure read-only status is allowed |
| What should the checklist require before an AWS MDM E2E run starts? | Exact local gate AWS will run; Narrow Native App check only; No local gate; Other | Exact local gate AWS will run |
| How should emergency/debug execution be represented? | Allowed but not acceptance; Not allowed; Allowed with operator note; Other | Allowed but not acceptance |
| Should Phase 1 define a cost boundary for bounded production runs? | Yes, explicit limits required; No, use script defaults; Later phases only; Other | Yes, explicit limits required |

**Notes:** State-changing and paid execution require local/static readiness, production identifiers, secret-safety scan, live discovery, and strict hosted graph preflight first.

---

## Data Issue Routing

| Question | Options Presented | User's Choice |
|----------|-------------------|---------------|
| How detailed should the Phase 1 issue-routing contract be? | Concrete triage table by layer; High-level owners only; Evidence links only; Other | Concrete triage table by layer |
| What should be the first stop for an operator investigating launch data issues? | Gate matrix first; Dashboard first; CLI first; Other | CLI first |
| How should Phase 1 represent the dashboard's role? | Inspection only after gates; One-stop starting point; Optional visual aid; Other | Inspection only after gates |
| How should data issue severity map to go-live status? | Acceptance gate driven; Dashboard driven; Manual judgment; Other | Acceptance gate driven |
| Should Phase 1 assign owners by layer? | Yes, role-based owners; No owners; Named people; Other | Yes, role-based owners |

**Notes:** Operators start with CLI verification and dbt tests, then use the dashboard for read-only inspection and explanation.

---

## Agent Discretion

None.

## Deferred Ideas

None.
