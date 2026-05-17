# Phase 06: Relationship Derivation Coverage — Research

**Researched:** 2026-05-17
**Domain:** MDM pipeline relationship derivation, skip diagnostics, test coverage
**Confidence:** HIGH — all findings read directly from source files

---

## Summary

- All 6 derivers already exist in `pipeline.py`. Phase 6 is purely additive: expanded skip counters (D-02), per-pair stderr events (D-03), fixture additions for MANAGES_FUND/ISSUED_BY (D-01), and a full-corpus idempotency test (D-04).
- Four of the six derivers (`_derive_is_entity_of`, `_derive_is_person_of`, `_derive_manages_fund`, `_derive_issued_by`) iterate pre-filtered MDM rows and have exactly ONE possible skip reason: `skipped_existing`. The `skipped_corporate`, `skipped_unresolved_source`, and `skipped_unresolved_target` counters are structurally always 0 for these types.
- The two derivers that read silver directly (`_derive_is_insider`, `_derive_holds`) have three distinct skip sites, but the current code collapses the "unresolved source" and "unresolved target" cases into a single `if issuer_id is None or person_id is None: skipped += 1`. Splitting this correctly requires a priority rule to avoid double-counting.
- D-03 structured events create a contradiction for the four entity-only derivers: they never hold silver-layer business keys, only surrogate entity_ids. The cleanest resolution is to suppress D-03 emission for the entity-only types (they only ever skip on "existing", which is low-signal on second run).
- MANAGES_FUND and ISSUED_BY have zero test coverage today. Enabling them requires adding MdmFund and MdmSecurity rows to `fixture_world` and MdmSourceRef rows so `_security_entity_id()` can resolve via source_id lookup.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Extend the existing `_seed_registry` stub fixture (in-memory SQLite, no DuckDB dependency) rather than creating a new end-to-end test class. Add one MdmFund row with `adviser_entity_id` pointing to the existing stub adviser entity, and one MdmSecurity row with `issuer_entity_id` pointing to the existing stub company entity.
- **D-02:** Extend the per-type summary dict returned by `derive_relationships` with four additional keys: `skipped_corporate`, `skipped_unresolved_source`, `skipped_unresolved_target`, `skipped_existing`. The existing `skipped` key becomes the sum of all four for backward compatibility.
- **D-03:** For each skipped pair emit a JSON-line to stderr: `print(json.dumps({...}), file=sys.stderr, flush=True)`. Do NOT import from `sec_client.py` — copy the pattern inline. Do NOT log surrogate MDM entity IDs — log silver-layer business keys (CIKs, accession numbers).
- **D-04:** Add one test that runs `derive_relationships()` (no filter, no target_per_type) twice and asserts `inserted == 0` for all 6 types on second run.

### Claude's Discretion

- None specified — all implementation decisions are locked.

### Deferred Ideas (OUT OF SCOPE)

- End-to-end test with real DuckDB silver fixture
- Coverage-ratio percentage (% can be computed from counters by operator)
- Neo4j edge sync for relationship instances (Phase 7)
- Alerting when coverage ratio drops below a threshold
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REL-01 | MDM derives IS_INSIDER relationships for all non-corporate Forms 3/4/5 reporting owners with resolved issuer and person entities | Skip site map in Section 1 shows corporate-filter + unresolved-source/target logic; fixture tests in Section 6/7 |
| REL-02 | MDM derives HOLDS and ISSUED_BY relationships for ownership securities with resolved owners, securities, and issuers | HOLDS skip sites in Section 1; ISSUED_BY fixture requirements in Sections 3, 7 |
| REL-03 | MDM derives MANAGES_FUND, IS_ENTITY_OF, and IS_PERSON_OF relationships for adviser/fund/company/person links | MANAGES_FUND fixture in Section 2; entity-only skip-site characterization in Section 1 |
| REL-04 | Relationship derivation is idempotent: repeated runs against unchanged silver and MDM data do not create duplicate active relationship rows | Idempotency gap analysis in Section 6 |
</phase_requirements>

---

## 1. Skip Site Map (per deriver, per D-02 category)

`[VERIFIED: edgar_warehouse/mdm/pipeline.py direct read]`

### IS_INSIDER (`_derive_is_insider`, lines 249–284)

| Skip site | Approx line | Current code | D-02 category |
|-----------|-------------|--------------|---------------|
| Corporate owner | 263–265 | `if owner_cik in company_ciks: skipped += 1; continue` | `skipped_corporate` |
| Combined unresolved | 268–270 | `if issuer_id is None or person_id is None: skipped += 1; continue` | Needs split: `skipped_unresolved_source` (person) vs `skipped_unresolved_target` (issuer) |
| Existing row | 280–281 | `skipped += 0 if created else 1` | `skipped_existing` |

**Split rule (important):** When splitting line 268-270 into two counters, check source first:
```python
if person_id is None:
    skipped_unresolved_source += 1; continue  # source = person
if issuer_id is None:
    skipped_unresolved_target += 1; continue  # target = company
```
This prevents double-counting: a pair where both are None counts only as `unresolved_source`. This preserves the invariant `skipped == skipped_corporate + skipped_unresolved_source + skipped_unresolved_target + skipped_existing`.

### HOLDS (`_derive_holds`, lines 286–331)

| Skip site | Approx line | Current code | D-02 category |
|-----------|-------------|--------------|---------------|
| Corporate owner | 303–305 | `if owner_cik in company_ciks: skipped += 1; continue` | `skipped_corporate` |
| Combined unresolved | 310–312 | `if person_id is None or security_id is None: skipped += 1; continue` | Needs split: `skipped_unresolved_source` (person) vs `skipped_unresolved_target` (security) |
| Existing row | 328–329 | `skipped += 0 if created else 1` | `skipped_existing` |

**Note:** For HOLDS, source = person, target = security. Apply same priority rule: check `person_id` first.

### IS_ENTITY_OF (`_derive_is_entity_of`, lines 333–347)

| Skip site | Approx line | Current code | D-02 category |
|-----------|-------------|--------------|---------------|
| Existing row | 343–344 | `skipped += 0 if created else 1` | `skipped_existing` |

**Structural observation:** `_adviser_company_pairs()` queries `MdmAdviser.linked_company_entity_id IS NOT NULL`, so source and target entity IDs are always non-None. `skipped_corporate`, `skipped_unresolved_source`, `skipped_unresolved_target` are structurally always 0 for this type. No silver rows touched.

### MANAGES_FUND (`_derive_manages_fund`, lines 365–383)

| Skip site | Approx line | Current code | D-02 category |
|-----------|-------------|--------------|---------------|
| Existing row | 379–380 | `skipped += 0 if created else 1` | `skipped_existing` |

**Structural observation:** Query is `select(MdmFund).where(MdmFund.adviser_entity_id.isnot(None))`. Both `fund.adviser_entity_id` (source) and `fund.entity_id` (PK, target) are guaranteed non-None. Only `skipped_existing` is populated.

### ISSUED_BY (`_derive_issued_by`, lines 385–403)

| Skip site | Approx line | Current code | D-02 category |
|-----------|-------------|--------------|---------------|
| Existing row | 399–400 | `skipped += 0 if created else 1` | `skipped_existing` |

**Structural observation:** Query is `select(MdmSecurity).where(MdmSecurity.issuer_entity_id.isnot(None))`. Both `security.entity_id` (PK, source) and `security.issuer_entity_id` (target) are guaranteed non-None. Only `skipped_existing` is populated.

### IS_PERSON_OF (`_derive_is_person_of`, lines 349–363)

| Skip site | Approx line | Current code | D-02 category |
|-----------|-------------|--------------|---------------|
| Existing row | 359–360 | `skipped += 0 if created else 1` | `skipped_existing` |

**Structural observation:** `_adviser_person_pairs()` performs a JOIN between `MdmAdviser` and `MdmPerson` on `owner_cik`, filtered to `linked_company_entity_id IS NULL`. Both returned entity IDs are always non-None from the JOIN. Only `skipped_existing` is populated.

---

## 2. MdmFund Fixture Fields

`[VERIFIED: edgar_warehouse/mdm/database.py direct read]`

### MdmFund model (lines 272–295)

```python
class MdmFund(Base):
    __tablename__ = "mdm_fund"

    entity_id: Mapped[str]               # PK, FK -> mdm_entity.entity_id  (required, no default)
    adviser_entity_id: Mapped[Optional[str]]  # FK -> mdm_entity.entity_id  (nullable=True)
    canonical_name: Mapped[str]          # nullable=False                  (required)
    fund_type: Mapped[Optional[str]]     # nullable=True
    jurisdiction: Mapped[Optional[str]]  # nullable=True
    aum_amount: Mapped[Optional[object]] # nullable=True
    aum_as_of_date: Mapped[Optional[object]]  # nullable=True
    valid_from                           # server_default=NOW()
    valid_to                             # nullable=True
```

**Required fields (no-default, no-null):** `entity_id`, `canonical_name`.

**FK semantics:** `entity_id` is FK to `mdm_entity.entity_id` (not self-assigned — requires pre-inserting an MdmEntity row of `entity_type='fund'`). `adviser_entity_id` is also FK to `mdm_entity.entity_id` directly, NOT to `mdm_adviser` — so any existing adviser's `entity_id` can be used.

**`_derive_manages_fund` query:** Filters on `adviser_entity_id.isnot(None)`, then uses `fund.adviser_entity_id` as source and `fund.entity_id` as target. There is no silver lookup — the deriver reads only from the MDM fund table.

### Example `fixture_world` extension for MANAGES_FUND

```python
# In fixture_world (test_pipeline_relationships.py)
fund_entity_id = _add_entity(session, "fund")
session.add(MdmFund(
    entity_id=fund_entity_id,
    adviser_entity_id=firm_adviser_id,   # points to existing adviser MdmEntity
    canonical_name="Linked Growth Fund",
))
session.commit()
# Return: fixture_world["fund_entity_id"] = fund_entity_id
```

For MANAGES_FUND to produce 1 inserted row: fund row with `adviser_entity_id` set is sufficient. No MdmSourceRef needed and no silver rows needed.

---

## 3. MdmSecurity Fixture Fields

`[VERIFIED: edgar_warehouse/mdm/database.py direct read]`

### MdmSecurity model (lines 247–269)

```python
class MdmSecurity(Base):
    __tablename__ = "mdm_security"

    entity_id: Mapped[str]               # PK, FK -> mdm_entity.entity_id  (required, no default)
    issuer_entity_id: Mapped[Optional[str]]  # FK -> mdm_entity.entity_id  (nullable=True)
    canonical_title: Mapped[str]         # nullable=False                  (required)
    security_type: Mapped[Optional[str]] # nullable=True
    cusip: Mapped[Optional[str]]         # nullable=True
    isin: Mapped[Optional[str]]          # nullable=True
    valid_from                           # server_default=NOW()
    valid_to                             # nullable=True
```

**Required fields (no-default, no-null):** `entity_id`, `canonical_title`.

**FK semantics:** `entity_id` FK -> `mdm_entity.entity_id` (requires pre-inserting MdmEntity of `entity_type='security'`). `issuer_entity_id` FK -> `mdm_entity.entity_id` directly — point at the existing company's `entity_id`.

**`_derive_issued_by` query:** Filters on `issuer_entity_id.isnot(None)`, uses `security.entity_id` as source and `security.issuer_entity_id` as target. Like MANAGES_FUND, this reads only MDM tables — no silver lookup, no MdmSourceRef needed for the ISSUED_BY deriver itself.

**Distinction from HOLDS:** `test_writes_holds_from_non_derivative_transactions` (line 381) already adds an MdmSecurity with a MdmSourceRef (`source_id="0000-issuer-1:0:0"`) so that `_security_entity_id()` can resolve a security from a txn row. That MdmSourceRef is needed for HOLDS (silver-based lookup) but NOT for ISSUED_BY (MDM-table iteration). The D-01 fixture extension for ISSUED_BY only needs the MdmSecurity row itself with `issuer_entity_id` set.

### Example `fixture_world` extension for ISSUED_BY

```python
# In fixture_world (test_pipeline_relationships.py)
security_entity_id = _add_entity(session, "security")
session.add(MdmSecurity(
    entity_id=security_entity_id,
    issuer_entity_id=issuer_company_id,  # points to existing company MdmEntity
    canonical_title="Common Stock",
))
session.commit()
# Return: fixture_world["security_entity_id"] = security_entity_id
```

---

## 4. Current Summary Dict Structure

`[VERIFIED: edgar_warehouse/mdm/pipeline.py lines 209–227]`

### Keys returned by `derive_relationships` today

```python
summary[rel_type_name] = {
    "existing": existing,   # int — active rows before this run
    "inserted": inserted,   # int — new rows created in this run
    "skipped":  skipped,    # int — pairs not inserted (all reasons combined)
    "target":   target_per_type,  # int or None
    "total":    existing + inserted,  # int — final count after run
}
```

### Required extension for D-02

After the extension, the dict will contain 9 keys:

```python
summary[rel_type_name] = {
    "existing":                  existing,
    "inserted":                  inserted,
    "skipped":                   skipped_corporate + skipped_unresolved_source
                                 + skipped_unresolved_target + skipped_existing,
    "skipped_corporate":         skipped_corporate,
    "skipped_unresolved_source": skipped_unresolved_source,
    "skipped_unresolved_target": skipped_unresolved_target,
    "skipped_existing":          skipped_existing,
    "target":                    target_per_type,
    "total":                     existing + inserted,
}
```

**Backward compatibility invariant:** `skipped == skipped_corporate + skipped_unresolved_source + skipped_unresolved_target + skipped_existing` for every type and every run. This must hold exactly to avoid breaking callers that only read `skipped`. The `run_relationships()` method at line 192–193 sums `inserted` only — it is unaffected.

**`PipelineStats.relationship_counts_by_type`** stores the summary dict verbatim (line 412). New keys flow through automatically.

---

## 5. `_emit` Pattern to Copy

`[VERIFIED: edgar_warehouse/infrastructure/sec_client.py lines 144–153]`

### Original implementation in sec_client.py

```python
def _emit_sec_pull_event(event: str, **payload: object) -> None:
    parsed = urlparse(str(payload.get("url", "")))
    document = {
        "event": event,
        "emitted_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "host": parsed.netloc,
        "path": parsed.path,
        **payload,
    }
    print(json.dumps(document, sort_keys=True), file=sys.stderr, flush=True)
```

### Pattern to copy inline into pipeline.py (D-03)

Do NOT import `_emit_sec_pull_event`. Copy the pattern directly. Required imports to add to `pipeline.py`:

```python
import json
import sys
from datetime import datetime, timezone
```

Inline emission call per skip event:

```python
print(
    json.dumps(
        {
            "event": "mdm_relationship_skip",
            "emitted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "rel_type": rel_type_name,          # e.g. "IS_INSIDER"
            "reason": "corporate",              # or "unresolved_source" / "unresolved_target"
            "source_key": str(owner_cik),       # silver-layer CIK — never entity_id
            "target_key": str(row.get("issuer_cik")),
        },
        sort_keys=True,
    ),
    file=sys.stderr,
    flush=True,
)
```

### D-03 scope constraint: entity-only derivers

`_derive_is_entity_of`, `_derive_is_person_of`, `_derive_manages_fund`, `_derive_issued_by` iterate pre-filtered MDM rows. They never have silver-layer business keys (CIKs, accession numbers) available — only surrogate entity_ids. D-03 explicitly says "Do NOT log surrogate MDM entity IDs". Therefore, suppress D-03 emission for these four types. They only ever skip on `skipped_existing`, which is low-signal. D-03 emission applies only to `_derive_is_insider` and `_derive_holds`.

---

## 6. Existing Idempotency Test Gap

`[VERIFIED: tests/mdm/test_pipeline_relationships.py lines 427–436]`

### What `test_relationship_derivation_is_idempotent` currently covers

```python
def test_relationship_derivation_is_idempotent(self, session, fixture_world):
    pipe = MDMPipeline(session=session, silver=self._stub())
    first = pipe.run_relationships()   # 4 rows: 2 IS_INSIDER + 1 IS_ENTITY_OF + 1 IS_PERSON_OF
    second = pipe.run_relationships()
    assert first == 4
    assert second == 0
    rows = list(session.scalars(select(MdmRelationshipInstance)))
    assert len(rows) == 4
```

**Types covered:** IS_INSIDER (2 rows), IS_ENTITY_OF (1 row), IS_PERSON_OF (1 row) — only 3 of 6 types.

**Types NOT covered:** HOLDS, MANAGES_FUND, ISSUED_BY — all produce 0 rows with current `self._stub()` because the stub returns no non-derivative txn rows, no MdmFund rows, no MdmSecurity rows.

### What D-04 needs

D-04 requires one test that runs all 6 types and asserts `inserted == 0` on the second run. Options:

1. **Extend `fixture_world` + `self._stub()`** to add fund/security/txn data, then replace `test_relationship_derivation_is_idempotent` with a new comprehensive version using `derive_relationships()` directly (not `run_relationships()`) to get per-type `inserted` values for assertion.

2. **Add a new test method** `test_all_six_types_idempotent` alongside the existing one with a richer fixture. Per D-01, no new test files — must stay in `test_pipeline_relationships.py`.

**Recommended approach (option 2, additive):** Keep the existing test (it covers 3 types; regression value retained). Add `test_all_six_types_idempotent` that uses `derive_relationships()` (not `run_relationships()`) to get the per-type dict and asserts `second[rel_type]["inserted"] == 0` for all 6 types. This also satisfies D-02 assertion requirements.

---

## 7. MANAGES_FUND + ISSUED_BY Test Coverage Gap

`[VERIFIED: tests/mdm/test_pipeline_relationships.py — grep for "MANAGES_FUND", "ISSUED_BY"]`

### Current state

`grep "MANAGES_FUND\|ISSUED_BY"` in `test_pipeline_relationships.py` returns only:

- Line 84: `("MANAGES_FUND", "adviser", "fund", "extend_temporal"),` — in the `rel_types` seeding loop in `_seed_registry`
- Line 83: `("ISSUED_BY", "security", "company", "extend_temporal"),` — same loop

Zero test methods test MANAGES_FUND or ISSUED_BY derivation. No test asserts any MdmRelationshipInstance with `rel_type_name == "MANAGES_FUND"` or `rel_type_name == "ISSUED_BY"`.

### What fixture additions enable them

**For MANAGES_FUND:**
- Add one MdmEntity row (entity_type="fund")
- Add one MdmFund row with `entity_id=<fund_entity_id>` and `adviser_entity_id=<any_adviser_entity_id>`
- No silver stub changes needed — `_derive_manages_fund` reads MDM tables only
- One `derive_relationships(relationship_types=["MANAGES_FUND"])` call → assert `inserted == 1`

**For ISSUED_BY:**
- Add one MdmEntity row (entity_type="security")
- Add one MdmSecurity row with `entity_id=<security_entity_id>` and `issuer_entity_id=<any_company_entity_id>`
- No silver stub changes needed — `_derive_issued_by` reads MDM tables only
- One `derive_relationships(relationship_types=["ISSUED_BY"])` call → assert `inserted == 1`

**For HOLDS (separate gap):** `test_writes_holds_from_non_derivative_transactions` (line 380) already tests one HOLDS insertion in isolation, but it does NOT test idempotency and does NOT use `fixture_world`. The D-04 all-types idempotency test must include HOLDS with silver stub rows. The existing HOLDS test at line 380 provides the exact stub row format to reuse.

---

## 8. `_company_cik_set()` Corporate Filter

`[VERIFIED: edgar_warehouse/mdm/pipeline.py lines 447–452]`

### Implementation

```python
def _company_cik_set(self) -> set:
    from edgar_warehouse.mdm.database import MdmCompany
    from sqlalchemy import select
    return set(self.session.scalars(
        select(MdmCompany.cik).where(MdmCompany.cik.isnot(None))
    ))
```

**Source:** Queries the MDM `mdm_company` table (Postgres/SQLite), not DuckDB silver. Returns the set of all CIK integers that are registered as MDM companies.

**Used in:** `_derive_is_insider` (line 258), `_derive_holds` (line 300), and `run_persons` (line 164). NOT used in IS_ENTITY_OF, IS_PERSON_OF, MANAGES_FUND, or ISSUED_BY.

**Increment pattern for IS_INSIDER:**
- Line 263–265: `if owner_cik in company_ciks: skipped += 1; continue` → maps to `skipped_corporate`

**Increment pattern for HOLDS:**
- Line 303–305: `if owner_cik in company_ciks: skipped += 1; continue` → maps to `skipped_corporate`

**Test verification:** `test_company_cik_set` (line 179) confirms the method returns `{910001, 910002}` from the seeded fixture world. The test at line 313 `test_skips_corporate_beneficial_owner` verifies that `owner_cik=910001` (Issuer Corp) is excluded from IS_INSIDER rows.

---

## Risks / Gotchas

### 1. Double-counting risk in unresolved-source/target split

The current code at lines 268–270 (IS_INSIDER) and 310–312 (HOLDS) uses a single `or` check. If BOTH source and target are None, incrementing both `skipped_unresolved_source` and `skipped_unresolved_target` would break the backward-compat invariant `skipped == sum of four`. The split rule is: check source first, count `unresolved_source` and `continue`; only reach `unresolved_target` if source resolved. This is load-bearing for correctness.

### 2. D-03 does not apply to four of six derivers

The entity-only derivers (`IS_ENTITY_OF`, `IS_PERSON_OF`, `MANAGES_FUND`, `ISSUED_BY`) have no silver-layer keys available. Emitting D-03 events for "existing" skips on these types would require logging entity_ids (violating D-03's "no surrogate keys" rule) or doing extra lookups. The planner should explicitly scope D-03 to `_derive_is_insider` and `_derive_holds` only.

### 3. MdmFund and MdmSecurity require MdmEntity parent rows

Both `MdmFund.entity_id` and `MdmSecurity.entity_id` are FKs to `mdm_entity`. The `_add_entity(session, entity_type)` helper at line 99 must be called first to get the entity_id, then the domain row is created. The fixture world already shows this pattern for every existing entity type.

### 4. `_seed_registry` does NOT return entity IDs — `fixture_world` does

`_seed_registry` (lines 62–96) only seeds entity-type definitions and relationship-type rows and returns `{name: rel_type_id}`. The domain entities (companies, advisers, persons, securities, funds) are all added in `fixture_world`. The D-01 fixture additions belong in `fixture_world`, not in `_seed_registry`.

### 5. `test_writes_holds_from_non_derivative_transactions` adds a MdmSecurity + MdmSourceRef locally

This test (line 380) creates its own security inline — it does NOT modify `fixture_world`. For the D-04 all-types idempotency test, if HOLDS coverage is required, the test must either add a security row inline or the `fixture_world` fixture must include one. Adding to `fixture_world` is simpler but changes what existing tests see — verify no existing test asserts `len(rows)` counts that would break.

### 6. `_derive_manages_fund` and `_derive_issued_by` were UNTESTABLE before Phase 6

With zero MDM fund or security rows in any fixture, both derivers silently produce `(0, 0)` — no rows inserted, no rows skipped. This is correct behavior but means no test has ever exercised their `ensure_relationship` call path. Phase 6 is the first exercise of these code paths in the test suite.

### 7. The `HOLDS` rel_type merge_strategy is `extend_temporal`

In `_seed_registry` line 81 and confirmed at database line 565–566, HOLDS uses `extend_temporal`. The `ensure_relationship` dedup logic (in `edgar_warehouse/mdm/graph.py`, not in pipeline.py) is what marks `created=False` for existing rows. The idempotency of HOLDS relies on the `ensure_relationship` implementation finding the existing row — verify this passes in the HOLDS-specific test before relying on it in the D-04 comprehensive test.

---

## Sources

### Primary (HIGH confidence)
- `edgar_warehouse/mdm/pipeline.py` — complete file read; all counter locations and method implementations verified by line
- `edgar_warehouse/mdm/database.py` — complete file read; MdmFund, MdmSecurity, MdmRelationshipInstance field definitions verified
- `tests/mdm/test_pipeline_relationships.py` — complete file read; `_seed_registry`, `fixture_world`, all test classes and methods
- `edgar_warehouse/infrastructure/sec_client.py` lines 144–153 — `_emit_sec_pull_event` pattern
- `.planning/workstreams/neo4j-pipe/phases/06-relationship-derivation-coverage/06-CONTEXT.md` — D-01 through D-04 locked decisions
- `.planning/workstreams/neo4j-pipe/REQUIREMENTS.md` — REL-01 through REL-04
- `.planning/workstreams/neo4j-pipe/ROADMAP.md` — Phase 6 success criteria

### Secondary / Tertiary
None — all findings verified directly from source files.

---

## Metadata

**Confidence breakdown:**
- Skip site map: HIGH — line-by-line read of pipeline.py
- Fixture field requirements: HIGH — SQLAlchemy model definitions read directly
- Summary dict structure: HIGH — `derive_relationships` implementation read directly
- Emit pattern: HIGH — sec_client.py read directly
- Test coverage gaps: HIGH — full test file read, confirmed by absence of test methods

**Research date:** 2026-05-17
**Valid until:** Until pipeline.py, database.py, or test_pipeline_relationships.py are modified
