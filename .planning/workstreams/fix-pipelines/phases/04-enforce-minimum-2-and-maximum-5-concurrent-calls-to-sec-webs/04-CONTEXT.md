# Phase 4: SEC Rate Limiting - Context

**Gathered:** 2026-05-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Enforce concurrency bounds on outbound SEC EDGAR HTTP calls across all pipeline ECS tasks:
1. Cap the Map state `MaxConcurrency` (i.e., `BOOTSTRAP_BATCH_CONCURRENCY`) at a default of 5 in `deploy-aws-application.sh` for both `bootstrap_phased` (BatchBootstrap) and `silver_mdm_gold` (BatchSilver).
2. Add `pyrate-limiter` rate limiting to `edgar_warehouse/infrastructure/sec_client.py` at 9 req/sec, matching the `edgartools` library's existing per-process limit.
3. Document the recommended floor of 2 concurrent tasks in `CLAUDE.md` and/or the runbook.

What this phase does NOT do: add per-task HTTP parallelism (async/threading within a task), add hard validation that rejects out-of-range values at deploy time, or change the `edgartools` library's own rate limiter.

</domain>

<decisions>
## Implementation Decisions

### What "concurrent" means
- **D-01:** Concurrent = ECS task concurrency at the Step Functions Map state level (`MaxConcurrency`), not HTTP connection concurrency within a task. Within each ECS task, SEC calls remain sequential.

### BOOTSTRAP_BATCH_CONCURRENCY default
- **D-02:** Update the default value of `BOOTSTRAP_BATCH_CONCURRENCY` from 10 → 5 in `deploy-aws-application.sh`. The variable stays configurable; no hard validation gate is added.
- **D-03:** Both `bootstrap_phased` (BatchBootstrap Map state) and `silver_mdm_gold` (BatchSilver Map state) use `BOOTSTRAP_BATCH_CONCURRENCY` — both get the new default.

### sec_client.py rate limiting
- **D-04:** Add `pyrate-limiter` (already in `uv.lock`) to `edgar_warehouse/infrastructure/sec_client.py`. Apply a 9 req/sec in-process rate limiter to `download_sec_bytes()`, matching `EDGAR_RATE_LIMIT_PER_SEC` (the edgartools default). No new env var needed — keep the rate consistent at 9/sec.

### Minimum floor
- **D-05:** The minimum of 2 concurrent tasks is a **documentation-only** recommendation. Note it in `CLAUDE.md` (the platform ops section) and/or the runbook as "do not run below 2 concurrent tasks — throughput is too low for production loads." No code enforcement.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### State machine definition (where MaxConcurrency lives)
- `infra/scripts/deploy-aws-application.sh` lines ~1288–1404 — `write_bootstrap_phased_definition()` — the Python-in-bash heredoc that generates `bootstrap_phased`. `BatchBootstrap` Map state's `MaxConcurrency: int(batch_concurrency)` at ~line 1348.
- `infra/scripts/deploy-aws-application.sh` lines ~1410–1530 — `write_silver_mdm_gold_definition()` — `BatchSilver` Map state's `MaxConcurrency: int(batch_concurrency)` at ~line 1478.
- `infra/scripts/deploy-aws-application.sh` ~line 1590 — `BOOTSTRAP_BATCH_CONCURRENCY` variable sourced from ECS env / shell; passed into both Python heredocs.

### SEC HTTP client (where rate limiting goes)
- `edgar_warehouse/infrastructure/sec_client.py` — our synchronous SEC client. `download_sec_bytes()` is the function to rate-limit. Currently uses bare `httpx.Client` with no throttle.

### edgartools library reference (pattern to match)
- `.venv/lib/python3.12/site-packages/edgar/httpclient.py` lines ~136–175 — `get_edgar_rate_limit_per_sec()` reads `EDGAR_RATE_LIMIT_PER_SEC` (default 9) and feeds it into `_create_rate_limiter()` using `pyrate_limiter.Rate` + `pyrate_limiter.Limiter`. Use this as the implementation pattern.

### pyrate-limiter (already in lockfile)
- `uv.lock` — `pyrate-limiter` (version 4.1.0) and `httpxthrottlecache` (0.3.5) are already resolved dependencies. No `uv add` needed; just `from pyrate_limiter import ...`.

### CLAUDE.md ops section (where to document the floor)
- `CLAUDE.md` — platform operator instructions. Add to the "Phased Pipeline" section: `BOOTSTRAP_BATCH_CONCURRENCY` recommended range is 2–5; values below 2 are not recommended for production runs.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `edgar_warehouse/infrastructure/sec_client.py` — single entry point for all our direct SEC calls. A module-level `Limiter` instance added here automatically applies to every `download_sec_bytes()` call without touching callers.
- `pyrate_limiter.Rate`, `pyrate_limiter.Duration`, `pyrate_limiter.InMemoryBucket`, `pyrate_limiter.Limiter` — available in the lockfile; same interface used by edgartools (line ~154 of `httpclient.py`).

### Established Patterns
- State machine `MaxConcurrency` is set via `int(batch_concurrency)` in the Python heredoc — a one-line change to the default value in the shell variable sets it for all new deployments.
- `download_sec_bytes()` already has its own retry loop (3 attempts with exponential backoff for 429/5xx). A `pyrate-limiter` transport wraps at the call level, not the transport level — acquire the rate token at the top of the function before each attempt.

### Integration Points
- After changing `BOOTSTRAP_BATCH_CONCURRENCY` default, redeploy via `deploy-aws-application.sh --skip-build` to push the new `MaxConcurrency` value live (same pattern as Phase 1, Task 2).
- The rate limiter in `sec_client.py` is in-process; it does not coordinate across ECS tasks. With 5 concurrent tasks each at 9 req/sec theoretical max, peak is ~45 req/sec — well under SEC's 10 req/sec per-IP limit because tasks are staggered and actual throughput per task is much lower than 9/sec (network + parsing overhead).

</code_context>

<specifics>
## Specific Ideas

- Rate limit in `sec_client.py`: use `pyrate_limiter.Rate(9, Duration.SECOND)` with `InMemoryBucket`. Acquire once per `download_sec_bytes()` call (before the retry loop). A module-level singleton `_SEC_RATE_LIMITER` is fine — same pattern as edgartools `HTTP_MGR`.
- `BOOTSTRAP_BATCH_CONCURRENCY` comment in `deploy-aws-application.sh`: update the inline comment when changing the default so operators understand the intent (e.g., "SEC rate limit: keep between 2–5 for production").

</specifics>

<deferred>
## Deferred Ideas

- Per-task HTTP parallelism (async/threading within an ECS task) — not in scope for Phase 4; would require significant refactor of `warehouse_orchestrator.py`.
- Hard validation of `BOOTSTRAP_BATCH_CONCURRENCY` range at deploy time (fail if outside [2, 5]) — user chose documentation-only for the floor; no code enforcement.
- Shared cross-task rate limiter (e.g., DynamoDB-backed token bucket) to enforce a true global ceiling across all concurrent ECS tasks — over-engineering for current scale; not in scope.

</deferred>

---

*Phase: 04-SEC Rate Limiting*
*Context gathered: 2026-05-16*
