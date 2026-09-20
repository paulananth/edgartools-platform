# Form ADV individual-registrant Person pipeline: what the code does

Ticket: [14](../issues/14-trace-adv-individual-person-pipeline.md). Run 2026-09-19. Code-only.
Every claim is `path:line` in this worktree (branch `claude/person-consumer-contract`);
Snowflake is gone, so no row counts anywhere below. Clean MDM rows are read from
`origin/codex/clean-mdm-integration` with `git show` (identical to this branch's copy
per `git diff --stat`, empty).

## What was read

- Parsers: `edgar_warehouse/parsers/adv.py` (whole file), `edgar_warehouse/parsers/__init__.py`,
  `edgar_warehouse/application/adv_bulk_ingest.py` (whole file),
  `edgar_warehouse/application/adv_firm_roster_ingest.py` (CRD/7B lines),
  `edgar_warehouse/application/adv_bronze_discovery.py`.
- Fetch/commands: `edgar_warehouse/application/adv_bulk_fetch.py` (whole file),
  `edgar_warehouse/application/warehouse_orchestrator.py` lines 197, 1848-2044, 3744-3748,
  3836-3846, 3849-3948, 5389-5408, 5486-5488; `edgar_warehouse/application/commands/__init__.py`;
  `edgar_warehouse/cli.py` 198-208, 800-830; `infra/scripts/deploy-aws-application.sh` 3814-3894;
  `edgar_warehouse/application/workflows/drive_adv_bulk_dataset_discovery.py` docstring.
- Silver: `edgar_warehouse/silver_schema.py` 38-109, 523-541; `edgar_warehouse/silver_landing_store.py`
  284-307; `infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql` 121-138;
  `infra/snowflake/dbt/edgartools_gold/models/silver/sec_adv_filing.sql`;
  `edgar_warehouse/mdm_entity_backfill.py` 78-146.
- Legacy MDM: `edgar_warehouse/mdm/adv_bulk.py` (whole file), `edgar_warehouse/mdm/resolvers/adviser.py`,
  `edgar_warehouse/mdm/resolvers/person.py` 30-57, `edgar_warehouse/mdm/pipeline.py` 178-195,
  1080-1083, 1712-1728, 2314-2331, 2465-2482, 3367-3424, 4764-4780, `edgar_warehouse/mdm/database.py`
  266-313, `edgar_warehouse/mdm/migrations/002_seed_data.sql` 238-280, `edgar_warehouse/mdm/coverage.py` 258-284.
- Downstream: `infra/snowflake/dbt/edgartools_gold/models/gold/adviser_disclosures.sql`,
  `adviser_offices.sql`; `edgar_warehouse/mdm/snowflake_graph.py` 25-52, 1594-1597;
  `edgar_warehouse/mdm/graph.py`; `edgar_warehouse/mdm/api/routers/advisers.py`, `companies.py`;
  `edgar_warehouse/serving/manager_bundle_read.py` 1-60; `edgar_warehouse/serving/subject_bundle_read.py`.
- Tests: `tests/mdm/test_pipeline_relationships.py` 258-297, 503-513; `tests/application/test_adv_bulk_ingest.py`;
  `tests/application/test_parse_adv_bronze.py`; `tests/unit/test_adv_and_evidence_landing_passthrough.py`.
- Prior evidence: `.planning/workstreams/fix-pipelines/phases/06-relationship-investigation-and-population/06-PHASE-CLOSURE-LEDGER.md` 34-35;
  `docs/data-architecture.md:95`; `docs/aws-mdm-source-to-mdm.md` 71-79.
- Clean MDM target: `docs/specs/clean-mdm/pipeline-inventory.md` rows 21, 29; `docs/specs/clean-mdm/domain-model.md` 12, 62, 87.

## Findings

### F1 — Source form and fetch: three paths, and only the unscheduled ones can carry a CIK

**Path A, scheduled (IAPD bulk).** `fetch-adv-bulk` polls
`https://reports.adviserinfo.sec.gov/reports/foia/reports_metadata.json` and downloads monthly
`ADV_Filing_Data_YYYYMMDD_YYYYMMDD.zip` archives (`adv_bulk_fetch.py:26,151,173`) over a
13-month rolling window (`adv_bulk_fetch.py:72,183`), stages them in bronze under
`runs/fetch-adv-bulk/<run-id>/` and writes a `{"kind": "iapd_adv_bulk", ...}` manifest
(`adv_bulk_fetch.py:139-146`; `warehouse_orchestrator.py:1980-2001`).
`ingest-relationship-sources` reads that manifest, verifies SHA-256, and dispatches
`kind == "iapd_adv_bulk"` to `ingest_adv_bulk_archive` (`warehouse_orchestrator.py:1872-1884`).
Both run in `load_history` Stage 1C and `daily_incremental` as `FetchAdvBulk → IngestAdvBulkSources`
then `FetchFirmRoster → IngestFirmRosterSources` (`deploy-aws-application.sh:3866-3894`).
Idempotency: the fetch-level skip reads already-ingested periods from
`sec_adv_private_fund.source_dataset_period`, not `sec_adv_filing`, with this verbatim comment:
"sec_adv_filing has no source_dataset_period column (a pre-existing gap: ingest_adv_bulk_archive's
filing_rows never carries it, unlike fund_rows -- see the adv-pipeline map ticket 06 for the flagged
follow-up)" (`warehouse_orchestrator.py:1962-1972`). Row-level key is
`accession_number = f"iapd-adv:{filing_id}"` (`adv_bulk_ingest.py:151`).

**Path B, manual (`parse-adv-bronze --artifact`).** Operator-staged ADV XML/HTML/text goes through
`parse_adv` (`warehouse_orchestrator.py:3917-3922`), passing `candidate.cik` from the artifact
descriptor (`adv_bronze_discovery.py:129`). Documented as "Manual/backfill-only ... ADV is not captured
by normal SEC EDGAR bootstrap" (`docs/data-architecture.md:95`).

**Path C, EDGAR configured-parser path.** `ADV_FORMS = {"ADV", "ADV/A", "ADV-E", "ADV-E/A", "ADV-H",
"ADV-H/A", "ADV-NR", "ADV-W", "ADV-W/A"}` (`warehouse_orchestrator.py:197`) is a configured parser
form (`:3838`) with its own lookback (`--adv-lookback-years`, `cli.py:198-208`; `:3744-3748`), and
the generic per-accession parse calls `parser(accession_number, content, form_type, filing.get("cik"))`
(`:5400`) then `db.merge_adv_filings(...)` (`:5405`). This is the only *automated* path that can put a
non-NULL `cik` into `sec_adv_filing`. Which ADV-family forms actually appear in EDGAR indexes cannot be
determined from code.

**Path A writes `"cik": None` for every filing row** (`adv_bulk_ingest.py:237`). This one line
decides F4.

### F2 — Parser: no individual-vs-firm decision exists anywhere

**Bulk parser** (`parse_adv_bulk_archive`, `adv_bulk_ingest.py:103-219`) selects exactly four archive
members by regex: `IA_ADV_Base_A|ERA_ADV_Base`, `IA|ERA_Schedule_D_7B1`, `..._7B2`, `ADV_Filing_Types`
(`:126-129`). From base rows it reads only `FilingID`, `1E1` (CRD), `1A`/`1B1` (name), `1D`
(SEC file number), `DateSubmitted`, `7B` (`:146-157`). It emits `AdvBulkFiling` (`:17-27`) and
`AdvBulkFund` (`:31-46`). No Item 3 organization-form column, no owner or person column is read.
Test fixtures carry exactly `"FilingID","DateSubmitted","1A","1D","1E1","7B"`
(`tests/application/test_adv_bulk_ingest.py:39`). Firm roster reads `Organization CRD#` plus 7B
aggregates only (`adv_firm_roster_ingest.py:29,136-141`).

**XML/HTML parser** (`parse_adv`, `parsers/adv.py:31-71`, `PARSER_NAME = "adv_v1"`) emits exactly
four tables: `sec_adv_filing`, `sec_adv_office`, `sec_adv_disclosure_event`, `sec_adv_private_fund`
(`:66-71`). The registrant name is one field from the first of `primaryBusinessName`,
`registrantName`, `adviserName`, `companyName`, `name`, then a regex, then `<title>` (`:87-106`).
CRD is `crdNumber`/`iardNumber` or regex `(?:CRD|IARD)\s*(?:No\.?|Number)?[:#]?\s*([0-9]{3,})`
(`:20,45`). `_find_tags` matches by lowercase tag name across the whole document (`:297-303`);
`disclosure`/`fund` tags are bounded at 25/100 rows (`:193,247`). No defect TODOs in the file.

Neither parser has a person identifier or a natural-person flag. "How it decides individual vs
firm": it does not. `manager_bundle_read.py:3-5` tags the XML parser output as
`heuristic_adv_parse` and states "Heuristic ADV parses are never agent-grade."

### F3 — Silver: five ADV tables, none person-shaped; `mdm_entity_id` is an Adviser ID

`sec_adv_filing` columns: `accession_number, cik, form, adviser_name, sec_file_number, crd_number,
effective_date, filing_status, filing_action, source_format, parser_version, last_sync_run_id,
mdm_entity_id` (`silver_schema.py:48-62`; DDL `11_silver_landing_schema.sql:121-137`, `cik BIGINT`
nullable, `crd_number TEXT`). Only `accession_number` is REQUIRED (`silver_schema.py:527-529`).
The other four: `sec_adv_office` (`:78-88`), `sec_adv_disclosure_event` (`:38-47`),
`sec_adv_private_fund` (`:89-109`), `sec_adv_firm_roster` (`:63-77`). No name-of-a-person column
in any of them. Writers are landing passthroughs with no dedupe (`silver_landing_store.py:284-307`);
the dbt collapse keeps the last `parse_sequence` per `accession_number`
(`models/silver/sec_adv_filing.sql:23-26`). Back-propagation writes `sec_adv_filing.mdm_entity_id`
for `entity_type="adviser"`, `source_system="adv_filing"`, `source_id = accession_number`
(`mdm_entity_backfill.py:78-79,135-141`). There is no ADV→Person legacy ID in silver.

### F4 — Legacy MDM: CRD keys the Adviser; the Person hop is CIK-only and unreachable from the scheduled path

**Adviser resolution** is `resolve_advisers_bulk` (`adv_bulk.py:195`, invoked by
`pipeline.py:1080-1083`); no matcher chain, no thresholds, no `AdviserResolver` (deleted,
`resolvers/adviser.py:3-12`). Identity is `f"crd:{crd}"` else `f"accession:{...}"` (`:203-207`);
`entity_id = uuid5(NAMESPACE_URL, identity)` (`:287`); `resolution_method` is `iapd_crd_exact` or
`adv_accession_exact`, `confidence 1.0` (`:311-312`). Fields staged are `ADVISER_FIELDS`
(`resolvers/adviser.py:16-26`): `canonical_name, cik, crd_number, sec_file_number, adviser_type
(= filing_status), hq_city, hq_state, aum_total, fund_count` (`adv_bulk.py:291-300`).
`linked_company_entity_id = companies_by_cik.get(cik_int)` (`:304`). Existing advisers are updated
by `for field_name, value in golden.items(): if value is not None: setattr(adviser, field_name, value)`
(`:316-319`) — the "direct bulk non-null overwrites" Clean MDM's inventory cites at "line 308"; in this
worktree line 308 is inside the `new_entities.append` branch and the overwrite is 316-319.

**Person link.** `_derive_is_person_of` (`pipeline.py:2465-2482`) iterates `_adviser_person_pairs()`
= `select(MdmAdviser.entity_id, MdmPerson.entity_id).join(MdmPerson, MdmPerson.owner_cik ==
MdmAdviser.cik).where(MdmAdviser.cik.isnot(None)).where(MdmAdviser.linked_company_entity_id.is_(None))`
(`:4772-4780`) and calls `ensure_relationship(rel_type_name="IS_PERSON_OF", source_system="adv_filing")`
with no properties, no `effective_from` (`:2472-2477`). `IS_ENTITY_OF` is the sibling:
`linked_company_entity_id IS NOT NULL` (`:2314-2331`, `:4764-4770`). CRD is not in either join.
Seed registry: `IS_PERSON_OF` is `adviser → person`, `is_temporal FALSE` (the only non-temporal type
among the eight seeded in `002_seed_data.sql:238-279`; `EMPLOYED_BY` is seeded `TRUE` in
`005_fundamentals_relationships.sql:86`), `merge_strategy 'replace'`, description "Individual adviser
CIK is the same natural person" (`002_seed_data.sql:275-279`); closing pattern `no_versioning_needed`
(`pipeline.py:191`) — no retirement handling. Change handling on the adviser side: `adv_bulk.py` has no
`reconciliation_pass` parameter (grep: zero hits), which Clean MDM's own inventory records as "ADV bulk
lacks this flag" (`pipeline-inventory.md:31`).

**Why it is unreachable from Path A.** `MdmAdviser.cik` is `int(row["cik"])` or None
(`adv_bulk.py:278-279,292`), and Path A writes `cik: None` for every row (`adv_bulk_ingest.py:237`).
NULL never satisfies `MdmAdviser.cik.isnot(None)`, so `_adviser_person_pairs` yields no ADV-bulk
adviser; likewise `linked_company_entity_id` is always None on that path (`:304`), so `IS_ENTITY_OF`
is equally unreachable, and `unclaimed_by_cik.pop(cik_int, None)` (`:281-282`) is dead code there.
`MdmAdviser` has exactly two writers (`adv_bulk.py:345`; `pipeline.py:3401`): the second is
`_ensure_thirteenf_manager`, which creates `cik=<13F filer CIK>`, `adviser_type="13f_manager"`, no CRD
(`pipeline.py:3401-3406`). Setting Path C aside (below), those stubs are the only automated-path
advisers that can enter the `IS_PERSON_OF` join — and they match a `MdmPerson.owner_cik`, i.e. a
Form 3/4/5 reporting owner with the same CIK as a 13F filer, which is the entity-reporting-owner case,
not an individually registered adviser. A Path C row (`warehouse_orchestrator.py:5400,5405`) would
carry the EDGAR filer's CIK into the same `SELECT * FROM sec_adv_filing` (`adv_bulk.py:236`) and could
enter the join; its volume is not code-determinable, and the runbook states "ADV (Form ADV) filings
are **not** in EDGAR. They are filed through IARD/IAPD" (`docs/aws-mdm-source-to-mdm.md:73-74`,
a documented claim, not a code fact).

The fix-pipelines ledger recorded EDGE-06 as "EXCLUDED — source-coverage exclusion scoped to the
current tracking-list universe ... Re-check required if the adviser universe grows"
(`06-PHASE-CLOSURE-LEDGER.md:35`); `coverage.py:258-284` reproduces the join. The code says the
trigger names the wrong variable: growth arriving via Path A (the scheduled IAPD path) cannot change
that outcome because every such row has `cik = NULL`; only Path B/C rows could, at a volume not
determinable from code. The passing test supplies what Path A never writes: fixture adviser
`MdmAdviser(entity_id=individual_adviser_id, cik=910101, canonical_name="Individual Adviser (RIA)",
linked_company_entity_id=None)` with no CRD, paired with `MdmPerson(owner_cik=910101)`
(`tests/mdm/test_pipeline_relationships.py:276-278,295-296,503-513`).

### F5 — Downstream: no consumer reads an ADV person

- Gold: `adviser_disclosures.sql` and `adviser_offices.sql` key `coalesce(f.cik, c.cik) as cik` →
  `company_key` (`adviser_disclosures.sql:24,34`; `adviser_offices.sql:25,36`) — NULL for every Path A
  row; `private_funds.sql` names only `fund_name` (`:27,33`) and `adv_fund_count_reconciliation.sql`
  has no person/owner column (grep: none). No gold model projects a person from ADV.
- Graph: `GRAPH_EDGE_IS_PERSON_OF` view exists (`snowflake_graph.py:1594-1597`) but
  `POPULATED_RELATIONSHIP_TYPES = ("COMPANY_HOLDS", "HOLDS", "ISSUED_BY", "IS_INSIDER")` (`:52`) —
  verify-graph never checks it; the comment block (`:42-50`) records "confirmed NONE reached
  graph-populated status". `graph.py` has no `IS_PERSON_OF` handling (grep: none).
- API: `/advisers/{crd_number}` resolves by CRD (`advisers.py:15-24`); `/advisers/{crd}/companies`
  follows `linked_company_entity_id` only (`:36-44`); no person endpoint on advisers, and
  `routers/graph.py` has no adviser/`IS_PERSON_OF` reference (grep: none).
- Agent Query Surface: `manager_bundle_read.py` has `SECTION_MANAGES_FUND` and `SECTION_IS_ENTITY_OF`
  (`:32-33`); no person section. `subject_bundle_read.py`'s person handling (`:149-187`) is for insider
  edges, not ADV.

### F6 — Clean MDM's stated target

`pipeline-inventory.md:21` (row "ADV Adviser — `mdm/adv_bulk.py:195`"): inputs "Latest `sec_adv_filing`
per CRD or accession; `sec_adv_office`"; current "Separate Adviser ID linked to Company by CIK; direct
bulk non-null overwrites at line 308 bypass shared survivorship"; target "Classify holder as
Company/Person, then attach governed registration profile; no new role identity; expose profile
registration history". `:29` (row "Adviser associations — `mdm/pipeline.py:2314`, `:2465`"): current
"`IS_ENTITY_OF`, `IS_PERSON_OF` join separate domain IDs"; target "Same-identity profile membership;
genuine employment/association remains a separately evidenced relationship".
`domain-model.md:12`: Person = "A natural person"; "Adviser where individually registered. Never merge
with a Company, employer, sole-proprietor business, or similarly named person through a role."
`:62`: "Same-ID profile membership replaces `IS_ENTITY_OF` / `IS_PERSON_OF`; employment/association is
a real edge, not a merge." `:87`: "Legacy IDs become an explicitly verified, versioned crosswalk".
Line numbers in the inventory match this worktree for `adv_bulk.py:195`, `pipeline.py:2314`, `:2465`;
"line 308" drifted (F4).

### F7 — Schedule A/B, Schedule D (beyond 7.B), and Part 2B: not parsed anywhere

Positive enumeration, not grep absence: Path A reads four members and six base columns (F2); Path B
emits four tables with no owner/person tag names (`parsers/adv.py:66-71,87-106,124,175,227`); silver
has five ADV tables with no person column (F3). Repo-wide grep for `schedule a`, `schedule_a`,
`schedule b`, `part 2b`, `supervised person`, `direct owner`, `indirect owner`, `control person`
across `*.py`/`*.sql`/`*.md`/`*.yml` (excluding `.scratch`, `.planning`, `docs/specs/clean-mdm`)
returns no source hit; every `Schedule D` hit is 7.B private funds
(`adv_bulk_ingest.py:127-128`, `docs/release-readiness/adviser-fund-source-contract.md:5`).
Research 01's belief is confirmed from code: no natural person from Schedule A/B (direct/indirect
owners and executive officers), Schedule D sections other than 7.B, or Part 2B (supervised persons) is
captured. "Complete Person scope" for ADV therefore requires new capture, not a resolver change.

## What this settles for tickets 02/03/05/06 and the ADV fog item

- **02 (what binds).** From ADV, the only identifier is CRD, and CRD keys an *Adviser*, never a
  Person (`adv_bulk.py:203-207`; `database.py:275` unique). The Person hop is CIK-equality with a Form
  3/4/5 reporting owner (`pipeline.py:4776-4777`), and the scheduled path never supplies that CIK
  (`adv_bulk_ingest.py:237`). No code distinguishes an individually registered adviser from a firm (F2).
- **03 (reporting-owner classification).** On the scheduled IAPD path the only `IS_PERSON_OF`
  candidates are 13F-manager stubs whose CIK equals a reporting-owner CIK (F4) — the entity-owner
  case ticket 03 is classifying. An IAPD-sourced ADV registrant cannot reach that join today.
- **05 (relationships).** Legacy `IS_PERSON_OF` is a propertyless, non-temporal, never-closed edge
  (`002_seed_data.sql:275-279`; `pipeline.py:191,2472-2477`) with no graph parity check, no API reader,
  no gold projection, no Agent Query Surface section (F5). Clean MDM replaces it with same-ID profile
  membership (`domain-model.md:62`).
- **06 (legacy ID crosswalk).** Silver's `sec_adv_filing.mdm_entity_id` is an Adviser ID
  (`mdm_entity_backfill.py:137`). There is no legacy Person ID derived from ADV to cross-walk.
- **ADV fog item (Schedule A/B, Part 2B).** Not parsed on any path (F7). Whether the IAPD monthly
  archive contains those members is not code-determinable (below); if it does, capture is a parser
  extension of `parse_adv_bulk_archive`'s member list; if not, a new source.

## Could not be determined from code

- How many `sec_adv_filing` rows in prod carry a non-NULL `cik` from Path B (hand-staged XML) or
  Path C (EDGAR ADV-family forms), and therefore how many `MdmAdviser` rows ever had a CIK from ADV.
- Which ADV-family forms in `ADV_FORMS` actually appear in EDGAR daily indexes (Path C's real input).
- Whether the IAPD `ADV_Filing_Data_*.zip` archives include Schedule A/B or Part 2B members:
  `_rows()` filters `bundle.namelist()` by regex (`adv_bulk_ingest.py:55-56`) and silently ignores
  everything else, so "not parsed" is certain and "not present" is not.
- Whether any `IS_PERSON_OF` or `IS_ENTITY_OF` row ever existed in prod Postgres; the last recorded
  live check found 0 of 1 adviser (`06-PHASE-CLOSURE-LEDGER.md:34-35`).
- Whether 13F-manager stubs and CRD-keyed advisers for the same firm were ever unified: the
  `unclaimed_by_cik` claim (`adv_bulk.py:215-219,281-282`) needs an ADV row with a CIK, which Path A
  never produces.
