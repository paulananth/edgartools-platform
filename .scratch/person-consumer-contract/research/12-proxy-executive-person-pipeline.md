# DEF 14A executive-record Person pipeline: code trace

Ticket: [12](../issues/12-trace-proxy-executive-person-pipeline.md). Run 2026-09-19. Code-only.

Every `path:line` below is relative to the repo root on
`claude/person-consumer-contract`; `edgar/proxy/html_extractor.py` is the
installed `edgartools==5.30.0` wheel (`uv.lock` line 655-656; pin
`edgartools>=5.29.0`, `pyproject.toml:16`) read at
`.venv/lib/python3.12/site-packages/edgar/proxy/html_extractor.py`.

## What was read

- Parser: `edgar_warehouse/parsers/proxy_fundamentals.py` (130 lines, whole),
  `edgar_warehouse/parsers/__init__.py:5-30`, and the edgartools extractor it
  delegates to, `edgar/proxy/html_extractor.py:445-895`.
- Fetch stage: `edgar_warehouse/application/workflows/fundamentals_ingest.py`
  (whole), `edgar_warehouse/application/commands/bootstrap_fundamentals.py:161-180`,
  `infra/scripts/deploy-aws-application.sh:3759-3787`.
- Silver: `edgar_warehouse/silver_schema.py:1-17,251-265,514,591-596`,
  `edgar_warehouse/silver_landing_store.py:57-65,379-420,476-480,576-579`,
  `infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql:387-404`,
  `infra/snowflake/dbt/edgartools_gold/models/silver/sec_executive_record.sql`,
  `infra/snowflake/dbt/edgartools_gold/models/gold/executive_records.sql`,
  `.../gold/gold.yml:352-363`, and the pre-Ticket-17 DuckDB DDL recovered
  with `git show 35f6f07b^:edgar_warehouse/silver_store.py` (line 794-820).
- Legacy MDM: `edgar_warehouse/mdm/pipeline.py:140-192,658-735,3247-3260,3496-3596,3743-3901`,
  `edgar_warehouse/mdm/resolvers/person.py:26-57`, `edgar_warehouse/mdm/rules.py:140-175`,
  `edgar_warehouse/mdm/database.py:304-306,680-692`, `edgar_warehouse/mdm/coverage.py:415-419`,
  `edgar_warehouse/mdm/export.py:449-460`, `docs/adr/0008-name-relationship-closing-patterns.md:10`.
- Downstream: `edgar_warehouse/mdm/snowflake_graph.py:22-40`,
  `edgar_warehouse/serving/subject_bundle_read.py:1-60,219-260,390-398`,
  `edgar_warehouse/serving/targets/snowflake.py:98`,
  `edgar_warehouse/infrastructure/run_manifest_builder.py:29`.
- Tests: `tests/unit/test_fundamentals_modules.py`, `tests/unit/test_fundamentals_landing_passthrough.py`,
  `tests/mdm/test_pipeline_relationships.py:864-1000`, `tests/mdm/test_relationship_temporal_contract.py:62-178`.
- Clean MDM target (never checked out): `git show origin/codex/clean-mdm-integration:docs/specs/clean-mdm/pipeline-inventory.md`
  (row 26) and `...:docs/specs/clean-mdm/domain-model.md` (lines 12, 25-28, 68, 87).

## Findings

**F1 — Source form and fetch.** Forms: `PROXY_FORMS = {"DEF 14A", "DEF 14A/A", "DEFA14A", "PRE 14A"}`
(`edgar_warehouse/parsers/__init__.py:12`), dispatched by `get_parser()` to
`parse_proxy_fundamentals` (`__init__.py:26-27`). The fetch is
`bootstrap-fundamentals --mode per-filing` (`commands/bootstrap_fundamentals.py:169-177`)
→ `run_bootstrap_fundamentals_per_filing` (`workflows/fundamentals_ingest.py:136`).
It does not call SEC: it reads `sec_company_filing` for the CIK slice
(`fundamentals_ingest.py:173-182`, form filter `BRANCH_B_FILING_FORMS`, line 46-49),
then the filing's `is_primary` attachment and its `sec_raw_object.storage_path`
from bronze (`:243-253`, `:85-105`). Proxy filings get the *primary* document
only (`:273-274`); no Item 5.02-style lookback bounds them (`:199-206` bounds
8-Ks only). Step Functions state: `FetchPerFilingFundamentals` in
`load_history`, `fundamentals_mode_stage("per-filing", wh_large_arn, windowed=True, ...)`
(`deploy-aws-application.sh:3775-3787`), with a Catch that skips to
`FetchThirteenFHoldings` — "a transient Branch B failure never blocks MDM/gold"
(`:3763-3765`). Idempotency key: `sec_fundamentals_processed_accession(mode='per-filing', accession_number)`,
bulk-prefetched (`fundamentals_ingest.py:113-133`, `:221-228`) and written
strictly last per accession (`:324-331`; contract in
`silver_landing_store.py:57-65`). There is no `--force` path for per-filing
reprocessing in this workflow (`force` exists only on `run_bootstrap_entity_facts`,
`:343`), so a parser fix does **not** re-parse already-marked accessions.

**F2 — Parser-defect root cause (the 47 % role-text `exec_name`).** The
platform parser does not split anything: `exec_name` is
`str(entry.name).strip()` (`proxy_fundamentals.py:108`) taken verbatim from
`edgar.proxy.html_extractor.extract_summary_compensation` (`:82`, `:93`).
The defect is in that extractor's row walk, `html_extractor.py:857-864`:

```
for row in data_rows:
    if name_col < len(row) and row[name_col]:
        cell_text = row[name_col]
        if cell_text and not cell_text.startswith('(') and len(cell_text) > 2:
            name, title = _split_name_title(cell_text)
            if name and not any(kw in name.lower() for kw in ['total', 'footnote', 'note']):
                current_name = name
                current_title = title
```

Mechanism: a Summary Compensation Table lays each executive out as a block
of one `<tr>` per fiscal year, and the "Name and Principal Position" column
(header regex `name|principal\s+position`, `:469`) puts the name in the
first row and the wrapped title lines in the following rows of the same
column — e.g. row 1 `Tim Cook | 2023 | ...`, row 2 `Chief Executive Officer | 2022 | ...`,
row 3 `| 2021 | ...`; multi-line titles wrap as `Chairman of the` / `Board and Chief` / `Executive Officer`.
For each such row `_split_name_title` (`:547-581`) finds no `,`/`\n`
separator (`:554-566`) and no concatenated keyword at index `> 3`
(`:570-579` — `'Chief '` at index 0 fails the `idx > 3` test), so it
returns `(cell, '')` (`:581`): the title fragment *is the name*, with an
empty title. The only rejection filter on the candidate name is
`['total', 'footnote', 'note']` (`:862`); `_TITLE_KEYWORDS` (`:527-531`) is
never applied to the name side. `current_name` is therefore overwritten by
the title fragment, and every subsequent year row in the block (`:883-884`)
is emitted with `name='Chief Executive Officer'`, `title=''`. This
reproduces every symptom in research 01 F1: "chief financial officer"
under 203 issuers (the single most common second-row cell), "President and"
/ "Chairman of the" / "Executive Officer" (wrap fragments), "former"
(a `Former` prefix line), and single tokens. Footnote markers survive on
real names ("Brian B. Yoor,(1)") because `_FOOTNOTE_RE` (`:492`) is applied
only in `_parse_comp_dollar` (`:501`), and the comma branch rejects `(1)`
as a title (`:561`) so the whole cell is returned. Only the first-year row
of each block carries the right name. No comment or TODO in either file
acknowledges this; `proxy_fundamentals.py:1-3` calls the extractor
"DOM-based" and the gold model comment (`executive_records.sql:82-88`)
treats the extractor's output as trustworthy.

**F3 — Parser emitted fields and secondary role defect.** Per entry the
parser emits `cik, accession_number, fiscal_year, exec_name, exec_role, total_comp, base_salary, bonus, stock_awards, option_awards, non_equity_incentive, parser_version='1'`
(`proxy_fundamentals.py:103-117`). There is **no person identifier** —
no CIK, no owner index, no position in the table; the row's only person
handle is the raw `exec_name` string (docstring `:11-13`: "Person identity
and tenure are NOT written to silver"). `pension_change` and
`other_compensation`, which the extractor does return
(`html_extractor.py:461-462`), are dropped. `exec_role` is
`_infer_role(raw_title) or raw_title[:200]` (`:109`); because edgartools
already abbreviates titles (`html_extractor.py:533-544,563-566`), the
platform's `_ROLE_MAP` entry `"president and chief executive officer"`
(`:26`) is unreachable, and an abbreviated `"President & CEO"` matches
`"president"` (`:41`) → `exec_role = "President"`, losing the CEO
designation. For the defective rows in F2, `raw_title == ''` so
`exec_role` is `None` while the role sits in `exec_name`.

**F4 — Silver.** Landing table `sec_executive_record`
(`11_silver_landing_schema.sql:387-404`; mirrored `silver_schema.py:251-265`):
`exec_name TEXT NOT NULL`, `exec_role TEXT`, six `DOUBLE` comp columns,
`parser_version`, `ingested_at TIMESTAMP_TZ`, `parse_sequence` PK.
REQUIRED (NOT NULL) set: `cik, accession_number, fiscal_year, exec_name`
(`silver_schema.py:591-596`). Writer: `merge_executive_records` →
`_record_landing_passthrough("sec_executive_record", rows, defaults={}, stamp=ingested_at)`
(`silver_landing_store.py:576-579`, `:476-480`) — append-only, no dedupe
in Python. The dbt collapse key is `(cik, accession_number, exec_name)`,
latest `parse_sequence` wins (`models/silver/sec_executive_record.sql:23-26`),
which is the old DuckDB `PRIMARY KEY (cik, accession_number, exec_name)`
(`git show 35f6f07b^:edgar_warehouse/silver_store.py`, line 820).
**`fiscal_year` is not in the key**: a three-year SCT block for one
executive collapses to one row per filing, keeping the last-appended year.
There is no `mdm_entity_id` back-propagation column on this table
(`silver_schema.py:251-265` has none; the six tables that do are at `:61,108,145,403,420,434`).
The old DDL comment says this is deliberate: "exec_person_entity_id —
entity resolution is MDM's responsibility; the resolved entity_id lives on
mdm_relationship_instance (source_entity_id), not denormalised to silver"
(old `silver_store.py:812-814`).

**F5 — Legacy MDM: no resolver, name-exact global lookup, per-issuer UUID5 stub.**
`PersonResolver` (`resolvers/person.py:30`, chain `CIKExactMatcher → FuzzyNameMatcher(context_fields=("issuer_cik",)) → optional Splink`, `:39-55`)
is **not** on this path; `run_persons` reads reporting owners only
(`pipeline.py:1416` onward). Proxy rows are consumed solely by
`_derive_employed_by` (`pipeline.py:3743`), SQL at `:3783-3794`
(`WHERE exec_name IS NOT NULL`, watermark `ingested_at > ?` under checkpoint
key `EMPLOYED_BY:exec`, `:3780-3793`; two keys because the type has two
source tables, `database.py:685-688`). Person side is `_ensure_proxy_person(exec_name, cik, accession)`
(`:3520`): (1) `_person_entity_id(None, exec_name)` (`:3546`) which, with
`owner_cik=None`, runs `select(MdmPerson.entity_id).where(MdmPerson.canonical_name == owner_name)`
(`:3256-3258`) — an exact, case-sensitive, **issuer-unscoped** match over
all persons; (2) otherwise `uuid5(NAMESPACE_DNS, f"{company_cik}:{normalized}")`
with `normalized = NFKD(exec_name.strip().lower())` (`:3551-3552`) and
creation of `MdmEntity(resolution_method="uuid5_proxy_stub", confidence=0.5)`,
`MdmPerson(canonical_name=exec_name.strip(), name_variants=[...])`,
`MdmSourceRef(source_system="proxy_filing", source_id=accession, source_priority=50, confidence=0.5)`,
plus an `mdm_change_log` row so export drains it (`:3564-3595`, `:3496-3518`).
No thresholds exist on this path — there is no fuzzy score. Two
consequences follow from the code alone:

- The docstring's claim "UUID5 deduplication is intentionally per-company
  (AD-06). An exec named 'John Smith' at AAPL ... and at MSFT ... will
  receive two different entity_ids" (`:3530-3533`) is defeated by step (1):
  the second issuer's row finds the first issuer's stub by verbatim
  `canonical_name` and reuses it. With F2's defect this means one Person
  entity named "Chief Financial Officer" accrues `EMPLOYED_BY` edges to
  every issuer whose table wraps that way (research 01: 203 issuers).
- Step (1)'s "Exact Form 4 anchor" (`:3526`, `:3753`) is structurally a
  near no-op: Form 4 `canonical_name` is `normalize_name(owner_name)` —
  lowercased, punctuation stripped (`rules.py:152-160`, `resolvers/person.py:76-80`)
  — while the proxy lookup uses the verbatim mixed-case `exec_name`, so an
  exact `==` can only hit another proxy stub, never a normalized Form 4
  person. Name-only binding across issuers is therefore the *actual*
  behaviour, and it binds to the wrong anchor set.

Relationship written: `EMPLOYED_BY` (`RELATIONSHIP_TYPES`, `pipeline.py:152`),
`ensure_relationship(rel_type_name="EMPLOYED_BY", source=person_id, target=company_id, properties, effective_from=date(fiscal_year,1,1), source_system="proxy_filing", source_accession=accession)`
(`:3871-3879`), `properties = {role, title (both = exec_role), fiscal_year, total_compensation, stock_awards, option_awards, non_equity_incentive, source_accession}`
(`:3857-3866`). Closing pattern `property_differs_from_prior`
(`:192`, ADR 0008 line 10) via `_deactivate_if_properties_changed`
(`:3867-3870`, helper `:658-719`): the prior open version of the
(person, company) pair is closed at `effective_from` only when
`confirmed_chronologically_after(effective_from, current.valid_from_date)`
(`:706-710`); the docstring records that without this "97.8% of rows created
since PR #568 landed were quarantined" (`:3773-3775`). Dedup key per docstring:
`(source_entity_id, target_entity_id, fiscal_year)` (`:3756`). Retirement of
a person is never handled — a stub has no lifecycle beyond creation; a
parser fix producing a corrected `exec_name` for the same accession creates
a *new* stub (different UUID5 input) and leaves the old one and its edges
in place, subject only to the watermark: re-appended landing rows carry a
fresh `ingested_at`, so they will be re-derived (`:3791-3793`).

**F6 — Downstream consumers.** Gold: `executive_records`
(`models/gold/executive_records.sql`), grain `(cik, accession_number, exec_name)`
(`:15`), `fact_key = surrogate_key(accession_number, exec_name)` (`:20`),
YoY `lag(total_comp) over (partition by cik, exec_name order by fiscal_year)`
(`:48-50`) and `is_current_role` from `partition by cik, exec_role` (`:53`,
`:90`) — both keyed on the defective strings, so YoY compares "Chief
Financial Officer" to itself across filings. `gold.yml:352-363` tests only
`not_null` on `cik, accession_number, exec_name`. Source-layer export
`executive_record → fact_executive_record` (`serving/targets/snowflake.py:98`,
manifest key `run_manifest_builder.py:29`). Graph: `EMPLOYED_BY` is in
`ALLOWED_RELATIONSHIP_TYPES` (`snowflake_graph.py:25`) but explicitly
"excluded from named parity checks until Phases 6-7 populate them"
(`:35-39`); `export_active_relationship_endpoints` exists specifically
because "proxy persons ... created entities without a change-log row, so
edges could export while person/security nodes never reached the Snowflake
MDM mirror" (`export.py:449-460`). Coverage: `EMPLOYED_BY` evidence query is
`SELECT accession_number, cik, exec_name FROM sec_executive_record`
(`coverage.py:415-419`, version `edge09-v2-proxy-item502`). API: no
router under `edgar_warehouse/mdm/api/` references `EMPLOYED_BY`
(grep, zero hits). Agent Query Surface: `build_issuer_subject_bundle`'s
`employment` section takes `employment_edges` with `source_system ∈ {"proxy_def14a", "item_5_02"}`
(`subject_bundle_read.py:40-42`, `:219-236`) and `executive_pay_rows`
labelled `source: "gold_proxy_executive_record"` (`:239-249`); its
`_person_key` falls back to `name:<lowercased name>` when no entity id is
present (`:390-398`). Note the source-system string the bundle expects
(`proxy_def14a`) differs from what the derivation writes (`proxy_filing`,
`pipeline.py:3877`); unknown values are surfaced "but mark non-standard"
(`:225-228`). `infra/snowflake/sql/decision_contract/*.sql` contains no
`EMPLOYED_BY`/executive reference (grep, zero hits).

**F7 — Tests.** No test in the repo calls `parse_proxy_fundamentals`,
`_split_name_title` or `extract_summary_compensation` (grep over `tests/`,
zero hits); the parser's name/title behaviour is unpinned. What is pinned:
`test_new_derive_methods_exist` lists `_ensure_proxy_person`
(`tests/unit/test_fundamentals_modules.py:849-857`);
`test_writes_employed_by_relationship` and
`test_proxy_person_stub_writes_change_log_for_export` feed clean names
(`"Jane CEO"`, `"Proxy Only Exec"`) and assert one insert and
`resolution_method == "uuid5_proxy_stub"` (`tests/mdm/test_pipeline_relationships.py:867-915`);
`test_item_502_event_predating_proxy_baseline_is_skipped_not_crashed`
(`:951-990`) pins the proxy-baseline-then-event ordering; the temporal
contract tests use `EMPLOYED_BY` as their only fixture type
(`tests/mdm/test_relationship_temporal_contract.py:62`). The landing
passthrough tests cover the write path generically
(`tests/unit/test_fundamentals_landing_passthrough.py:87-200`).

**F8 — Clean MDM's stated target.** `pipeline-inventory.md` row 26 (Codex
branch, inspected at `b1babd8b`): `| Proxy/officer — mdm/pipeline.py:3743, :3520 | sec_executive_record, sec_employment_event | Person lookup/stub creation inside derivation; dated EMPLOYED_BY, compensation/role properties | Identity first, then reported employment; no direct stub master writes; provenance includes event and filing dates |`.
`domain-model.md`: Person is "A natural person ... Never merge with a
Company, employer, sole-proprietor business, or similarly named person
through a role" (line 12); "Company and Person are the first supported
identities" (line 25); `EMPLOYED_BY / insider association | Person to Company | Source-reported office/role and valid dates; holdings do not imply employment`
(line 68); "Legacy IDs become an explicitly verified, versioned crosswalk"
(line 87). The same two files also exist on this branch under
`docs/specs/clean-mdm/` (untouched).

## What this settles for tickets 02/03/05/06/10

- **02 (what binds a Person):** the proxy source carries no identifier of
  any kind (F3); its only handle is `(cik, exec_name)`, and today ~half of
  those names are title fragments (F2). Legacy binds by verbatim name
  globally (F5), which is the cross-issuer name binding the map forbids.
  Form 4 canonical names are normalized, proxy names are not (F5) — any
  future `(issuer CIK, normalized name)` key must normalize both sides the
  same way (`rules.py:152`).
- **03 (reporting-owner classification):** nothing on this path touches
  reporting owners; the Form 4 "anchor" in `_ensure_proxy_person` never
  fires in practice (F5).
- **05 (relationships):** legacy `EMPLOYED_BY` properties, effective-date
  rule (`Jan 1 of fiscal_year`), closing pattern and the two-checkpoint
  watermark are all in F5; `source_system` is `proxy_filing` in Postgres
  but the bundle contract expects `proxy_def14a` (F6). Silver keeps one
  year per (filing, exec_name) (F4), so "one edge per person-company-year"
  (`pipeline.py:3757`) can only see the surviving year per filing.
- **06 (legacy ID crosswalk):** legacy proxy Person IDs are
  `uuid5(NAMESPACE_DNS, "{cik}:{nfkd-lowercased exec_name}")` (F5) —
  deterministic from silver, so a crosswalk can be recomputed, but with
  the caveats that (a) a global name hit reuses another issuer's ID instead
  of minting one, and (b) any ID minted from a title fragment identifies no
  person. Stubs carry `confidence=0.5`, `source_priority=50`, and one
  `MdmSourceRef` per accession.
- **10 (parser fix):** the split is not in the platform; it is
  `edgar/proxy/html_extractor.py:857-864` and `:547-581` in edgartools
  5.30.0. Two repair points:
  1. Upstream (edgartools): in `extract_summary_compensation`, before
     assigning `current_name` (`:862-864`), reject a `name` whose lowercase
     form contains any `_TITLE_KEYWORDS` entry (`:527-531`) or is
     all-stopwords (`of the`, `and`, `former`) and instead append it to
     `current_title`; strip `_FOOTNOTE_RE` from the name cell.
  2. Platform-only (no upstream wait), in `parse_proxy_fundamentals`
     (`proxy_fundamentals.py:100-118`): walk `entries` in order carrying
     `last_good_name`; when `entry.name` matches title vocabulary (reuse
     `_ROLE_MAP` keys plus the extractor's `_TITLE_KEYWORDS`) or has no
     alphabetic token outside that vocabulary, emit the row with
     `exec_name = last_good_name` and fold the fragment into `exec_role`
     (via `_infer_role`); strip trailing `,` and `(\d+)` footnotes from
     names. Also fix the `_ROLE_MAP` ordering/abbreviation gap (F3).
  Proposed test (new `tests/unit/test_proxy_fundamentals.py`): build
  `ExecutiveCompEntry` objects `[("Tim Cook","",2023), ("Chief Executive Officer","",2022), ("","",2021)]`-shaped
  via a monkeypatched `extract_summary_compensation`, assert three rows all
  with `exec_name == "Tim Cook"`, `exec_role == "CEO"`, distinct
  `fiscal_year`; and a footnote case `"Brian B. Yoor,(1)"` → `"Brian B. Yoor"`.
  Reprocessing note: the per-filing marker (F1) means fixed code will not
  revisit marked accessions; a re-export needs the marker rows cleared or a
  new `--force` path, and the silver collapse key (F4) will keep only one
  year per exec per filing regardless.

## Could not be determined from code

- Which fraction of the 47 % comes from the "title on subsequent row"
  layout versus other layouts (e.g. name and title in separate `<td>`s
  under one colspan header) — the mechanism in F2 explains every reported
  symptom, but the layout mix is a data question and Snowflake is gone.
- Whether the `.venv` copy of edgartools (5.30.0) is the version in the
  running warehouse image; `uv.lock` pins 5.30.0 but the deployed image
  digest was not checked (no AWS access).
- Whether `EMPLOYED_BY` edges have ever been exported to the graph in prod
  (`snowflake_graph.py:35-39` says the type is excluded from parity; the
  export helper in `export.py:449` implies the path was exercised at least
  once for Ticket 20).
- Whether any consumer actually passes `employment_edges` into
  `build_issuer_subject_bundle` with `source_system="proxy_def14a"` — no
  caller in the repo constructs that value (grep found only the constant).
- Whether the upstream edgartools repository has since changed
  `_split_name_title`/`extract_summary_compensation` (no network access).
