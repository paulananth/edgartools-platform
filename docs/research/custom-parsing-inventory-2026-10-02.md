# Custom parsing inventory

Date: 2026-10-02. Code baseline: `main` at `542a9fa04f4359bed7e097b4cb1d5fa4b89ede15`.
Research branch: `codex/custom-parsing-research-20261002`.

## Answer

**Yes. Source-specific parsing and preparation still exist in Python outside a declarative parsing contract.** Configured Bookkeeping operations select those implementations; selecting an operation by configuration does not make its field extraction, document grammar or classification logic declarative.

The principal reachable areas are SEC submissions staging, Company landing-to-input preparation, native GLEIF archive decoding and interpretation, and the SEC/GLEIF Name Census. The repository also contains retained helpers without production callers, external `edgartools` smoke scripts, and a separate Rust Source Contract prototype whose field extraction really is configured.

“Reachable” below means a call path exists in checked-in source. It does not establish deployment, data coverage or PostgreSQL qualification. No code or contracts were changed for this inventory. Unmerged PR #780 changes are outside this baseline.

## Classification

| Category | Meaning |
| --- | --- |
| Source-specific Python | Source field names, shape assumptions or admissibility decisions are encoded in Python rather than a `read` grammar. |
| Config-selected implementation | A contract names fields, predicates or a versioned primitive; its generic algorithm is implemented in code. This supports configuration and is not necessarily a bypass. |
| Retained, no production caller found | Repository search finds definition/export/tests, but no production call or registration. This is a cleanup candidate, not proof that deletion is safe. |
| External-library smoke tool | Script calls `edgartools` parsing APIs rather than implementing the parser locally. |
| Format/control validation | Decode manifests, verify envelopes, inspect transport structure or parse operator input; does not extract SEC domain facts. |

## Reachable source-specific Python

### Configuration boundary verified locally

A read-only probe loaded all three current source documents through
[`rules.files.load_source`](../../edgar_warehouse/rules/files.py#L125), using
this worktree's module, and built the executable CLI parser. None of the five
Dataset Contracts declares `read` at the source, contract or adapter level.

| Current configuration | What is configured | Raw reading/preparation boundary |
| --- | --- | --- |
| [`SEC Company`](../../rules/sources/sec.submissions.company/source.yaml#L1) | Acquisition completeness, Bookkeeping stages, MDM mapping and quality | Selects `company.silver` and `company.prepare`; Python implements the extraction and joins below. |
| [`SEC Person`](../../rules/sources/sec.submissions.person/source.yaml#L1) | Raw submissions paths for CIK and legal name, classification and quality | No dedicated Person reader is declared. This mapping does not establish an executable raw-file-to-Person pipeline. |
| [`GLEIF`](../../rules/sources/gleif/source.yaml#L1) | Three datasets' field/identifier/relationship mappings and quality | Native bytes and intermediate relationship records are decoded by Python below. |

The common configured MDM intake is
[`mdm.ingest`](../../edgar_warehouse/bookkeeping/clean/mdm_capabilities.py#L145)
→ [`normalize_input`](../../edgar_warehouse/bookkeeping/clean/source_input.py#L12)
→ [`adapters.normalize`](../../edgar_warehouse/mdm/clean/adapters.py#L245).
It verifies fixed NDJSON input and frozen registered contracts; it does not
interpret an arbitrary configured raw JSON/XML/CSV grammar. CLI/config probing
passed; database or hosted source execution was not exercised.

### 1. SEC submissions to Silver landing

[`bronze_submission_extractors.py`](../../edgar_warehouse/loaders/bronze_submission_extractors.py#L65) contains **six source loaders**: `stage_company_loader`, `stage_address_loader`, `stage_former_name_loader`, `stage_manifest_loader`, `stage_recent_filing_loader`, and `stage_pagination_filing_loader`. Their source field names and target row keys are written in Python. Examples include `name -> entity_name`, `stateOrCountry -> state_or_country`, `formerNames`, and parallel `accessionNumber`/`filingDate`/`form` arrays.

Two additional public helpers in this module affect the interpretation:

- [`is_individual_filer`](../../edgar_warehouse/loaders/bronze_submission_extractors.py#L38) uses a hardcoded ownership-form set, `entityType == other`, absence of SIC and absence of tickers. This is source-specific classification before the MDM mapping. It is separate from any positive Company rules in the mastering policy.
- [`filter_rows_by_min_filing_date`](../../edgar_warehouse/loaders/bronze_submission_extractors.py#L11) keeps undated rows and applies a caller-supplied date threshold. [`common.py`](../../edgar_warehouse/loaders/common.py#L9) supplies fixed date slicing and tolerant indexed string/integer conversions.

Caller chain:

1. [`configured_bookkeeping`](../../edgar_warehouse/bookkeeping/clean/cli.py#L20) registers Company expansion, Silver and MDM-preparation capabilities.
2. [`register_company_silver.execute`](../../edgar_warehouse/bookkeeping/clean/company.py#L295) reads verified captures and calls `SilverLandingStore.stage_submission`.
3. [`stage_submission`](../../edgar_warehouse/silver_landing_store.py#L188) imports the loaders, gates Company/address/former-name rows using `is_individual_filer`, and combines recent and pagination filing rows.

The source-specific pagination grammar is also Python: [`register_company_expansion`](../../edgar_warehouse/bookkeeping/clean/company.py#L156) reads `filings.files`, verifies bounded distinct page names and generates the child worklist. [`register_company_silver.captures`](../../edgar_warehouse/bookkeeping/clean/company.py#L233) checks that actual pages match that declared inventory.

### 2. Company landing-to-mastering input

[`company_source.py`](../../edgar_warehouse/mdm/clean/company_source.py#L101) reads fixed Silver table shapes and prepares a Company input record:

- `_catalog_tickers` groups by CIK, sorts source ranks and deduplicates tickers.
- `_filed_forms` groups distinct forms by CIK.
- `_business_addresses` picks `address_type == business`.
- [`business_address`](../../edgar_warehouse/mdm/clean/company_source.py#L158) pivots fixed SEC address columns, selects `state_or_country` or `country_code`, and derives region/country using the configured SEC place-code reference.
- [`prepare_company_bundle`](../../edgar_warehouse/mdm/clean/company_source.py#L383) explicitly pins and joins Company, filing, address, ticker and Name Census evidence before writing records.
- [`census_filers`](../../edgar_warehouse/mdm/clean/company_source.py#L577) joins former names to Companies; [`cascade_filers`](../../edgar_warehouse/mdm/clean/company_source.py#L626) adds business addresses and delegates mapped fields to the approved contract.

Callers: [`register_company_mdm_preparation`](../../edgar_warehouse/bookkeeping/clean/company.py#L466), [`prepare_clean_company`](../../edgar_warehouse/mdm/clean/cli.py#L399) and [`name_census`](../../edgar_warehouse/mdm/clean/cli.py#L417). This preparation is upstream of the configured `adapters.normalize` mapping.

### 3. Native GLEIF archive decoding

The source configuration explicitly documents the boundary: [`rules/sources/gleif/source.yaml`](../../rules/sources/gleif/source.yaml#L1) says parsing stays in `gleif_source.py` and has no `read` section.

[`gleif_source.py`](../../edgar_warehouse/mdm/clean/gleif_source.py#L28) contains hardcoded member/CDF versions, JSON wrapper names, XML root/header/container/record names and namespaces. Its custom decoder uses libraries as tokenizers:

- [`_json_records`](../../edgar_warehouse/mdm/clean/gleif_source.py#L105): `ijson` event consumption with a required wrapper and duplicate-key/depth/trailing-data checks.
- [`_xml_value`](../../edgar_warehouse/mdm/clean/gleif_source.py#L146): attributes become `@name`, text becomes `$`, and repeated child elements become lists.
- [`_xml_records`](../../edgar_warehouse/mdm/clean/gleif_source.py#L164): `lxml` streaming events with GLEIF-specific header/content structure; the relationship member receives an additional wrapper.
- [`inspect_archive`](../../edgar_warehouse/mdm/clean/gleif_source.py#L239): one unencrypted ZIP member, bounded compressed/expanded/record sizes, hash and count verification, decoder selection and callbacks.

Callers include publication validation in [`source_publications.py`](../../edgar_warehouse/mdm/clean/source_publications.py#L329) and Name Census construction in [`name_census.py`](../../edgar_warehouse/mdm/clean/name_census.py#L154). Hash, count and security checks are format safeguards; the member/tag/wrapper grammar is source-specific custom parsing.

### 4. Native GLEIF interpretation before configured mapping

[`record_evidence`](../../edgar_warehouse/mdm/clean/gleif_source.py#L400) performs source-specific interpretation before calling `normalize`:

- Reads fixed relationship endpoint fields, requires LEI endpoint types and approved Company scope.
- Selects exactly one `RELATIONSHIP_PERIOD`, interprets dates and requires compatible ACTIVE/INACTIVE intervals.
- Rebuilds the relationship into a smaller fixed intermediate record.
- Reads fixed Level 1 category paths and validates a hardcoded category set.
- Reads fixed exception categories/reasons and defers reporting exceptions rather than creating a fabricated parent relationship.
- [`_refuse_deletion`](../../edgar_warehouse/mdm/clean/gleif_source.py#L388) handles the GLEIF deletion extension.

The final master projection is configuration-driven: [`dataset_contract`](../../edgar_warehouse/mdm/clean/gleif_source.py#L367) loads mappings from source YAML, and [`record_evidence`](../../edgar_warehouse/mdm/clean/gleif_source.py#L513) delegates to `normalize`. [`native_consumption.py`](../../edgar_warehouse/mdm/clean/native_consumption.py#L11) imports and uses `record_evidence`; this is not a standalone unused helper.

### 5. SEC/GLEIF Name Census extraction

[`name_census.py`](../../edgar_warehouse/mdm/clean/name_census.py#L53) explicitly reads `OtherEntityNames.OtherEntityName` and `TransliteratedOtherEntityNames.TransliteratedOtherEntityName`. Its [`on_record`](../../edgar_warehouse/mdm/clean/name_census.py#L133) callback reads fixed GLEIF Entity/LEI/LegalName/Registration fields and excludes BRANCH records from the ordinary census. [`cascade_entity`](../../edgar_warehouse/mdm/clean/name_census.py#L76) admits GENERAL for the cascade, then calls configured field/quality mappings.

The census reuses registered versioned name normalizers, but those source field selections and exclusions are still Python. Caller: [`write_name_census`](../../edgar_warehouse/mdm/clean/company_source.py#L713), exposed by the MDM CLI and used in Company preparation.

### 6. Ticker-catalog completeness grammar

[`_is_valid_ticker_catalog_json`](../../edgar_warehouse/acquisition/source_family_registry.py#L192) recognizes SEC's `fields/data` and numbered `cik_str` object shapes in Python. [`change_journal.capture.complete`](../../edgar_warehouse/change_journal/capture.py#L43) calls it when configured format is `ticker_catalog`.

This is reachable source-specific validation, **not a ticker row parser or an active ticker acquisition workflow by itself**. The surrounding source-family policy classes also contain historical comments about retired orchestration paths; comments are not current caller evidence.

## Retained custom helpers without a production caller found

| Helper | Custom interpretation | Caller evidence |
| --- | --- | --- |
| [`stage_daily_index_filing_loader`](../../edgar_warehouse/loaders/bronze_daily_index_extractors.py#L9) | SEC daily index regex, accession extraction, dates, URL and record hash | Exported in `loaders/__init__.py`; no production call found. |
| [`seed_universe_loader`](../../edgar_warehouse/loaders/bronze_reference_extractors.py#L8) | Two SEC ticker JSON shapes to CIK/ticker/exchange rows | Exported in `loaders/__init__.py`; no production call found. |
| [`_parse_company_ticker_rows`](../../edgar_warehouse/silver_landing_store.py#L601) | Similar ticker shape decoder | Definition and historical completeness-check comment; no production call found. `replace_company_tickers` takes already parsed rows. |
| [`securities.publish` / `_title`](../../edgar_warehouse/mdm/clean/securities.py#L11) | 13F CUSIP grouping and regex Class A/B/C or Option title inference | No production import/call found. This is a semantic classifier, not an XML parser. |

These findings use source-wide symbol searches outside tests, then caller inspection. They are evidence for follow-up review, not authorization to delete shared contracts or source evidence.

The old `edgar_warehouse/parsers/` directory and old `runtime.py` are absent at this baseline. There is no checked-in active Python ownership/ADV filing parser in those former locations. Silver passthrough methods and schemas mentioning ADV, ownership, 13F or financial facts do not prove a corresponding parser still exists.

## Config-selected implementations that still contain custom code

| Area | Configuration controls | Code controls |
| --- | --- | --- |
| [`adapters.normalize`](../../edgar_warehouse/mdm/clean/adapters.py#L245) | Field paths, kind/kind values/classification, identifiers, profiles and relationships | Path traversal, shape validation and projection algorithms. |
| [`adapters.FORMATS`](../../edgar_warehouse/mdm/clean/adapters.py#L36) | `sec_cik` / `lei` format names | Zero-padding/nonzero numeric CIK checks and LEI syntax/mod-97 checksum. |
| [`quality.CHECKS` / `FIXES`](../../edgar_warehouse/mdm/clean/quality.py#L237) | Versioned checks/fixes and arguments from source quality YAML | State-tag regex, blanking and address-standardization implementations. [`_UNIT` / `_WORDS`](../../edgar_warehouse/mdm/clean/quality.py#L178) encode unit removal and abbreviation spellings. |
| [`primitives.NORMALIZERS`](../../edgar_warehouse/mdm/clean/primitives.py#L76) | Normalizer names and policy predicate arguments/order | Fixed implementations including [`names.legal_form_key`](../../edgar_warehouse/mdm/clean/names.py#L23), legal-form spellings and SEC conformed-name tag removal. |
| [`names.edgar_jurisdiction`](../../edgar_warehouse/mdm/clean/names.py#L62) | SEC place-code reference file | Lookup/country/subdivision comparison algorithms and US territory handling. |

Configuration-driven does not mean there is no custom code. A named, versioned implementation may be the intended extension point. The sharper question is whether source grammar, mappings and policy choices remain inspectable and pinned in the contract, or are hidden in an upstream reader.

## Rust Source Contract prototype

[`crates/source-contract/contracts/thirteenf/contract.yaml`](../../crates/source-contract/contracts/thirteenf/contract.yaml#L8) has an actual `read` grammar: XML root, table iteration, column paths, number defaults and registered `custom` steps. It is labeled `prototype-1`.

[`Engine.parse`](../../crates/source-contract/src/lib.rs#L48) consumes that grammar; [`eval`](../../crates/source-contract/src/lib.rs#L190) dispatches `ordinal`, `text`, `number`, `steps` and `custom`. [`xml.rs`](../../crates/source-contract/src/xml.rs#L71) provides a custom generic XML representation using `quick_xml`, with namespace-prefix stripping, attributes, repeated children and control-character filtering. [`blank_missing_token`](../../crates/source-contract/src/lib.rs#L88) is a fixed code implementation selected explicitly by the contract. [`main.rs`](../../crates/source-contract/src/main.rs#L23) registers it by versioned name.

This is **configured source parsing plus custom engine/step implementations**, not an unconfigured 13F parser. Searches of Python runtime, CLI, Dockerfiles, workflows and deployment scripts found no integration caller for this executable. Its known callers are its standalone Rust binary and crate tests. Do not present it as the current Company/Person/GLEIF production parser.

## Batch scripts and other decoding

There are **28 Python files under `scripts/batch/`**; this is a file count, not 28 custom parsers. They exercise `edgartools` APIs for ownership, 13F, offerings, fund reports, Company facts, XBRL, SGML and filing sections. For example:

- [`batch_8k_section_detection.py`](../../scripts/batch/batch_8k_section_detection.py#L90) calls external `parse_html` with `ParserConfig(form='8-K')`; it adds result reporting, not a repository HTML parser.
- [`batch_entity_facts.py`](../../scripts/batch/batch_entity_facts.py#L17) calls external `EntityFactsParser.parse_company_facts`.
- [`query_form4.py`](../../scripts/batch/query_form4.py#L10) calls `filing.obj()` and explicitly selects owner fields for CSV output. That custom projection exists in an operator script, not the current warehouse acquisition command route.

These scripts can make SEC requests when run. This research did not execute them or infer that they are deployed.

Other custom decoding includes strict JSON envelope handling in [`bookkeeping.clean.artifacts`](../../edgar_warehouse/bookkeeping/clean/artifacts.py#L15), fixed NDJSON reading in [`source_input`](../../edgar_warehouse/bookkeeping/clean/source_input.py#L12), generic JSON/XML/ZIP completeness checks in [`capture.complete`](../../edgar_warehouse/change_journal/capture.py#L35), manifest/config readers, SQL/CLI response decoding in infrastructure scripts, and dashboard numeric-input parsing in [`streamlit_app.py`](../../infra/snowflake/streamlit/streamlit_app.py#L788). These are format/control interfaces, not evidence of hidden SEC filing parsers.

Snowflake load wrappers decode their export manifests, for example [`JSON.parse` in the fundamentals loader](../../infra/snowflake/sql/bootstrap/06_fundamentals_load_wrapper.sql#L150). They load already produced warehouse artifacts. A `parser_version` column or SQL regex over filing metadata does not establish a custom filing-body parser.

## Recommended follow-up scope

1. Decide whether the goal is declarative **source reading** or only declarative **master projection and quality policy**. The current Python implementation supplies the latter with custom readers upstream.
2. If source reading must be declarative, start with the six SEC submission loaders and the pre-MDM individual gate, preserving pagination, classification and missing-data behavior as separately reviewed contracts.
3. Inventory Company table joins/pivots and GLEIF pre-normalization decisions before moving them. Those contain more than byte decoding: scope, identity admissibility and interval checks require explicit governance.
4. Retain bounds, duplicate-key handling, hashes, parser security and immutable evidence even if the source grammar moves to configuration.
5. Review uncalled helpers separately from active reader migration. Avoid counting generic validators, configured primitives or external parser smoke tools as unsupported bespoke filing parsers.

## Method and limits

Inspected the production Python package, runnable batch/ops scripts, infrastructure Python/SQL, and the Rust Source Contract crate. Searched parser/decoder/transform symbols and source-library imports; read definitions and executable callers; checked absence of old parser/runtime files. All cited evidence is checked-in local source at the stated base. No hosted deployment, real source sampling, SEC call, parser qualification or database mutation was performed. A repository search cannot exclude external callers that are not checked in.
