Type: task
Status: resolved

## Question

`_ensure_security_by_cusip` (`edgar_warehouse/mdm/pipeline.py:3271-3390`) issues a fresh `SELECT MdmSecurity.entity_id WHERE cusip = ?` round trip on every holding row it's called for — never memoized. Given a CUSIP is referenced heavily across `sec_thirteenf_holding`, should this be cached the same way the sibling `_ensure_thirteenf_manager`/`adviser_id_by_cik` lookup already is?

## Context

Raised directly by the user while reviewing `INSTITUTIONAL_HOLDS` throughput (same investigation that surfaced [Ticket 06](06-relationship-derivation-batch-level-commit.md)'s commit gap): "review 6.8 million rows 13F to optimize also are we loading only 2 years of 13f."

**2-year loading question, answered first and separately:** confirmed via code read (`warehouse_orchestrator.py:267`, `_resolve_thirteenf_lookback_years`) — `WAREHOUSE_THIRTEENF_LOOKBACK_YEARS` defaults to `DEFAULT_FUNDAMENTALS_LOOKBACK_YEARS = 2`. This is an ingestion-time filter (what gets fetched/parsed from SEC into `sec_thirteenf_holding`), not a query-time filter — the 6.8M-row figure already reflects that 2-year bound, not full history. No fix needed here; the answer is "yes, already bounded."

**Optimization finding, the real subject of this ticket:** live measurement against prod Snowflake (2026-09-08):

```sql
SELECT COUNT(*) AS total_rows, COUNT(DISTINCT CUSIP) AS distinct_cusips, COUNT(DISTINCT CIK) AS distinct_managers
FROM EDGARTOOLS_PROD.EDGARTOOLS_SILVER.SEC_THIRTEENF_HOLDING;
-- total_rows: 6,799,919  distinct_cusips: 41,225  distinct_managers: 8,783
```

Each CUSIP is referenced ~165x on average. `_ensure_security_by_cusip` pays a full round trip for every one of those 6.8M references, even though the entity_id mapping is permanent and deterministic (`UUID5(NAMESPACE_DNS, f"cusip:{cusip}")`) — once resolved, it never needs re-querying. This is the same shape as `_ensure_thirteenf_manager`'s existing, already-fixed CIK memoization (`adviser_id_by_cik`, declared once in `_derive_institutional_holds`, shared across all CIK-range batches) sitting in the very same function, just never ported to the security side.

The reason it was left unmemoized (per the function's own pre-existing comment): it opportunistically backfills `security_class` when NULL, "so a later row with a non-NULL value can still backfill an earlier NULL one." A naive cache risks silently skipping a real backfill.

## Answer

**Fix (implemented):** `_ensure_security_by_cusip` gained an optional `cache: dict[str, tuple[str, bool]]` parameter — `cusip -> (entity_id, security_class_confirmed_satisfied)`. Declared once in `_derive_institutional_holds` (`security_id_by_cusip`, same scope/lifetime as `adviser_id_by_cik`) and threaded through `_derive_institutional_holds_batch` down to the per-row call.

Correctness preserved exactly by tracing every branch of the original function:
- Cache hit + `security_class` truthy + not yet satisfied → still performs the real backfill check (`session.get`), same cost as before, just skips the now-redundant initial entity_id `SELECT`.
- Cache hit + already satisfied, or no `security_class` offered → skip entirely, no round trip at all.
- Cache miss (first time seeing a CUSIP) → runs the original lookup/creation logic unchanged, then populates the cache with a `satisfied` flag that's `True` only when the DB's `security_class` non-NULL state was just actually confirmed (via creation-with-a-value, or a backfill check that found/set one) — `False` whenever the original code would also never have checked (row offered no class), so a later row can still trigger the real check.

Cache stores only primitives (`str` entity_id + `bool`), never ORM object references — this is deliberately safe against Ticket 06's new periodic mid-derivation commits (which expire ORM object attributes via SQLAlchemy's default `expire_on_commit=True`, but never invalidate plain cached values).

`/gof-refactor-reviewer` consulted before implementing (CLAUDE.md hard rule): confirmed the single-caller scope and the `adviser_id_by_cik` precedent justify this shape, and walked every branch of `_ensure_security_by_cusip` to confirm no edge case lets the cache silently skip a real backfill.

Tests: 2 new in `tests/mdm/test_pipeline_relationships.py`'s `TestInstitutionalHoldsBatching` —
`test_ensure_security_by_cusip_cache_batches_round_trips_not_one_per_row` (3 rows, 2
distinct CUSIPs → asserts exactly 2 by-cusip `SELECT`s via a `before_cursor_execute`
event counter; confirmed to fail with 3 against the pre-fix code via a `git stash`
round-trip — an initial looser bound (`<=4`) was caught as not actually distinguishing
pre/post-fix behavior and tightened to the precise `==2` before being trusted) and
`test_ensure_security_by_cusip_cache_preserves_backfill_correctness` (a CUSIP's first
row offers no `security_class`, cached unsatisfied; a second row for the same CUSIP
offers one; asserts the backfill still lands). Full `tests/mdm/` suite green.

**Not yet deployed or live-verified as of this entry** — same as Ticket 06, this fix has
not yet been built into an image or deployed to prod. Real before/after wall-clock or
round-trip-count measurement against a live `INSTITUTIONAL_HOLDS` derivation is the
natural follow-up once deployed, matching this map's "real measurements" standing
preference.
