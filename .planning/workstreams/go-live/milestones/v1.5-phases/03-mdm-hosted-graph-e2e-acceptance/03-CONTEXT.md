# Phase 3: MDM Hosted Graph E2E Acceptance - Context

**Gathered:** 2026-06-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Operators can prove the production MDM and hosted graph path end to end before
approving go-live (Requirements: MDM-01, GRAPH-01, GRAPH-02, LIVE-03).

Production AWS passive infrastructure (`infra/aws-prod-application.json`) does
not exist yet — the same class of structural blocker carried forward from
Phase 2. Phase 3 does **not** wait for that blocker to clear. Instead it:

1. Runs a full dev rehearsal of the MDM hosted-graph E2E chain
   (`run-aws-mdm-e2e.sh --env dev`) as live acceptance evidence for
   LIVE-03/GRAPH-02.
2. Live-reproduces the prod structural blocker via
   `run-aws-mdm-e2e.sh --env prod --status-only` (read-only) as a concrete
   BLOCKED-row proof, mirroring Phase 2's SNOW-01 `backend.hcl` reproduction.
3. Re-verifies dev MDM Snowflake Postgres connectivity/migration/counts live
   as a precedent refresh for MDM-01.
4. Cites existing dev hosted-graph verification evidence
   (`03-LIVE-DEV-RUN.md`) for GRAPH-01/GRAPH-02 without re-running it.
5. Documents the prod MDM secret-population runbook (BLOCKED row) with full
   placeholder commands for `postgres_dsn` and `snowflake`.
6. Documents `--status-only`/`--skip-preflight` framing per Success Criterion
   5 (emergency debug runs cannot be mistaken for acceptance).

</domain>

<decisions>
## Implementation Decisions

### Phase 3 Scope Given Prod AWS Blocker
- **D-01:** Phase 3 scope is a **dev rehearsal run + documentation** —
  not Phase 2's D-01 "document-and-validate-only" pattern. The dev rehearsal
  is a full E2E run (see D-09).
- **D-02:** Live-reproduce `run-aws-mdm-e2e.sh --env prod --status-only`
  (read-only) as concrete BLOCKED-row proof of the missing
  `infra/aws-prod-application.json`, mirroring Phase 2's SNOW-01
  `backend.hcl` rc=1 reproduction.
- **D-03:** For MDM-01, since prod MDM Postgres secrets don't exist yet,
  Phase 3 **re-verifies dev MDM Postgres connectivity/migration/counts live**
  as a dev-precedent refresh, in addition to documenting the prod commands
  as a BLOCKED required-fix.
- **D-04:** For GRAPH-01/GRAPH-02, the existing
  `.planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/03-LIVE-DEV-RUN.md`
  is cited as-is as dev precedent — **no new live `verify-graph` run** is
  performed for this requirement pair.

### MDM Secret Population Runbook (MDM-01)
- **D-05:** Document **full `aws secretsmanager put-secret-value` commands
  with placeholders** (not just names/JSON shape) for the BLOCKED "MDM
  Snowflake Postgres secret container and connectivity" row.
- **D-06:** Population-runbook entries are scoped to exactly two of the four
  `edgartools-prod/mdm/*` secrets:
  - `postgres_dsn` — runbook entry required.
  - `snowflake` — runbook entry required.
  - `neo4j` — **not required**, documented as legacy/N/A under the
    Snowflake-hosted graph (per Phase 2 framing). No population entry.
  - `api_keys` — **deferred**, purpose unclear. No population entry this
    phase.
- **D-07:** The runbook uses the **dev MDM Postgres connection** (re-verified
  live per D-03) as a non-secret "shape reference" for what the prod
  `postgres_dsn` value should contain — connection-string **structure only,
  no values**. The prod runbook is otherwise independent.
- **D-08:** Evidence for the "secret exists but not populated" vs "populated"
  distinction on the BLOCKED row is an
  `aws secretsmanager describe-secret` **presence check only** (non-secret
  metadata) — no new value-dumping commands.

### Acceptance-vs-Debug Framing (`--status-only` / `--skip-preflight`)
- **D-09:** The "dev rehearsal run" (D-01) is a **full E2E run** of
  `run-aws-mdm-e2e.sh --env dev` (`RUN_E2E=true`, the default — i.e. no
  `--status-only`). This generates fresh acceptance evidence for
  LIVE-03/GRAPH-02 chain steps (`mdm_migrate`, `mdm_run`,
  `mdm_backfill_relationships`, `mdm_sync_graph`, `mdm_verify_graph`,
  `mdm_counts`), **supplementing** — not replacing — the cited
  `03-LIVE-DEV-RUN.md` precedent used for GRAPH-01/GRAPH-02 (D-04).
- **D-10:** LIVE-03's "stop before expensive AWS execution when local
  acceptance gates cannot pass" requirement is demonstrated **live**: the dev
  rehearsal run uses the script's **default local `verify-graph` preflight**
  (no `--skip-preflight`), and the preflight pass is captured as the gate
  that allows the full E2E run to proceed. This pass/gate evidence is part of
  the Phase 3 deliverable.
- **D-11:** `--skip-preflight` is **not used, demonstrated, or documented**
  anywhere in Phase 3 deliverables — omitted entirely. The script's own help
  text and inline warning ("This cannot satisfy Phase 3 acceptance") are
  sufficient; Phase 3 does not duplicate or reinforce that warning.
- **D-12:** Prod-targeted commands in Phase 3 are limited strictly to the
  `--status-only` structural-blocker reproduction (D-02).
  `--skip-preflight` is **never invoked against prod** in this phase.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Workstream contracts
- `.planning/workstreams/go-live/ROADMAP.md` — Phase 3 goal, requirements
  (MDM-01, GRAPH-01, GRAPH-02, LIVE-03), and success criteria (1-5).
- `.planning/workstreams/go-live/REQUIREMENTS.md` — full requirement
  definitions and traceability table.

### Launch gate matrix and evidence templates (Phase 1)
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md`
  — BLOCKED rows for MDM/hosted graph and "Required Production Identifiers"
  that Phase 3 must update with live evidence.
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md`
  — evidence template to populate for MDM-01/GRAPH-01/GRAPH-02.

### Phase 2 precedent (deploy-readiness pattern to mirror)
- `.planning/workstreams/go-live/phases/02-aws-and-snowflake-production-deployment-dry-run/02-CONTEXT.md`
  — prior decisions on prod-blocker reproduction pattern (SNOW-01
  `backend.hcl`).
- `.planning/workstreams/go-live/phases/02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md`
  — runbook format/style to follow for the MDM secret-population runbook
  (D-05 through D-08).

### Dev hosted-graph precedent (cited, not re-run)
- `.planning/workstreams/neo4j-snowflake/phases/03-hosted-graph-verification-and-e2e-cutover/03-LIVE-DEV-RUN.md`
  — dev hosted-graph E2E evidence cited as-is for GRAPH-01/GRAPH-02 (D-04).

### Scripts and CLI under test
- `infra/scripts/run-aws-mdm-e2e.sh` — the E2E driver. Note: `--env`,
  `--status-only` (RUN_E2E=false, status report only), `--skip-preflight`
  (bypasses local `verify-graph`, explicitly "cannot satisfy Phase 3
  acceptance"), default local `verify-graph` preflight gate (~line 209+).
- `edgar_warehouse/mdm/cli.py` — `sync-graph` and `verify-graph` CLI commands
  invoked by the E2E driver and by the dev MDM Postgres re-verification
  (D-03).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `infra/scripts/run-aws-mdm-e2e.sh` — drives both the dev rehearsal (full
  run, D-09) and the prod blocker reproduction (`--status-only`, D-02). No
  new scripts needed.
- `edgar_warehouse/mdm/cli.py` (`sync-graph`, `verify-graph`, migration/counts
  commands) — used for the dev MDM Postgres re-verification (D-03).

### Established Patterns
- Phase 2's `evidence/*.md` + `runbook/*.md` pairing — live command output as
  non-secret evidence, paired with a runbook documenting the
  population/remediation steps for BLOCKED items. Phase 3 follows the same
  pairing for the MDM secret-population runbook (D-05–D-08) and the prod
  `--status-only` BLOCKED-row reproduction (D-02).
- `01-LAUNCH-GATE-MATRIX.md` BLOCKED row format — Phase 3 updates the
  MDM/hosted-graph BLOCKED rows with the new live evidence (dev rehearsal,
  dev Postgres re-verify, prod `--status-only` reproduction, secret
  presence checks).

### Integration Points
- `01-LAUNCH-GATE-MATRIX.md` MDM/hosted-graph BLOCKED rows and "Required
  Production Identifiers" section — primary integration point for Phase 3's
  evidence outputs.
- `evidence/mdm-hosted-graph.md` template — destination for dev rehearsal,
  dev Postgres re-verify, and prod `--status-only` evidence.

</code_context>

<specifics>
## Specific Ideas

- The two secrets requiring population-runbook entries are
  `edgartools-prod/mdm/postgres_dsn` and `edgartools-prod/mdm/snowflake`
  (full `put-secret-value` commands with placeholders, per D-05/D-06).
- The dev MDM Postgres DSN **shape** (connection-string structure, no values)
  doubles as the non-secret reference for the prod `postgres_dsn` secret
  format (D-07).
- "Secret exists but not populated" evidence = `aws secretsmanager
  describe-secret` presence check only (D-08) — no `get-secret-value` or
  value dumps anywhere in Phase 3.

</specifics>

<deferred>
## Deferred Ideas

- `edgartools-prod/mdm/api_keys` secret — purpose unclear; no population
  runbook entry in Phase 3. Revisit when its consumer is identified.
- `edgartools-prod/mdm/neo4j` secret — documented as not required / legacy
  graph container under the Snowflake-hosted graph path (per Phase 2
  framing). No action needed unless the legacy Neo4j path is formally
  deprecated (tracked as a Future Requirement in REQUIREMENTS.md).
- Reproducing the `--skip-preflight` warning against prod — explicitly not
  done (D-11/D-12); prod evidence stays limited to `--status-only`.

### Reviewed Todos (not folded)
None — `todo.match-phase '3'` returned 0 matches during this discussion.

</deferred>

---

*Phase: 3-mdm-hosted-graph-e2e-acceptance*
*Context gathered: 2026-06-15*
