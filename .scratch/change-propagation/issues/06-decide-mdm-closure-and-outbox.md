# Decide MDM affected-key closure and publication outbox

Type: grilling
Status: resolved
Blocked by: 02, 04, 05

## Question

How does a completed silver publication select and resolve only the affected
company, adviser, person, security, fund, audit-firm, and relationship work
while preserving matching and survivorship correctness?

Decide domain-content hashes for every source type, bounded candidate-neighbor
expansion, order dependencies among entity types, relationship derivation,
retirement/merge/supersession/quarantine propagation, retry/resume boundaries,
and the periodic full-universe reconciliation backstop. Specify how successful
MDM commits transactionally enqueue the existing publication outbox so every
entity or relationship mutation—including close and provenance-only changes—
becomes exportable exactly once by idempotent drain.

## Answer

Grilled 2026-08-26. Real finding at the outset: the "existing publication
outbox" the ticket refers to (`edgar_warehouse/mdm/publication.py`) is
fully built and unit-tested — lease-based claiming, a 5-state lifecycle,
a staleness SLO — but **completely dormant in production**. `grep -rln
"request_publication(" edgar_warehouse/ tests/` returns only
`publication.py` itself and its own tests; `claim_next_publication_request`/
`advance_publication_lifecycle` are the same — real CLI probes exist
(`mdm publication-claim`/`-status`) but nothing automated calls them, and
`advance_publication_lifecycle` has zero callers anywhere. This reframed
the ticket's real job: mostly deciding *how to wire an already-designed
mechanism*, not designing a new one.

**Outbox enqueue point:** once per upstream `cause_reference` (Ticket 04's
Run identity), not per-row (too fine-grained, thousands of requests per
`mdm run`) and not once per whole `mdm run` invocation (too coarse, spans
unrelated keys). MDM processing resulting from one silver publication tied
to one `cause_reference` enqueues exactly one publication request for that
Run, carrying `cause_reference` in the already-available `source_summary`
JSON field. Concrete wiring (both writer and consumer sides) deferred to
new [Ticket 36](36-wire-mdm-publication-outbox.md).

**Domain-content hashes:** already generic — `MdmSourceRef.source_content_hash`
is keyed to `mdm_entity` (not company-specific), but the skip-if-unchanged
fast path *using* it was, per this repo's own documented history, built
for `run_companies` specifically; whether the other five entity types
already have it wasn't fully confirmed here. Decided: generalize to all
six entity types regardless of current wiring state — the schema already
supports it. Wiring deferred to new [Ticket 37](37-generalize-mdm-skip-if-unchanged.md).

**Bounded candidate-neighbor expansion** — this is where Ticket 04's
deferred "real Affected-Key Closure expansion for MDM" gets decided:
1-hop — when a source row changes, also re-check entities with a *direct*
existing relationship edge to the resolved entity (known officers,
adviser, auditor), not the whole graph and not zero expansion. Matches
"bounded" in the ticket's own wording and keeps cost proportional to the
actual change. Deeper multi-hop ripple effects a 1-hop pass would miss are
explicitly **not** this pass's job — that's the reconciliation backstop's,
below.

**Order dependencies among entity types:** already an accepted, working
property of the current system (company before person/security in Stage
2, resolution before relationship derivation, `run_companies`' own
docstring documents per-row CIK-scoped idempotency) — nothing new to
decide.

**Retry/resume boundaries:** already decided and built by a settled
predecessor (`pipeline-resumability`) — `run_companies` already supports
`resume_ledger_run_id`/frozen-snapshot resumption for a full-universe
attempt, and per-CIK resolution is already idempotent on retry. Not
reopened.

**Periodic full-universe reconciliation backstop:** confirmed, twice now
(once by `mdm-ahead-of-silver`'s own Ticket 04, once here), genuinely
needed and genuinely undesigned. Decided it's needed specifically to catch
what the 1-hop bounded pass structurally misses — deferred its actual
design to new [Ticket 38](38-design-mdm-full-universe-reconciliation-backstop.md),
including how it relates to the existing, adjacent-but-distinct
release-readiness `Relationship Generation Snapshot`/`Per-Type Exact
Relationship Parity` point-in-time gate mechanism.

**Retirement/merge/supersession/quarantine propagation — a real
mistake made and caught, not silently corrected.** Initial investigation
found `stewardship.py`'s `merge_entities` re-points `MdmSourceRef` rows
and tombstones the discarded entity, but never touches
`mdm_relationship_instance` — read as a genuine gap (dangling relationship
edges after a merge) and a fix was drafted and briefly applied: re-point
`source_entity_id`/`target_entity_id`, recompute the deterministic
`relationship_id`, handle merge-induced self-loops and collisions.

Before committing that fix, found primary-source evidence directly
contradicting the "gap" framing: a comment already shipped in
`snowflake_graph.py` states plainly that `merge_entities` "never rewrites
`mdm_relationship_instance.source_entity_id`/`target_entity_id`... This
[is] not a new gap" — it is a **deliberate design choice**, compensated
for downstream by an already-built, already-working read-side mechanism:
`GRAPH_ENTITY_MERGE_LINEAGE`, a Snowflake view that walks
`mdm_change_log`'s `merged_from` chain forward at graph-sync time to
resolve edges onto their canonical (post-merge) endpoint, while
deliberately *preserving* the original (pre-merge) endpoint as history —
`MDM_GRAPH_EDGES` even carries dedicated `SOURCENODEID_ORIGINAL`/
`TARGETNODEID_ORIGINAL` columns for exactly this, and a test,
`tests/mdm/test_temporal_graph_queries.py`'s RLINE-01 coverage, already
proves traversal converges onto the canonical entity. The drafted fix
would have destroyed that preserved original-endpoint history and mutated
an ID whose whole documented purpose is staying "stable across
re-derivation and generations." **Reverted before commit** — no code
change landed from this thread. Retirement/merge/supersession/quarantine
propagation is already correctly handled; this bullet needed no decision
and no follow-up ticket.

**Tests:** none — this ticket resolved to decisions and three follow-up
task/decision tickets (36/37/38), plus one drafted-then-reverted code
change with zero net diff. No test suite run needed; `git status`
confirms `edgar_warehouse/mdm/stewardship.py` is clean.
