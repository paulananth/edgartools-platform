# Phase 6: Relationship Investigation And Population - Pattern Map

**Mapped:** 2026-07-08
**Files analyzed:** 3 (modified, no wholly-new files — this phase extends existing derivers/verification)
**Analogs found:** 3 / 3 (all self-analogs — sibling functions in the same files)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `edgar_warehouse/mdm/pipeline.py` (`_derive_institutional_holds` — CIK-range batching, D-03) | service (MDM relationship deriver) | batch / CRUD-upsert | `edgar_warehouse/mdm/pipeline.py` (`_derive_employed_by` / `_derive_audited_by` — same file, sibling deriver methods) | exact (same file, same method being extended) |
| `edgar_warehouse/mdm/pipeline.py` (EDGE-05/EDGE-06 SQL-confirmed zero-overlap check — no code change expected unless a diagnostic/CLI surface is added) | service / diagnostic query | request-response (SQL check) | `edgar_warehouse/mdm/pipeline.py` (`_adviser_company_pairs` / `_adviser_person_pairs`, L1438-1454) | exact — same join logic being independently verified |
| `edgar_warehouse/mdm/snowflake_graph.py` (extend `POPULATED_RELATIONSHIP_TYPES` + `_named_relationship_parity_checks`, D-05) | service (graph verification gate) | request-response / event-driven (verify-graph CLI) | `edgar_warehouse/mdm/snowflake_graph.py` — Phase 5's own 05-03 addition of this exact function (L1227-1260) | exact (identical pattern, additive only) |

No new files are created this phase — all work extends already-established functions in
`pipeline.py` and `snowflake_graph.py`. Treat each modified function as both the target and
its own best analog: Phase 6 must follow the conventions already used by sibling derivers in
the same file, and the exact pattern already built in Phase 5 for the verification file.

## Pattern Assignments

### `edgar_warehouse/mdm/pipeline.py` — INSTITUTIONAL_HOLDS CIK-range batching (D-03, EDGE-11)

**Analog:** `_derive_employed_by` / `_derive_audited_by` in the same file (both already use
`_fetch_optional_relationship_rows` + `_bounded_relationship_sql`), and `_derive_institutional_holds`
itself (current unbatched version, `pipeline.py:1330-1436`).

**Existing bounded-fetch mechanism to extend, not replace** (`pipeline.py:100-142`):
```python
@staticmethod
def _bounded_relationship_sql(sql: str, remaining: Optional[int], existing: int = 0) -> str:
    """Append a LIMIT that grows with `existing` so the source window keeps
    advancing past already-converted rows on repeat runs."""
    if remaining is None:
        return sql
    source_limit = int(existing) + max(
        int(remaining) * _RELATIONSHIP_SOURCE_LIMIT_MULTIPLIER,
        _RELATIONSHIP_SOURCE_LIMIT_MINIMUM,
    )
    return f"{sql.rstrip()} LIMIT {source_limit}"

def _fetch_optional_relationship_rows(
    self, sql: str, remaining: Optional[int], *,
    rel_type_name: str, source_table: str, existing: int = 0,
) -> list[dict]:
    try:
        return self.silver.fetch(self._bounded_relationship_sql(sql, remaining, existing))
    except Exception as exc:
        if not self._is_missing_source_table(exc, source_table):
            raise
        print(json.dumps({
            "event": "mdm_relationship_skip",
            "rel_type": rel_type_name,
            "reason": "missing_source_table",
            "source_table": source_table,
            "ts": datetime.now(timezone.utc).isoformat(),
        }), file=sys.stderr, flush=True)
        return []
```

**Current `_derive_institutional_holds` structure to preserve** (`pipeline.py:1330-1376`,
truncated — full source-select/skip-counter/`ensure_relationship` loop pattern is identical
to `_derive_employed_by`/`_derive_audited_by` below):
```python
def _derive_institutional_holds(
    self, sync_engine: GraphSyncEngine, remaining: Optional[int]
) -> tuple[int, int, int, int, int]:
    sql = """
        SELECT cik, accession_number, period_of_report, cusip,
               issuer_name, security_title, shares_held, market_value,
               put_call, discretion_type, security_class
        FROM sec_thirteenf_holding
        WHERE cusip IS NOT NULL
        ORDER BY cik, accession_number, cusip
    """
    existing = self._relationship_count("INSTITUTIONAL_HOLDS")
    inserted = 0
    skipped_corporate = 0
    skipped_unresolved_source = 0
    skipped_unresolved_target = 0
    skipped_existing = 0

    for row in self._fetch_optional_relationship_rows(
        sql, remaining,
        rel_type_name="INSTITUTIONAL_HOLDS",
        source_table="sec_thirteenf_holding",
        existing=existing,
    ):
        cik = row.get("cik")
        cusip = row.get("cusip") or ""
        ...
```

**Batching design to add (D-03, per TODOS.md L1-33):** Wrap the existing per-row loop body in
an outer `for cik_lo, cik_hi in cik_range_batches(batch_size=...)` loop, changing the `sql`
string to append `AND cik BETWEEN {cik_lo} AND {cik_hi}` (parameterize, don't string-format
raw user input — follow the same `.rstrip()` + f-string LIMIT convention already used in
`_bounded_relationship_sql` for consistency, but prefer bound params if `silver.fetch` supports
them — check `SilverDatabase.fetch`'s signature before choosing). Keep `_relationship_count`,
skip-counter accumulation, and the `remaining is not None and inserted >= remaining: break`
early-exit exactly as-is across the outer loop (accumulate across all CIK-range batches, don't
reset per-batch). TODOS.md explicitly notes: "The adviser-entity resolution is per-CIK, so the
ordering requirement doesn't apply — this deriver is safely batchable," meaning batch order
does not need to match the single-query `ORDER BY cik, accession_number, cusip`.

**Skip/error JSON logging pattern to reuse verbatim** (identical across `_derive_employed_by`,
`_derive_audited_by`, `_derive_institutional_holds` — `pipeline.py:1156-1163` shown, same shape
throughout):
```python
print(json.dumps({
    "event": "mdm_relationship_skip",
    "rel_type": "EMPLOYED_BY",
    "reason": "unresolved_target",
    "cik": cik,
    "ts": datetime.now(timezone.utc).isoformat(),
}), file=sys.stderr, flush=True)
```

**Return signature convention (all derivers, unchanged):**
`tuple[int, int, int, int, int]` = `(inserted, skipped_corporate, skipped_unresolved_source, skipped_unresolved_target, skipped_existing)`.

---

### `edgar_warehouse/mdm/pipeline.py` — EDGE-05/EDGE-06 zero-overlap SQL check (D-04)

**Analog:** `_adviser_company_pairs` / `_adviser_person_pairs` (`pipeline.py:1438-1454`) — the
exact join logic the SQL-confirmed check must independently verify (not a weaker proxy):

```python
def _adviser_company_pairs(self):
    from edgar_warehouse.mdm.database import MdmAdviser
    from sqlalchemy import select
    return self.session.execute(
        select(MdmAdviser.entity_id, MdmAdviser.linked_company_entity_id)
        .where(MdmAdviser.linked_company_entity_id.isnot(None))
    ).all()

def _adviser_person_pairs(self):
    from edgar_warehouse.mdm.database import MdmAdviser, MdmPerson
    from sqlalchemy import select
    return self.session.execute(
        select(MdmAdviser.entity_id, MdmPerson.entity_id)
        .join(MdmPerson, MdmPerson.owner_cik == MdmAdviser.cik)
        .where(MdmAdviser.cik.isnot(None))
        .where(MdmAdviser.linked_company_entity_id.is_(None))
    ).all()
```

Existing `_derive_is_entity_of`/`_derive_is_person_of` (`pipeline.py:662-726`) already iterate
these pair generators and call `sync_engine.ensure_relationship(...)` — this is the production
code path D-04's SQL check must corroborate, not duplicate with different logic. Per CONTEXT.md
D-04, the check itself is: `MdmCompany.cik ∩ MdmAdviser.cik` (EDGE-05) and
`MdmPerson.owner_cik ∩ MdmAdviser.cik` (EDGE-06) — a standalone diagnostic SQL query (ad-hoc via
`snow sql` / a debug script), not necessarily a new pipeline.py function. If a permanent
diagnostic surface is warranted, follow the `_adviser_company_pairs`/`_adviser_person_pairs`
style: a small `select(...).where(...)` returning a count, added near those two methods.

---

### `edgar_warehouse/mdm/snowflake_graph.py` — extend `POPULATED_RELATIONSHIP_TYPES` + parity checks (D-05)

**Analog:** Phase 5's own 05-03 work — this is the exact pattern to repeat, not a new design.

**Constant to extend** (`snowflake_graph.py:33-39`):
```python
# D-01 / EDGE-01..04: the 4 relationship types already populated this milestone.
# The remaining 7 ALLOWED_RELATIONSHIP_TYPES (AUDITED_BY, EMPLOYED_BY,
# HAS_PARENT_COMPANY, INSTITUTIONAL_HOLDS, IS_ENTITY_OF, IS_PERSON_OF,
# MANAGES_FUND) are intentionally excluded from named parity checks until
# Phases 6-7 populate them -- named-checking a legitimately-zero type this
# milestone does not yet cover would false-fail verify-graph (T-05-05).
POPULATED_RELATIONSHIP_TYPES = ("COMPANY_HOLDS", "HOLDS", "ISSUED_BY", "IS_INSIDER")
```
Phase 6 must add only the specific types this phase's investigation confirms populated (per
D-05's sequencing note: derive → sync → verify per type). Do NOT add a type to
`POPULATED_RELATIONSHIP_TYPES` before `mdm sync-graph` has run for it — 05-03's design makes
this fail closed on purpose (a "no parity row" hard failure), not a bug to work around.
Update the comment block to move each newly-populated type out of the "remaining"
enumeration and into the tuple, keeping the "T-05-05" false-fail rationale intact for whatever
types are still deferred (e.g. HAS_PARENT_COMPANY, MANAGES_FUND if out of Phase 6 scope).

**Named parity-check function — zero new SQL needed, already generic over the tuple**
(`snowflake_graph.py:1227-1260`):
```python
def _named_relationship_parity_checks(
    relationship_parity: dict[str, Any],
) -> list[dict[str, Any]]:
    """EDGE-01..04 (D-01): one named parity check per already-populated relationship type.

    Reads only the already-computed relationship_parity["by_relationship_type"] rows --
    no new SQL. Scoped to POPULATED_RELATIONSHIP_TYPES only; the 7 not-yet-populated
    relationship types are intentionally excluded (T-05-05).
    """
    by_type = {
        row["relationship_type"]: row for row in relationship_parity["by_relationship_type"]
    }
    checks = []
    for relationship_type in POPULATED_RELATIONSHIP_TYPES:
        row = by_type.get(relationship_type)
        present = row is not None
        mdm_active_count = row["mdm_active_count"] if present else 0
        snowflake_graph_edge_count = row["snowflake_graph_edge_count"] if present else 0
        at_parity = present and row["mdm_minus_graph"] == 0 and row["graph_minus_mdm"] == 0
        check = {
            "name": f"relationship_parity_{relationship_type.lower()}",
            "relationship_type": relationship_type,
            "present": present,
            "mdm_active_count": mdm_active_count,
            "snowflake_graph_edge_count": snowflake_graph_edge_count,
            "status": "ok" if at_parity else "failed",
        }
        if not present:
            check["remediation"] = (
                f"No parity row for relationship_type={relationship_type!r}: confirm "
                "mdm load-relationships has populated this type and re-run mdm sync-graph."
            )
        checks.append(check)
    return checks
```
This function requires **no code change** — it already iterates `POPULATED_RELATIONSHIP_TYPES`
generically. Editing the tuple constant is the entire "code change" for D-05; the docstring
comment above the tuple is the only prose that needs updating to reflect the new coverage.

**Wiring point (unchanged, do not fragment):** `verify()` at `snowflake_graph.py:313-314` calls
`_named_relationship_parity_checks(relationship_parity)` — this is the single gate consumed by
Step Functions `mdm_verify_graph` and `go-live.sh`'s local preflight (Phase 5 D-01). Phase 6
must not add a second/parallel verification path.

---

## Shared Patterns

### Idempotent upsert via `ensure_relationship`
**Source:** `edgar_warehouse/mdm/pipeline.py` (used identically by every deriver: `_derive_is_entity_of`,
`_derive_is_person_of`, `_derive_employed_by`, `_derive_audited_by`, `_derive_institutional_holds`)
**Apply to:** Any new/modified deriver logic in this phase — do not re-derive idempotency;
`created` bool from `ensure_relationship(...)` already distinguishes insert vs. existing-skip.
```python
_rel, created = sync_engine.ensure_relationship(
    rel_type_name="EMPLOYED_BY",
    source_entity_id=person_id,
    target_entity_id=company_id,
    properties={...},
    effective_from=effective_from,
    source_system="proxy_filing",
    source_accession=accession_number,
)
if created:
    inserted += 1
else:
    skipped_existing += 1
```

### Missing-source-table graceful skip
**Source:** `_fetch_optional_relationship_rows` / `_is_missing_source_table` (`pipeline.py:121-142`)
**Apply to:** Any deriver reading an artifact table that may not exist yet in a freshly loaded
dev environment (`sec_executive_record`, `sec_accounting_flag`, `sec_thirteenf_holding`) — emits
a structured `mdm_relationship_skip` JSON event to stderr and returns `[]` rather than raising.

### Structured skip/error logging
**Source:** repeated verbatim across all three artifact-backed derivers (`pipeline.py:1156-1163`,
`1274-1280`, `1286-1294`, etc.)
**Apply to:** Any new skip branch added by D-03's batching or D-04's diagnostic check — always
`json.dumps({"event": "mdm_relationship_skip", "rel_type": ..., "reason": ..., ...,
"ts": datetime.now(timezone.utc).isoformat()})` to `sys.stderr`.

### Named per-type parity check (Phase 5 -> Phase 6 extension)
**Source:** `edgar_warehouse/mdm/snowflake_graph.py:1227-1260` (built in 05-03, see
`.planning/workstreams/fix-pipelines/phases/05-node-and-populated-relationship-graph-parity/05-03-PLAN.md`
and `05-03-SUMMARY.md`)
**Apply to:** `POPULATED_RELATIONSHIP_TYPES` constant only — the check function itself needs no
change, confirming this is a pure data (tuple) extension, not new code.

## No Analog Found

None. Every file/function this phase touches already has an established sibling pattern in the
same module (pipeline.py derivers mirror each other; snowflake_graph.py's named-check pattern
was purpose-built in Phase 5 to be extended this way).

## Metadata

**Analog search scope:** `edgar_warehouse/mdm/pipeline.py`, `edgar_warehouse/mdm/snowflake_graph.py`,
`.planning/workstreams/fix-pipelines/phases/05-node-and-populated-relationship-graph-parity/`
**Files scanned:** 2 source files (read in targeted, non-overlapping sections), 1 CONTEXT.md,
1 TODOS.md excerpt, 1 prior-phase plan file (05-03-PLAN.md, grep only)
**Pattern extraction date:** 2026-07-08
