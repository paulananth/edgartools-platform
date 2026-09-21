# Research 02 — What Form 3/4/5 and GLEIF parsing needs

Ticket: [02-inventory-what-form-345-and-gleif-parsing-needs](../issues/02-inventory-what-form-345-and-gleif-parsing-needs.md)
Map: [source-contract](../map.md)
Date: 2026-09-21. Method: read the code and local files only. No network request was made: no SEC, GLEIF API or S3 call.
All paths are relative to the repo root. `path:N` means that line in that file.

## Summary

- **Form 3/4/5**: the parser writes **58 silver columns** across 3 tables. **57 of them can be built from generic primitives** if a `lookup` primitive exists. The one exception is `owner_name`, which needs edgartools' company-or-person classifier and name reversal: that is **1 custom column of 58 (1.7%)**. Without a `lookup` primitive, the 9 rule C-J columns also become custom: **10 of 58 (17%)**. Six more columns are filled by the engine or by MDM, not by the read step (`last_sync_run_id` ×3, `mdm_entity_id` ×3).
- **GLEIF**: **no production parser and no silver table exist today.** Level 1 is only captured and parsed by throwaway research scripts under `.scratch/gleif-company-augmentation/research/`. Clean MDM has a synthetic 2-field fixture only. Below is a *proposed* 39-column Level 1 table plus 6 child tables. Every column is a primitive: **0 custom (0%)**. The hard parts are in the reader, not the columns: a zipped JSON array, values that are sometimes an object and sometimes a list, and an open question of XML versus JSON.
- **Rule C-J lookup**: a generic `lookup(source, key)` can express it. The signature needs a key format, a "which snapshot" rule, a found/not-found flag and the matched artifact's sha256. The classifier that *reads* the lookup result is the custom part, not the lookup itself.

---

## Part A — Form 3/4/5 (`edgar_warehouse/parsers/ownership.py`, `PARSER_VERSION = "3"`)

### A.0 Entry, reader and write path

- Entry point: `parse_ownership(accession_number, content, form_type, *, submissions_lookup=None)` (`edgar_warehouse/parsers/ownership.py:71-77`). It is selected for forms `3, 3/A, 4, 4/A, 5, 5/A` (`edgar_warehouse/parsers/__init__.py:10,22-23`).
- The caller reads the primary artifact bytes and decodes them as UTF-8 with `errors="replace"` (`edgar_warehouse/application/warehouse_orchestrator.py:5438-5440`). It then passes the lookup in (`:5442`).
- Reader, `_ownership_root` (`ownership.py:261-276`):
  - slices out the text between the first `<XML>` and the last `</XML>` when present, so it handles a full SEC `.txt` submission;
  - strips the `<?xml ...?>` declaration;
  - parses the XML; if that fails, strips control characters and tries once more;
  - requires the root tag to be `ownershipDocument`.
  - Otherwise all three tables come back empty (`:79-80`). Tests: `tests/unit/test_ownership_parser.py:425,431,436`.
- Write path: the rows go to `merge_ownership_*` (`warehouse_orchestrator.py:5447-5449`), which calls `_record_landing_passthrough`. That call adds `last_sync_run_id` from the sync run (`edgar_warehouse/silver_landing_store.py:269-282,485-491`) and raises if a column marked NOT NULL is missing (`:414-424`).
- The declared silver columns are in `edgar_warehouse/silver_schema.py:383-452`. The NOT NULL columns are in `:673-686`. The landing DDL is `infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql:554-634`.
- Collapse to one row per key: `row_number() over (partition by accession_number, owner_index order by parse_sequence desc) = 1`. The model then joins `sec_company_filing` to add the issuer `cik` (`infra/snowflake/dbt/edgartools_gold/models/silver/sec_ownership_reporting_owner.sql`, the `qualify` clause and the final join).

### A.1 Row grain and repeating groups (item 2)

| Table | Row grain | Key (`silver_schema.py:673-686`) | Repeating group it iterates |
|---|---|---|---|
| `sec_ownership_reporting_owner` | one row per `<reportingOwner>` | `(accession_number, owner_index)` | `./reportingOwner` (`ownership.py:88,101`). `owner_index` = 1-based position (`:101`). |
| `sec_ownership_non_derivative_txn` | one row per **kept** `nonDerivativeTransaction` | `(accession_number, owner_index, txn_index)` | `./nonDerivativeTable/nonDerivativeTransaction`, filtered to those that have `transactionAmounts`, `ownershipNature` and `postTransactionAmounts` (`:143-146`). `txn_index` = 1-based position **after** the filter (`:147`; test `test_ownership_parser.py:554`). |
| `sec_ownership_derivative_txn` | one row per **kept** `derivativeTransaction` | same | `./derivativeTable/derivativeTransaction`, filtered on the same blocks plus `underlyingSecurity` (`:160-163`). |

The transaction and owner groups are **not crossed**, so there are no owners × transactions rows:

- The SEC schema gives a transaction no owner reference (`ownership.py:25-31`).
- So every transaction row has the constant `owner_index = 1` (`:151,168`).
- Every transaction row also carries `reporting_owner_count = len(./reportingOwner)`, a document-level count copied onto each child row (`:89,154,176`).
- Test: `test_ownership_parser.py:452-475`. A joint filing with 3 owners gives owner rows 1..3 and transaction rows `(1, n, 3, nature)`.

Some values are computed once per document and copied onto every owner row:

- `issuer_cik` (`:82`)
- `filing_remarks` (`:83`)
- `filing_footnote_text`: every `./footnotes/footnote` rendered as `"[id] text"` and joined with `" | "` (`:84-87`; test `:545`).

`./footnotes/footnote` and each transaction's `footnoteId` children are also repeating groups. They are only ever *aggregated* into a string, never turned into rows.

### A.2 Column inventory (item 1)

Key to the "Primitive?" column:
- **yes** = one generic primitive expresses it.
- **yes (chain)** = a short chain of generic primitives expresses it.
- **lookup** = generic only if a `lookup` primitive exists.
- **custom** = needs a custom step.

"Absent" says what the column holds when the source element is missing.

#### `sec_ownership_reporting_owner` (27 silver columns: 25 from the parser, 2 from the engine or MDM)

| Column | Source path | Transform | Absent | Primitive? |
|---|---|---|---|---|
| accession_number | artifact context (argument) `:111` | none | — (NOT NULL) | yes: `context` |
| owner_index | position in `./reportingOwner` `:101,112` | 1-based ordinal | — (NOT NULL) | yes: `ordinal` |
| owner_cik | `reportingOwnerId/rptOwnerCik` `:102` | text → int, `None` if not numeric (`:324-328`) | None | yes: `int` |
| owner_name | `reportingOwnerId/rptOwnerName` + lookup payload `:113` | raw if `_is_company(cik, payload)`, else edgartools `reverse_name(raw)` (`:47-48,235-258`) | reversed raw | **custom** |
| owner_name_raw | `reportingOwnerId/rptOwnerName` `:103,118` | all descendant text, stripped (`_text`, `:283-289`) | "" | yes: `text` |
| is_director | `reportingOwnerRelationship/isDirector` `:119` | true if text is in `{1,Y,true,True,TRUE}` (`:314-317`) | False | yes: `flag` |
| is_officer | `…/isOfficer` `:120` | flag | False | yes: `flag` |
| is_ten_percent_owner | `…/isTenPercentOwner` `:121` | flag | False | yes: `flag` |
| is_other | `…/isOther` `:122` | flag | False | yes: `flag` |
| officer_title | `…/officerTitle` `:105-107,123` | text; if it contains "see remarks" (any case), replace with `./remarks`; "" → None | None | yes (chain): `text → when(contains_ci) → ref(filing_remarks) → empty_to_null` |
| other_text | `…/otherText` `:126` | text | "" | yes: `text` |
| filing_footnote_text | `./footnotes/footnote[]` `:84-87,127` | join of `"[@id] text"` with `" \| "` | "" | yes (chain): `join(each, template)` |
| filing_remarks | `./remarks` `:83,128` | text | "" | yes: `text` |
| address_is_care_of | `reportingOwnerAddress/rptOwnerStreet1` `:131-132` | text → upper → remove spaces → starts with `C/O` | False | yes (chain): `text → upper → strip_spaces → starts_with` |
| address_non_us | `reportingOwnerAddress/rptOwnerNonUSAddressFlag` `:133` | flag | False | yes: `flag` |
| owner_submissions_present | lookup found? `:223` / `:204` | bool | False | lookup |
| owner_submissions_sha256 | sha256 of the lookup's matched artifact (`_bronze_sha256`, `:62,224`) | text, "" if absent | "" | lookup |
| owner_entity_type | submissions `entityType` `:225` | JSON value → text, None → "" (`:320-321`) | "" | lookup |
| owner_sic | `sic` `:226` | same | "" | lookup |
| owner_state_of_incorporation | `stateOfIncorporation` `:227` | same | "" | lookup |
| owner_ein | `ein` `:228` | same | "" | lookup |
| owner_ticker_count | `tickers` `:229` | length of list (None → 0) | 0 | lookup (+ `len`) |
| owner_org | `ownerOrg` `:230` | text | "" | lookup |
| owner_fiscal_year_end | `fiscalYearEnd` `:231` | text | "" | lookup |
| parser_version | constant `"3"` `:55,136` | none | — | yes: `contract_version` |
| last_sync_run_id | *engine stamp* (`silver_landing_store.py:485-491`) | — | — | not in read |
| mdm_entity_id | *MDM backfill*, `entity_type="person"` (`edgar_warehouse/mdm_entity_backfill.py:114-119`) | — | NULL at parse | not in read |

The parser also writes **`issuer_cik`** (`ownership.py:124`). It is **not** a silver column: it is absent from `silver_schema.py:424-452` and from the DDL `:603-633`. The Snowflake load copies by column name (`MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE`, `infra/snowflake/sql/bootstrap/13_silver_landing_ingest.sql:110`), so this extra Parquet column is dropped at load. The dbt model gets the issuer `cik` by joining `sec_company_filing` instead. A contract that declares its silver table (map Q7) would make this leak visible.

#### Columns shared by both transaction tables (`_transaction_fields`, `ownership.py:188-200`, plus the per-row fields at `:149-156`, `:166-178`)

| Column | Source path (relative to the transaction) | Transform | Absent | Primitive? |
|---|---|---|---|---|
| accession_number | context | — | — | yes: `context` |
| owner_index | constant `1` `:151,168` | — | — | yes: `const` |
| txn_index | position among kept transactions | ordinal after filter | — | yes: `ordinal` (with a group `filter`) |
| security_title | `securityTitle` | `value` child + `" [F1,F2]"` footnote marker (`:300-311`; test `:364`) | "" | yes: `value_with_footnotes` (or chain `concat(text(value), join(attr(footnoteId/@id)))`) |
| transaction_date | `transactionDate/value` | leading `YYYY-MM-DD` only (`:338-352`; test `:416`) | None | yes: `date_prefix` |
| transaction_code | `transactionCoding/transactionCode` | text | "" | yes: `text` |
| transaction_shares | `transactionAmounts/transactionShares` | all descendant text → float (`:331-335`) | None | yes: `number` |
| transaction_price | `transactionAmounts/transactionPricePerShare` | float | None | yes: `number` |
| acquired_disposed_code | `transactionAmounts/transactionAcquiredDisposedCode` | text | "" | yes: `text` |
| shares_owned_after | `postTransactionAmounts/sharesOwnedFollowingTransaction` | float | None | yes: `number` |
| ownership_direct_indirect | `ownershipNature/directOrIndirectOwnership` | text | "" | yes: `text` |
| ownership_nature | `ownershipNature/natureOfOwnership` | text | "" (test `:387`) | yes: `text` |
| reporting_owner_count | document `count(./reportingOwner)` | copied onto each row | — | yes: `count` |
| parser_version | `"3"` | — | — | yes: `contract_version` |
| last_sync_run_id / mdm_entity_id | engine / MDM backfill (`mdm_entity_backfill.py:120-131`, `entity_type="security"`) | — | — | not in read |

Derivative table only (`ownership.py:171-175`):

| Column | Source path | Transform | Primitive? |
|---|---|---|---|
| conversion_or_exercise_price | `conversionOrExercisePrice/value` | float | yes: `number` |
| exercise_date | `exerciseDate/value` | date prefix | yes: `date_prefix` |
| expiration_date | `expirationDate/value` | date prefix | yes: `date_prefix` |
| underlying_security_title | `underlyingSecurity/underlyingSecurityTitle` | value + footnote marker | yes: `value_with_footnotes` |
| underlying_security_shares | `underlyingSecurity/underlyingSecurityShares/value` | float | yes: `number` |

Silver column totals: non-derivative 16 (14 from the parser); derivative 21 (19 from the parser). **Parser-produced landed columns: 25 + 14 + 19 = 58.**

Findings the contract must be able to express:

1. **Two conventions for reading the same kind of element.** `transaction_shares` and `transaction_price` read *all descendant text* (`_text`, `:194-195`). `conversion_or_exercise_price` reads only the `<value>` child (`_value`, `:171,292-297`). Both give the same result only while `<footnoteId/>` stays an empty element. A contract should use one path form (`…/value`) and pin this with a parse test.
2. **Empty-value conventions differ by type.** Absent text gives `""`, absent numbers and dates give `None`, and `officer_title` gives `None` through `or None` (`:123`). Every primitive therefore needs an explicit `default`.
3. **DDL type conflict.** `owner_index` and `txn_index` are `SMALLINT` in the landing DDL (`11_silver_landing_schema.sql:556-557,583-584,605`). CLAUDE.md's schema rule says count-derived index columns must be BIGINT. A contract-declared silver type should apply that rule.

### A.3 Rule C-J cross-source lookup (item 3)

What the current code does (`warehouse_orchestrator.py:5357-5390`):

- **Key**: the reporting owner's CIK (an int), taken from `rptOwnerCik` (`ownership.py:102,104`).
- **Source**: bronze `submissions_main`, found by glob `submissions/sec/cik=<cik>/main/*/*/*/CIK<cik zero-padded to 10>.json` (`edgar_warehouse/infrastructure/dataset_path_catalog.py:222-228`; test `tests/unit/test_ownership_parse_pipeline_bronze_lookup.py:57-72`).
- **Selection**: the *last* match that `find_existing` returns (`warehouse_orchestrator.py:5019`). This works as "newest" because the date path sorts correctly (test `:57`). It is **not** the snapshot as of the filing date.
- **Return value**: the JSON payload, with the matched object's sha256 added under `_bronze_sha256` (`:5386-5389`; `ownership.py:62`; test `:115`). A missing file, or a payload that is not a dict, gives `None` (`:5382-5384`).
- **Caching**: hits are cached for the run; misses are re-checked every time (`:5370-5373`; test `:75-96`). The parser also memoizes per CIK within one document (`ownership.py:91-98`; test `test_ownership_parser.py:302`).
- **Network**: zero network access, enforced by a socket guard in tests (`test_ownership_parse_pipeline_bronze_lookup.py:19-24`).

What reads the payload:

- (a) **Nine plain field reads** (`ownership.py:216-232`): presence, sha256, 6 scalar fields read with a `""` default, and 1 list length.
- (b) The **`_is_company` classifier** (`:235-258`). It reads `name`, `tickers`, `exchanges`, `stateOfIncorporation`, `entityType`, the first 50 of `filings.recent.form`, `ein`, the two `insiderTransaction*Exists` flags, and the CIK. It passes all of them to edgartools' private `_classify_is_individual`. Its signals are pinned by `test_ownership_parser.py:497-530`.

**Verdict: a generic `lookup` expresses (a) fully, but not (b).** The primitive needs this signature:

```
lookup(source: <bronze artifact family>, key: <column>, key_format: cik10,
       select: newest | as_of(<column>), missing: null)
  → { found: bool, artifact_sha256: str, payload: <json> }
```

Then each of the 9 columns is `get(lookup.payload, path, default="")`, `len(...)`, `lookup.found` or `lookup.artifact_sha256`. Nothing about this signature is specific to SEC.

Three contract points this raises:

1. **"Which snapshot" must be declared.** Today it is `newest`. That makes the output depend on when the run happens: re-parsing the same Form 4 later can change the evidence columns and `owner_name`. This connects to the map's unresolved "Change and replay" item. `as_of(filing_date)` would make it deterministic, but changes today's behaviour.
2. **The lookup reads a second Bronze Artifact family.** So a source's contract depends on another source's bronze layout (the `submissions_main` path). Acceptance checks 1 and 2 (a source folder is self-contained, and deleting it breaks nothing else) need the lookup target named by **artifact family**, not by a raw glob. The runner resolves the family to a path.
3. **Local only.** The lookup must fail closed to `missing` and never fetch, to satisfy acceptance check 4. Today's code already does this.

### A.4 What must be custom, and the smallest boundary (item 4)

| Candidate | Why it cannot be a primitive | Smallest honest boundary |
|---|---|---|
| **`owner_name`** (the only custom column) | It depends on edgartools' private 9-signal classifier `_classify_is_individual` and the display transform `reverse_name` (`ownership.py:41-48`). These must stay byte-identical to edgartools (5,356-artifact equivalence, per CLAUDE.md's ownership note). The classifier is a library policy, not a data rule. | One pure function `owner_display_name(owner_name_raw, owner_cik, lookup.payload) -> str`. Input: 3 values already in the row or the lookup. Output: 1 column. No fetch, write or MDM call. It declares its edgartools version pin. It could be split into `is_company(payload, cik) -> bool` plus `reverse_name(text)`, but that makes a second custom step for no gain. |
| Reader: SEC `.txt` envelope + control-character retry (`ownership.py:261-276`) | This is not a column. It is how the artifact becomes an XML tree. | Better as **reader options** than custom code: `xml(root: ownershipDocument, envelope: between("<XML>","</XML>"), strip_declaration: true, on_error: retry_strip_control_chars, else: empty)`. Mark it custom only if the reader vocabulary stays deliberately small. |
| Group filter "must have child blocks" (`:143-146,160-163`) | Needed before `ordinal`, or `txn_index` changes (test `:554`). | A group-level `filter(require_children: [...])` primitive. Not custom. |

Not custom but worth recording: `value_with_footnotes` is an SEC ownership XML convention. It can be written as a chain, but one named primitive is simpler and SEC's other XML forms will likely reuse it.

---

## Part B — GLEIF Level 1

### B.0 How GLEIF Level 1 is captured and parsed today

- **No production code.** `grep -ril gleif` over `edgar_warehouse/`, `tests/` and `infra/` finds only a docstring in `edgar_warehouse/mdm/clean/source_publications.py:4` ("not a claim that native GLEIF XML is supported") and one synthetic fixture. There is no GLEIF parser, silver table, dbt model or Step Function.
- **Capture (research only).** `.scratch/gleif-company-augmentation/research/01-fetch-gleif-snapshot.py:22-44` streams three Golden Copy **`json.zip`** files: `lei2` (LEI_3.1, 3,428,477 records), `rr` and `repex`. It records their sha256 in `01-gleif-snapshot-manifest.json`. The zips are gitignored (`research/.gitignore`), so no raw Golden Copy file is in the repo.
- **Parse (research only).**
  - `03-04-extract-accepted-gleif.py` streams the one zip member through `unzip -p` (`:103-128`). It splits the pretty-printed `{"records":[…]}` array record by record (`:68-100`) and keeps only records that touch the 308 accepted LEIs (`:64-65,131-161`).
  - Output: `03-accepted-level1-records.jsonl`, **316 records** (`03-04-extract-manifest-level1.json`). This is the only local Level 1 sample.
  - Field extraction is in `02-compare-gleif-identities.py:303-335` (`record_fields`), `:213-241` (names) and `:244-270` (addresses), plus `03-analyze-attribute-lift.py:106-231`.
- **Clean MDM input.** `tests/fixtures/clean_mdm/publication_v1/` is "synthetic … not GLEIF XML" (its `README.md`). `level1.jsonl` rows are `{"key","name"}`. `dataset.json` maps `adapter.identifiers = {"lei": "key"}` and `fields = {"name": "name"}`.
- **Format conflict.** Clean MDM's specs say Level 1 is an **XML ZIP**: `docs/specs/clean-mdm/source-evidence.md:82`, and `docs/specs/clean-mdm/company-completion.md:32` ("Stream bounded XML ZIP processing"). The only artifact ever captured is the **JSON** Golden Copy. The JSON uses a BadgerFish-style mapping: text goes in `"$"` and attributes in `"@name"`. So paths map one-to-one between the two formats, but the Source Contract must name which one is the Bronze Artifact.
- **Which fields are needed.** Ticket 15 (`.scratch/gleif-company-augmentation/issues/15-decide-attribute-survivorship-and-conflicts.md`, "Answer") says to "Preserve the complete Level 1 record at source grain". It also lists the projected fields (`.scratch/gleif-company-augmentation/spec.md:131-137`). Names, addresses, events, expiration and successors are kept as evidence but not projected.

### B.1 Row grain and repeating groups (item 2)

- **Main row grain**: one row per `LEI` per publication. The extractor fails on a duplicate LEI within one file (`03-analyze-attribute-lift.py:99-101`).
- **Repeating groups**: counts below come from a local walk of all 316 extracted records. Each "N/316" is the number of records containing that path.

| Group | Path | Seen in | Shape |
|---|---|---|---|
| Other names | `Entity.OtherEntityNames.OtherEntityName[]` (`$`, `@type`, `@xml:lang`) | 48/316 | list |
| Transliterated names | `Entity.TransliteratedOtherEntityNames.TransliteratedOtherEntityName[]` | 5/316 | list |
| Address extra lines | `Entity.{LegalAddress,HeadquartersAddress}.AdditionalAddressLine[]` | 204 / 127 | list |
| Other addresses | `Entity.OtherAddresses.OtherAddress[]` (`@type`) | 3/316 | list |
| Legal entity events | `Entity.LegalEntityEvents.LegalEntityEvent[]` (`@event_status`, `@group_type`, type, effective/recorded dates, `AffectedFields.AffectedField[]`) | 70/316 | list, nested list |
| Successors | `Entity.SuccessorEntity[]` (`SuccessorLEI` or `SuccessorEntityName`) | 11/316 | list |
| Other validation authorities | `Registration.OtherValidationAuthorities.OtherValidationAuthority[]` | 3/316 | list |
| Geocoding extension | `Extension.gleif:Geocoding` | ~57 as a single **object**, 48 as a **list** | **object or list** |

**Object-or-list values** are the one structural trap. The research code wraps every such value in `as_list` (`02-compare-gleif-identities.py:128-131,219,227,248`). `gleif:Geocoding` actually occurs in both shapes in the sample. So any `each(path)` primitive must treat a single object as a one-item list.

### B.2 Column inventory: *proposed* `gleif_lei_record` (item 1)

No GLEIF silver table exists, so this is the smallest table that matches ticket 15 (keep the whole record, flatten the projected and evidence scalars). The source paths are real: each path was confirmed in the local sample or in the research extractors cited. Absent value: `None` everywhere, using `scalar()`: `"$"` → stripped text, empty → None (`02-compare-gleif-identities.py:119-125`).

| # | Column | Source path (JSON Golden Copy) | Transform | Sample presence | Primitive? |
|---|---|---|---|---|---|
| 1 | lei | `LEI.$` | text | 316 | yes: `text` |
| 2 | legal_name | `Entity.LegalName.$` | text | 316 | yes |
| 3 | legal_name_language | `Entity.LegalName.@xml:lang` | text | 316 | yes |
| 4 | legal_jurisdiction | `Entity.LegalJurisdiction.$` | text (kept raw; normalization is matching logic) | 316 | yes |
| 5 | entity_category | `Entity.EntityCategory.$` | text | 316 | yes |
| 6 | entity_status | `Entity.EntityStatus.$` | text | 316 | yes |
| 7 | entity_creation_date | `Entity.EntityCreationDate.$` | ISO-8601 → timestamp | 255 | yes: `timestamp` |
| 8 | entity_expiration_date | `Entity.EntityExpirationDate.$` (`03-analyze-attribute-lift.py:202-204`) | timestamp | 0 | yes |
| 9 | entity_expiration_reason | `Entity.EntityExpirationReason.$` (`:205`) | text | 0 | yes |
| 10 | legal_form_code | `Entity.LegalForm.EntityLegalFormCode.$` | text | 316 | yes |
| 11 | other_legal_form | `Entity.LegalForm.OtherLegalForm.$` | text | 41 | yes |
| 12 | registration_authority_id | `Entity.RegistrationAuthority.RegistrationAuthorityID.$` | text | 316 | yes |
| 13 | registration_authority_entity_id | `Entity.RegistrationAuthority.RegistrationAuthorityEntityID.$` | text | 294 | yes |
| 14 | registration_status | `Registration.RegistrationStatus.$` | text | 316 | yes |
| 15 | initial_registration_date | `Registration.InitialRegistrationDate.$` | timestamp | 316 | yes |
| 16 | last_update_date | `Registration.LastUpdateDate.$` | timestamp | 316 | yes |
| 17 | next_renewal_date | `Registration.NextRenewalDate.$` | timestamp | 316 | yes |
| 18 | managing_lou | `Registration.ManagingLOU.$` | text | 316 | yes |
| 19 | validation_sources | `Registration.ValidationSources.$` | text | 316 | yes |
| 20 | validation_authority_id | `Registration.ValidationAuthority.ValidationAuthorityID.$` | text | 316 | yes |
| 21 | validation_authority_entity_id | `Registration.ValidationAuthority.ValidationAuthorityEntityID.$` | text | 294 | yes |
| 22 | conformity_flag | `Extension.gleif:conformity.gleif:conformityflag.$` | text | 316 | yes |
| 23 | legal_address_first_line | `Entity.LegalAddress.FirstAddressLine.$` | text | 316 | yes |
| 24 | legal_address_additional_lines | `Entity.LegalAddress.AdditionalAddressLine[].$` | join (object-or-list) | 204 | yes: `join(each)` |
| 25-28 | legal_address_{city,region,country,postal_code} | `Entity.LegalAddress.{City,Region,Country,PostalCode}.$` | text | 316/292/316/315 | yes ×4 |
| 29 | hq_address_first_line | `Entity.HeadquartersAddress.FirstAddressLine.$` | text | 316 | yes |
| 30 | hq_address_additional_lines | `Entity.HeadquartersAddress.AdditionalAddressLine[].$` | join | 127 | yes: `join(each)` |
| 31-34 | hq_address_{city,region,country,postal_code} | `Entity.HeadquartersAddress.{…}.$` | text | 316/297/316/316 | yes ×4 |
| 35 | successor_leis | `Entity.SuccessorEntity[].SuccessorLEI.$` | join | 10 | yes: `join(each)` (or a child table) |
| 36 | raw_record | whole record | canonical JSON (the form `03-04-extract-accepted-gleif.py:24-25` already uses) | 316 | yes: `raw` |
| 37 | publication_key | artifact context (publication time from the manifest) | — | — | yes: `context` |
| 38 | artifact_sha256 | artifact context (`01-gleif-snapshot-manifest.json` `sha256`) | — | — | yes: `context` |
| 39 | contract_version | contract | — | — | yes: `contract_version` |

Proposed child tables. Each is keyed by `(lei, publication_key, ordinal)` and every column is `text`, `attr`, `timestamp` or `ordinal`, so all are primitive:

- `gleif_lei_other_name` (`$`, `@type`, `@xml:lang`, plus a `transliterated` bool constant per source group)
- `gleif_lei_other_address`
- `gleif_lei_event` (with `AffectedField[]` joined)
- `gleif_lei_successor`
- `gleif_lei_other_validation_authority`
- optionally `gleif_lei_geocoding`, the object-or-list group

Alternatively, all of these stay inside `raw_record` until something consumes them. That is closer to ticket 15's "retained as source evidence, not projected".

Kept out of the read step on purpose: `normalize_text`, `suffix_normalize`, `normalize_postal`, `normalize_region` and `LEGAL_SUFFIXES` (`02-compare-gleif-identities.py:35,134-189`). They exist for *matching* against SEC, which belongs to the Mastering Policy map, not to parsing.

Connection to the Dataset Contract: Clean MDM's `value()` walks dotted paths through dicts only and returns `None` at a list (`edgar_warehouse/mdm/clean/adapters.py:33-39`). So the unchanged `adapter` block (map Q8) can reach `LEI.$` directly, but **cannot reach any repeating group**. The flat silver table above is what makes the adapter usable without changing Clean MDM.

### B.3 Cross-source lookups and custom steps (items 3-4)

- **Level 1 needs no cross-source lookup.** `RelationshipRecord` (RR) and `REPEX` records point to Level 1 by LEI. If they get their own contracts, that is a join in the Dataset or Mastering layer, not a parse-time lookup. Research extracted them separately (`03-04-extract-accepted-gleif.py:196-205`).
- **No column-level custom step.** The only non-trivial pieces are in the reader:
  - (a) a zip with exactly one member (`03-04-extract-accepted-gleif.py:104-108`);
  - (b) a streamed top-level JSON array under a wrapper key (`records` / `relations` / `exceptions`), because `lei2` is about 927 MB compressed and must not be loaded whole;
  - (c) object-or-list normalization.

  All three are generic reader or `each` options (`zip(single_member)`, `json_array(stream, wrapper)`, `each(…, object_as_list)`). The research splitter's line-based approach (`:68-100`) depends on GLEIF's pretty-printing. A real reader should use a proper streaming JSON parser. That is an engine concern, not a contract one.

---

## Part C — Draft primitive list with coverage (item 5)

The counts are the **58** parser-produced Form 3/4/5 columns and the **39** proposed GLEIF main-table columns. Group-level operations (`filter`, `each`) and reader options sit outside the column counts.

| Primitive | Meaning | Form 3/4/5 cols | GLEIF cols |
|---|---|---|---|
| `context(name)` | artifact or run value (accession, publication key, artifact sha256) | 3 | 2 |
| `contract_version` | the contract's parser version | 3 | 1 |
| `const(v)` | literal | 2 | 0 |
| `ordinal(group)` | 1-based position in a repeating group (after `filter`) | 3 | 0 (child tables only) |
| `count(group)` | size of a document-level group, copied to child rows | 2 | 0 |
| `text(path, default)` | stripped descendant text / JSON `"$"` / `@attr` | 11 | 27 |
| `int(path)` | numeric text → int, else null | 1 | 0 |
| `flag(path, true_set)` | text ∈ true_set | 5 | 0 |
| `number(path)` | text → float, else null | 8 | 0 |
| `date_prefix(path)` | leading `YYYY-MM-DD`, else null | 4 | 0 |
| `timestamp(path)` | ISO-8601 → timestamp | 0 | 5 |
| `value_with_footnotes(path)` | SEC ownership `value` + `[F…]` marker | 3 | 0 |
| string chain (`upper`, `strip_spaces`, `starts_with`, `contains_ci`, `when`, `empty_to_null`) | small pure string ops | 2 (`address_is_care_of`, `officer_title`) | 0 |
| `join(each(group), template, sep)` | aggregate a repeating group into one string | 1 | 3 |
| `raw` | canonical JSON of the whole record | 0 | 1 |
| `lookup(source, key, key_format, select, missing)` + `get` / `len` / `.found` / `.artifact_sha256` | read another bronze family by key, local only | 9 | 0 |
| **custom step** | declared, versioned, pure, lives in the source folder | **1** (`owner_name`) | **0** |
| **Total** | | **58** | **39** |

Group-level operations and reader options (not columns):

- `each(path, object_as_list)`
- `filter(require_children)`
- reader `xml(root, envelope, strip_declaration, on_error)`
- reader `zip(single_member)` and `json_array(stream, wrapper)`

**Custom fraction (acceptance check 11):**

| Source | With `lookup` as a primitive | Without `lookup` |
|---|---|---|
| Form 3/4/5 | 1/58 = **1.7%** | 10/58 = **17.2%** |
| GLEIF Level 1 (proposed) | 0/39 = **0%** | 0/39 = **0%** |

Also excluded from the read step on both sides: engine stamps (`last_sync_run_id`, `parse_sequence`) and MDM write-backs (`mdm_entity_id`). These are six Form 3/4/5 silver columns plus the DDL's `parse_sequence`. The contract's `silver` section should mark such columns as *engine-owned*, so the read step is not asked to produce them.

## Open points for the next tickets

1. **Snapshot selection for `lookup`**: keep `newest` (today's behaviour, depends on when the run happens) or switch to `as_of(filing_date)` (deterministic replay). This connects to the map's "Change and replay" item.
2. **GLEIF Bronze Artifact format**: XML ZIP (Clean MDM specs) or JSON ZIP (the only artifact captured so far). Paths map one-to-one, but the contract must name one.
3. **Whether `value_with_footnotes` becomes a named primitive** or stays a documented chain.
4. **The `issuer_cik` leak** (`ownership.py:124`, not a silver column) and **SMALLINT index columns** in the ownership DDL. A contract-declared silver table would catch both. Record them here; do not fix them in this map (retrofits are out of scope).
