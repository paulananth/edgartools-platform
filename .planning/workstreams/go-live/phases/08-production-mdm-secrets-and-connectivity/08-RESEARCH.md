# Phase 8: Production MDM Secrets And Connectivity - Research

**Researched:** 2026-06-20
**Domain:** AWS Secrets Manager population + Postgres connectivity verification (MDM CLI), Snowflake-hosted Postgres
**Confidence:** HIGH

## Summary

Phase 8 has two plans: populate two production AWS Secrets Manager containers
(`edgartools-prod/mdm/postgres_dsn`, `edgartools-prod/mdm/snowflake`) per the
already-authored v1.5 runbook, then run three MDM CLI commands
(`check-connectivity`, `migrate`, `counts`) against the production MDM
database and capture secret-safe evidence. Nearly all of the procedural,
command, and security-convention work was already done in v1.5 Phase 3
(`runbook/mdm-secrets.md`) and Phase 1 (`evidence/mdm-hosted-graph.md`'s dev
precedent). Phase 8 is primarily an **execution and evidence-capture phase**,
not a design phase — the runbook already specifies exact commands, exact
output shapes, and exact secret-safety rules.

The codebase declares Terraform containers for **four** MDM secrets
(`postgres_dsn`, `neo4j`, `api_keys`, `snowflake`), but the v1.5 runbook
explicitly and authoritatively narrows Phase 8's scope to the **two** named in
ROADMAP.md/REQUIREMENTS.md (MDM-02): `postgres_dsn` and `snowflake`. `neo4j`
is declared "Not required — legacy graph container" (the Snowflake-hosted
graph replaced external Neo4j/Aura) and `api_keys` is declared "Deferred —
purpose unclear" (its real consumer is the MDM FastAPI auth layer, an
unrelated runtime surface). This is not an open question — it is a locked,
already-documented scope decision from the runbook's own Sections 3 and 4.

One genuine gap remains open: **no Terraform resource and no prod-targeted
SQL script in this repo provisions the production Snowflake Postgres
instance itself.** `infra/snowflake/postgres/mdm_create_instance.sql` is
hardcoded to create `EDGARTOOLS_DEV_MDM` and must be manually edited and run
via `snow sql` for any other environment — there is no
`mdm_create_instance_prod.sql` or prod Terraform equivalent. Phase 8 must
treat "does the prod Snowflake Postgres instance already exist" as an
external precondition to verify (likely via Snowsight or `snow sql DESCRIBE
POSTGRES INSTANCE`, outside this repo's CLI surface) before attempting
`postgres_dsn` population — this is a blocking dependency that should
surface as a Phase 8 task or explicit open question, not be assumed.

**Primary recommendation:** Follow `runbook/mdm-secrets.md` verbatim for
08-01 (secret population + `describe-secret` evidence), and follow the
`evidence/mdm-hosted-graph.md` D-03 dev precedent verbatim for 08-02 (CLI
verification + evidence). Add one task before 08-01 to confirm the prod
Snowflake Postgres instance exists (operator-driven, likely Snowsight/`snow
sql`, not currently scripted for prod in this repo).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Secret value population (`postgres_dsn`, `snowflake`) | Operator / AWS CLI | AWS Secrets Manager (storage) | Terraform creates empty containers only; values are populated out-of-band per CLAUDE.md/STATE.md secret-safety contract — Terraform never owns runtime secret values |
| Prod Postgres instance provisioning | Snowflake operator (Snowsight / `snow sql`) | — | Not modeled in this repo's Terraform; `mdm_create_instance.sql` is dev-only and manually run, not automated for prod |
| DSN load into runtime | Operator shell (in-process env var) | MDM CLI (`get_engine()` reads `MDM_DATABASE_URL`) | DSN must move from Secrets Manager to env var without ever being printed/logged/committed |
| Connectivity/migration/counts verification | MDM CLI (`edgar_warehouse/mdm/cli.py` + `database.py` + `migrations/runtime.py`) | — | Pure Python/SQLAlchemy against Postgres; no AWS/Snowflake API calls in this step |
| `snowflake` secret functional verification | Out of scope for Phase 8 (Phase 9) | — | `_snowflake_setting()` consumer is `export.py` (sync-graph/export path), not the CLI commands required by MDM-02; Phase 8 can only confirm presence via `describe-secret`, not function |
| Evidence capture / secret-safety enforcement | Operator + Markdown evidence file | Launch gate matrix | `describe-secret` metadata only; no DSN/value pasting; matches existing Phase 1 evidence template |

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MDM-02 | MDM operator can populate prod `postgres_dsn` and `snowflake` secrets, then verify connectivity, migration, and counts without printing secret values | `runbook/mdm-secrets.md` Sections 1, 2, 5 give exact population + presence-check commands; `evidence/mdm-hosted-graph.md` D-03 gives exact CLI verification commands and expected non-secret output shapes; Security Note gives the exact prohibition rules for evidence |

## User Constraints

No CONTEXT.md exists for Phase 8 yet (confirmed via repo state and prior session note: "CONTEXT.md does not exist for this phase; TEXT_MODE active for workstream"). The following are locked constraints carried forward from STATE.md / ROADMAP.md / REQUIREMENTS.md / CLAUDE.md, which function as the binding constraints in lieu of a phase-specific CONTEXT.md:

### Locked Decisions (from STATE.md / milestone-level)
- "No secrets, DSNs, tokens, raw connector errors, Terraform state, or sensitive generated deployment values may be committed."
- "Use existing deploy and verification scripts before adding automation."
- "[Milestone v1.6]: Research is optional and disabled by workstream default; production launch execution should prefer existing runbooks and evidence gates over new architecture." (This research run was explicitly requested for Phase 8 despite that default — see prior session note S240 flagging Phase 8 as needing extra scrutiny before planning.)
- "Continue phase numbering from v1.5; do not delete v1.5 phase evidence."
- AWS-only architecture; no non-AWS deployment paths, registries, or secret-management systems (ISO-03).

### Claude's Discretion
- Exact task breakdown within 08-01/08-02 (the ROADMAP.md plan split into 2 plans is fixed; task-level structure within each plan is open).
- How to phrase/verify the "does the prod Postgres instance exist" precondition check — not specified anywhere in existing artifacts.
- Whether the Postgres-instance-existence check becomes a standalone task in 08-01 or a blocking precondition documented separately.

### Deferred Ideas (OUT OF SCOPE)
- `edgartools-prod/mdm/api_keys` population — explicitly deferred per runbook Section 4 ("purpose unclear... revisit when the consumer is identified").
- `edgartools-prod/mdm/neo4j` population — explicitly not required per runbook Section 3 (legacy, unused by Snowflake-hosted graph).
- "Formal deprecation or removal of external Neo4j runtime remnants" — REQUIREMENTS.md Future Requirements, not in scope for v1.6.
- Snowflake functional verification of the `snowflake` secret (sync-graph, Native App) — that is Phase 9 (GRAPH-03/GRAPH-04), not Phase 8.

## Standard Stack

No new libraries or packages are introduced by this phase. It uses only:
- AWS CLI (`aws secretsmanager ...`) — already a project dependency, version confirmed present: `aws-cli/2.34.53` `[VERIFIED: aws --version on this machine]`
- `edgar-warehouse` CLI (already installed via `uv sync --extra mdm-runtime`) — existing `edgar_warehouse/mdm/cli.py` subcommands
- `uv` — confirmed present: `uv 0.11.16` `[VERIFIED: uv --version on this machine]`

**Package Legitimacy Audit:** Not applicable — Phase 8 installs no new packages.

## Architecture Patterns

### System Architecture Diagram

```
Operator (prod credentials, never committed)
   |
   |--1--> aws secretsmanager put-secret-value --secret-id edgartools-prod/mdm/postgres_dsn
   |         (via infra/scripts/bootstrap-aws-mdm-secrets.sh --dsn-stdin; validates DSN shape)
   |
   |--2--> aws secretsmanager put-secret-value --secret-id edgartools-prod/mdm/snowflake
   |         (raw CLI call, JSON secret-string, 7 keys; no helper script exists)
   |
   |--3--> aws secretsmanager describe-secret --secret-id <both>
   |         --> non-secret metadata (Name, ARN, LastChangedDate, VersionIdsToStages)
   |         --> committed to evidence/*.md (D-08 pattern)
   |
   |--4--> export MDM_DATABASE_URL="$(aws secretsmanager get-secret-value \
   |          --secret-id edgartools-prod/mdm/postgres_dsn --query SecretString --output text)"
   |         (in-shell only; value never printed; unset after use)
   |
   v
edgar-warehouse mdm check-connectivity   --> get_engine() reads MDM_DATABASE_URL --> SELECT 1
edgar-warehouse mdm migrate              --> idempotent schema/seed apply       --> {"seeded": true}
edgar-warehouse mdm counts                --> table row counts + relationship counts
   |
   v
Evidence Markdown (sanitized JSON output only; DSN never appears)
   |
   v
Launch Gate Matrix rows (22+) updated PASS
```

### Recommended Project Structure (evidence/runbook artifacts for this phase)
```
.planning/workstreams/go-live/phases/08-production-mdm-secrets-and-connectivity/
├── 08-01-*-PLAN.md          # secret population plan
├── 08-02-*-PLAN.md          # connectivity/migrate/counts verification plan
└── evidence/
    └── mdm-prod-secrets-and-connectivity.md   # new evidence file (or append to existing prod evidence file if one already exists from Phase 6/7)
```

### Pattern 1: DSN-validated helper script for `postgres_dsn`
**What:** `infra/scripts/bootstrap-aws-mdm-secrets.sh --dsn-stdin` validates scheme/host-suffix/database/sslmode before writing, and accepts the DSN via stdin (never as a shell argument, avoiding shell-history/process-listing leakage).
**When to use:** Always, for `postgres_dsn`. Do not hand-roll a raw `put-secret-value` call for this secret — the helper script's validation is the only place the DSN-shape invariants (`.snowflake.app` suffix, `database=mdm`, `sslmode=require`) are enforced before write.
**Example:**
```bash
# Source: .planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md
printf '%s' "postgresql://<APPLICATION_ROLE_USER>:<APPLICATION_ROLE_PASSWORD>@<PROD_SNOWFLAKE_POSTGRES_HOST>.snowflake.app:5432/mdm?sslmode=require" | \
  bash infra/scripts/bootstrap-aws-mdm-secrets.sh \
    --env prod \
    --aws-profile aws-admin-prod \
    --aws-region us-east-1 \
    --dsn-stdin
```

### Pattern 2: Raw `put-secret-value` for `snowflake` (no helper exists)
**What:** The `snowflake` secret has no validation helper; populate directly with the AWS CLI using a JSON `--secret-string` containing exactly the 7 keys `_snowflake_setting()` checks.
**When to use:** Only for `edgartools-prod/mdm/snowflake`.
**Example:**
```bash
# Source: .planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md
aws secretsmanager put-secret-value \
  --profile aws-admin-prod \
  --region us-east-1 \
  --secret-id edgartools-prod/mdm/snowflake \
  --secret-string '{
    "MDM_SNOWFLAKE_ACCOUNT": "<ORGNAME-ACCOUNTNAME>",
    "MDM_SNOWFLAKE_USER": "<PROD_MDM_SNOWFLAKE_USER>",
    "MDM_SNOWFLAKE_PASSWORD": "<PROD_MDM_SNOWFLAKE_PASSWORD>",
    "MDM_SNOWFLAKE_DATABASE": "<EDGARTOOLS_PROD>",
    "MDM_SNOWFLAKE_WAREHOUSE": "<EDGARTOOLS_PROD_REFRESH_WH>",
    "MDM_SNOWFLAKE_SCHEMA": "EDGARTOOLS_GOLD",
    "MDM_SNOWFLAKE_ROLE": "<EDGARTOOLS_PROD_DEPLOYER>"
  }' >/dev/null
```
`MDM_SNOWFLAKE_SCHEMA` is `EDGARTOOLS_GOLD` — known, not a placeholder.

### Pattern 3: Load DSN into env var without printing it, then unset
**What:** `MDM_DATABASE_URL` is read directly from the process environment by `get_engine()` (`edgar_warehouse/mdm/database.py:74`: `url = url or os.environ["MDM_DATABASE_URL"]`). The secret must travel from Secrets Manager into this env var without ever appearing in stdout/logs/evidence.
**When to use:** Immediately before running `check-connectivity`/`migrate`/`counts` in 08-02; unset immediately after.
**Example:**
```bash
# Source: .planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/03-01-live-mdm-graph-rehearsal-PLAN.md:212-213
export MDM_DATABASE_URL="$(aws secretsmanager get-secret-value \
  --profile aws-admin-prod --region us-east-1 \
  --secret-id edgartools-prod/mdm/postgres_dsn --query SecretString --output text)"

uv run --extra mdm-runtime edgar-warehouse mdm check-connectivity
uv run --extra mdm-runtime edgar-warehouse mdm migrate
uv run --extra mdm-runtime edgar-warehouse mdm counts

unset MDM_DATABASE_URL   # record in evidence that this happened
```
This `export $(get-secret-value ...)` invocation itself must never be pasted into evidence/planning files verbatim with real values — it is shown here only as a structural/placeholder pattern, matching the precedent's own disclaimer convention.

### Anti-Patterns to Avoid
- **Printing or logging `MDM_DATABASE_URL`:** never `echo $MDM_DATABASE_URL`, never let CLI output include the DSN (the CLI commands themselves do not echo it — confirmed by reading `cli.py` handlers — but operator-added debug output could).
- **Pasting `put-secret-value` or `get-secret-value --query SecretString` output into evidence:** explicitly forbidden by the runbook's Security Note; only `describe-secret` metadata is safe.
- **Treating `neo4j`/`api_keys` as in-scope:** the runbook explicitly closes this — do not add population tasks for them in 08-01.
- **Inventing a "snowflake secret connectivity check" in 08-02:** the `snowflake` secret is not consumed by `check-connectivity`/`migrate`/`counts`; it is consumed by `_snowflake_setting()` in `export.py`, exercised only in Phase 9's sync-graph/verify-graph path. 08-02 can only presence-check `snowflake` via `describe-secret`, not functionally verify it.
- **Assuming the prod Snowflake Postgres instance exists:** no Terraform or prod-targeted SQL script in this repo provisions it; this must be confirmed, not assumed.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| DSN shape validation before writing to Secrets Manager | A new validation script/inline checks | `infra/scripts/bootstrap-aws-mdm-secrets.sh` | Already validates scheme/host-suffix/database/sslmode; has `--dry-run` |
| Connectivity/migration/counts verification logic | New SQL/Python verification scripts | `edgar-warehouse mdm check-connectivity` / `migrate` / `counts` | Already implemented in `edgar_warehouse/mdm/cli.py` + `migrations/runtime.py`; outputs are already JSON and already proven against dev |
| Evidence template/structure | A new evidence format | The existing `evidence/mdm-hosted-graph.md` D-03 section as a template | Matches launch gate matrix expectations and already passed verification (03-VERIFICATION.md) |

**Key insight:** Phase 8 has essentially zero net-new engineering — its risk surface is entirely in execution discipline (secret-safety, correct order, evidence accuracy), not in writing new code.

## Common Pitfalls

### Pitfall 1: Assuming the prod Snowflake Postgres instance already exists
**What goes wrong:** Operator runs `bootstrap-aws-mdm-secrets.sh` with a DSN pointing at a host that was never created, then `check-connectivity` fails with a connection-refused/DNS error in 08-02 — wasting a cycle and risking a raw connector error leaking into evidence.
**Why it happens:** `mdm_create_instance.sql` only creates `EDGARTOOLS_DEV_MDM`; there is no prod variant or Terraform resource for the Postgres instance itself in this repo, so its existence is invisible to a repo-only audit.
**How to avoid:** Add an explicit precondition task/check before 08-01: confirm via Snowsight or `snow sql --connection <prod-conn> -q "DESCRIBE POSTGRES INSTANCE EDGARTOOLS_PROD_MDM"` (or equivalent prod instance name) that the instance exists and is in a ready state, before populating `postgres_dsn`.
**Warning signs:** `check-connectivity` returns a connection error rather than `{"connected": true, ...}`.

### Pitfall 2: Pasting `put-secret-value` response output into evidence
**What goes wrong:** `put-secret-value` returns ARN + VersionId to stdout by default; if an operator pastes this into an evidence Markdown file, it creates an operational linkage that should never be committed.
**Why it happens:** It's easy to copy terminal output wholesale when writing evidence quickly.
**How to avoid:** Redirect `put-secret-value` output to `/dev/null` (as shown in the runbook); only commit `describe-secret` metadata.
**Warning signs:** Evidence Markdown contains a `VersionId` or `ARN` string sourced from a `put-secret-value` call rather than a `describe-secret` call.

### Pitfall 3: Leaving `MDM_DATABASE_URL` set after verification
**What goes wrong:** The DSN (containing prod credentials) remains in the shell environment after the CLI commands finish, increasing exposure window (e.g., visible to subsequent commands' env, terminal history of `env`/`export` if run carelessly).
**Why it happens:** Easy to forget the `unset` step when focused on capturing command output.
**How to avoid:** Always `unset MDM_DATABASE_URL` immediately after the three CLI commands, and record that fact in evidence (the dev precedent in `evidence/mdm-hosted-graph.md` explicitly records "`MDM_DATABASE_URL` unset after all three commands" as an evidence line item — replicate this).
**Warning signs:** Evidence file doesn't mention unsetting the variable.

### Pitfall 4: Treating `snowflake` secret population as "connectivity verified"
**What goes wrong:** A plan or evidence file claims the `snowflake` secret is "verified" based on the same three CLI commands used for `postgres_dsn`, when those commands never touch `_snowflake_setting()`/`export.py` at all.
**Why it happens:** The two secrets are populated together in 08-01, making it easy to conflate their respective verification scopes.
**How to avoid:** Document explicitly in evidence that `postgres_dsn` is functionally verified (via CLI commands) while `snowflake` is only presence-verified (via `describe-secret`) in Phase 8; functional Snowflake verification happens in Phase 9.
**Warning signs:** Evidence or plan language says "snowflake secret connectivity passed" without a corresponding sync-graph/export call.

### Pitfall 5: Running CLI commands with `aws` defaulting to the wrong region
**What goes wrong:** AWS CLI commands default to a configured profile's default region, which may not be `us-east-1`; secrets could be created/read against the wrong region silently.
**Why it happens:** CLAUDE.md explicitly flags this: "infra is us-east-1, not the default us-east-2."
**How to avoid:** Always pass `--region us-east-1` explicitly on every `aws secretsmanager` invocation, as the runbook already does consistently.
**Warning signs:** `describe-secret` returns `ResourceNotFoundException` despite the secret existing (it exists in a different region).

## Code Examples

### check-connectivity / migrate / counts handlers (confirms exact invocation and output contract)
```python
# Source: edgar_warehouse/mdm/cli.py (read directly from repo)
def _handle_migrate(args) -> int:
    from edgar_warehouse.mdm.database import get_engine
    from edgar_warehouse.mdm.migrations.runtime import migrate
    payload = migrate(get_engine(), seed=args.seed)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0

def _handle_counts(args) -> int:
    from edgar_warehouse.mdm.database import get_engine
    from edgar_warehouse.mdm.migrations.runtime import count_tables
    engine = get_engine()
    payload = dict(count_tables(engine))
    with Session(engine) as session:
        payload["relationships_by_type"] = _relationship_counts_by_type(session)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0

def _handle_check_connectivity(args) -> int:
    from edgar_warehouse.mdm.database import get_engine
    from edgar_warehouse.mdm.migrations.runtime import check_connectivity
    payload = {"sql": check_connectivity(get_engine())}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0
```

### Expected non-secret output shapes (dev precedent — prod will differ only in row counts)
```text
# Source: .planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md (D-03, lines 190-212)
check-connectivity --> {"connected": true, "dialect": "postgresql", "missing_tables": []}
migrate (idempotent) --> {"dialect": "postgresql", "seeded": true}
counts --> 19 tables with non-zero counts (mdm_entity, mdm_company, mdm_person, mdm_security, etc.)
          + relationship counts by type (IS_INSIDER, HOLDS, ISSUED_BY, COMPANY_HOLDS), each with active/pending_graph_sync subtotals
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| External Neo4j/Aura for graph storage, `NEO4J_*` env vars/secrets | Snowflake-hosted Graph Native App, pure SQL (`SnowflakeGraphSyncExecutor`) | Pre-v1.5 cutover (PRs #51-54 area per prior session notes) | `neo4j` secret container is now legacy/unused; Phase 8 does not populate it |
| AWS RDS for MDM relational store | Snowflake-hosted Postgres app (`*.snowflake.app` host) | Same cutover window | `postgres_dsn` must point at a `.snowflake.app` host, not an RDS endpoint; enforced by `validate_snowflake_postgres_dsn()` |

**Deprecated/outdated:**
- `load-relationships` CLI help text still says "sync requested relationship targets to Neo4j" — stale docstring, not a Phase 8 blocker, but worth a follow-up doc fix ticket outside this phase's scope.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The production Snowflake Postgres instance does not yet exist (or its existence is unverified) and must be confirmed via Snowsight/`snow sql` before `postgres_dsn` population | Summary, Pitfall 1 | If it already exists and is ready, this becomes an unnecessary verification step rather than a blocker — low risk either way, but if it genuinely does not exist, skipping this check causes 08-02 to fail with a leaked connector error |
| A2 | The prod MDM Postgres instance will be named analogously to the dev instance (e.g., `EDGARTOOLS_PROD_MDM`) | Pitfall 1 example command | Naming mismatch would only affect the exact `snow sql` query text, not the underlying precondition-check task |

**This table is intentionally short** — the vast majority of this phase's procedural content (commands, output shapes, security rules) is directly verified from existing repo files (the v1.5 runbook and Phase 1 evidence), not assumed.

## Open Questions

1. **Does the production Snowflake Postgres MDM instance already exist?**
   - What we know: `infra/snowflake/postgres/mdm_create_instance.sql` only creates `EDGARTOOLS_DEV_MDM`; comments say "Update the instance name... before running" for other environments, implying manual edit-and-run per environment with no prod automation in this repo. No Terraform resource models a Snowflake Postgres instance (Snowflake-side compute, not AWS).
   - What's unclear: Whether a Snowflake operator has already created the prod instance out-of-band (Snowsight) as part of earlier v1.5/v1.6 work, or whether this is still pending.
   - Recommendation: Phase 8 (or a precondition immediately before 08-01) should include a verification step — `snow sql --connection <prod> -q "DESCRIBE POSTGRES INSTANCE <prod-instance-name>"` or equivalent Snowsight check — and if the instance does not exist, that becomes a documented blocker requiring Snowflake operator action (analogous to the existing `mdm_create_instance.sql` step, run for prod) before secret population can proceed meaningfully.

2. **What is the exact production prod instance/host naming convention?**
   - What we know: Dev uses `EDGARTOOLS_DEV_MDM` (Snowflake Postgres instance name) and the DSN host suffix is `.snowflake.app`.
   - What's unclear: The exact prod instance name and resulting host string aren't documented anywhere in the repo (correctly redacted, since this would be a real-world identifier).
   - Recommendation: Operator supplies this at execution time; no placeholder guess should be hardcoded into the plan beyond the `<PROD_SNOWFLAKE_POSTGRES_HOST>` placeholder already used in the runbook.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| AWS CLI | Secret population/describe-secret/get-secret-value | ✓ | 2.34.53 | — |
| uv | `edgar-warehouse` CLI invocation | ✓ | 0.11.16 | — |
| `edgar-warehouse` CLI (`mdm-runtime` extra) | check-connectivity/migrate/counts | Not directly probed (requires `uv sync --extra mdm-runtime`) | — | Run `uv sync --extra mdm-runtime` before 08-02 if not already installed in the execution environment |
| Snowflake CLI (`snow`) | Confirming prod Postgres instance existence (Open Question 1) | Not probed in this research session | — | If unavailable, fall back to Snowsight UI for the existence check; document as a manual operator step |
| AWS prod credentials/profile (`aws-admin-prod`) | All secret population/verification commands | Operator-supplied at execution time, not verifiable from this research session | — | None — this is a hard human-action precondition already flagged in HANDOFF.json (`human_actions_pending`) |

**Missing dependencies with no fallback:**
- Prod AWS credentials/profile access — operator action, already tracked in HANDOFF.json.

**Missing dependencies with fallback:**
- `snow` CLI for the Postgres-instance-existence check — Snowsight UI is a viable manual fallback.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | None applicable — this phase is an operator-execution/evidence-capture phase against live production infrastructure, not application code under test |
| Config file | none |
| Quick run command | `uv run --extra mdm-runtime edgar-warehouse mdm check-connectivity` (itself the "test") |
| Full suite command | `check-connectivity` + `migrate` + `counts` in sequence, as already proven in dev (D-03) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MDM-02 | Prod secrets populated without printing values | manual (operator) | `aws secretsmanager describe-secret ... --query '{Name,ARN,LastChangedDate,VersionIdsToStages}'` | ✅ documented in runbook |
| MDM-02 | Connectivity/migration/counts pass against prod MDM DB | smoke | `uv run --extra mdm-runtime edgar-warehouse mdm check-connectivity && ... migrate && ... counts` | ✅ command exists in `cli.py`; no new test file needed |

### Sampling Rate
- **Per task commit:** N/A — this phase produces evidence Markdown, not code; no per-commit test run applies beyond running the CLI commands themselves as the verification act.
- **Per wave merge:** Re-run `check-connectivity` once more if 08-01 and 08-02 land in separate sessions, to confirm the secret is still correctly populated.
- **Phase gate:** Evidence file must show successful exit status (0) for all three CLI commands before the launch gate matrix rows are flipped to PASS.

### Wave 0 Gaps
None — existing CLI commands and evidence template fully cover phase requirements. No new test infrastructure needed.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No | No new auth surface introduced |
| V3 Session Management | No | N/A |
| V4 Access Control | Yes (indirectly) | IAM profile `aws-admin-prod` scoping is out of this phase's control surface but must be operator-verified as least-privilege before use |
| V5 Input Validation | Yes | DSN shape validated by `bootstrap-aws-mdm-secrets.sh` / `validate_snowflake_postgres_dsn()` before write |
| V6 Cryptography | Yes | `sslmode=require` enforced on the Postgres DSN; AWS Secrets Manager handles encryption-at-rest for both secrets — never hand-roll secret storage |

### Known Threat Patterns for this phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| Secret value (DSN, Snowflake credentials) leaking into committed evidence/planning Markdown | Information Disclosure | `describe-secret`-only evidence rule (D-08); never paste `put-secret-value`/`get-secret-value --query SecretString` output (runbook Security Note) |
| DSN left in shell environment after use | Information Disclosure | `unset MDM_DATABASE_URL` immediately after the three CLI commands; record the unset as evidence |
| Wrong-region secret operations creating shadow/duplicate secrets | Tampering / availability confusion | Always pass `--region us-east-1` explicitly on every `aws secretsmanager` call |
| Populating `postgres_dsn` against a non-existent or wrong Postgres instance | Denial of Service (self-inflicted) / Tampering | Verify prod Snowflake Postgres instance exists and is ready (Open Question 1) before writing the secret |

## Sources

### Primary (HIGH confidence)
- `.planning/workstreams/go-live/phases/03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md` — authoritative v1.5 runbook for secret population, scope (2 vs 4 secrets), and security rules
- `.planning/workstreams/go-live/phases/01-production-readiness-inventory-and-launch-gate-contract/evidence/mdm-hosted-graph.md` — dev precedent for CLI command sequence and output shapes (D-03), DSN shape reference (D-07)
- `edgar_warehouse/mdm/cli.py` — exact handler implementations for `migrate`/`counts`/`check-connectivity`
- `edgar_warehouse/mdm/database.py` — `get_engine()` confirms `MDM_DATABASE_URL` env var contract
- `edgar_warehouse/mdm/export.py` — `_snowflake_setting()` confirms the `snowflake` secret's real (different) consumer
- `infra/scripts/bootstrap-aws-mdm-secrets.sh` — DSN validation helper, confirmed read in full
- `infra/snowflake/postgres/mdm_create_instance.sql` — confirms no prod-automated Postgres instance provisioning exists in-repo
- `infra/terraform/modules/warehouse_runtime/main.tf` / `outputs.tf` — confirms 4 Terraform-managed empty secret containers
- `infra/terraform/accounts/prod/mdm_secret_moves.tf` — confirms no `moved` block for `neo4j` (corroborating its legacy/unmanaged status)
- `.planning/workstreams/go-live/{STATE,ROADMAP,REQUIREMENTS}.md`, `.planning/HANDOFF.json` — phase scope, blockers, requirement text (MDM-02)
- `CLAUDE.md` — region/uv/secret-safety project constraints

### Secondary (MEDIUM confidence)
- `TODOS.md` 5-whys entry on the `neo4j` Terraform-reconciliation incident — corroborates `neo4j`'s legacy/fragile status but is historical context, not a Phase 8 requirement

### Tertiary (LOW confidence)
- None used as load-bearing claims in this research

## Project Constraints (from CLAUDE.md)

- **HARD RULE:** Claude and Codex must never commit to the same branch; check `git branch --show-current` before any commit, and confirm the branch is owned by this runtime for this workstream.
- Use separate GSD workstream directories under `.planning/workstreams/<name>/`; do not edit another runtime's active workstream files.
- Run `git status --short` and `git log -1`, and inspect `.planning/active-workstream` before editing.
- 5-whys discipline required for any error encountered while executing Phase 8 plans (e.g., a connectivity failure must get a 5-whys root-cause pass, not just a retry).
- All AWS CLI/Terraform commands must use `--region us-east-1` explicitly (not the AWS CLI default region).
- Use `uv` for all Python dependency management and CLI execution (`uv run --extra mdm-runtime edgar-warehouse mdm <command>`); never bare `pip`.
- No secrets, DSNs, tokens, raw connector errors, Terraform state, or sensitive generated deployment values may be committed (repo-wide contract, reinforced by the v1.5 runbook's own Security Note).

## Metadata

**Confidence breakdown:**
- Standard stack: N/A — no new stack introduced
- Architecture: HIGH — all commands and output shapes are directly read from existing, already-verified repo artifacts (runbook + dev evidence), not inferred
- Pitfalls: HIGH — sourced from explicit repo documentation (Security Note, TODOS.md incident history) rather than generic domain knowledge
- Open question (prod Postgres instance existence): MEDIUM — confirmed absence of in-repo automation, but actual real-world existence state is unknowable from this repo alone and must be operator-confirmed

**Research date:** 2026-06-20
**Valid until:** Stable until the next MDM secrets/Postgres architecture change (no fixed expiry; re-verify if `runbook/mdm-secrets.md` or `mdm_create_instance.sql` are modified)
