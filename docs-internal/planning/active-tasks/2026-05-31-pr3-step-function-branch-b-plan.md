# Implementation Plan: PR-3 — Step Function Parallel Branch B

**Date Created**: 2026-05-31
**Planning Phase**: 2 of 3 (FIC Workflow)
**Based on Research**: Session exploration of `deploy-aws-application.sh`, `bootstrap_fundamentals.py`, `fundamentals_ingest.py`
**Next Phase**: Implementation (`/implement`)

---

## Overview

PR-1 (95/95 verified) and PR-2 (24/24 verified) laid the data-model and export-wiring foundation for Branch B fundamentals ingestion. The CLI command (`bootstrap-fundamentals`) and all parsers exist and are tested. The one remaining gap is the **Step Function orchestration**: `write_load_history_definition()` in `infra/scripts/deploy-aws-application.sh` has no Branch B parallel state.

PR-3 closes that gap by:
1. Updating `write_load_history_definition()` to replace `WindowedBootstrap → MdmRun` with a `Stage1Parallel` state that runs Branch A (unchanged) and Branch B concurrently.
2. Creating the `scripts/verify-pr3/` offline harness — two stages checking Step Function JSON integrity and a local `bootstrap-fundamentals` smoke run.

PR-4 (deferred) will add the `thirteenf` mode and cloud roundtrip verification (Parquet → S3 → Snowflake COPY INTO).

---

## Current State Analysis

### What is fully done (do not touch)

| Component | Location | Status |
|---|---|---|
| 6 fundamentals parsers | `edgar_warehouse/parsers/{financials,financials_derived,earnings_release,proxy_fundamentals,thirteenf,accounting_flags}.py` | ✅ |
| 6 silver table DDLs | `edgar_warehouse/silver_store.py` lines 390–549 | ✅ |
| `bootstrap-fundamentals` CLI command | `edgar_warehouse/application/commands/bootstrap_fundamentals.py` | ✅ |
| 3 workflow functions | `edgar_warehouse/application/workflows/fundamentals_ingest.py` | ✅ |
| CLI registration | `edgar_warehouse/cli.py` lines 152, 563 | ✅ |
| 6 dbt gold models | `infra/snowflake/dbt/edgartools_gold/models/gold/` | ✅ |
| Snowflake DDL bootstrap | `infra/snowflake/sql/bootstrap/06_fundamentals_load_wrapper.sql` | ✅ |
| MDM pipeline extensions | `edgar_warehouse/mdm/pipeline.py` | ✅ |
| snowflake_graph.py allowlist | 3 new types added | ✅ |

### The gap (Task #7, second half)

`infra/scripts/deploy-aws-application.sh` was **not touched** in commit `947c066` (feat: Branch B silver + MDM + gold). The `write_load_history_definition()` function (line 1291) generates the `load_history` state machine ASL. Its current shape:

```
SeedUniverse → WindowSizeCheck → WindowSizeDefault → ComputeWindows
    → WindowedBootstrap (Map, MaxConcurrency=1)
    → MdmRun → MdmBackfill → MdmSync → MdmVerify → GoldRefresh → WriteRunSummary
```

`WindowedBootstrap` runs `bootstrap-next` (Branch A — `silver/ownership/` shard). There is no state that runs `bootstrap-fundamentals` (Branch B — `silver/fundamentals/` shard).

### Why Branch B can safely run in parallel with Branch A

Each ECS task writes to its own local `/tmp/silver/fundamentals/shard-N.duckdb` before uploading to S3. Branch A writes to `silver/ownership/` and Branch B writes to `silver/fundamentals/` — separate S3 prefixes, separate local DuckDB files. No shared writer conflict (AD-05).

### thirteenf mode is deferred to PR-4

`thirteenf` mode reads from a different CIK input (SEC 13F filer list, ~5,500 adviser CIKs) rather than the company CIK windows. Mixing it into the `load_history` `cik_windows.jsonl` Map would require separate input manifests. PR-4 will handle it alongside the cloud roundtrip verification that `thirteenf` enables.

---

## Desired End State

1. `write_load_history_definition()` emits a `load_history` ASL JSON where stage (4) is a `Parallel` state with two branches:
   - **Branch A** (`WindowedBootstrap`): unchanged `bootstrap-next` Map at MaxConcurrency=1
   - **Branch B** (`FundamentalsBootstrap`): two sequential Maps — `FundamentalsPerFiling` then `FundamentalsEntityFacts`, each at MaxConcurrency=1, each reading the same `cik_windows.jsonl`

2. `scripts/verify-pr3/` harness passes all checks offline (no Snowflake credentials, no live AWS):
   - Stage 1: Structural checks on `deploy-aws-application.sh` (Parallel state, Branch B task def)
   - Stage 2: Local `bootstrap-fundamentals` smoke run (2–3 CIKs, mock or real data)

3. Task #7 is fully resolved; the task list can be marked closed.

---

## Out of Scope

- `thirteenf` mode in Step Function → PR-4
- Cloud roundtrip verification (Parquet → S3 → Snowflake) → PR-4
- Daily incremental Step Function Branch B → separate task after PR-4
- New ECS task definition profile for fundamentals (medium profile suffices; no new profile needed)

---

## Implementation Approach

### Phase 1: Update `write_load_history_definition()` ⬜

**Goal**: Replace `WindowedBootstrap → MdmRun` in the `load_history` ASL with a `Stage1Parallel` state, then resume MDM chain.

**File**: `infra/scripts/deploy-aws-application.sh`

#### 1a. Add `FundamentalsPerFiling` Map state (inside Branch B)

Reads the same `cik_windows.jsonl` produced by `ComputeWindows`. Each item is `{"window_offset": N, "window_limit": M}`. Per-window command:

```
bootstrap-fundamentals --cik-list <s3-key> --mode per-filing --run-id <execution-name>
```

Wait — `bootstrap-fundamentals` takes `--cik-list` (a file path or S3 key of CIK integers), not `--cik-limit`/`--cik-offset`. The `cik_windows.jsonl` format has `window_offset` and `window_limit` integers; Branch A reconstructs the CIK slice in `bootstrap-next`. Branch B needs the same slice.

**Two options:**
- Option A: Pass `--cik-offset` / `--cik-limit` to `bootstrap-fundamentals` (requires CLI accepts those args, consistent with Branch A pattern)
- Option B: Pass the `cik_windows.jsonl` S3 key as `--cik-list` and let `fundamentals_ingest.py` read from offset/limit

Check whether `bootstrap_fundamentals.py` already supports `--cik-offset`/`--cik-limit`:

> From the summary: `bootstrap_fundamentals.py` takes `--cik-list`, `--mode`, `--fundamentals-silver-path`, `--run-id`. It does **not** have `--cik-offset` / `--cik-limit`.

The cleanest approach consistent with the existing code is: **Branch B Maps also read from `cik_windows.jsonl`** and pass `window_offset` + `window_limit` via `--cik-offset` / `--cik-limit`, requiring a small CLI addition to `bootstrap-fundamentals`. This keeps the Step Function item shape identical between both branches.

#### 1b. Changes required in `bootstrap_fundamentals.py` and CLI

Add `--cik-offset` (int, default 0) and `--cik-limit` (int, default None) to the `bootstrap-fundamentals` subparser in `edgar_warehouse/cli.py`. When both are provided alongside `--cik-list`, `execute()` slices the CIK list to `[offset : offset + limit]`.

This is a 10-line change in `cli.py` + 5 lines in `execute()`. No change to the three workflow functions.

#### 1c. Build the `Stage1Parallel` state

Replace the current `WindowedBootstrap` entry in `definition["States"]` with:

```python
stage1_parallel = {
    "Type": "Parallel",
    "Comment": (
        "Branch A: ownership bootstrap (bootstrap-next, silver/ownership/). "
        "Branch B: fundamentals bootstrap (per-filing then entity-facts, silver/fundamentals/). "
        "Both run concurrently; each branch's Maps are MaxConcurrency=1 to prevent shard conflicts."
    ),
    "Branches": [
        {
            "StartAt": "WindowedBootstrap",
            "States": {"WindowedBootstrap": windowed_bootstrap_end},  # is_end=True variant
        },
        {
            "StartAt": "FundamentalsPerFiling",
            "States": {
                "FundamentalsPerFiling":  fundamentals_per_filing,   # → FundamentalsEntityFacts
                "FundamentalsEntityFacts": fundamentals_entity_facts, # is_end=True
            },
        },
    ],
    "ResultPath": None,  # discard both branches' outputs; input passes through unchanged
    "Next": "MdmRun",
}
```

**Important**: The existing `windowed_bootstrap` dict uses `"Next": "MdmRun"`. When moved inside a Parallel branch, it must use `"End": True` instead. The `ecs_state()` helper already supports `is_end=True`. Create a separate `windowed_bootstrap_a` variable that is identical but has its Map's inner state set to `is_end=True` and the Map itself set to `"End": True`.

#### 1d. `FundamentalsPerFiling` Map definition

```python
per_window_fundamentals_per_filing = ecs_state(wh_medium_arn,
    "States.Array('bootstrap-fundamentals', '--cik-list', States.Format('warehouse/bronze/reference/cik_universe/runs/{}/cik_windows.jsonl', $$.Execution.Name), '--cik-offset', States.Format('{}', $.window_offset), '--cik-limit', States.Format('{}', $.window_limit), '--mode', 'per-filing', '--run-id', $$.Execution.Name)",
    is_end=True)

fundamentals_per_filing = {
    "Type": "Map",
    "Comment": "Branch B per-filing: 8-K + DEF 14A → sec_earnings_release, sec_executive_record (silver/fundamentals/).",
    "MaxConcurrency": 1,
    "ToleratedFailurePercentage": 0,
    "ItemReader": {
        "Resource": "arn:aws:states:::s3:getObject",
        "ReaderConfig": {"InputType": "JSONL", "MaxItems": 100000},
        "Parameters": {
            "Bucket": bronze_bucket_name,
            "Key.$": "States.Format('warehouse/bronze/reference/cik_universe/runs/{}/cik_windows.jsonl', $$.Execution.Name)",
        },
    },
    "ItemProcessor": {
        "ProcessorConfig": {"Mode": "INLINE"},
        "StartAt": "RunFundamentalsPerFiling",
        "States": {"RunFundamentalsPerFiling": per_window_fundamentals_per_filing},
    },
    "ResultPath": None,
    "Next": "FundamentalsEntityFacts",
}
```

#### 1e. `FundamentalsEntityFacts` Map definition

Same shape, `--mode entity-facts`, `is_end=True` on the Map.

#### 1f. Update `definition["States"]`

Remove `"WindowedBootstrap": windowed_bootstrap` entry.
Add `"Stage1Parallel": stage1_parallel` (after `ComputeWindows`).
Update `compute_windows` to use `next_state="Stage1Parallel"`.

#### 1g. Update the `Comment` in `definition`

Reflect that stage (4) is now a Parallel state with two branches.

**Verification**:
- [ ] Run `python3 -c "import json,sys; json.load(open('sfn-load-history.json'))"` on the generated JSON — no parse errors
- [ ] Confirm `Stage1Parallel` state appears in `definition["States"]`
- [ ] Confirm `definition["States"]["Stage1Parallel"]["Type"] == "Parallel"`
- [ ] Confirm `definition["States"]["Stage1Parallel"]["Branches"]` has exactly 2 items
- [ ] Confirm neither branch has `"Next"` on its terminal states (they use `"End": true`)
- [ ] Confirm MDM chain `MdmRun` is still present and follows `Stage1Parallel`

---

### Phase 2: CLI extension for `--cik-offset` / `--cik-limit` ⬜

**Goal**: Allow `bootstrap-fundamentals` to accept window offsets from Step Functions item payloads, identical to how `bootstrap-next` uses `--cik-offset` / `--cik-limit`.

**Files**:
- `edgar_warehouse/cli.py` — add two optional args to `bootstrap_fundamentals` subparser
- `edgar_warehouse/application/commands/bootstrap_fundamentals.py` — slice CIK list when offset/limit provided

**Changes in `cli.py`** (bootstrap_fundamentals subparser, ~line 563):
```python
bootstrap_fundamentals.add_argument("--cik-offset", type=int, default=0,
    help="Slice offset into --cik-list (for Step Function windowed dispatch).")
bootstrap_fundamentals.add_argument("--cik-limit", type=int, default=None,
    help="Maximum CIKs to process from --cik-list starting at --cik-offset.")
```

**Changes in `execute()` (bootstrap_fundamentals.py**, after CIK list is loaded):
```python
offset = int(getattr(args, "cik_offset", 0) or 0)
limit  = getattr(args, "cik_limit", None)
if offset or limit:
    end = (offset + limit) if limit else None
    cik_list = cik_list[offset:end]
```

**Verification**:
- [ ] `edgar-warehouse bootstrap-fundamentals --cik-list tests/fixtures/ciks.json --cik-offset 0 --cik-limit 2 --mode per-filing` runs without error
- [ ] With `--cik-offset 2 --cik-limit 2` and a 4-item list, only CIKs at index 2 and 3 are processed
- [ ] Without `--cik-offset`/`--cik-limit`, behaviour is unchanged (all CIKs processed)

---

### Phase 3: `scripts/verify-pr3/` harness ⬜

**Goal**: Offline verification harness that confirms (a) the deploy script produces the correct Step Function ASL shape and (b) `bootstrap-fundamentals` smoke-runs locally.

**Files to create**:
```
scripts/verify-pr3/
├── 00_lib.sh               (copy from verify-pr2/00_lib.sh — identical helper library)
├── 01_check_sfn_branch_b.sh
├── 02_smoke_bootstrap_fundamentals.sh
└── run_all.sh
```

#### Stage 1: `01_check_sfn_branch_b.sh` — Step Function structural integrity

This script does **not** deploy anything. It calls `write_load_history_definition()` locally (via a `bash -c` shim that stubs out AWS calls) or more practically: it reads the deploy script source and checks for structural markers.

Two approaches:
- **Approach A (source grep)**: Grep `deploy-aws-application.sh` for required patterns. Fast, no AWS needed, fragile to refactoring.
- **Approach B (dry-run JSON)**: Run `write_load_history_definition()` with dummy ARNs, then parse the JSON output. Authoritative, slightly more setup.

**Recommendation**: Approach B. The Python heredoc inside `write_load_history_definition()` can be extracted and run with placeholder ARNs. The output JSON can then be validated with `python3`.

Checks:
1. Deploy script contains `write_load_history_definition` function — file-level sanity
2. `Stage1Parallel` state exists in generated JSON
3. `Stage1Parallel.Type == "Parallel"`
4. `Stage1Parallel.Branches` has exactly 2 branches
5. Branch A contains `WindowedBootstrap` Map state
6. Branch B contains `FundamentalsPerFiling` Map state  
7. Branch B contains `FundamentalsEntityFacts` Map state
8. `FundamentalsPerFiling` command includes `--mode per-filing`
9. `FundamentalsEntityFacts` command includes `--mode entity-facts`
10. `MdmRun` state still present after `Stage1Parallel`

#### Stage 2: `02_smoke_bootstrap_fundamentals.sh` — local smoke run

Runs `bootstrap-fundamentals` with a tiny fixture CIK list (2–3 CIKs known to have 8-K filings) in `per-filing` mode against a local DuckDB shard. Verifies:

1. Command exits 0
2. Silver shard exists at specified `--fundamentals-silver-path`
3. `sec_earnings_release` table has ≥ 1 row (or ≥ 0 rows if CIKs have no 8-K in the window — use a known-good CIK)
4. `sec_executive_record` table exists

**Known-good CIK for smoke**: Apple (CIK 320193) — files 8-K and DEF 14A regularly. A single CIK with `--cik-limit 1` keeps runtime short.

If network is unavailable (CI environment), skip Stage 2 with a logged warning rather than failing.

#### `run_all.sh`

Follows the exact pattern from `verify-pr2/run_all.sh`:
```bash
for stage in 01_check_sfn_branch_b.sh 02_smoke_bootstrap_fundamentals.sh; do
    ...
done
```

**Verification**:
- [ ] `bash scripts/verify-pr3/run_all.sh` exits 0 after Phase 1 and Phase 2 are complete
- [ ] Stage 1 produces output like `✓ Stage1Parallel state present` for each check
- [ ] Stage 2 produces `✓ sec_earnings_release has rows` (or `⚠ skipping smoke — no network`)

---

## Testing Strategy

### Unit verification (fast, no network)

The CLI offset/limit slicing logic in `execute()` is pure Python — add a unit test in `tests/test_bootstrap_fundamentals.py`:
```python
def test_cik_slice_offset_limit():
    cik_list = [1, 2, 3, 4, 5, 6]
    offset, limit = 2, 3
    result = cik_list[offset : offset + limit]
    assert result == [3, 4, 5]
```

### Integration verification (offline)

`01_check_sfn_branch_b.sh` Stage 1 checks are the integration gate — they validate the actual generated JSON with no AWS access.

### End-to-end (deferred to PR-4)

A real `bootstrap-fundamentals` run against live S3/Snowflake requires PR-4 scope (cloud roundtrip verify). The smoke run in Stage 2 is the closest offline proxy.

---

## Risk Mitigation

### Risk: Parallel state blows up `load_history` execution time
**Mitigation**: Branch B uses the same `MaxConcurrency=1` as Branch A — each branch processes one window at a time. The two branches run concurrently but each is internally sequential. Net wall-clock increase = Branch B duration (typically shorter than Branch A since `bootstrap-fundamentals` skips artifact re-fetch for cached files).

### Risk: Branch A `WindwedBootstrap` output format changes when wrapped in Parallel
**Mitigation**: Set `ResultPath: null` on both branches and on the `Stage1Parallel` state itself. The execution input (with `window_size`, `run_id`, etc.) passes through unchanged to `MdmRun`. This is the same pattern used in `ComputeWindows` and `WriteRunSummary`.

### Risk: `--cik-list` for Branch B is an S3 key, not a local path
**Mitigation**: `fundamentals_ingest.py` already resolves S3 paths via `read_cik_list()`. The `--cik-list` arg accepts both local paths and `s3://` URIs. Passing the S3 key in the Step Functions `States.Format(...)` is consistent with how Branch A passes `--run-id`.

### Risk: Step Function item payload for Branch B has wrong shape
**Mitigation**: Both branches read from the same `cik_windows.jsonl` which always produces `{"window_offset": N, "window_limit": M}` items. Branch B uses `$.window_offset` and `$.window_limit` — identical field names to Branch A.

---

## Dependencies

- `write_load_history_definition()` requires `wh_medium_arn` for Branch B ECS tasks (same profile as Branch A — no new task definition profile needed)
- `bootstrap-fundamentals --cik-offset` / `--cik-limit` (Phase 2 must complete before Phase 1 generates correct ASL)
- `verify-pr3/00_lib.sh` can be copied verbatim from `verify-pr2/00_lib.sh` — no changes needed

---

## Success Criteria

- [ ] `write_load_history_definition()` generates valid JSON with `Stage1Parallel` of type `Parallel` with 2 branches
- [ ] Branch A and Branch B both use `ResultPath: null`; `MdmRun` follows `Stage1Parallel`
- [ ] `bootstrap-fundamentals --cik-offset 0 --cik-limit 2` works correctly
- [ ] `bash scripts/verify-pr3/01_check_sfn_branch_b.sh` passes all 10 checks
- [ ] `bash scripts/verify-pr3/02_smoke_bootstrap_fundamentals.sh` passes (or skips gracefully)
- [ ] `bash scripts/verify-pr3/run_all.sh` exits 0
- [ ] Task #7 status updated to reflect both halves complete

---

## Estimated Effort

- Phase 1 (Step Function ASL update): ~2 hours — careful Python heredoc editing inside shell script, JSON validation
- Phase 2 (CLI offset/limit): ~30 minutes — small, well-scoped change
- Phase 3 (verify-pr3 harness): ~2 hours — copy 00_lib.sh, write two stage scripts + run_all.sh
- **Total**: ~4.5 hours

---

## PR-4 Preview (deferred, do not implement now)

| Item | Notes |
|---|---|
| `thirteenf` mode in Step Function | Needs separate `13f_filer_windows.jsonl` input; different CIK universe (~5,500 adviser CIKs) |
| Cloud roundtrip verify | Parquet → S3 upload → Snowflake COPY INTO for all 6 tables; requires real AWS credentials |
| verify-pr4 harness | Stages: thirteenf smoke, S3 upload check, Snowflake table row counts |

---

## Notes for Implementation

- The Python heredoc inside `write_load_history_definition()` spans ~180 lines (lines 1300–1471). Edit carefully — the bash function wraps a `python3 - <<'PY' ... PY` block. Indentation inside the heredoc is significant Python.
- The `ecs_state()` helper at the top of the heredoc accepts `is_end=True` to emit `"End": true` instead of `"Next": <state>`. Use this for all terminal states within Parallel branch sub-state-machines.
- `ResultPath: None` in Python serializes to `"ResultPath": null` in JSON — this is the correct Step Functions syntax for discarding task output.
- The deploy script uses `printf '%s\n' "$(...)"` not `echo` for ARN output — keep consistent.
- All Step Functions state names must be unique within their state machine scope. Within a Parallel branch's sub-state-machine, names only need to be unique within that branch — `WindowedBootstrap` can exist in Branch A and `FundamentalsPerFiling` in Branch B without conflict.
