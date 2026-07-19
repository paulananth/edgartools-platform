# Execute Required Relationship Production Bulk Load

Type: task
Status: open
Blocked by: none
Blocks: 06

## Task

Run the strict production bulk load at the frozen Release Data Watermark, repair every unresolved candidate, derive all required relationship types without caps, publish the graph generation, and commit the passing evidence artifact.

**Coverage policy (document-type specific):** do not freeze a single global
2013 start for every form. Locked agent windows (wayfinder + PR #170/#171):
13F `max(W−3y, 2013-05-20)`, proxy `[W−5y, W]` latest-in-band only, Item 5.02 /
ambiguous 8-K `[W−2y, W]`. Rebuild freeze with `coverage_by_document_type`
before GO. Live 2013-era freeze is **rejected** under `release_mode`.

## Done when (revised 2026-07-19 per Release Owner insider-scoping decision — see Ticket 21)

- Candidate inventory and Bulk-Load Completion Ledger reconcile exactly.
- Failure, quarantine, circuit-breaker-leftover, and unapproved-force counts are zero;
  Item 5.02 `unresolved_accepted` stays within the bounded threshold with every
  accepted accession enumerated in evidence (see completion-gate doctrine).
- **Insider coverage: zero unresolved insiders** — every Form 3/4/5 reporting
  owner observed in silver resolves to one MDM person with an `IS_INSIDER`
  version (`mdm verify-insider-coverage`; bound into evidence via
  `reconcile-relationship-release --insider-coverage`). This is the EMPLOYED_BY
  completeness bar; non-insider executives are best-effort, not gating.
- A no-change rerun makes no SEC requests and produces identical silver/MDM semantic digests with zero new relationship identities.
- `EMPLOYED_BY` passes exact MDM-to-hosted-graph parity and current-at-watermark checks.
  `INSTITUTIONAL_HOLDS` parity is verified and reported in evidence but is
  **non-blocking** for the launch decision (Release Owner decision, 2026-07-19).
- Named Warehouse, MDM, Graph, Release Data Operator, and Release Owner attestations are bound to the evidence artifact.

## Pre-image ticket hygiene (2026-07-18)

| Ticket | Status | Close before image? |
| --- | --- | --- |
| 16 ledger | **resolved** | Already closed |
| 17 strict bulk-load | **resolved** | Already closed |
| 18 Item 5.02 | **resolved** | Already closed |
| 19 13F effective set | **resolved** | Already closed |
| Usefulness windows 01–13 | **resolved** (map complete) | Already closed |
| **20 this ticket** | **open** | **No** — keep open until production PASS |

## Current disposition

**NO_GO** (as of 2026-07-18). Prior strict runs **FAILED**. Do not claim GO.
See `docs/release-readiness/ticket20-production-remediation-evidence.json` and
resume notes.

### Latest failed executions (2026-07-18)

| Field | Value |
| --- | --- |
| First fail | `ticket20-strict-20260718T013201Z` (click / map threshold) |
| Resume fail | `ticket20-strict-resume-20260718T104737Z` — **0/160** batches; map 1 fail / 4 aborted / 155 pending |
| Freeze used | `ticket20-strict-20260718T013201Z` — **528,829** candidates, `coverage_start=2013-05-20`, **no** `coverage_by_document_type` |
| Fingerprint | `ded1b9a2c3e14c3b1c30fd01e30924acac158014c4e9a114e18b76f47fbbf746` |
| Data plane | ~~`edgartools-prodb-*` + `sec_platform_prodb_runner_*`~~ **migrated 2026-07-19** → `edgartools-prod-*-690839588395` + `sec_platform_prod_runner_*` (task defs `medium:31`/`large:31`/`mdm-*:30`; freeze copied keys-preserved, fingerprint unchanged) |

### Implementation path status (code / unit)

| Prerequisite | Status |
| --- | --- |
| Tickets 16–19 | **Closed / resolved** |
| Agent windows + freeze encoding (usefulness 01–13) | **Closed / resolved** |
| click pin + resume P0/P1 | **Landed** — PR #168 |
| Per-form agent freeze builder | **Landed** — PR #170 |
| Fail-closed strict freeze gate | **Landed** — PR #171 |
| PASS evidence + attestations on reconcile | **Landed** — PR #173 |
| Freeze preflight CLI | **Landed** — `validate_relationship_release_manifest` (PR #174) |
| Strict SF execution input builder | **Landed** — `build_ticket20_strict_execution_input` |
| Warehouse image with #168–#174+ | **Not yet** rebuilt after those merges |
| Agent-window freeze rebuild | **Not done** (required; old freeze fails gate) |
| Strict SF PASS | **Not done** |

### Still required for GO (do not mark resolved until all pass)

1. ~~Build + deploy **new** warehouse image from current `main`; register new task defs (**P3**: no redrive).~~ **Done** — warehouse `sha-b9e926e2d2b0`, MDM `sha256:f9796382…`, task defs `edgartools-prod-medium:27` / `edgartools-prod-mdm-medium:26`.
2. ~~**Rebuild freeze** under agent windows (new fingerprint + `coverage_by_document_type`).~~ **Done** — fingerprint `abecbde87ce3d71d2cbbe6be9fc4a0679e46d28629c95ff2ff977bd93f3160b2`, 125,819 candidates / 12,444 CIKs, 125 batches, uploaded to `s3://edgartools-prod-bronze-690839588395/warehouse/bronze/reference/relationship_release/ticket20-agent-20260718T225510Z/` (originally on the prodb bucket; copied keys-preserved in the 2026-07-19 prodb→prod cutover — the SM input uses bucket-relative keys, so the frozen input and fingerprint are unchanged).
3. ~~Preflight: `validate_relationship_release_manifest` → `READY_FOR_STRICT_LOAD`.~~ **Done** — `strict_release_eligible: true`.
4. **In progress** — New strict SF execution (attestations in input); all batches succeed fail-closed. Execution `ticket20-strict-agent-20260718T225510Z`, started 2026-07-19T00:56:27Z, `RUNNING` as of last check (0/125 batches succeeded, 4 running, 121 pending).
5. Reconcile ledger + `required_relationship_bulk_load_evidence.json` PASS.
6. MDM run/backfill/export/sync/verify; exact `EMPLOYED_BY` + `INSTITUTIONAL_HOLDS` parity.
7. No-change rerun: zero SEC network, identical semantic digests.

Until those produce PASS evidence, leave status **open** / disposition
**NO_GO**. Do **not** treat ordinary skip-policy full-chain as Ticket 20 proof.

### Operator notes from this session

- ~~Empty `edgartools-prod-*-690839588395` buckets are **not** the live store;
  deploy must target **prodb** buckets + `sec_platform_prodb_runner_*` roles.~~
  **Obsolete since 2026-07-19:** the prodb→prod cutover migrated all data into
  the canonical `-690839588395` buckets and replaced the prodb IAM roles with
  `sec_platform_prod_runner_*`; deploys now target canonical names only.
- Docker layer push to prod ECR failed on corrupted `uv` binary; **crane copy**
  from dev→prod ECR succeeded for digest `1b654302…`.
