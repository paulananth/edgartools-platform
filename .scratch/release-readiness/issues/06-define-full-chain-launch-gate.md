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

### Ordered gate set (one production execution under a new execution name)

1. **Candidate Identity Binding** (01) — opens the Candidate Evidence Set at
   `docs/release-readiness/releases/rc-<YYYYMMDD>-<12-char-commit>/` for the
   RC commit + warehouse/MDM image digests.
2. **Rollback-readiness check** (05, standing precondition, not per-candidate)
   — gate confirms the standing rollback proof matches the current rollback
   mechanism before any pipeline work starts. This is a cheap fail-fast check
   based on mechanism identity, not a calendar expiration; 05 defines what
   proves it.
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

**Cross-cutting, not a numbered stage:** Release Evidence Automation (09)
runs alongside stages 1–8, assembling each stage's evidence into the
Candidate Evidence Set as it's produced. **GO Packet assembly is the
downstream decision workflow defined by ticket 08, not a ninth gate.** The
candidate becomes ready for the Release Owner only after automation validates
the complete eight-gate set; GO itself remains an explicit human decision.

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

After stage 8, Release Evidence Automation writes
`full-chain-launch-pass.json` into the Candidate Evidence Set
(mirrors ticket 03's `maxconcurrency4-data-integrity.json` naming), an
ordered array of the eight required gates each with `{stage, status, evidence_ref,
completed_at}`, plus the rollback-readiness precondition result. Overall
`status: "pass"` requires every entry `pass` with zero exclusions. This is
the artifact ticket 08 (GO Packet) reads.

**Correction (2026-07-29):** ticket 08's later, more specific packet decision
supersedes this Answer's original classification of GO Packet assembly as
stage 9. The launch gate has eight required gates; packet assembly validates
and indexes their results without becoming another gate.

### Note — INSTITUTIONAL_HOLDS = 0 is a reader-registration bug, not a fetch gap

**Correction (2026-07-26, superseding this note's original text):** the
EDGE-11 finding cited here as "bulk fetch never selects 13F-HR" is stale.
Live prod evidence: `EDGARTOOLS_PROD.EDGARTOOLS_SOURCE.SEC_THIRTEENF_HOLDING`
already has **6.8M rows** — the fetch/parse pipeline works and has run at
scale. The real cause, confirmed against prod CloudWatch logs
(`mdm-mdm-large/edgar-warehouse/7fd06878e8254bcab9cbdb4263066ab8`,
2026-07-25T23:26:52Z): `{"event": "mdm_relationship_skip", "rel_type":
"INSTITUTIONAL_HOLDS", "reason": "missing_source_table", "source_table":
"sec_thirteenf_filing"}`. MDM's relationship-derive step reads silver
through `ShardedSilverReader` (`edgar_warehouse/silver_support/sharded_reader.py`),
which only exposes tables listed in its hardcoded `_TABLES` allowlist as
cross-shard UNION ALL views. `sec_thirteenf_filing` was added to the schema
in the same commit as `sec_thirteenf_holding` (d20cad8) but never added to
`_TABLES` — so the derive query's JOIN against it raises a DuckDB catalog
error, which `_find_missing_source_table`'s deliberately-broad exception
matching (see its own comment) swallows as a legitimate "not loaded yet"
skip. A registration bug and an empty universe are indistinguishable through
that path — exactly the "unproven zero" stage 7 exists to reject. Same bug
also silently drops `sec_employment_event` (the EDGE-09 sibling gap for
EMPLOYED_BY's Item 5.02 8-K path).

Fix: add both table names to `_TABLES`
(`edgar_warehouse/silver_support/sharded_reader.py`) — a one-line
registration fix, not a fetch/parse change. No new SEC fetching is needed;
the source data already exists in the shards. Regression test:
`tests/unit/test_sharding.py::test_sharded_silver_reader_exposes_thirteenf_filing_and_employment_event`.

Because stage 7 has no exclusion valve, this gate **cannot reach Pass**
until the fix is deployed and `derive-relationships` is re-run for
INSTITUTIONAL_HOLDS (and EMPLOYED_BY's 8-K path). That is a deliberate
consequence of inheriting ticket 04's rule, not something 06 needs to
soften — it surfaces the real blocker instead of hiding it behind a
documented-exclusion escape hatch.
