# Define the Full-Chain Launch Gate

Type: grilling
Status: resolved
Blocked by: none

## Question

What exact ordered stage set, stop conditions, correctness assertions, and evidence must all pass for one release-candidate production execution to qualify as a Full-Chain Launch Pass?

## Dependency note (hygiene 2026-07-26)

Relationship-data **implementation** tickets 16–23 are **resolved** (including
Ticket 20 technical PASS 2026-07-25 and ADV private-fund 21). Insider-scoped
EMPLOYED_BY completeness engineering is **24** (resolved). This gate ticket is
no longer blocked on those tasks; it must still **define** the ordered pass
criteria that incorporate their evidence plus residual holds graph fill,
dashboard acceptance, rollback rehearsal, and GO packet.

## Answer

The gate is a **reusable template**, parameterized by Release Candidate (RC) —
not bound to today's Ticket 20 or residual-full execution specifically.
Binding a specific candidate's evidence to this gate is ticket 08's (GO
Packet) job, not 06's.

### Ordered stage set (one production execution under a new execution name)

1. **Candidate Identity Binding** (01) — opens the Candidate Evidence Set at
   `docs/release-readiness/releases/rc-<YYYYMMDD>-<12-char-commit>/` for the
   RC commit + warehouse/MDM image digests.
2. **Rollback-readiness check** (05, standing precondition, not per-candidate)
   — gate confirms an unexpired rollback rehearsal exists for the current
   rollback mechanism before any pipeline work starts. Cheap fail-fast check;
   05 itself defines the rehearsal cadence/trigger and what proves it, not 06.
3. **MdmExport Preflight** (02/10) — same-runtime, non-mutating entitlement
   check of rotated secret + warehouse before any export runs.
4. **BatchSilver @ MaxConcurrency=4 + Integrity Proof** (03) + contention-safe
   publication (11) — `maxconcurrency4-data-integrity.json` evidence; fails
   closed unless all Map children succeed at exactly MaxConcurrency=4.
5. **Relationship Source Completion** (12–15) — per-relationship-type
   accession-level source inventory/completion ledgers (EMPLOYED_BY,
   INSTITUTIONAL_HOLDS, MANAGES_FUND, HAS_PARENT_COMPANY, AUDITED_BY).
6. **MDM run + relationship derivation + graph sync** (16–24 execution
   procedures) — includes residual-holds fill as one of the mechanisms that
   populates ticket 04's eleven relationship types, not a separate family.
7. **Relationship Eligibility & Hosted Graph Parity** (04, residual-holds
   folded in) — **strict inheritance of ticket 04's rule, no exclusion
   valve.** All eleven relationship types required; no excluded types, no
   unresolved/missing candidates, no unproven zero classifications. Fails
   closed under the current data state because INSTITUTIONAL_HOLDS is 0 (see
   Note below) — that is intentional, not a gap in this gate's design.
   INSTITUTIONAL_HOLDS parity is an adviser→security edge keyed by **CUSIP**
   (security identity), distinct from the CIK-keyed company checks elsewhere
   in this stage.
8. **Release-Bound Dashboard Acceptance** (07) — dashboard reads back
   correctly against this candidate's fully assembled data; runs last among
   data stages since it's the first check that reads the complete result.
9. **GO Packet assembly** (08) — final evidence packet presented for the
   explicit human GO decision. GO is never automated by this gate.

**Cross-cutting, not a numbered stage:** Release Evidence Automation (09)
runs alongside stages 1–8, assembling each stage's evidence into the
Candidate Evidence Set as it's produced. Its own done-condition ("manifest
fully assembled") is a precondition for stage 9, not a checkpoint with
pass/fail semantics on pipeline data.

### Stop conditions

Full-chain success is mandatory (per CLAUDE.md doctrine) — any single stage
failure halts the chain; no downstream stage waives an upstream failure, and
no stage's success substitutes for another's. On failure, the next attempt
always starts under a **new execution name** (never redrive/resume a failed
execution in place, per the 2026-07-26 handoff instruction). This is not a
stateful "resume" feature the gate needs to build: stages 3–6 are already
idempotent (BatchSilver dedup, relationship completion ledgers, no
unintended SEC refetch), so a fresh execution naturally skips already-
completed work rather than truly redoing it.

### Evidence artifact

Stage 9 writes `full-chain-launch-pass.json` into the Candidate Evidence Set
(mirrors ticket 03's `maxconcurrency4-data-integrity.json` naming), an
ordered array of the 9 stages each with `{stage, status, evidence_ref,
completed_at}`, plus the rollback-readiness precondition result. Overall
`status: "pass"` requires every entry `pass` with zero exclusions. This is
the artifact ticket 08 (GO Packet) reads.

### Note — INSTITUTIONAL_HOLDS = 0 is a known, undeployed gap, not new work

EDGE-11 (`.planning/workstreams/fix-pipelines/REQUIREMENTS.md`) already
root-caused this: the bulk artifact-fetch pipeline never selects 13F-HR
forms for fetch, so `sec_thirteenf_holding` is never populated. A fast-path
fix is committed but undeployed, blocked on a deferred fetch-volume/cost
decision — not a diagnosis gap. Because stage 7 has no exclusion valve, this
gate **cannot reach Pass** until that fix ships and INSTITUTIONAL_HOLDS is
populated. That is a deliberate consequence of inheriting ticket 04's rule,
not something 06 needs to soften — it surfaces the deferred cost decision as
real pressure on the release timeline instead of hiding it behind a
documented-exclusion escape hatch.
