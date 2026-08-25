# 23 — Migrate reference catalogs

**What to build:** Carry each supported SEC reference catalog through explicit
version, completeness, acquisition, revision, and Silver lifecycle semantics.

**Blocked by:** 17 — Make Bronze capture retry-safe and recoverable; 20 —
Version and activate the Acquisition Universe

**Status:** resolved (partially — see Answer for the one bullet that depends
on a later ticket)

- [~] Each catalog Strategy defines its source scope, producer version evidence,
  completeness proof, conditional acquisition policy, and required producers.
- [x] A complete catalog records its member count and ordered member-key digest;
  a valid zero-member catalog can complete without fabricated rows.
- [x] Partial, unavailable, or malformed catalogs cannot emit Scope Completion
  or retire prior authoritative members.
- [x] Replays and byte-identical observations produce no duplicate business
  mutations while retaining explicit acquisition evidence.
- [x] Each catalog command uses a bundled acquisition handler and introduces no
  catalog-specific branching into the shared Facade.

## Answer

Added a `reference_catalog` Source Family alongside `filing_artifact`/
`submissions`/`company_facts`, closely mirroring Ticket 22's architecture
(single-phase, since each catalog is one whole-file JSON snapshot with no
pagination inventory), but per-source-name rather than per-CIK — a fixed,
small candidate set (`company_tickers`, `company_tickers_exchange`) instead of
a bounded CIK universe:

- **Strategy** (`ReferenceCatalogPolicy`, `source_family_registry.py`): fetches
  via `edgartools_sec_gateway.download_bytes`; completeness is a new,
  deliberately stricter check (`valid_ticker_catalog_json`) than Ticket 22's
  `valid_json_object` — it structurally validates against SEC's two actual
  ticker-catalog shapes (`company_tickers.json`'s numbered-dict-of-entries
  shape, `company_tickers_exchange.json`'s `{"fields": [...], "data": [...]}`
  shape), rejecting a well-formed-but-wrong-shaped JSON payload that
  `_parse_company_ticker_rows` would otherwise silently parse to zero rows —
  indistinguishable from a genuine, valid empty catalog (bullet 2's
  complete-empty-scope case). Both shapes' legitimate empty forms (`{}`, an
  empty `data` list) are still complete.
- **Discovery** (`reference_catalog_discovery.py`, new): one Fetch Decision per
  source name, from a fixed candidate set built directly from
  `SUPPORTED_SOURCE_NAMES` rather than a resolved universe.
  `reference_catalog_candidate_id(source_name)` keyed only by source name —
  replay-safety verified directly (network-fetch-count stays flat across two
  full command invocations, applying Tickets 21/22's hard-won lesson from the
  start). Deliberately covers only the two auto-refetched ticker catalogs —
  the PCAOB firm registry is a third reference source in
  `edgartools_sec_gateway`'s catalog list, but it arrives today only via the
  operator-driven `import-relationship-source`/`pcaob_firm_registry`
  evidence-import ladder in `warehouse_orchestrator.py`; that path belongs to
  Ticket 25, not this one.
- **Silver acceptance** (`reference_catalog_silver_acceptance.py`, new): seals
  `sec_company_ticker` as the sole required producer, gated by
  `UnsupportedRequiredProducers` (ported upfront, per Ticket 32's pattern).
  Reuses `SilverDatabase.replace_company_tickers` and `_parse_company_ticker_rows`
  exactly as the legacy `_sync_reference_data` path does — no new write
  method, no new deletion mechanism. `_member_digest`'s keys are prefixed with
  each row's ordinal, so sorting for the digest reproduces the catalog's own
  file order, satisfying "ordered member-key digest" literally, not just
  "unordered membership."
- **Command** (`drive-reference-catalog-discovery`): bundles execute/
  resolve_scope/planned_writes in the same shape as every sibling family;
  `facade.py` and `warehouse_orchestrator.py` (including `_sync_reference_data`,
  the legacy path) both have empty diffs, confirming no source-family branch
  was added and no legacy code was touched.

**Retirement, and a real pre-existing gap this ticket surfaces but does not
fix:** unlike `sec_financial_fact` (Ticket 22), `sec_company_ticker` already
supports retirement today — `replace_company_tickers`'s per-`source_name`
delete-then-insert. This module reuses that unmodified, gated behind
CAPTURED-and-complete (bullet 3's negative gate), so a genuinely bad
observation cannot trigger it — proven directly by a test that replaces a
two-ticker scope with a one-ticker scope and confirms the dropped ticker is
gone from the *local candidate* database. But `silver_protection.py`'s
`merge_candidate_into_canonical` documents, in its own words, that it "never
deletes a row that exists only in canonical" — so that local retirement does
**not** propagate to canonical once the candidate is merged. This is not a
new gap: Ticket 02's table-change-semantics inventory already recorded
"Local replacement deletes for ticker catalogs ... are not exported"; this
ticket confirms the same gap also applies at the DuckDB candidate-to-canonical
merge layer, not only the Snowflake-landing-export layer. Documented in
`reference_catalog_silver_acceptance.py`'s own module docstring rather than
silently inherited as an assumption. Fixing `merge_candidate_into_canonical`'s
conservative "never shrinks a scope" policy is a real, separate design change
(it exists specifically to protect a windowed CIK-slice candidate from
looking like the whole table shrank) — out of this ticket's scope.

**One bullet is honestly partial, not silently claimed complete** (same
pattern as Tickets 21/22, this time confirmed by both parallel `/code-review`
passes independently):

- **Bullet 1** (conditional acquisition policy): `ReferenceCatalogPolicy.fetch`
  takes no ETag/If-Modified-Since, and there is no `NOT_MODIFIED` terminal
  disposition for this family — every replay still pays a full network GET
  before `ContentImpact.NO_IMPACT` dedup happens post-fetch. Identical, already
  -accepted gap shared with `submissions`/`company_facts`; closes via the
  already-open [Ticket 28](28-add-conditional-fetch-and-not-modified-linking.md)
  across every family, not here.

**Deliberately not reproduced:** `_sync_reference_data`'s
`seed_company_sync_state_bulk` side effect (bulk-seeding
`sec_company_sync_state` tracking rows for every discovered CIK). That is
Ticket 20's Acquisition Universe seeding concern, not a Silver domain producer
this family's `required_producers` model can express — there is no domain
table or read-back verification for it. Documented explicitly in
`reference_catalog_silver_acceptance.py`'s module docstring; whoever cuts a
universe-seeding command over to this new family must decide independently
how/where that seeding happens.

**Code review (Standards + Spec axes, fixed point `origin/main`):**

- **Standards** found and this session fixed two things: (1) a naming
  collision — `reference_catalog_discovery.py` had defined its own
  `REFERENCE_CATALOG_SOURCE_FAMILY` reusing the exact same name as
  `source_family_registry.py`'s module constant, breaking the sibling
  convention (`SUBMISSIONS_DISCOVERY_SOURCE_FAMILY`,
  `COMPANY_FACTS_DISCOVERY_SOURCE_FAMILY`) — renamed to
  `REFERENCE_CATALOG_DISCOVERY_SOURCE_FAMILY`; (2) a real, reproduced bug —
  `_parse_company_ticker_rows`'s numbered-dict branch only guards a missing
  `cik_str`, not an empty ticker string, but `replace_company_tickers`
  silently skips any row with a falsy ticker; the Silver-acceptance module's
  verification set was built from the unfiltered parse, so a real SEC catalog
  entry with a blank ticker would produce a false FAILED. Fixed by filtering
  `rows` the same way the writer does, upfront, before building
  `member_keys`/the verification set — regression test
  `test_finalize_settles_verified_when_a_numbered_dict_entry_has_a_blank_ticker`
  confirmed to fail with the exact false-FAILED symptom before the fix and
  pass after.
- **Spec** verified bullets 2–5 fully implemented and tested (including the
  complete-empty-scope and NO_IMPACT/replay legs); confirmed `facade.py` and
  `warehouse_orchestrator.py` both have zero-line diffs (no scope creep);
  confirmed bullet 1's gap is a precise repeat of the already-accepted
  Ticket 21/22 stance, not a new one.

Full suite green: 2579 passed, 4 skipped, before this session's two fixes;
`tests/acquisition/` + `tests/application/` (581 tests, +1 for the blank-ticker
regression) reconfirmed green afterward.
