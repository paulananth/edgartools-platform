# Execute Required Relationship Production Bulk Load

Type: task
Status: open
Blocked by: none (operator hold — see note below, not a wayfinder dependency edge)
Blocks: 06

~~**ON HOLD (2026-07-20, explicit operator decision):** do not relaunch until
the "Company Identity Pipeline" wayfinder map
(`.scratch/company-master-pipeline/map.md`) has progressed far enough to
untangle the Company/Ownership/ADV coupling.~~ **Lifted (2026-07-23,
confirmed retroactively):** six strict executions launched after the hold
date, including the currently-active `ticket20-strict-1yr-retry6-*` — this
doc was simply never updated when the hold was informally lifted. Treat
Ticket 20 as unblocked; this line only exists so future readers don't trust
stale "on hold" language over what AWS actually shows running.

**2026-07-23 — 13F lookback narrowed to one quarter (operator decision):**
historical 13F depth judged to have no real value on its own (holdings are a
point-in-time snapshot; only current state + go-forward `daily_incremental`
matter). `THIRTEENF_AGENT_LOOKBACK_YEARS = 1` (itself narrowed from the
original 3-year lock, PR #217) replaced by `THIRTEENF_AGENT_LOOKBACK_MONTHS =
3` in `relationship_bulk_load.py`. Item 5.02 8-K (2y) window unchanged.
retry6 (running under the old 1-year window) was stopped and a fresh
freeze/execution built under the new window — see the end of this file for
the new fingerprint/execution name once launched.

**2026-07-23/24 — freeze rebuilt and relaunched under quarter/1y windows.**
`retry6` (`ticket20-strict-1yr-retry6-20260722T200844Z`, 19/110 batches done)
confirmed `ABORTED`. New freeze built via the new `mdm
build-relationship-release-manifest` CLI subcommand (PR/commit `64031b5`) run
as an ad-hoc ECS task against `edgartools-prod-mdm-medium:50` — the S3 pull of
`silver.duckdb` happens inside AWS's network instead of an operator's laptop
(the prior local-download approach failed 3x over an unreliable home
connection; see commit `64031b5`). Freeze prefix
`warehouse/bronze/reference/relationship_release/ticket20-agent-q1y-20260724T003912Z`,
watermark `2026-07-02` (unchanged — the frozen Release Data Watermark, not
advanced), fingerprint `61be5eaeebc99c7eb9bf1e5a5e2c67076619bcc28b19ece715a7c2ebb175d852`,
**20,833 candidates / 10,792 CIKs / 108 batches** (down sharply from prior
freezes — expected, given the narrower windows).
`coverage_by_document_type`: 13F `[2026-04-02, 2026-07-02]`, proxy
`[2025-07-02, 2026-07-02]`, item 5.02/ambiguous 8-K `[2024-07-02, 2026-07-02]`
(item 502's 2y window is now the earliest/floor). Preflight:
`READY_FOR_STRICT_LOAD`, `strict_release_eligible: true`. New execution
**`ticket20-strict-q1y-20260724T004600Z`** started 2026-07-23T20:46:02-04:00
(fresh name per P3 — retry6's name stays consumed, never reused). retry6's
19 completed batches are **not** reused — the candidate universe changed
under the new windows, so this is a from-scratch pass over the smaller,
narrower candidate set.

**2026-07-23 — proxy lookback narrowed to one year (operator decision):**
same rationale — current board/executive composition, not multi-year proxy
history. `PROXY_AGENT_LOOKBACK_YEARS = 5 → 1`. This is bundled into the same
freeze rebuild as the 13F change above.

## Task

Run the strict production bulk load at the frozen Release Data Watermark, repair every unresolved candidate, derive all required relationship types without caps, publish the graph generation, and commit the passing evidence artifact.

**Coverage policy (document-type specific):** do not freeze a single global
2013 start for every form. Locked agent windows (wayfinder + PR #170/#171,
13F narrowed 3y→1y by PR #217 then 1y→1 quarter 2026-07-23; proxy narrowed
5y→1y 2026-07-23):
13F `max(W−1 quarter, 2013-05-20)`, proxy `[W−1y, W]` latest-in-band only,
Item 5.02 / ambiguous 8-K `[W−2y, W]`. Rebuild freeze with
`coverage_by_document_type` before GO. Live 2013-era freeze is **rejected**
under `release_mode`.

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
4. **Not done** — New strict SF execution (attestations in input); all batches succeed fail-closed. **Three** prior attempts FAILED and their names are consumed (**P3**: no redrive, never reuse): `ticket20-strict-agent-20260718T225510Z`, `ticket20-strict-gatev2-20260719T135202Z` (`States.ExceedToleratedFailureThreshold` — NULL 13F `report_date` passed `""` into a DuckDB DATE column; fixed by PR #192, cover-page `periodOfReport` fallback), and `ticket20-strict-insider-20260720T020331Z` (same threshold error — an upstream `edgartools` namespace-selection bug silently returned zero holding rows for a real, populated 13F information table; see TODOS.md "13F namespace 5-whys" for the full chain; fixed via an xsi-stripped reparse fallback in `edgar_warehouse/parsers/thirteenf.py`). Each is a distinct root cause, not a repeat — 0% tolerance fail-closed correctly both times. Next attempt: brand-new name (`ticket20-strict-insider2-<UTC-ts>`), new image with the namespace fix to be built/deployed before relaunch.
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
- **Live monitoring (added 2026-07-19):** run
  `uv run python scripts/ops/watch_release.py --env prod` alongside the launch.
  It prints every state transition as it happens, Distributed Map batch counts
  (succeeded/running/pending/failed — the strict Map's per-batch work is
  invisible in the top-level execution history), ECS task IDs with
  `tail-task.sh` hints, and any failed batch child with a ready-to-paste
  `diagnose-execution.sh` command. Exit code mirrors the execution outcome.
  Validated by replaying the `gatev2` failure end-to-end; unit-tested in
  `tests/unit/test_watch_release.py`.
