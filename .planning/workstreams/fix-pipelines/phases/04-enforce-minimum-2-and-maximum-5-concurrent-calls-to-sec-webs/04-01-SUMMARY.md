---
plan: 04-01
phase: 04-enforce-minimum-2-and-maximum-5-concurrent-calls-to-sec-webs
status: complete
completed: 2026-05-16
commit: e029629
---

# Plan 04-01 Summary: SEC Rate Limiter + BOOTSTRAP_BATCH_CONCURRENCY Docs

## What Was Built

**Task 1 — Rate limiter in `sec_client.py`**
- Added `from pyrate_limiter import Duration, InMemoryBucket, Limiter, Rate` at module scope
- Defined `_create_sec_rate_limiter()` factory using the multi-version try/except guard (pyrate-limiter 3.x/4.x compatible)
- Declared `_SEC_RATE_LIMITER: Limiter = _create_sec_rate_limiter()` as a module-level singleton initialized at import time
- Inserted `_SEC_RATE_LIMITER.try_acquire("sec_download")` inside `download_sec_bytes()` after `_validate_sec_url(url)` and before `last_error = None` (before the retry loop) — one token consumed per logical SEC request

**Task 2 — Unit test in `tests/unit/test_sec_client.py`**
- Added `_SEC_RATE_LIMITER` to the import line
- Added `test_rate_limiter_called_once_per_request` covering: success case (try_acquire called once) and retry case (try_acquire called once even when first attempt raises httpx.RequestError)
- All 4 tests pass (3 existing + 1 new)

**Task 3 — CLAUDE.md documentation**
- Appended bullet to "Key invariants (do not break):" documenting `BOOTSTRAP_BATCH_CONCURRENCY` recommended range 2–5, current default 3 confirmed compliant, with rationale for both bounds (throughput floor at <2, SEC rate limit risk at >5)

## Verification Results

```
uv run pytest tests/unit/test_sec_client.py -x -v
4 passed in 0.67s
```

Source checks confirmed:
- `_SEC_RATE_LIMITER` at module scope (line 32) and `try_acquire` inside `download_sec_bytes` (line 62)
- `from pyrate_limiter import` at module scope
- CLAUDE.md Key invariants bullet present at line 154

## Key Decisions

- `BOOTSTRAP_BATCH_CONCURRENCY` default of 3 NOT changed (already within 2–5 bounds; per user decision captured in plan)
- pyrate-limiter 4.1.0 `Limiter(bucket)` branch of the try/except guard is the effective path at runtime; try/except guard retained for forward compatibility

## Acceptance Criteria Met

- [x] `_SEC_RATE_LIMITER` singleton at module scope in sec_client.py
- [x] `try_acquire("sec_download")` before retry loop in `download_sec_bytes()`
- [x] `test_rate_limiter_called_once_per_request` test exists and passes
- [x] All 4 sec_client unit tests pass
- [x] CLAUDE.md documents BOOTSTRAP_BATCH_CONCURRENCY recommended range 2–5 with default 3 as compliant
- [x] No existing CLAUDE.md content removed or reformatted
- [x] `deploy-aws-application.sh` line 139 unchanged (BOOTSTRAP_BATCH_CONCURRENCY=3)
