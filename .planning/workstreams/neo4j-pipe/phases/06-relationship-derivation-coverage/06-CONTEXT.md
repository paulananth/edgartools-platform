# Phase 6: Relationship Derivation Coverage - Context

**Gathered:** 2026-05-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Prove and harden relationship derivation coverage for all 6 MDM relationship types:
IS_INSIDER, HOLDS, ISSUED_BY, MANAGES_FUND, IS_ENTITY_OF, IS_PERSON_OF.

All 6 derivers already exist in `edgar_warehouse/mdm/pipeline.py`. Phase 6 closes three
specific gaps: missing test coverage for MANAGES_FUND and ISSUED_BY, no broken-down skip
diagnostics, and no per-pair structured events for unresolvable pairs.

**In scope:**
- Extend `_seed_registry` stub fixture in `tests/mdm/test_pipeline_relationships.py` with
  MdmFund rows (adviser_entity_id set) and MdmSecurity rows (issuer_entity_id set) to
  make MANAGES_FUND and ISSUED_BY derivers testable
- Add broken-down skip counts to the `derive_relationships` summary dict:
  `skipped_corporate`, `skipped_unresolved_source`, `skipped_unresolved_target`,
  `skipped_existing` per relationship type
- Emit structured JSON-line skip events to stderr per skipped pair, following the
  `_emit_sec_pull_event` pattern in `sec_client.py`
- Full-corpus idempotency test covering all 6 relationship types in one pass
- Phase 6 tests remain in the existing `tests/mdm/test_pipeline_relationships.py` file;
  no new test files

**Out of scope:**
- Neo4j sync (Phase 7)
- New silver table queries — all derivers already read from the correct silver tables
- Changing the deriver SQL logic unless required to pass the new tests
- Loader rewrites unrelated to relationship derivation

</domain>

<decisions>
## Implementation Decisions

### Test fixture approach
- **D-01:** Extend the existing `_seed_registry` stub fixture (in-memory SQLite, no DuckDB
  dependency) rather than creating a new end-to-end test class. Add one MdmFund row with
  `adviser_entity_id` pointing to the existing stub adviser entity, and one MdmSecurity row
  with `issuer_entity_id` pointing to the existing stub company entity. This is the fastest
  path and is consistent with the existing test style in `test_pipeline_relationships.py`.

### Coverage-ratio diagnostics
- **D-02:** Extend the per-type summary dict returned by `derive_relationships` with four
  additional keys:
  - `skipped_corporate` — pairs skipped because `owner_cik` is in `_company_cik_set()`
    (IS_INSIDER and HOLDS only; 0 for other types)
  - `skipped_unresolved_source` — pairs where the source entity (person, security, adviser)
    could not be resolved to an MDM entity ID
  - `skipped_unresolved_target` — pairs where the target entity (company, fund, person)
    could not be resolved to an MDM entity ID
  - `skipped_existing` — pairs that were already present as active relationship instances
  The existing `skipped` key becomes the sum of all four categories for backward
  compatibility. Tests must assert all four new keys.

### Structured skip events
- **D-03:** For each skipped pair, emit a JSON-line to stderr using the same
  `print(json.dumps(...), file=sys.stderr, flush=True)` pattern as `sec_client.py`.
  Event structure:
  ```json
  {
    "event": "mdm_relationship_skip",
    "rel_type": "<IS_INSIDER|HOLDS|...>",
    "reason": "<corporate|unresolved_source|unresolved_target|existing>",
    "source_key": "<owner_cik or accession or entity_id>",
    "target_key": "<issuer_cik or entity_id>"
  }
  ```
  Emit at most once per skipped pair (not per retry). Do NOT log secret values or MDM
  entity IDs that are surrogate keys with no audit trail — log the silver-layer business
  keys (CIKs, accession numbers) that operators can cross-reference.

### Idempotency coverage
- **D-04:** Add one test that runs `derive_relationships()` (no relationship_types filter,
  no target_per_type) twice against the same in-memory fixture and asserts that the second
  run has `inserted == 0` for all 6 types. This directly satisfies REL-04.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Relationship deriver implementation
- `edgar_warehouse/mdm/pipeline.py` lines 229–405 — `_derive_relationship_type` dispatch
  and all 6 `_derive_*` methods; the `inserted/skipped` counter pattern is the edit point
  for D-02 and D-03

### Existing test fixture and patterns
- `tests/mdm/test_pipeline_relationships.py` lines 62–175 — `_seed_registry()`, stub
  fixture world, and existing relationship test classes; D-01 extends this fixture
- `edgar_warehouse/infrastructure/sec_client.py` lines 127–136 — `_emit_sec_pull_event`
  pattern to copy for D-03 structured events

### Phase 5 deliverables (do not regress)
- `tests/mdm/test_source_to_mdm_load_path.py` — Phase 5 tests that must keep passing
- `edgar_warehouse/mdm/cli.py` `_handle_derive_relationships` — preflight wiring from
  Phase 5; do not touch unless extending for new diagnostics

### Requirements
- `.planning/workstreams/neo4j-pipe/REQUIREMENTS.md` REL-01 through REL-04
- `.planning/workstreams/neo4j-pipe/ROADMAP.md` Phase 6 success criteria

</canonical_refs>

<specifics>
## Specific Ideas

- The `_seed_registry` fund row needs `adviser_entity_id = adviser_entity["adviser"]` and
  `entity_id = fund_entity_id` (a new stub fund entity). The MdmFund already has an
  `adviser_entity_id` FK field per the 05-03 fix — verify by reading database.py MdmFund.
- For D-02, the `_derive_is_insider` and `_derive_holds` loops already have three skip
  sites: corporate check, `person_id is None`, `issuer_id/security_id is None`, and
  `created == False` (existing). Map each to the four new counter keys.
- For D-03, the `_emit_sec_pull_event` helper is in `sec_client.py` (infrastructure layer).
  Do NOT import it from pipeline.py. Copy the pattern inline:
  `print(json.dumps({...}), file=sys.stderr, flush=True)`.
- Broken-down skip key backward compatibility: keep the existing `skipped` key equal to
  `skipped_corporate + skipped_unresolved_source + skipped_unresolved_target +
  skipped_existing` so callers that only read `skipped` don't break.

</specifics>

<deferred>
## Deferred Ideas

- End-to-end test with real DuckDB silver fixture (heavier, deferred to Phase 7 smoke test)
- Coverage-ratio percentage (total silver pairs / resolved) — counters are sufficient; % can
  be computed by the operator from the summary dict
- Neo4j edge sync for relationship instances (Phase 7)
- Alerting when coverage ratio drops below a threshold (out of scope for this milestone)

</deferred>

---

*Phase: 06-relationship-derivation-coverage*
*Context gathered: 2026-05-17 via discuss-phase*
