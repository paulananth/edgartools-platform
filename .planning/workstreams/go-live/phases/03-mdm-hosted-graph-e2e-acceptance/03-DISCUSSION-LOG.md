# Phase 3: MDM Hosted Graph E2E Acceptance - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-15
**Phase:** 3-mdm-hosted-graph-e2e-acceptance
**Areas discussed:** Phase 3 scope given prod AWS blocker, MDM secret population runbook (MDM-01), Acceptance-vs-debug framing for --status-only/--skip-preflight

---

## Phase 3 Scope Given Prod AWS Blocker

### Q1: Should Phase 3 follow Phase 2's D-01 "document-and-validate-only" pattern, given the same class of structural blocker (missing infra/aws-prod-application.json)?

| Option | Description | Selected |
|--------|-------------|----------|
| Document-and-validate-only (like Phase 2 D-01) | Mirror Phase 2's approach of documenting evidence without live runs | |
| Dev rehearsal run + documentation | Run the MDM hosted-graph E2E chain live on dev plus documentation | ✓ |
| Defer Phase 3 entirely | Wait until prod AWS infra is available | |

**User's choice:** Dev rehearsal run + documentation

---

### Q2: Should Phase 3 live-reproduce the run-aws-mdm-e2e.sh --env prod structural blocker (like Phase 2 reproduced the SNOW-01 backend.hcl rc=1 failure) as concrete BLOCKED-row proof?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — run --env prod --status-only live | Read-only reproduction of the missing infra/aws-prod-application.json failure | ✓ |
| No — document from source only | Describe the blocker from the script source without running it | |

**User's choice:** Yes — run --env prod --status-only live

---

### Q3: MDM-01 (production MDM Snowflake Postgres connectivity/migration/counts) — what should Phase 3 actually run, given prod Postgres secrets don't exist yet?

| Option | Description | Selected |
|--------|-------------|----------|
| Document prod commands as BLOCKED required-fix | Only document the commands that would run once secrets exist | |
| Re-verify dev MDM Postgres live as precedent | Run dev MDM Postgres connectivity/migration/counts checks live as a precedent refresh | ✓ |

**User's choice:** Re-verify dev MDM Postgres live as precedent

---

### Q4: GRAPH-01/GRAPH-02 dev precedent — is the existing 03-LIVE-DEV-RUN.md evidence sufficient to cite as-is, or should Phase 3 spot-check it's still valid?

| Option | Description | Selected |
|--------|-------------|----------|
| Cite existing evidence, no new run | Reference 03-LIVE-DEV-RUN.md as-is | ✓ |
| Spot-check dev precedent first | Re-run a portion of the dev verify-graph to confirm it's still valid | |

**User's choice:** Cite existing evidence, no new run

---

## MDM Secret Population Runbook (MDM-01)

### Q5: How deep should the secret-population runbook documentation go for the BLOCKED "MDM Snowflake Postgres secret container and connectivity" row?

| Option | Description | Selected |
|--------|-------------|----------|
| Full put-secret-value commands w/ placeholders | Complete aws secretsmanager put-secret-value commands with placeholder values | ✓ |
| Names + expected JSON shape only | Just secret names and the JSON structure they should contain | |

**User's choice:** Full put-secret-value commands w/ placeholders

---

### Q6: Which of the 4 edgartools-prod/mdm/* secrets need a population-runbook entry in Phase 3, given the dev-rehearsal + cite-dev-precedent scope decided for Phase 3?

| Option | Description | Selected |
|--------|-------------|----------|
| postgres_dsn | MDM Snowflake Postgres connection secret | ✓ |
| snowflake | Snowflake connection secret for MDM | ✓ |
| neo4j | Legacy graph container secret | |
| api_keys | API keys secret, purpose unclear | |

**User's choice:** postgres_dsn, snowflake
**Notes:** neo4j and api_keys NOT selected — neo4j documented as "not required, legacy graph container" per Phase 2 framing; api_keys deferred (purpose unclear, no population runbook entry this phase).

---

### Q7: Should the runbook use the dev MDM Postgres connection (to be re-verified live per the Phase 3 scope decision) as a non-secret "shape reference" for what the prod postgres_dsn value should contain?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — reference dev DSN shape, no values | Use dev connection string structure (no values) as a format reference | ✓ |
| No — keep prod runbook fully independent | Prod runbook documented without referencing dev | |

**User's choice:** Yes — reference dev DSN shape, no values

---

### Q8: What evidence format should Phase 3 use for the "secret exists but not populated" vs "populated" distinction on the BLOCKED row?

| Option | Description | Selected |
|--------|-------------|----------|
| describe-secret presence check only | aws secretsmanager describe-secret presence check (non-secret metadata) | ✓ |
| No new evidence command — documentation only | Document without running any new evidence commands | |

**User's choice:** describe-secret presence check only

---

## Acceptance-vs-Debug Framing for --status-only/--skip-preflight

### Q9: Given GRAPH-01/02 will cite the existing 03-LIVE-DEV-RUN.md dev precedent (no new live verify-graph run, per Area 1), what should the 'dev rehearsal run' of run-aws-mdm-e2e.sh --env dev actually invoke?

| Option | Description | Selected |
|--------|-------------|----------|
| --status-only on dev | Lightweight rehearsal: report Step Functions status without starting executions | |
| Full E2E run on dev | Re-execute the full mdm_migrate -> mdm_verify_graph chain on dev (RUN_E2E=true, default) | ✓ |

**User's choice:** Full E2E run on dev
**Notes:** Full E2E run (RUN_E2E=true, default) on dev generates fresh acceptance evidence for LIVE-03/GRAPH-02, supplementing rather than replacing the cited 03-LIVE-DEV-RUN.md precedent for GRAPH-01/02.

---

### Q10: LIVE-03 requires operators to "stop before expensive AWS execution when local acceptance gates cannot pass." How should Phase 3 demonstrate this gating behavior?

| Option | Description | Selected |
|--------|-------------|----------|
| Demonstrate live via preflight | Run the local verify-graph preflight as part of the dev rehearsal and show it gating the full E2E run | ✓ |
| Document from source only | Cite the script's existing preflight-gate logic and --skip-preflight warning with no demonstration run | |

**User's choice:** Demonstrate live via preflight
**Notes:** The dev rehearsal run should use the script's default local verify-graph preflight (no --skip-preflight) so the preflight pass gates the full E2E run that follows — captured as live evidence.

---

### Q11: --skip-preflight is explicitly marked "cannot satisfy Phase 3 acceptance" in the script's help text. Should Phase 3's documentation explicitly reinforce this as a debug-only escape hatch?

| Option | Description | Selected |
|--------|-------------|----------|
| Document as debug-only, not for acceptance | Add a clearly-labeled subsection stating --skip-preflight bypasses the LIVE-03 acceptance gate | |
| Omit from Phase 3 docs entirely | Don't mention --skip-preflight in Phase 3 deliverables — the script's own help text already covers it | ✓ |

**User's choice:** Omit from Phase 3 docs entirely
**Notes:** --skip-preflight is not used, demonstrated, or documented anywhere in Phase 3 deliverables. The script's own help text/warning is sufficient.

---

### Q12: For the prod --status-only BLOCKED-row reproduction (Area 1 decision) — should this be the only prod-targeted command run in Phase 3?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — prod limited strictly to --status-only | --skip-preflight is never invoked against prod in this phase | ✓ |
| Also reproduce --skip-preflight warning against prod | Additionally run with --skip-preflight against prod to capture its WARNING text | |

**User's choice:** Yes — prod limited strictly to --status-only
**Notes:** --skip-preflight is never invoked against prod in this phase. Prod evidence is limited to the read-only --status-only structural-blocker reproduction.

---

## Claude's Discretion

None — all 12 questions were answered with specific choices (no "Other"/"you decide" selections).

## Deferred Ideas

- `edgartools-prod/mdm/api_keys` secret — purpose unclear; no population runbook entry in Phase 3. Revisit when its consumer is identified.
- `edgartools-prod/mdm/neo4j` secret — documented as not required / legacy graph container under the Snowflake-hosted graph path. No action needed unless the legacy Neo4j path is formally deprecated.
- Reproducing the `--skip-preflight` warning against prod — explicitly not done; prod evidence stays limited to `--status-only`.
