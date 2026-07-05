## Conflict Detection Report

Ingest set: 11 documents, all DOC type
Mode: new
Precedence: ADR > SPEC > PRD > DOC (no ADR, SPEC, or PRD documents in this ingest set)
Cycle detection: no cycles found in cross-reference graph
UNKNOWN-confidence-low documents: none

### BLOCKERS (0)

No blockers detected. No LOCKED ADRs exist in this ingest set; no LOCKED-vs-LOCKED
contradictions are possible. No UNKNOWN-confidence-low documents were found.

### WARNINGS (0)

No competing acceptance variants detected. All 11 documents are DOC type. No two PRDs
define requirements on the same scope with non-identical acceptance criteria (no PRD
documents exist in this ingest set).

### INFO (5)

[INFO] Terraform CLI version pin is scope-specific, not a single value
  Found: infra/terraform/README.md states Terraform CLI pinned to 1.14.7 for AWS roots
  Found: infra/terraform/snowflake/README.md states Terraform CLI pinned to 1.14.8
  Found: docs/runbook.md states 1.14.8 or later in the 1.14.x line
  Note: These are scope-specific pins (AWS roots vs Snowflake roots) and are not
  contradictory. All three values fall within the 1.14.x line. The most restrictive
  value is 1.14.8. Constraint CON-010 records 1.14.8 as the recommended unified pin to
  satisfy all three scopes.
  Resolution: scope-specific; no winner required across scopes; CON-010 documents the
  recommendation to use 1.14.8 for both root types
  source: infra/terraform/README.md, infra/terraform/snowflake/README.md, docs/runbook.md

[INFO] Gold table count inconsistency between Quick Navigation and authoritative scope
  Found: CLAUDE.md Quick Navigation section states "dbt gold models (8 dynamic tables)"
  Found: infra/snowflake/dbt/edgartools_gold/README.md lists 9 business tables
    (COMPANY, FILING_ACTIVITY, OWNERSHIP_ACTIVITY, OWNERSHIP_HOLDINGS, ADVISER_OFFICES,
    ADVISER_DISCLOSURES, PRIVATE_FUNDS, FILING_DETAIL, TICKER_REFERENCE) plus
    EDGARTOOLS_GOLD_STATUS (a view, not a dynamic table)
  Found: CLAUDE.md data-layer section lists 10 entities including edgartools_gold_status
  Note: The dbt README is the authoritative source for dbt project scope per the
  DOC > DOC same-precedence rule (dbt README is scoped to the dbt project; CLAUDE.md
  Quick Nav is a developer convenience index that was not updated when TICKER_REFERENCE
  was added). The count is 9 business dynamic tables + 1 status view = 10 total objects.
  Resolution: auto-resolved in synthesis — requirements.md REQ-gold-tables uses 9
  business tables + 1 view, sourced from infra/snowflake/dbt/edgartools_gold/README.md.
  CLAUDE.md Quick Nav "8 dynamic tables" is stale and should be updated.
  source: CLAUDE.md, infra/snowflake/dbt/edgartools_gold/README.md

[INFO] Python version minimum differs between dashboard and platform runtime
  Found: examples/dashboard/README.md states "Python 3.11+"
  Found: docs/runbook.md and CLAUDE.md Dockerfile references use python:3.12-slim-bookworm
    as the container base layer (implying 3.12+ for ECS runtime)
  Note: These are scoped requirements. The dashboard is a standalone consumer of
  Snowflake gold tables; it does not run inside the warehouse container. Python 3.11+ is
  the dashboard's stated minimum. The warehouse runtime targets 3.12. Both are correct
  in their respective scopes.
  Resolution: auto-resolved — constraints.md CON-020 records 3.11+ for dashboard and
  3.12 for warehouse runtime as separate scoped constraints
  source: examples/dashboard/README.md, CLAUDE.md

[INFO] README.md install command uses bare pip, contradicting uv tooling policy
  Found: README.md Installation section shows "pip install -e \".[s3,snowflake]\""
  Found: CLAUDE.md, AGENTS.md establish project policy that bare pip is forbidden
    and uv sync / uv pip install must be used instead
  Note: README.md is a public-facing overview doc; it uses the simpler pip form for
  quick-start readability. CLAUDE.md and AGENTS.md are authoritative developer guides
  that override this for repo workflows. The tooling policy (CON-002) governs all
  contributor and operator workflows; the README install command is a documentation
  shorthand for new users.
  Resolution: auto-resolved — CLAUDE.md and AGENTS.md win as authoritative developer
  policy docs (both are more specific in scope than README.md). CON-002 records the
  binding constraint. The README pip command is flagged as documentation debt.
  source: README.md, CLAUDE.md, AGENTS.md

[INFO] retired non-AWS path paths appear in runbook and README but AGENTS.md marks AWS as only active path
  Found: AGENTS.md states "AWS is the only active deployment path; non-AWS paths must not
    be added or revived without explicit user request"
  Found: CLAUDE.md states "Do not add non-ECR registry, non-AWS SDK, ODBC, or
    non-AWS deployment steps back into this repo unless the platform architecture changes explicitly"
  Found: docs/runbook.md and README.md document retired non-AWS path parallel-run migration
    path with setup instructions, scripts, and environment variables
  Note: These are consistent when read in context. The retired non-AWS path documentation
  describes a migration path that is in parallel-run state — it exists to allow output
  validation before decommissioning AWS/Snowflake. "Only active path" means the primary
  operational path; the non-AWS path is a documented migration-only path, not a revival.
  Resolution: auto-resolved — not a contradiction; context.md records this under
  "Current Platform State" with the correct framing. DEC-001 records the AWS-only policy
  for new work.
  source: AGENTS.md, CLAUDE.md, docs/runbook.md, README.md
