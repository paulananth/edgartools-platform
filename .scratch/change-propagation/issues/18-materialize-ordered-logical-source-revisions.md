# 18 — Materialize ordered logical source revisions

**What to build:** Convert verified Bronze captures into immutable, ordered
Logical Source Revisions and reasoned Processing Decisions without treating
transport identity or operational timestamps as business change.

**Blocked by:** 04 — Prototype the Change Propagation Run contract; 15 — Capture
one filing-artifact family through the gated Facade

**Status:** resolved

- [x] A revision records the logical source identity, observation position,
  source-native revision, three versioned content hashes, interpretation
  versions, completeness declaration, and verified evidence lineage.
- [x] Observation positions are monotonic per logical key but may contain gaps
  for failed, skipped, and not-modified observations.
- [x] Processing is serialized per logical source key while unrelated keys may
  proceed concurrently.
- [x] Changed interpretation reuses verified Bronze without downloading again;
  authenticated new source revisions with unchanged domain content record an
  explicit publication-backed `NO_IMPACT` path.
- [x] Tests reject run identifiers, arrival times, object paths, mutable
  pointers, and ETags alone as revision identity.

## Answer

New module `edgar_warehouse/acquisition/revisions.py` (`SourceRevisionLedger`)
plus a new `source_revision` table (`SourceRevisionRecord` in `models.py`,
mirrored into `013_acquisition_ledger.sql` -- edited in place, not yet
applied anywhere, same precedent as Tickets 15/17) and a new
`edgartools_acquisition_processor` database role -- processing is its own
ledger lifecycle per Ticket 03's authority model, so it gets its own owner
role rather than reusing `edgartools_acquisition_worker`.

**Blocked-by note:** Ticket 18 listed Ticket 04 ("Prototype the Change
Propagation Run contract") as a blocker; Ticket 04 is still open. Re-checked
before implementing: Ticket 03's own "Source revision identity and ordering"
section already names all three things Ticket 18's bullets needed --
the three versioned content hashes (exact raw-byte hash, versioned
canonical-source hash, versioned domain-content hash), the per-family
completeness declaration (the source-family table), and revision identity's
exact composition including its explicit exclusions (`run_id`, S3 key,
arrival time, ETag alone, mutable `latest` pointers). Ticket 04's edge on
Ticket 18 was stale for this subset; Ticket 04 stays open for the
run-manifest/expected-producer-set/replay-linkage portions later stages
(06-11) still need.

**Bullet 1 (revision identity fields):** `SourceRevisionRecord` carries
`decision_id`/`parent_revision_id`/`revision_relationship` (two
mutually-exclusive provenance shapes -- a fresh capture or a derived
revision reusing a parent's Bronze evidence), `source_family` +
`logical_source_key` + `observation_position`, `source_native_revision`,
all three hashes (`raw_evidence_hash`, `canonical_source_hash`,
`domain_content_hash`), `contract_version`/`parser_version`/
`schema_version`/`configuration_version`, `completeness_type` +
`declared_replacement_scope`, `bronze_artifact_reference`, and
`content_impact`.

**Bullet 2 (gaps):** a revision's position is the decision's own reserved
per-key position (from the same `source_observation_cursor` counter
`create_fetch_decision` already uses), not a dense renumbering of
materialized revisions -- a `CAPTURED_DISCOVERY` decision that resolves
`OUT_OF_SCOPE` reserves a position but creates no work row and no revision,
leaving a real gap. (Tested via `OUT_OF_SCOPE`, not `FAILED` -- a `FAILED`
decision's work row stays in `source_fetch_work`'s active-key partial unique
index, so a second, separate `candidate_id` for the same key can't be
created until it's retried to a terminal state; `OUT_OF_SCOPE` never creates
a work row at all, so it's the disposition that actually demonstrates a gap
without fighting that constraint.)

**Bullet 3 (serialized per key, concurrent across keys):** enforced by a
unique constraint on `(source_family, logical_source_key,
observation_position)` plus an idempotent-insert-then-reread-on-conflict
pattern (mirroring `create_fetch_decision`'s own candidate_id idempotency) --
no explicit application-level lock. Proven against a real multi-connection
file-based SQLite engine with genuine concurrent threads (same recipe as
`tests/mdm/test_run_companies_concurrency.py`): 8 threads racing to
materialize the *same* decision converge to exactly one revision row; 6
threads materializing 6 *different* keys all succeed independently.

**Bullet 4 (reinterpretation + NO_IMPACT):** `materialize_reinterpretation`
takes no fetch capability at all (structurally cannot redownload) and
inherits `raw_evidence_hash`/`canonical_source_hash`/
`bronze_artifact_reference`/`source_native_revision`/`completeness_type`/
`declared_replacement_scope` unchanged from its parent -- only
`domain_content_hash` and the four interpretation-version fields are
supplied fresh, since interpretation is the only thing that changed. Both
`materialize_from_capture` and `materialize_reinterpretation` determine
`content_impact` by comparing the new `domain_content_hash` against the
immediately preceding revision for the same key (the first revision for a
key is always `CHANGED`, since there's no prior state).

**Bullet 5 (identity exclusions):** proven two ways -- structurally (neither
`SourceRevisionRecord`'s columns nor either `materialize_*` method's
parameters include `run_id`/`arrival_time`/`object_path`/`s3_key`/
`latest_pointer`/`etag`) and behaviorally (replaying `materialize_from_capture`
for the same `decision_id` after a real wall-clock delay returns the
identical `revision_id`).

**Review:** Standards + Spec `/code-review` planned as parallel sub-agents;
the Spec agent hit a session usage limit before returning and was not
retried (usage-limit checkpoint mid-session) -- the Spec axis was instead
self-checked against all 5 bullets plus a scope-creep check (confirmed
`discovery.py` is untouched; wiring this module into the live discovery flow
is Ticket 19's job, not this one). Standards agent completed and found one
real issue, fixed: a new public `require_processor_role` was added to
`ledger.py` specifically for `revisions.py` to reuse (its own docstring said
so), but `revisions.py` defined an identical private `_require_processor_role`
instead of importing it -- dead code plus duplicated logic, the same
sibling-divergence shape this repo's CLAUDE.md repeatedly flags. Fixed by
deleting the private duplicate and wiring both call sites to the shared
public one. (Standards also noted `observation_position`'s `Integer` vs. the
migration's `BIGINT` typing mismatch -- pre-existing on
`SourceFetchDecisionRecord`/`SourceObservationCursor` before this ticket,
faithfully replicated rather than introduced here; out of this ticket's
scope to fix broadly.)

Tests: 18 new in `tests/acquisition/test_revisions.py`, 1 new in
`tests/acquisition/test_migration.py`, 1 new in
`tests/integration/test_acquisition_ledger_postgres.py` (real
`postgres:16-alpine`, exercises the full role/grant/immutability/idempotency
shape end-to-end through the actual Python API). Full repo suite green:
2411 passed, only the 2 pre-existing unrelated
`test_bootstrap_dbt_snowflake_secret.py` failures.
