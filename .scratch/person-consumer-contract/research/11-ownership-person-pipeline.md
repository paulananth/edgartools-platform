# Form 3/4/5 reporting-owner Person pipeline: code trace

Ticket: [11](../issues/11-trace-ownership-person-pipeline.md). Run 2026-09-19.
Code-only (no Snowflake, AWS or network reads). Line numbers are from the
`claude/person-consumer-contract` worktree at HEAD; Clean MDM lines are from
`origin/codex/clean-mdm-integration` via `git show`, never checked out.

## What was read

- Fetch/parse: `edgar_warehouse/application/warehouse_orchestrator.py`
  (lines 190-215, 1200-1290, 3655-3730, 3836-3846, 5352-5420, 5471-5493),
  `edgar_warehouse/cli.py` 672-703, `edgar_warehouse/bronze_filing_artifacts.py`
  156-200 and 624-660, `edgar_warehouse/config/warehouse_paths.properties`,
  `edgar_warehouse/acquisition/{discovery,silver_acceptance,capture_parity}.py`,
  `edgar_warehouse/application/workflows/drive_filing_discovery.py`,
  `infra/scripts/deploy-aws-application.sh` (1986, 2787-2925, 3610-3655).
- Parser: `edgar_warehouse/parsers/ownership.py`, `parsers/__init__.py`.
- Silver: `edgar_warehouse/silver_schema.py`, `silver_landing_store.py` 269-281
  and 379-431, `serving/silver_landing_export.py`,
  `infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql` 554-617,
  `13_silver_landing_ingest.sql` 105-125, dbt silver models
  `sec_ownership_reporting_owner.sql`, `sec_ownership_non_derivative_txn.sql`,
  `sec_company_filing.sql` 20-45, macro `silver_not_retired.sql`,
  `edgar_warehouse/mdm_entity_backfill.py`.
- Legacy MDM: `mdm/resolvers/person.py`, `mdm/resolvers/base.py`, `mdm/match.py`,
  `mdm/rules.py` 98-185, `mdm/sql_fragments.py`, `mdm/pipeline.py` (78-82,
  141-180, 295-302, 568-720, 1376-1503, 1740-2139, 3177-3300),
  `mdm/graph.py` 231-353, `mdm/stewardship.py` 155-175, `mdm/database.py`
  296-318, `mdm/migrations/002_seed_data.sql`.
- Downstream: dbt gold `ownership_holdings.sql`, `ownership_activity.sql`,
  `mdm/snowflake_graph.py` 20-75 and 1340-1400 and 1559-1567, `mdm/export.py`
  23-29, `mdm/api/routers/{persons,graph}.py`, `mdm/api/schemas/entities.py`
  62-69, `serving/subject_bundle_read.py` 148-179, `docs/adr/0008`, `docs/adr/0014`,
  `.scratch/agent-open-query-interface/map.md`, `research/05-mdm-postgres-ddl-inventory.md`.
- Clean MDM: `docs/specs/clean-mdm/pipeline-inventory.md` rows 20-25,
  `domain-model.md` 8-30, 58-70, 84-92 (Codex branch).
- Tickets 01, 02, 03, 05, 06 of this map.

## Findings

### 1. Source form and fetch

**F1 — Forms 3, 3/A, 4, 4/A, 5, 5/A, primary document only, 2-year window.**
`OWNERSHIP_FORMS = {"3", "3/A", "4", "4/A", "5", "5/A"}`
(`warehouse_orchestrator.py:196`; mirrored by value at `parsers/__init__.py:10`
and `acquisition/discovery.py:49`). The parser reads the filing's `is_primary`
attachment (`warehouse_orchestrator.py:5471-5479`). Ownership accessions are
selected only within `DEFAULT_OWNERSHIP_LOOKBACK_YEARS = 2`
(`warehouse_orchestrator.py:204`, gate at `:3710-3713`), with the stated
rationale "Historical deep Form 4 histories ... are not useful for
IS_INSIDER / current insider identity; only the recent band matters. 0 = full
history (operator repair / explicit override only)" (`:200-203`). Amendments
(`/A`) are separate accessions with no code linkage to the original filing.

**F2 — Two producers exist; only the legacy one writes reporting-owner rows.**
(a) `load_history` Stage 1 runs `bootstrap-next --silver-only ... --artifact-policy
<input>` per window (`deploy-aws-application.sh:3654-3655`), which goes through
`fetch_filing_artifacts` (`bronze_filing_artifacts.py:156`) then
`_run_parse_pipeline` → `parse_ownership` → `merge_ownership_reporting_owners`
(`warehouse_orchestrator.py:5352-5404`). (b) `daily_incremental`'s ASL passes no
flag (`deploy-aws-application.sh:1986`), and the CLI default is
`enable_filing_artifact_gated_capture=True` (`cli.py:703`), so
`skip_ownership_forms=gated_capture_enabled` (`warehouse_orchestrator.py:1247`)
removes every `OWNERSHIP_FORMS` accession from the legacy fetch+parse loop
(`:3707-3709`) and `_run_filing_artifact_gated_capture` runs instead
(`:1281-1288`). That gated path's **only declared silver producer is
`sec_raw_object`** (`acquisition/silver_acceptance.py:43-44`), and the Ticket 53
parity diff compared `sec_raw_object` rows only (`capture_parity.py:309-312`).
No code path was found that parses a gated-captured Form 3/4/5 raw object into
`sec_ownership_reporting_owner`; the help text confirms the design intent
("Ownership forms are skipped in the legacy artifact pipeline while this is
on", `cli.py:682-686`). Whether the deployed image carried this default is a
data question (see "Could not be determined").

**F3 — Idempotency is layered, and the reporting-owner key is `(accession_number, owner_index)`.**
Bronze: `filings/sec/cik={cik}/accession={accession_number}/{section}/{document_name}`
(`warehouse_paths.properties:21`) written by `write_immutable_bytes`, "idempotent
for byte-identical content (create-once, verify-and-reuse on conflict)"
(`bronze_filing_artifacts.py:638-642`); `raw_object_id = sha256(payload)`
(`:643-647`). Parse: no `already_parsed` gate remains — "Repeat rows collapse in
the dbt silver model" (`warehouse_orchestrator.py:3862-3865`), i.e. every rerun
appends and the dbt QUALIFY keeps the highest `parse_sequence` (F6). MDM:
`mdm_source_ref.source_id = f"{accession_number}:{owner_index}"`
(`resolvers/person.py:64`), documented as the "Single source of truth for this
resolver's mdm_source_ref key" (`:60-63`).

### 2. Parser

**F4 — `parse_ownership` emits one owner row per `reporting_owners.owners` entry.**
Fields: `accession_number`, `owner_index` (1-based), `owner_cik`
(`_parse_cik` → int or None, `ownership.py:93-97`), `owner_name` (`str(...) or ""`),
`is_director`, `is_officer`, `is_ten_percent_owner` (from edgartools
`is_ten_pct_owner`), `is_other`, `officer_title`, `issuer_cik`, `parser_version`
(`ownership.py:24-39`; `PARSER_VERSION = "2"`, `:13`). The person identifier is
edgartools' `owner.cik`; the name is passed through unnormalized. Backing call:
`Ownership.from_xml(content)` (`:17`).

**F5 — Three parser defects visible in code.** (i) Every transaction row hardcodes
`"owner_index": 1` (`ownership.py:47`, `:66`), so on a multi-owner filing all
transactions join to reporting owner 1 via `t.owner_index = o.owner_index`
(HOLDS: `pipeline.py:1979-1980`, `:1999-2000`; gold: `ownership_holdings.sql:38-39`).
(ii) `issuer_cik` is emitted on owner rows (`:36`) but the landing table has no
such column (`silver_schema.py:422-435`); `_record_landing_passthrough` forwards
extra keys untouched (`silver_landing_store.py:420-428`). (iii) `ownership_nature`
exists in both txn tables (`silver_schema.py:394`, `:416`) but is never emitted.
Documented quirk, handled: `_to_date_str` strips footnote markers ("2021-02-04
[F2]") because "Snowflake's COPY INTO cast is strict and rejects them outright
-- aborting the whole silver-landing load for every table" (`ownership.py:114-128`).

### 3. Silver

**F6 — Landing DDL, dedupe key, collapse, and a widening side effect.**
`sec_ownership_reporting_owner` columns: `accession_number NOT NULL`,
`owner_index SMALLINT NOT NULL`, `owner_cik BIGINT`, `owner_name`, four BOOLEAN
flags, `officer_title`, `parser_version`, `last_sync_run_id`, `mdm_entity_id`,
`parse_sequence` (`11_silver_landing_schema.sql:601-617`; snapshot equality
enforced by `tests/unit/test_silver_schema_snapshot.py`, `silver_schema.py:3-7`).
REQUIRED = `(accession_number, owner_index)` (`silver_schema.py:666-669`); txn
tables add `txn_index`. The dbt collapse keeps one row per
`(accession_number, owner_index)` by `parse_sequence desc`
(`sec_ownership_reporting_owner.sql:31-34`), then LEFT JOINs `sec_company_filing`
on `accession_number` alone to add `cik` (`:39-42`). `sec_company_filing`'s grain
is `(accession_number, cik)` "uniformly" and it "widens unconditionally for every
multi-CIK accession" (`sec_company_filing.sql:31-37`), so the dbt owner model
yields two rows per owner on such accessions (one with `cik` = the owner's own
CIK). MDM compensates with `prefer_non_owner_cik_qualify` ("prefers whichever
candidate's cik is NOT this row's own owner_cik", `sql_fragments.py:12-42`); gold
does not (F14). No silver retirement writer targets ownership tables — the only
`SILVER_LANDING_RETIREMENT` writer is `acquisition/reference_catalog_silver_acceptance.py`.

**F7 — `mdm_entity_id` back-propagation is a best-effort sweep, and means different things per table.**
`backfill-mdm-entity-ids` (`BackpropagateIdsToSilver`, between Mastering and
Infer Relationships, `deploy-aws-application.sh:2909-2916`; failure is caught and
ignored, `:2918-2922`) re-emits full rows with `mdm_entity_id` filled by looking up
`MdmSourceRef` (`mdm_entity_backfill.py:264-302`). For `sec_ownership_reporting_owner`
the id is `entity_type="person"` keyed `accession:owner_index`
(`:115-120`); for both txn tables it is `entity_type="security"`
(`:122-134`) — **not the person**. Rows with no source ref "are left NULL for a
later sweep" (`:11`). The module warns the lookup "silently stops matching" if a
resolver's `source_id` shape changes (`:29-35`).

### 4. Legacy MDM

**F8 — Entry and row selection: `MDMPipeline.run_persons`, source system `ownership_filing`.**
Rows come from `sec_ownership_reporting_owner o LEFT JOIN sec_company_filing f`
with `owner_name IS NOT NULL` (`pipeline.py:1435-1442`; LEFT JOIN because "An
ownership filing's issuer is not necessarily a tracked company", `:1418-1428`).
Rows whose `owner_cik` is a known company CIK are dropped before resolution
(`eligible_rows`, `:1457-1459`, via `_company_cik_set`, `:3177-3182`) — that is
the only entity-vs-person classification. CIK-bearing rows run grouped by
`owner_cik` on a pool (`MDM_PERSON_RESOLVE_CONCURRENCY`, `:80-82`); CIK-less rows
run single-threaded afterwards because they "fall back to an UNSCOPED fuzzy name
match across the entire mdm_person table" (`:1407-1414`). `ownership_filing` has
source priority 3 (`002_seed_data.sql:37`). Daily volume note: `MDM_RUN_LIMIT=100`
once capped this at 100 persons/day — "21,650 ownership_filing rows resolved on
2026-08-19, then only ~511 more across the next 18 days, then 40,900 in one
unbounded catch-up run" (`deploy-aws-application.sh:2891-2901`).

**F9 — Matcher chain, thresholds, and what actually binds.** Chain:
`CIKExactMatcher` → `FuzzyNameMatcher(context_fields=("issuer_cik",))` → Splink
only if a model is injected (`resolvers/person.py:39-56`). Thresholds
(`002_seed_data.sql:62-64`): `cik_exact 1.00/1.00`, `fuzzy_name 0.92/0.80`,
`ml_splink 0.95/0.75`. Splink never runs: the only construction is
`PersonResolver()` with no model (`pipeline.py:1416`). Three code facts:
(i) CIK exact is definitive — `int(existing) == int(target)` → score 1.0,
`AUTO_MERGE` (`match.py:70-83`), and candidates are pre-filtered to that CIK
(`resolvers/person.py:154-155`). (ii) The fuzzy context check **can never pass**:
candidates carry only `entity_id`, `owner_cik`, `canonical_name`
(`resolvers/person.py:158-164`), and the check requires `c.get("issuer_cik") is not None`
(`match.py:125-130`), so any score ≥ 0.92 is clipped to `auto_min - 0.01`
(`:131-132`) → at most `REVIEW`. (iii) In ordinary mastering **`REVIEW` binds**:
`resolve_or_create` creates a new entity only for `None`/`QUARANTINE`; every other
verdict returns `verdict.candidate_entity_id` (`resolvers/base.py:268-288`), and
no caller inspects `MatchAction.REVIEW` (only `SKIPPED_UNCHANGED` at
`pipeline.py:1009`). `MdmMatchReview` rows are queued only under
`reconciliation_mode=True` (`base.py:263-266`, `:364-373`). Net: a CIK-less
reporting owner attaches to any existing person whose normalized name scores
Jaro-Winkler ≥ 0.80 against the whole `mdm_person` table, with no human gate.
Normalization lowercases, strips punctuation/apostrophes, drops legal suffixes and
a trailing "Class X", then title-cases (`rules.py:152-180`) — built for company
names; SEC person names arrive "LAST FIRST M".

**F10 — Fields written.** `mdm_person`: `owner_cik`, `canonical_name`,
`name_variants` (JSON, accumulates raw names), `primary_role`, `role_titles`
(JSON), `affiliated_company_count` (no writer found), `valid_from`/`valid_to`
(`database.py:296-318`; upsert at `resolvers/person.py:174-203`). Staged
attributes: `canonical_name`, `owner_cik`, `primary_role` (`:116`);
survivorship `canonical_name = source_priority`, `primary_role = most_recent`
(`002_seed_data.sql:54-55`). `issuer_cik` is hashed into the skip-if-unchanged
content hash but never staged (`resolvers/person.py:86-96`). Two disagreeing role
derivations from the same flags: `_derive_primary_role` → `"Director"`,
normalized title or `"Officer"`, `"10PctOwner"`, `"Other"`, else None
(`resolvers/person.py:134-143`) feeds the golden record; `_derive_role` →
`"director"`, `"officer"`, `"10pct_owner"`, `"other"` (`pipeline.py:295-302`) feeds
the `IS_INSIDER` edge property.

**F11 — `IS_INSIDER` derivation (`_derive_is_insider`, `pipeline.py:1740-1938`).**
Source: `sec_ownership_reporting_owner JOIN sec_company_filing` (INNER, `:1772-1779`)
+ `prefer_non_owner_cik_qualify` to avoid "a self-referential 'insider of
themselves' IS_INSIDER edge" (`:1761-1771`); watermarked on `accession_number`
(`:1787-1792`). Person lookup: bulk `owner_cik → entity_id` (`:1819-1820`,
`_person_entity_ids` `:3262-3277`), else `_person_entity_id` whose name branch is
`MdmPerson.canonical_name == owner_name` on the **raw** name (`:3247-3260`).
Skips: corporate owner (`:1867`), unresolved person (`:1877`), unresolved issuer
(`:1890`). Edge: person → company, `properties={"role": _derive_role(row),
"title": officer_title or ""}`, `effective_from = f.report_date`,
`source_system="ownership_filing"`, `source_accession` (`:1900-1913`). Type seed:
temporal, `dedup_key_fields ["source_entity_id","target_entity_id","title"]`,
`extend_temporal` (`002_seed_data.sql:240-244`).

**F12 — `HOLDS` derivation (`_derive_holds`, `pipeline.py:1940-2139`).** Source:
non-derivative UNION ALL derivative txns joined to the owner on
`(accession_number, owner_index)` and to `sec_company_filing`, `security_title IS NOT NULL`
(`:1965-2006`). Edge: person → security (target via `_security_entity_id`,
`:2079`), properties `shares_owned`, `direct_indirect`, `as_of_date`,
`is_derivative`, and the five derivative fields (`:2096-2106`),
`effective_from = transaction_date` (`:2112`). Seed: temporal, dedup on
`(source, target)`, `extend_temporal` (`002_seed_data.sql:245-249`). Both edges
are in `POPULATED_RELATIONSHIP_TYPES` (`snowflake_graph.py:52`).

**F13 — Change and retirement handling.** Persons: no retirement path — `valid_to`
is set only when `_merge_entities` tombstones the discarded entity and re-points
its source refs (`stewardship.py:160-168`); source refs are `session.merge`d, so a
row re-resolving to a different entity re-points silently (`base.py:112-129`).
Edges: `IS_INSIDER` closes the open version when `properties` differ
(`_deactivate_if_properties_changed`, `pipeline.py:658-720`, pattern
`property_differs_from_prior`, ADR 0008 line 10); `HOLDS` closes on
`shares_owned_after == 0` (`_deactivate_if_zero_shares`, `:582-656`, pattern
`value_signals_disposal`, ADR 0008 line 9); nothing closes by absence. Both
require the new date to be strictly after the open version's `valid_from_date`;
the guard was "missing here until 2026-09-16. Live crash:
daily-incremental-ticket17-verify-1789514832 hit this for HOLDS and then
COMPANY_HOLDS, poisoning the session for ~5 hours" (`:630-641`). Overlapping
different-property evidence resolves by `mdm_relationship_source_priority`, else the
new version is inserted quarantined — "no silent last-writer-wins"
(`graph.py:251-264`). Cross-run idempotency of these two edges was found broken
under repeated runs (CLAUDE.md, Ticket 28: "Every sequential rerun added the same
65 active IS_INSIDER and 1,349 active HOLDS relationships").

### 5. Downstream

**F14 — Consumers.** *Gold*: `ownership_holdings` and `ownership_activity` are the
only readers; there is no person dimension. Owner identity is a hash of
`'cik:' || owner_cik` else `'name:' || owner_name_norm` (`ownership_holdings.sql:63-67`),
never `mdm_entity_id`. Both join `sec_company_filing` with no owner-CIK guard
(`ownership_holdings.sql:37`; `ownership_activity.sql:44`), and `security_nk`
embeds `cf.cik` (`:69`), so a multi-CIK accession yields two facts per position,
one keyed to the owner's own CIK as `company_key`; `ownership_activity`'s
`fact_key` omits `cik` (`:88-89`) so those two rows share a key. *Graph*: person
nodes carry `owner_cik`, `canonical_name`, `primary_role`
(`snowflake_graph.py:1355-1372`); views `GRAPH_EDGE_IS_INSIDER` /
`GRAPH_EDGE_HOLDS` filter `MDM_GRAPH_EDGES` by type and active generation
(`:1559-1567`); `MDM_PERSON` mirrors to Snowflake (`export.py:26`). *API*
(undeployed, `agent-open-query-interface/map.md:45-53`): `/persons/search`
(ILIKE on `canonical_name`, optional `IS_INSIDER` filter by company CIK,
`routers/persons.py:25-37`), `/persons/{id}/affiliations` (IS_INSIDER, `:59-67`),
`/persons/{id}/holdings` (HOLDS, `:95-103`), `/graph/connections/shared-insiders`
(`routers/graph.py:314-326`); `PersonOut` exposes `owner_cik`, `canonical_name`,
`name_variants`, `primary_role`, `role_titles` (`schemas/entities.py:62-69`).
*Decision Contract*: "Agent-grade insiders require graph IS_INSIDER + gold source
accession" (`serving/subject_bundle_read.py:148`). *Agent Query Surface*: ADR 0014
exposes raw SQL over gold, graph and MDM with no result-level gate and "no
freshness or point-in-time identity of any kind" (`0014:42-43`); it defines no
person-specific field, redaction or privacy rule.

### 6. Clean MDM's stated target

**F15 — Inventory row 23 and domain-model rows, verbatim.**
`pipeline-inventory.md:23`: "| Ownership Person — `mdm/pipeline.py:1376`,
`mdm/resolvers/person.py:66` | Reporting owners and filing issuer context |
Person matching by CIK then fuzzy fallback; name/primary-role fields;
`IS_INSIDER` at line 1740 | Person assertions with source-specific capacities;
contextual role facts do not create Adviser registration |". Row 24 routes the
transaction tables to Security: "Separate Security identity; typed issuer
contract; distinguish positions, transactions, dates, units and reporting
capacities". `domain-model.md:12`: "| Person | A natural person | Adviser where
individually registered. Never merge with a Company, employer, sole-proprietor
business, or similarly named person through a role. |"; `:68`: "| `EMPLOYED_BY` /
insider association | Person to Company | Source-reported office/role and valid
dates; holdings do not imply employment |"; `:69`: "| Holdings | Accepted Person,
Company, or Fund Structure to Security | Source form, owner/manager capacity,
reporting period, units and quantities; 13F manager is not automatically
beneficial owner |"; `:86-89`: "Legacy IDs become an explicitly verified,
versioned crosswalk to new identities and profiles; ambiguous mappings remain
unresolved." Neither file names `HOLDS` or `IS_INSIDER` as retained edge names.

## What this settles for tickets 02/03/05/06

- **02 (what binds):** `owner_cik` is the only identifier in the source
  (F4); legacy treats it as definitive with no uniqueness constraint in
  `mdm_person` (`owner_cik` nullable, not unique, `database.py:304`). Legacy
  name binding for CIK-less rows is JW ≥ 0.80 against all persons with no
  issuer context and no human gate (F9) — the "issuer context" the map cites
  is configured but inoperative. The only per-row context available to a
  future key is `issuer_cik` from `sec_company_filing` (F6), which is absent
  for untracked issuers (F8).
- **03 (classification):** the sole legacy rule is "owner_cik ∈ known company
  CIKs → not a person" (F8, F11, F12); flags are used for role only
  (F10). Rows whose CIK is an entity not in `mdm_company` become persons.
  `INDIVIDUAL_ONLY_OWNERSHIP_FORMS` (`sql_fragments.py:57-63`) classifies the
  other direction (company-side exclusion of individuals) from filing history.
- **05 (relationships):** `IS_INSIDER` = person → issuer with
  `{role, title}` and `effective_from = report_date`; `HOLDS` = person →
  security with position fields and `effective_from = transaction_date`
  (F11, F12). Closing: property change (IS_INSIDER), zero shares (HOLDS),
  never by absence (F13). Amendments are new accessions with no supersession
  link (F1). All transactions attach to owner 1 (F5), so `HOLDS` on
  multi-owner filings is wrong at the source.
- **06 (crosswalk):** `sec_ownership_reporting_owner.mdm_entity_id` is the
  legacy person id keyed by `accession:owner_index`; the txn tables'
  `mdm_entity_id` is a security id (F7). The sweep is non-fatal and partial
  by design (F7), and a source ref can be silently re-pointed by merge or
  re-resolution (F13), so the column is not a stable person key. Legacy
  persons split into CIK-bound (deterministic, F9-i) and name-bound
  (REVIEW-band, F9-iii) with `mdm_source_ref.confidence` = verdict score
  (`resolvers/person.py:118-122`) and `mdm_entity.resolution_method`
  (`base.py:269-274`) distinguishing them.

## Could not be determined from code

- Whether the running prod image carried `enable_filing_artifact_gated_capture=True`,
  i.e. whether `daily_incremental` stopped producing reporting-owner rows
  after the Ticket 27 cutover (F2). CLAUDE.md warns "Confirm both are in the
  running image" for sibling changes; nothing here confirms it.
- What Snowflake `COPY INTO ... MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE` does
  with the parser's extra `issuer_cik` source column (F5-ii); the verified-live
  note in `13_silver_landing_ingest.sql:110-125` covers the opposite case.
- Whether edgartools' `owner.cik` is ever absent on real filings (the whole
  CIK-less branch, F9) and how often `owner_cik` collides with a company CIK
  (F8) — data questions, Snowflake is gone.
- Whether `affiliated_company_count` (F10) or `MdmMatchReview` for persons
  (F9) ever received rows in prod.
- Real-world frequency of multi-owner Form 4s (F5-i) and multi-CIK
  accessions (F6, F14) — both are by-construction effects, unmeasured here.
