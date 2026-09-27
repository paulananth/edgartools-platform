# Rules log: onboarding the GLEIF source (trial round 3, Phase A)

Sandbox: trials/round-3/gleif. Skill: repo/skills/rules/SKILL.md + REFERENCE.md.
Provenance tags used below: [files] = profile of inputs/, [code] = repo code,
[docs] = repo docs, [web] = public documentation, [assumption] = my guess.

## Step 1: Identify

- Inputs: three ZIPs, each one JSON member [files]:
  - `01-20260911-1600-gleif-goldencopy-lei2-golden-copy.json.zip` (927.6 MB zipped, 13.25 GB expanded), wrapper `{"records":[...]}`, LEI-CDF records.
  - `01-20260911-1600-gleif-goldencopy-rr-golden-copy.json.zip` (35.0 MB, 1.12 GB expanded), wrapper `{"relations":[...]}`, RR-CDF relationship records.
  - `01-20260911-1600-gleif-goldencopy-repex-golden-copy.json.zip` (63.7 MB, 1.55 GB expanded), wrapper `{"exceptions":[...]}`, reporting exceptions.
- Named as: GLEIF (Global Legal Entity Identifier Foundation) Golden Copy, publication 2026-09-11 16:00 UTC, full files, JSON: Level 1 (LEI-CDF), Level 2 relationships (RR-CDF), Level 2 reporting exceptions (REPEX). [files: names + wrappers]
- Not new. The repo already names it [code]:
  - reader: `edgar_warehouse/mdm/clean/gleif_source.py` (`dataset_contract` loads `rules_files.source("gleif")`, so the folder name is fixed: `rules/sources/gleif/`; its docstring says the mapping lives in `rules/sources/gleif/source.yaml`, "rules skill ticket 01").
  - source code `gleif.level1.v1` in `rules/merge/kinds/company.yaml` (`defaults.sources`, and the `source` of both SEC-to-GLEIF name rules).
  - `docs/specs/clean-mdm/source-evidence.md:84` names `gleif.reporting_exception` (a spec name, not code).
- The rules file `rules/sources/gleif/source.yaml` is missing, so per the skill: every step, full profile, keep the repo's names.
- `edgar-warehouse rules status` (to tell whether the source code is registered): NOT BUILT. Question for the operator.

## Missing commands (as reached)

- `edgar-warehouse rules status`: NOT BUILT (`edgar-warehouse rules --help` -> "invalid choice: 'rules'"; there is no `rules` subcommand at all). Step 1 says ask instead.
- `edgar-warehouse rules profile <files>`: NOT BUILT (same). Step 2's fallback used: a streaming script in scratch/.

## Step 2: Profile

Scripts: `scratch/profile_sample.py` (bounded sample: 3,000 records from the start, 3,000 from the byte middle, 3,000 from the end of each file, parsed with json), `scratch/full_counts.py` (full passes, only for counts that decide something), `scratch/bad_leis.py` (line-based LEI check-digit pass). Outputs: `scratch/profile-{l1,rr,repex}.json`, `scratch/full-{l1,rr,repex}.json`, `scratch/bad-{l1,repex}.json`, `scratch/sha256.txt`.

Method notes [files]:
- The members are pretty-printed JSON: a record opens with a line that is exactly `{` and closes with `},` / `}` / `}]}` at column 0. Records were split on that layout and each parsed with json. The line split's counts equal the JSON passes (L1 3,428,477; RR 487,721; REPEX 6,351,397), and the line-based check-digit pass equals the JSON pass (L1 256 bad = 256; RR endpoints 975,442 = 2 x 487,721 with 1 bad = 1).
- A ZIP member is one deflate stream: it cannot be seeked, so "a sample from the middle and the end" still costs decompressing the whole member (L1: 13.25 GB, ~11 min per pass here). Python `zipfile` inflates ~490 MB/s; `unzip -p` was ~20 MB/s. Timed on the sample first: json for 9,000 L1 records 1.1 s, so the full L1 JSON pass (694 s) was predicted.
- The JSON files carry no header: no ContentDate, FileContent or RecordCount. The reader (`gleif_source.validate_metadata`) needs those from a publication manifest; only the record count is derivable from the file (by a full pass).
- sha256 of the L1 zip = `1b6cd9cd...a36a6a`, the same `gleif_golden_copy_sha256` pinned in `rules/merge/pending-proofs.yaml` for the ticket 08 name-rule proofs [files + repo]. RR `089a2513...`, REPEX `f205fd8d...`.

### Level 1 (`lei2`, wrapper `records`), 3,428,477 records, 13.25 GB
- Record key: `LEI.$`, always filled, unique (3,428,477 distinct) [full pass].
- LEI check (regex `[A-Z0-9]{18}[0-9]{2}` + ISO 7064 mod 97 = 1, as `adapters._lei`): **256 fail** (e.g. `0292001629A3Q7XJ0D13`, `315700RY02YIDMWGWY53`, many `391200...`) [full pass]. The reader formats the LEI before its scope check, so each is `invalid_lei_checksum`, a blocking defect, whatever the approved scope.
- `Entity.EntityCategory.$` always filled [full]: GENERAL 3,043,262; FUND 248,988; SOLE_PROPRIETOR 127,272; RESIDENT_GOVERNMENT_ENTITY 6,955; BRANCH 1,913; INTERNATIONAL_ORGANIZATION 87. All six are in the reader's accepted set; no record lacks a category (LEI-CDF 3.1 makes it optional [web]).
- `Entity.EntitySubCategory.$` only on RESIDENT_GOVERNMENT_ENTITY (CENTRAL/STATE/LOCAL_GOVERNMENT, SOCIAL_SECURITY) [full].
- `Entity.EntityStatus.$`: ACTIVE / INACTIVE / NULL (NULL: 9,062 records, the text "NULL") [full].
- `Registration.RegistrationStatus.$`: ISSUED 1,969,108; LAPSED 1,197,761; RETIRED 252,467; DUPLICATE 6,491; ANNULLED 1,708; PENDING_TRANSFER 590; PENDING_ARCHIVAL 352 [full]. The file is every LEI ever published, not only live ones [files + web].
- Names: `Entity.LegalName.$` (always, text; `@xml:lang`); `Entity.OtherEntityNames.OtherEntityName[]` (`@type` PREVIOUS_LEGAL_NAME / TRADING_OR_OPERATING_NAME / ALTERNATIVE_LANGUAGE_LEGAL_NAME), `Entity.TransliteratedOtherEntityNames...` (AUTO_/PREFERRED_ASCII_TRANSLITERATED_LEGAL_NAME). Organisation-shaped; SOLE_PROPRIETOR records are person-shaped by definition [sample].
- Addresses: `Entity.LegalAddress` and `Entity.HeadquartersAddress`, each with FirstAddressLine, AdditionalAddressLine[] (list of `{"$": line}`), AddressNumber, AddressNumberWithinBuilding, MailRouting, City, Region (ISO 3166-2, e.g. `US-MA`), Country (ISO 3166-1), PostalCode. HQ postcode missing on 44,101, legal on 44,654 [full]. Plus OtherAddresses[] and TransliteratedOtherAddresses[] (typed) [sample].
- `Entity.LegalJurisdiction.$`: ISO country `US` (3,052,029) or subdivision `US-DE` (376,444 with `-`), 4 records have none [full].
- `Entity.LegalForm.EntityLegalFormCode.$`: ISO 20275 ELF code, or **placeholder `8888`** (327,578 records) meaning "no ELF code; see OtherLegalForm" (`Entity.LegalForm.OtherLegalForm.$`, free text) [full + web]. Logged as a placeholder the contract cannot turn into unknown.
- `Entity.EntityCreationDate.$` (~67% filled), `Entity.SuccessorEntity[]` (SuccessorLEI, SuccessorEntityName; 51,913 records), `Entity.LegalEntityEvents.LegalEntityEvent[]` (712,867 records; type, status, effective/recorded dates, affected fields) [full + sample]. No `AssociatedEntity`, no `EntityExpirationDate` in this file [full/sample].
- Registration: InitialRegistrationDate, LastUpdateDate (always, always with a timezone [full]), NextRenewalDate, ManagingLOU (an LEI, all pass [full]), ValidationSources (201 missing [full]), ValidationAuthority (ValidationAuthorityID RA code, ValidationAuthorityEntityID, OtherValidationAuthorityID), OtherValidationAuthorities[].
- Registration authority: `Entity.RegistrationAuthority.RegistrationAuthorityID.$` (RA code; `RA999999` = none available, 267,984 records; `RA888888` temporary [web: GLEIF RA list v1.8.1, `scratch/ra-list.csv`]) and `RegistrationAuthorityEntityID.$` (the entity's id in that register), `OtherRegistrationAuthorityID.$` (free text).
  - `RA000665` = SEC EDGAR [web: RA list]. 27,933 records carry it, 27,545 of them FUND. Their entity ids are shaped `S000005113` (SEC series id: 22,940), plain digits (a CIK: 4,981) or `999-9999999999` (12, an SEC file number shape) [full]. So GLEIF states SEC-issued ids, only some of them CIKs.
- Extension (always present; GLEIF and LOU namespaces) [full + sample]: `gleif:conformity.gleif:conformityflag` (CONFORMING / NON_CONFORMING / NOT_APPLICABLE; where LEI-CDF 3.1's ConformityFlag actually sits in this file), `gleif:Geocoding` (object or list: lat/lng, formatted address, match level), `ext:CIF` (Spanish tax id, at least 157,176 records: counted from a truncated top-N list), `leifr:SIREN` (French company id, at least 134,648 records, same caveat), `leifr:EconomicActivity` (NACE, NAF), `leifr:LegalFormCodification`, `leifr:FundNumber`, `leifr:FundManagerBusinessRegisterID`.
- Dates mix `...000Z` and `+02:00` offsets; all LastUpdateDate values carry a zone [full].

### Relationships (`rr`, wrapper `relations`), 487,721 records, 1.12 GB
- Shape: `RelationshipRecord.Relationship.{StartNode, EndNode, RelationshipType, RelationshipPeriods, RelationshipStatus, RelationshipQualifiers, RelationshipQuantifiers}`, `RelationshipRecord.Registration.{InitialRegistrationDate, LastUpdateDate, RegistrationStatus, NextRenewalDate, ManagingLOU, ValidationSources, ValidationDocuments, ValidationReference}` [sample]. No Extension anywhere [full].
- No record id. Candidate key (start LEI, end LEI, type): always filled, **unique** over the whole file (487,721 distinct) [full].
- Both node types are always `LEI` [full]. Check digits: 1 start node fails (`4469000001BG7ASKSB18`), blocking as the reader checks format first [full].
- Types [full]: IS_FUND-MANAGED_BY 150,982; IS_ULTIMATELY_CONSOLIDATED_BY 132,877; IS_DIRECTLY_CONSOLIDATED_BY 126,688; IS_SUBFUND_OF 73,834; IS_INTERNATIONAL_BRANCH_OF 1,959; IS_FEEDER_TO 1,381. All six are in `relationships.CONTRACTS` [code].
- RelationshipStatus: ACTIVE, INACTIVE (60), and the text `NULL` (345) [full]. The reader accepts only ACTIVE/INACTIVE, so NULL becomes `invalid_relationship_status_interval` (blocking) for in-scope pairs.
- Periods: a single object or a list with PeriodType RELATIONSHIP_PERIOD / ACCOUNTING_PERIOD / DOCUMENT_FILING_PERIOD. Exactly one RELATIONSHIP_PERIOD on 487,646; **none on 75** (the reader: `ambiguous_relationship_period`, blocking); 216 have a relationship period with no StartDate (reader: `invalid_relationship_interval`, blocking); 23 have an EndDate; 1 INACTIVE has no end; 16 ACTIVE have an end [full].
- Qualifiers: ACCOUNTING_STANDARD = IFRS / US_GAAP / OTHER_ACCOUNTING_STANDARD / GOVERNMENT_ACCOUNTING_STANDARD / absent. Quantifiers: ACCOUNTING_CONSOLIDATION, PERCENTAGE (e.g. `100.00`) [full].
- No active IS_DIRECTLY_CONSOLIDATED_BY start has two parents [full].
- `Registration.ValidationReference.$` holds URLs, some on sec.gov (not followed).

### Reporting exceptions (`repex`, wrapper `exceptions`), 6,351,397 records, 1.55 GB
- Shape: `LEI.$`, `ExceptionCategory.$`, `ExceptionReason[]` (list of `{"$"}`; 1 to 8 reasons), optional `ExceptionReference[]` (free text, 2,921), optional `Extension` [full].
- Key (LEI, category): unique (6,351,397 distinct; 3,188,712 LEIs) [full].
- Categories: DIRECT_ / ULTIMATE_ACCOUNTING_CONSOLIDATION_PARENT. Reasons: NATURAL_PERSONS, NON_CONSOLIDATING, NO_KNOWN_PERSON, NO_LEI, NON_PUBLIC, and the deprecated five; all in the reader's `EXCEPTION_REASONS` [full].
- **257,509 records carry `Extension: {"gleif:Deletion": null}`** in this full file [full]: an exception GLEIF marks deleted. A third-party page describes it as the delta-file deletion marker [web, third party: hint only]. The reader ignores it (every exception is set aside as `reported_parent_exception` anyway, so today it changes no record, but the retained evidence does not say "withdrawn").
- LEI check digits: **99 fail** (e.g. `5555001H4ERZCCQJRL13`, `555500C1020111000029`) [line-based full pass]. Blocking (checked before scope).

### Placeholders the contract cannot turn into unknown (logged per the skill)
- `8888` in `EntityLegalFormCode` (no ELF code).
- The text `NULL` in `EntityStatus` and in `RelationshipStatus`.
- `RA999999` (no registration authority) and `RA888888` (temporary) in RegistrationAuthorityID / ValidationAuthorityID.
- `"gleif:Deletion": null` in REPEX Extension (a marker, not a value).

### Records in the reader's shape [code: `gleif_source.record_evidence` lines 405-448; built by hand in `scratch/reader_shape.py`, output `scratch/reader-shape.json`]
- Level 1 and REPEX: the reader passes the native record unchanged plus `_native` (a second copy of it), so contract paths are native paths (`LEI.$`, `Entity.LegalName.$`, ...).
- RR: the reader reshapes to `{start, end, relationship_type, valid_from, valid_to, status, registration_status, _native}`, with `valid_from`/`valid_to` rewritten to UTC ISO (`2012-11-29T00:00:00+00:00`). Contract paths for RR run over this dict, not the raw file. Example: `{"start": "5493008RP59ZQ3UQ1882", "end": "549300JUF07L8VF02M60", "relationship_type": "IS_DIRECTLY_CONSOLIDATED_BY", "valid_from": "2020-12-17T00:00:00+00:00", "valid_to": null, "status": "ACTIVE", "registration_status": "PUBLISHED"}`.
- The reader keeps nothing else from RR: accounting standard (qualifier), consolidation percentage (quantifier), InitialRegistrationDate, ManagingLOU, ValidationSources/Documents/Reference stay only inside `_native`. Mapping them needs a reader change (not a rules-file change).
- REPEX never reaches `normalize`: every exception that passes validation is set aside as `reported_parent_exception` (line 494).

## Step 3: Research

Repo code [code]:
- Reader: `edgar_warehouse/mdm/clean/gleif_source.py`, run through `native_consumption.prepare_native` by `edgar-warehouse mdm mastering --model clean --manifest <native manifest> --run-id <id>` (`clean/cli.py`, needs MDM_DATABASE_URL, BOOKKEEPING_DATABASE_URL, CHANGE_LEDGER_DATABASE_URL, MDM_SOURCE_ARTIFACT_ROOT and registered datasets). Also read by `edgar-warehouse mdm name-census` (`name_census.py`).
- Fixed by the reader (not questions): folder `rules/sources/gleif/`; one `mdm` entry per member with `adapter.native_member` in {level1, relationships, reporting_exceptions}; `adapter.version` = `schema_version` = `gleif-native-record-v1` (`native_consumption.py:164-172`); no `classification` (line 401); contract `family` must equal the publication's `source_family`; `publication_family` must be `golden_copy` (`validate_release`); a release must carry all three members with three distinct source codes (`validate_release`); every record of the publication must be accounted for (`prepare_native` coverage check); the approved Company scope is a list of LEIs in the dataset's `native_contract.company_leis`, outside the rules file.
- Deferral reasons the reader can emit: `outside_approved_company_scope`, `invalid_identity_kind`, `unsupported_relationship_endpoint`, `ambiguous_relationship_period`, `invalid_relationship_interval`, `invalid_relationship_status_interval`, `unsupported_exception_category`, `missing_exception_reason`, `invalid_exception_reason`, `reported_parent_exception`, `invalid_native_field`; plus from `adapters.normalize`: `unsupported_identity_kind`, `invalid_lei`, `invalid_lei_checksum`, `missing_record_identity`, `invalid_field_shape`, `invalid_field_mapping`, `unsupported_relationship_type`.
- Reader gap: the LEI is check-digit-tested BEFORE the scope test (lines 409-417, 450-451), so a bad LEI blocks even when the record is outside the approved scope. With whole-publication accounting, every full Golden Copy load then carries 356 blocking records (256 L1 + 1 RR + 99 REPEX) [files + code].
- Reader gap: `gleif:Deletion` on REPEX is not read [files + code].
- Fixed by the merge rules and matching code: `gleif.level1.v1` is a Company source (`company.yaml defaults.sources`, second after SEC, so SEC wins every shared field). The SEC-to-GLEIF name rules read, on the GLEIF record: identifier `lei`; fields `name`, `jurisdiction`, `gleif_last_update` (must equal the census's raw `Registration.LastUpdateDate.$` string), `gleif_entity_status`, `gleif_registration_status`; `matching.headquarters_postal_code`, `matching.headquarters_country`; and `kind == company` (`matching.py`, `company.yaml`). `matching.py:109` says the contract admits only GENERAL as a Company.
- Company fields (`store.COMPANY_NAMED_FIELDS`): name, sic, sic_description, state_of_incorporation, fiscal_year_end, description, jurisdiction, address, gleif_legal_form, gleif_entity_status, gleif_registration_status, gleif_initial_registration, gleif_last_update, gleif_next_renewal, gleif_managing_lou, gleif_validation_source, gleif_registration_authority, gleif_registration_authority_entity_id, gleif_entity_creation_date.
- Kinds (`evidence.KINDS`): company, person, security, fund_structure, branch, government, international_organization, venue. Relationship contracts (`relationships.CONTRACTS`) already name all six GLEIF RR types, with profile requirements (fund links need `fund` profiles).
- No binding-family rule exists in `company.yaml`: GLEIF records bind only through the two name rules, both declared but inactive (`pending-proofs.yaml`: approved_by null). An RR record has its own subject (`subject_key(rr_code, key)`), so no RR edge can project yet: it would review as `unresolved_endpoint` (`relationships.project`).
- A source whose records are `company` must be in `defaults.sources` or its batch fails (`merge.check_company_sources`).

Repo docs [docs]:
- `docs/specs/mdm/policy-language.md` (~l.286): GLEIF kind table: `FUND -> fund_structure`, `BRANCH -> branch`, `RESIDENT_GOVERNMENT_ENTITY -> government`, `INTERNATIONAL_ORGANIZATION -> international_organization`, `SOLE_PROPRIETOR` left unnamed. With `matching.py:109`: `kind_values: {GENERAL: company}`. Not a question.
- `docs/specs/clean-mdm/company-completion.md` (2026-09-19): project LEI/link status, legal form/jurisdiction, entity/registration status, registration dates/authority, managing LOU, validation source, creation date; "initially retain GLEIF names, addresses, legal events, expiration and successor LEIs as separate source evidence". Later decisions disagree for `name`: the name rules (2026-09-25, `company.yaml`) read GLEIF's `name` field, so name is a field. Per the hard rule the later operator decision wins; both cited. For `address` no later decision exists: question.
- `docs/specs/clean-mdm/company-policy.md` Q1 (2026-09-19): Company scope = SEC universe plus approved GLEIF-only parents; not all of GLEIF. Q7: unsupported kinds remain evidence.
- `docs/specs/clean-mdm/source-evidence.md` (2026-09-19) proposes codes `gleif.lei`, `gleif.relationship`, `gleif.reporting_exception`. The later `company.yaml` (company-2026-09-25.13) and the reader use `gleif.level1.v1`, so for Level 1 the later name wins (both cited). For RR and REPEX nothing later names a code: question.
- `CONTEXT.md`: Accounting Direct Parent (GLEIF RR is the evidence; a missing parent is not proof of none), GLEIF Fund Link (IS_FUND-MANAGED_BY, IS_SUBFUND_OF, IS_FEEDER_TO, keep GLEIF's direction), IS_INTERNATIONAL_BRANCH_OF (Branch to head office). `company-completion.md` delivery boundary: no Fund/Person integration before the Company gate passes.
- Referenced but absent in this repo copy: `docs/specs/clean-mdm/native-gleif.md`, every `.scratch/...` link (e.g. `gleif-company-augmentation/issues/15-...`).
- No bronze family name for GLEIF exists anywhere in the repo (no acquisition registry entry): question.

Public docs [web; gleif.org documentation pages and the GLEIF RA code list CSV only; no data API, no sec.gov]:
- Golden Copy: three publications a day; full files hold every LEI ever published (current and historical), each once; delta files (8 h, 24 h, 7 d, 31 d) hold changes only. Formats XML/CSV/JSON. Level 1 LEI-CDF 3.1, RR-CDF 2.1, Reporting Exceptions 2.1 (www.gleif.org/en/lei-data/gleif-golden-copy).
- LEI-CDF 3.1: EntityCategory optional (this file always fills it), EntitySubCategory for government entities, EntityStatus ACTIVE/INACTIVE/NULL (lei-cdf_version_3.1-documentation.html; summarised by a fetch tool, so enumerations were taken from the files where they differed).
- REPEX 2.1: two categories, ten reasons (five deprecated).
- RA list v1.8.1: `RA000665` = SEC EDGAR; `RA999999` = none available; `RA888888` temporary.
- `gleif:Deletion` meaning: third-party GitHub issues only (hint, not authority).

## Step 4: Infer

Level 1, source code `gleif.level1.v1` (fixed [code]):
- Kind: `kind_field: Entity.EntityCategory.$`, `kind_values: {GENERAL: company}`, `probable_kind_values` as policy-language.md [docs + code]. Not a question.
- Record key: `[LEI.$]`, format `lei` [files + code].
- Identifiers: `lei: LEI.$` (format `lei`). Others carried: see the identifier question [files].
- Fields (fixed by matching/merge code): `name: Entity.LegalName.$`, `jurisdiction: Entity.LegalJurisdiction.$`, `gleif_last_update: Registration.LastUpdateDate.$`, `gleif_entity_status: Entity.EntityStatus.$`, `gleif_registration_status: Registration.RegistrationStatus.$` [code]. Named Company fields with one obvious path [code + files]: `gleif_initial_registration: Registration.InitialRegistrationDate.$`, `gleif_next_renewal: Registration.NextRenewalDate.$`, `gleif_managing_lou: Registration.ManagingLOU.$`, `gleif_validation_source: Registration.ValidationSources.$`, `gleif_registration_authority: Entity.RegistrationAuthority.RegistrationAuthorityID.$`, `gleif_registration_authority_entity_id: Entity.RegistrationAuthority.RegistrationAuthorityEntityID.$`, `gleif_entity_creation_date: Entity.EntityCreationDate.$`, `gleif_legal_form: Entity.LegalForm.EntityLegalFormCode.$` (8888 placeholder: question). `address`: question.
- Matching: `headquarters_postal_code: Entity.HeadquartersAddress.PostalCode.$`, `headquarters_country: Entity.HeadquartersAddress.Country.$` [code].
- Provenance: `native_record: _native` [code]; the file hash, member and locator travel as occurrences, not in the row.
- Relationships: none on Level 1 (SuccessorEntity is a list; not reachable by a dotted path).
- Publication: `semantics: patch`; `completeness`: full Golden Copy, every LEI ever published, content 2026-09-11 16:00 UTC; `effective_time`: Registration.LastUpdateDate (the reader sets it) [code + web]. `publication_families: [golden_copy]` [code].
- Non-blocking: `outside_approved_company_scope`, `unsupported_identity_kind` (FUND, BRANCH, SOLE_PROPRIETOR, government, international organisation: kinds MDM does not take from GLEIF yet). Everything else blocks, incl. `invalid_lei_checksum` [skill rule].

Relationships (`rr`), code: question:
- Kind: the start node's kind lives in the Level 1 file ("a kind taken from a record in another file": not expressible, REFERENCE). The reader admits only pairs whose both LEIs are in the Company scope, so `kind: company` [assumption from code], which requires the code in `company.yaml defaults.sources` (merge-rule change: question).
- Record key: `[start, relationship_type, end]` (unique over the file [files]), format none (composite). Identifier `lei: start` (format lei), so a future LEI binding rule could attach the record to the start Company [assumption].
- Relationship: `type_field: relationship_type`, `type_values` per scope question; `target_key: [end]`; `target_source: gleif.level1.v1` [code]; `valid_from: valid_from`, `valid_to: valid_to`; properties `source_status: status`, `source_registration_status: registration_status`; `scope`: fixed text per type (e.g. `gleif-accounting-consolidation`) [assumption].
- Non-blocking: `outside_approved_company_scope`; `unsupported_relationship_type` for types scoped out. Blocking (in scope only): 75 no-period, 216 no-start, 345 `NULL` status + 1 INACTIVE-without-end, 1 bad LEI (any scope).

Reporting exceptions (`repex`), code: question:
- Record key `[LEI.$, ExceptionCategory.$]` (unique [files]); every valid record is set aside as `reported_parent_exception` by the reader, which should be non-blocking (expected, explained: retained evidence, not a defect) [code + docs]. Also `outside_approved_company_scope` non-blocking. 99 bad LEIs block.
- Kind: never used by the reader for REPEX; the contract still needs one for `normalize` shape checks at registration [assumption]: `company`.

Not expressible in the rules file (logged per REFERENCE):
- the approved Company LEI scope (`native_contract.company_leis`) and the three-member release;
- RR kind from the Level 1 file;
- a list element by path (`SuccessorEntity[]`, `OtherValidationAuthorities[]`, `LegalEntityEvent[]`, OtherEntityNames);
- a conditional identifier (RA entity id is SEC-issued only when RA = RA000665), whose values mix CIKs, series ids and file numbers, so `sec_cik` format cannot apply;
- source placeholders `8888`, `NULL`, `RA999999`, `RA888888`;
- the REPEX deletion marker.

## Step 5: Questions asked (answers pending, Phase B)

See the numbered list in the reply. Nothing answered yet; nothing approved.

## Guesses made
- RR and REPEX `kind: company` (from the reader's scope rule; not stated anywhere).
- RR identifier `lei: start`, record key order, relationship `scope` texts.
- REPEX `gleif:Deletion` meaning (third-party hint only).

## Trial-rule disclosures
- Once, in the command that printed the L1 full counts, I ran bare `python3 -c "0"` (a no-op typed by mistake). Rule 2 forbids system `python3`; nothing else ran that way.
- The harness saved two things outside the sandbox that I did not read: the GLEIF Golden Copy spec PDF from one WebFetch, and a 31 KB tool output (L1 path listing), which I regenerated into `scratch/profile-l1.txt` instead.
- Network: only gleif.org documentation pages, one GLEIF web search set, and the RA code list CSV (`curl` into scratch/). No GLEIF data API, no SEC domain.

## Skill gaps found (for the skill's authors)
- The whole `edgar-warehouse rules` subcommand is absent: `rules status`, `rules profile`, `rules check`, `rules run --preview/--deploy`, `rules activate`, `rules init`, `rules migrate`. Reached so far: status, profile.
- "A sample from the start, the middle and the end" does not say that a ZIP member is one deflate stream: reaching the middle and end means inflating the whole member (13.25 GB here, ~11 min). Say so, and recommend Python `zipfile` over `unzip -p` (25x faster here).
- The rule "a defect always blocks" meets a reader that checks the LEI before the scope test: 356 out-of-scope source records block every full load. The skill has no advice for a defect the source publishes and the reader refuses before scope.
- "Do not ask what a field the merge rules already rank for this source means": `company.yaml` ranks sources per kind (`defaults.sources`), not per field, so every Company field counts as ranked for GLEIF. The sentence needs "per field" or an example.
- REFERENCE's `provenance` guidance ("every trace field the reader attaches: file hashes, run ids") does not fit a native reader: this one attaches only `_native`; hashes travel as occurrences.
- REFERENCE's folder rule `<provider>.<dataset>` versus a reader that fixes `gleif` (one folder, three datasets). Fine by "keep the reader's name", but the example suggests one dataset per folder.
- Step 3 points at docs the repo copy lacks (`native-gleif.md`, `.scratch/...`).
- The skill gives no way to name the bronze `family` when the repo has none.

---
# PHASE B

## Operator answers (source: operator, relayed by the coordinator, Phase B message, 2026-09-27)

1. Files: confirmed full Golden Copy L1 / RR / REPEX, 2026-09-11 16:00 UTC. Nothing registered; treat as new; keep every name the code fixes.
2. Source codes: `gleif.relationships.v1`, `gleif.reporting_exceptions.v1` beside `gleif.level1.v1`. One contract per file; NO fourth publication-level contract (no place in `rules/` today): logged as a gap below.
3. Capture family: one family `gleif` for all three (named like the rules folder). Publication family stays `golden_copy` (reader requires it).
4. RR types: map only IS_DIRECTLY_CONSOLIDATED_BY and IS_ULTIMATELY_CONSOLIDATED_BY. Branch and the three fund types stay captured evidence, unmapped (GLEIF decision: Fund and Branch wait).
5. Merge rules: no change this trial (needs its own approval). Log the change I would make and the code that needs it.
6. Non-blocking, on all three contracts: outside the approved Company scope; a kind MDM does not take yet; valid reporting exceptions. Everything else blocks.
7. The 356 bad check digits: keep blocking. Reader order fix (scope before check digit) is a separate code ticket.
8. The ~640 RR source-gap records: keep blocking; reader fixes in the same code ticket.
9. Address: GLEIF LEGAL address -> Company `address` (operator decision 2026-09-24: SEC business address and GLEIF legal address are each one structured value in the one `address` field, SEC first). HQ postcode and country go to `matching` only. This overrides my Phase A recommendation (HQ); the later operator decision wins.
10. Legal form: map the code as written; log `8888`; no field for free-text legal form.
11. Identifiers: RA code and RA entity id stay the existing Company fields (`gleif_registration_authority`, `gleif_registration_authority_entity_id`), not identifiers. Managing LOU stays its field. Map none of: validation-authority id, Spanish CIF, French SIREN, fund numbers, fund-manager id, successor LEIs. Whether GLEIF's other entity ids become lookup-only identifiers is an OPEN operator question.
12. Start LEI as `lei` on RR records: not decided; do not add. OPEN design question.

## Decisions I derived from the answers (flag for the operator)
- Answer 6 names three business reasons; the code has four reason strings for them. I mapped:
  - outside scope -> `outside_approved_company_scope`;
  - kind MDM does not take yet -> `unsupported_identity_kind` (L1 FUND / BRANCH / SOLE_PROPRIETOR / government / international organisation) AND `unsupported_relationship_type` (RR branch and fund types, per answer 4);
  - valid reporting exception -> `reported_parent_exception`.
  Listing `unsupported_relationship_type` is my interpretation: without it, every in-scope fund or branch relationship would block the run, which contradicts answer 4 ("stay as captured evidence"). Needs the operator's confirmation. Same four on all three contracts, per answer 6.
- `invalid_identity_kind` (reader: an unknown EntityCategory) stays blocking: it is a defect, not an expected category. None occur in this file [files].

## Open questions logged (not asked again this round)
- Lookup-only identifiers from GLEIF (answer 11). My recommendation: keep GLEIF's other entity ids as lookup-only identifiers named after who stated them (`gleif_ra_entity_id`, `gleif_es_cif`, `gleif_fr_siren`), never joining; skip the fund-manager id (another entity) and successor LEIs (a relationship, and in a list the path language cannot reach).
- Start LEI on RR records (answer 12). My recommendation: add `identifiers: {lei: start}` once an LEI identifier-binding rule exists, so an RR record can bind to the Company holding the start LEI; until then an RR record has no binding path and every edge reviews as `unresolved_endpoint`.

## Merge-rule change I would make (NOT made; answer 5)
- Add `gleif.relationships.v1` (and `gleif.reporting_exceptions.v1` if exceptions ever reach `normalize`) to `rules/merge/kinds/company.yaml` `defaults.sources`, last. Needed by `edgar_warehouse/mdm/clean/merge.py` `check_company_sources`: a batch holding `company` assertions from a code not listed fails ("Company policy has no source priority for: ..."). Shown in the dry run below.
- An LEI identifier-binding rule (family `binding`, namespace `lei`, issuing source `gleif.level1.v1`) so GLEIF records and RR records can bind without the name rules (`binding.py`, `activation.NAMESPACES`).

## Gaps: not expressible in `rules/` (logged per REFERENCE)
- The publication-level contract (answer 2): the native release (`native_contract`: version, `record_sources` member -> code, `company_leis` approved scope) that `source_publications.PublicationVerifier` and `gleif_source.validate_release` read from the registered dataset. No rules file holds it.
- The kind of an RR record taken from the Level 1 file (the start node's category).
- A value inside a list (successor LEIs, other validation authorities, legal-entity events, other names).
- Source placeholders meaning "none": `8888` legal form, text `NULL` in EntityStatus and RelationshipStatus, `RA999999`/`RA888888`.
- The REPEX `gleif:Deletion` marker.
- Address parts with no component: `AddressNumber`, `AddressNumberWithinBuilding`, `MailRouting` (left out of `address`).

## Step 6: Write

- File: `repo/rules/sources/gleif/source.yaml`. Values built in `scratch/build_rules.py`, written with `files.dumps` (`scratch/source.values.yaml`), comments inserted between keys by `scratch/add_comments.py`.
- Check: `files.source('gleif') == VALUE` -> True. The reader's own loader `gleif_source.dataset_contract(member)` returns each of the three contracts.
- Choices I made (guesses, flagged):
  - RR relationship `scope` text: "accounting consolidation as GLEIF states it" (one scope for both types; `relationships.project` checks conflicting parents per (type, scope)).
  - RR properties named `source_relationship_status`, `source_registration_status` (REFERENCE's `source_` prefix rule).
  - RR and REPEX `kind: company` (from the reader's scope rule). REPEX kind is inert: the reader never maps an exception.
  - REPEX `effective_time`: unknown (an exception record carries no dates; the reader's `Registration.LastUpdateDate` lookup gives None for it).
  - `completeness` texts, and a REPEX note that the full file includes exceptions GLEIF marks deleted.
- Left out on purpose: HQ address (matching only, answer 9); AddressNumber, AddressNumberWithinBuilding, MailRouting (no address component); OtherLegalForm (answer 10); all other identifiers (answer 11); start LEI identifier on RR (answer 12); Extension content (conformity flag, geocoding, CIF, SIREN...); names other than the legal name; legal-entity events; successor LEIs.

## Step 7: Check (dry run through the real reader)

- `edgar-warehouse rules check gleif`: NOT BUILT (no `rules` subcommand). Fallback used.
- Script: `scratch/dry_run.py`; output `scratch/dry-run.json`, `scratch/dry-run.txt`.
- Sample inputs: 29 records chosen by `scratch/pick_samples.py` (streamed from the captured zips, stopping early) to hit each mapping path and deferral reason, written as small archives in the source's own format (one-member ZIP, `{"records"|"relations"|"exceptions":[...]}`): `scratch/samples/sample-{level1,relationships,reporting_exceptions}.json.zip`.
- Run through the reader itself: `gleif_source.inspect_archive` (hash, one member, wrapper, count, byte length) with `on_record` -> `gleif_source.record_evidence` under the contracts from `dataset_contract` (i.e. the new rules file), then `evidence.validate_assertion` / `validate_deferred` on every output.
- TEST inputs, labelled: the member metadata (`content_date` 2026-09-11T16:00Z, `GLEIF_FULL_PUBLISHED`, `record_count`) comes from the file names and the sample, not from a verified publication manifest; the approved Company scope is a TEST scope of 26 sample LEIs, with 3 LEIs left out on purpose. `validate_release` passed on a TEST manifest built the same way (three distinct codes, golden_copy, sequence = publisher time).
- Checks the database registration and native consumption would make (replicated without a database): native_member, adapter.version and schema_version equal the reader's; family `gleif`; no classification; probable kinds are kinds; formats known; both mapped RR types have relationship contracts. All pass.

Results (what MDM would receive):
- Level 1 (13): 5 Company assertions; 5 set aside as `unsupported_identity_kind` (FUND -> fund_structure, BRANCH -> branch, RESIDENT_GOVERNMENT_ENTITY -> government, INTERNATIONAL_ORGANIZATION -> international_organization, SOLE_PROPRIETOR -> none), non-blocking; 2 `outside_approved_company_scope`, non-blocking, carrying probable kind company; 1 `invalid_lei_checksum` (`0292001629A3Q7XJ0D13`), BLOCKING. Example assertion: LEI `00GBW0Z2GYIER7DHDS71`, name "ARISTEIA CAPITAL, L.L.C.", jurisdiction `US-DE`, address {street "C/O The Corporation Trust Company", street2 "Corporation Trust Center\n1209 Orange St", city Wilmington, region US-DE, postcode 19801, country US}, the gleif_* fields as raw text, effective_at = LastUpdateDate in UTC, provenance {record_key, adapter_version, source.native_record, matching {headquarters_postal_code, headquarters_country}}.
- Relationships (10): 3 assertions (2 IS_DIRECTLY_CONSOLIDATED_BY, 1 IS_ULTIMATELY_CONSOLIDATED_BY), each `company` with no fields and one relationship whose `target_subject` = subject of the end LEI under `gleif.level1.v1`; 2 `unsupported_relationship_type` (IS_FUND-MANAGED_BY, IS_INTERNATIONAL_BRANCH_OF), non-blocking; 1 outside scope, non-blocking; BLOCKING: 1 `invalid_lei_checksum`, 1 `ambiguous_relationship_period` (no period), 2 `invalid_relationship_status_interval` (status text NULL; INACTIVE with no end).
- Reporting exceptions (6): 4 `reported_parent_exception` (incl. the one with the `gleif:Deletion` marker, read like any other), non-blocking; 1 outside scope, non-blocking; 1 `invalid_lei_checksum` (`4469000001BG7ASKSB18`), BLOCKING.
- `merge.check_company_sources(files.policy(), assertions)` -> refused: "Company policy has no source priority for: gleif.relationships.v1". A real batch with RR assertions fails until the merge-rule change (answer 5) is approved.

New findings from the dry run:
- The NULL-status RR record in the sample (`213800TQ8Q2668XD1U88` -> `2138008OJ7UXKCD35837`, direct, 2018-01-01 to 2018-12-31) is a complete historical relationship: its only defect is the status text NULL. The reader's rule blocks it (answer 8's code ticket).
- Placeholders now visible as field values: `gleif_entity_status: "NULL"` (text), `gleif_legal_form: "8888"`, `gleif_registration_authority: "RA999999"`. A missing RA entity id or creation date correctly becomes the `unknown` operation.
- Under RA000665 the RA entity id arrives zero-padded (`0001511857`, a CIK) as the field `gleif_registration_authority_entity_id` (answer 11: a field, not an identifier).
- Dates in the gleif_* fields keep GLEIF's mixed forms (`...000Z`, `+02:00`, `Z`): text, not normalized. `gleif_last_update` must stay raw for the Name Census.
- This dry run is NOT a preview: it matches nothing against existing records, binds nothing, and creates no identity (gap logged per the skill).
- Repo tests for the reader: none in this repo copy (no `tests/` directory), so none run.

## Step 8: Preview: NOT BUILT
- `edgar-warehouse rules run gleif --target mdm --preview`: not built. Stopped here per the skill. Nothing registered, activated or approved.

## Skill gaps found in Phase B
- `rules check`, `rules run --preview` absent (the whole `rules` subcommand).
- Step 7's fallback describes the normalize path (`adapters.normalize` with `policy=`), but a native reader needs its own metadata, a scope and an archive; the skill should say "call the reader's per-record function under `dataset_contract`" and warn that `check_company_sources` fails the batch before the merge stage when a new code is missing from the kind's sources.
- The operator's three business reasons map to four reason strings in code; the skill has no table from business reason to reason string.
- `files.dumps` folds long values: comments must go between keys, as the skill says; that worked.

## Trial-rule disclosure (Phase B)
- Once I ran `uv run --no-sync --project <repo> python` from `scratch/` (not from `repo/`) to patch `scratch/build_rules.py`. Rule 2 says run from `repo/`. It touched only the scratch script.

## Reader/contract gap: XML
- The reader also accepts `xml.zip`. `_xml_value` turns a single repeated child into an object, not a list. So under XML, a record with exactly one AdditionalAddressLine gives an object, and `street2: {lines: ...}` raises `invalid_field_shape` (blocking) [code]. The JSON Golden Copy writes it as a list (see the count below). The mapping is safe for JSON only; an XML capture would need a reader change or a second contract version.
- Full line-based count over Level 1 (`scratch/shape_counts.py`, `scratch/shape-counts.json`) [files]: `AdditionalAddressLine` is a list every time it appears (legal address 1,087,194; HQ 1,019,045; other addresses 76,559; never an object). So the `street2: {lines: ...}` mapping never blocks on the JSON capture. `ValidationSources` is an object on 3,428,276 records and absent on the other 201 (never a list), so those 201 become `unknown`, correctly.

## Confirmation needed from the operator (not an approval request)
- `unsupported_relationship_type` as non-blocking (my reading of "a kind MDM does not take yet"). Yes: fund and branch links wait quietly, and so would any relationship type GLEIF adds later (the reader does not check type names; today's file has only the six known types). No: every fund or branch link inside the approved Company list blocks the run.

## Prerequisites before step 9 (none met)
- Merge-rule change: `gleif.relationships.v1` in the Company source list (the dry run shows the refusal).
- An LEI matching rule, so GLEIF records and relationships can join a Company without the name rules.
- Acquisition-registry coverage for family `gleif` (`store.register_dataset` requires an active registry version covering the family).
- The approved Company LEI list (the publication-level contract).
- The reader fixes from answers 7 and 8 (scope before check digit; relationship source gaps).
