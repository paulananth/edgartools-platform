# Rules skill trial log: onboarding the source in `inputs/`

Skill: `repo/skills/rules/SKILL.md` + `REFERENCE.md`. Operator unreachable (trial rule 4):
each question is written as I would ask it, with my recommendation, and the recommendation is
assumed. Approval is never assumed.

Source-of-decision tags used below: [files] = the captured inputs / my profile of them;
[code] = repo code; [repo-docs] = repo docs/specs/rules files; [public-docs] = public GLEIF
documentation; [assumption] = my guess.

## Step 1. Identify

Files in `inputs/` (symlinks, streamed only, never extracted to disk):

| File | Compressed | Expanded | Top-level wrapper |
|---|---|---|---|
| `01-20260911-1600-gleif-goldencopy-lei2-golden-copy.json.zip` | 927.6 MB | 13.25 GB | `{"records":[...]}` |
| `01-20260911-1600-gleif-goldencopy-rr-golden-copy.json.zip` | 35.0 MB | 1.12 GB | `{"relations":[...]}` |
| `01-20260911-1600-gleif-goldencopy-repex-golden-copy.json.zip` | 63.7 MB | 1.55 GB | `{"exceptions":[...]}` |

Each zip holds exactly one JSON member. First records show GLEIF's JSON rendering of its XML
CDFs (`{"$": value}`, `@xml:lang`, `@type`).

Identification: **GLEIF Golden Copy, full publication of 2026-09-11 16:00 UTC, JSON format, three
members: Level 1 LEI records (LEI-CDF), Level 2 relationship records (RR-CDF) and Level 2
reporting exceptions (REPEX).** [files: names `gleif-goldencopy-{lei2,rr,repex}`, wrappers, record
shapes]

Question 1 (would ask the operator): "These look like the GLEIF Golden Copy published
2026-09-11 16:00 UTC: the full LEI file (Level 1, who is who), the relationship file (Level 2,
who owns whom) and the reporting-exceptions file (why a parent is not reported). Is that right?"
Recommendation: yes. Assumed answer: yes.

## Missing commands (every one the skill names that did not exist)

| Step | Command the skill names | What happened |
|---|---|---|
| 2 Profile | `edgar-warehouse rules profile <files>` | Does not exist: `edgar-warehouse rules --help` fails with `invalid choice: 'rules'`. Did the stand-in: `scratch/profile.py` (ijson stream per zip, never extracted), plus two grep passes for joins. |
| 7 Check | `edgar-warehouse rules check <source>` | Does not exist (no `rules` subcommand). Did the stand-in dry run through `adapters.normalize` (see step 7). |
| 8 Preview | `edgar-warehouse rules run <source> --target mdm --preview` | Does not exist. Skill says stop here; stopped. |
| 9 | `rules activate`, `rules run <source> --target mdm --deploy`, `--target silver` | Not built (skill says so); not reached (no approval). |
| - | `rules init`, `rules migrate --to-db / --to-files` | Not needed for this task; not built. |

Not a missing command, but a missing file the code points at: `gleif_source.py` and
`docs/specs/clean-mdm/{state-of-build,local-operations,source-publications}.md` link
`docs/specs/clean-mdm/native-gleif.md` ("native GLEIF operation"); it does not exist in the repo.

## Step 2. Profile

Stand-in script: `scratch/profile.py` (streams each zip member with ijson/yajl2_c; per path:
types, records filled, blank strings, distinct count capped at 200k, top values while under
2,000 distinct, samples, LEI-shaped + mod-97 check, CIK-shaped `^[0-9]{1,10}$`, ISO-date-shaped,
list lengths; exact key-uniqueness via hashed tuples). Outputs: `scratch/profile-{level1,rr,repex}.json`.
Level 1 is 13.25 GB expanded and profiles at ~800 records/s on this machine (about an hour), so
I also pulled the join columns with `unzip -p | grep -A1` (`scratch/level1-leis-fast.txt`,
`scratch/level1-grep.txt`).

How identifiers were checked: LEI = regex `[A-Z0-9]{18}[0-9]{2}` then ISO 7064 mod 97-10
(letters to 10..35, whole number mod 97 == 1), the same test as `adapters._lei`. CIK = 1-10
ASCII digits (shape only; there is no CIK check digit).

### RR (relationships) - 487,721 records [files]

- Record shape: `{"RelationshipRecord": {"Relationship": {...}, "Registration": {...}}}` (the extra
  wrapper `gleif_source._xml_records` adds for XML).
- Candidate record key: (StartNode LEI, RelationshipType) is unique and always filled (487,721
  distinct, 0 duplicates). (Start, End, Type) is also unique. Start alone is not (303,012 distinct).
  GLEIF's spec states the same uniqueness rule: a relationship record is "matched ... based on the
  combination of StartNodeID and RelationshipType" [public-docs: Golden Copy and Delta Files spec
  v2.2, s.1.3].
- `StartNode.NodeIDType` and `EndNode.NodeIDType`: always `LEI` (1 distinct value).
- LEI check: EndNode 487,721/487,721 pass mod 97. StartNode 487,720/487,721: `4469000001BG7ASKSB18`
  (record 155,811, IS_ULTIMATELY_CONSOLIDATED_BY, registered 2018) fails the check digit and is
  also a Level 1 LEI.
- `RelationshipType`: IS_FUND-MANAGED_BY 150,982; IS_ULTIMATELY_CONSOLIDATED_BY 132,877;
  IS_DIRECTLY_CONSOLIDATED_BY 126,688; IS_SUBFUND_OF 73,834; IS_INTERNATIONAL_BRANCH_OF 1,959;
  IS_FEEDER_TO 1,381. All six are in `relationships.CONTRACTS`.
- `RelationshipStatus`: ACTIVE 487,316; **NULL 345** (the literal text "NULL"); INACTIVE 60.
  `gleif_source.record_evidence` accepts only ACTIVE/INACTIVE, so the 345 would be deferred as
  `invalid_relationship_status_interval` (blocking).
- `RelationshipPeriods.RelationshipPeriod` is sometimes one object (189,666) and sometimes a list
  (297,982, up to 3). PeriodType: RELATIONSHIP_PERIOD, ACCOUNTING_PERIOD, DOCUMENT_FILING_PERIOD.
  215 single-object periods have no StartDate.
- `Registration.RegistrationStatus`: PUBLISHED 386,386; LAPSED 101,326; PENDING_ARCHIVAL 8;
  PENDING_TRANSFER 1. `ValidationSources`: FULLY_CORROBORATED 330,340; ENTITY_SUPPLIED_ONLY 140,263;
  PARTIALLY_CORROBORATED 17,118.
- Repeated groups: `RelationshipQualifiers` (31%, ACCOUNTING_STANDARD: IFRS / US_GAAP / OTHER /
  GOVERNMENT), `RelationshipQuantifiers` (11%, ACCOUNTING_CONSOLIDATION %, mostly 100.00).
- Dates: every date path is ISO 8601; mixed forms (`...000Z` and `...+02:00`, `-06:00`).
- `Registration.ValidationReference` (20%) holds URLs, many on sec.gov. Never opened.
- No `Extension` paths in RR.

### REPEX (reporting exceptions) - 6,351,397 records [files]

- Record key: (LEI, ExceptionCategory) unique and always filled (0 duplicates); LEI alone is not
  (3,188,712 distinct). Matches the spec's uniqueness rule [public-docs, spec s.1.3].
- `ExceptionCategory`: DIRECT_ACCOUNTING_CONSOLIDATION_PARENT 3,179,314; ULTIMATE_... 3,172,083.
- `ExceptionReason`: always a list (max 8). Values: NATURAL_PERSONS 2,363,792; NON_CONSOLIDATING
  2,201,580; NO_KNOWN_PERSON 1,336,144; NO_LEI 243,327; NON_PUBLIC 216,970; CONSENT_NOT_OBTAINED
  2,784; BINDING_LEGAL_COMMITMENTS 368; DETRIMENT_NOT_EXCLUDED 339; DISCLOSURE_DETRIMENTAL 310;
  LEGAL_OBSTACLES 233. All ten are in `gleif_source.EXCEPTION_REASONS`; nothing else occurs.
- `ExceptionReference`: 0.05%, free text ("Non Consolidating", "n/a", Italian sentences).
- LEI check: 6,351,298/6,351,397 pass mod 97 (99 fail).
- **`Extension.gleif:Deletion` is present (JSON null) on 257,509 records (4.05%) of this FULL
  file.** GLEIF's spec says deletion flags appear in delta files for Level 2 records being removed
  [public-docs, spec s.1.5]. `record_evidence` ignores `Extension` for REPEX. The contract
  language has no way to say "this record is a deletion"; noted for the operator (see Findings).

## Step 3. Research

Identification confirmed from the repo: the Level 1 zip's SHA-256 is
`1b6cd9cda3f94269fd406ee481842ea042b699e95eb5b8124b1496d4fda36a6a`, the exact Golden Copy pinned in
`rules/merge/pending-proofs.yaml` (`gleif_golden_copy_sha256`) and in
`tests/fixtures/clean_mdm/four_companies_v1/build.py` ("publication_utc": "2026-09-11 16:00:00").
RR zip `089a2513...d0c3`, REPEX zip `f205fd8d...e831`. [files + repo-docs]

What I read, and what each gave:

- `CONTEXT.md` (Clean MDM section): kinds and terms. GLEIF RR is the evidence for
  IS_INTERNATIONAL_BRANCH_OF, Accounting Direct Parent, GLEIF Fund Link (keep GLEIF's direction);
  Probable Kind; Source Stage (a record waits unbound until a matching rule links it). [repo-docs]
- `docs/specs/clean-mdm/source-evidence.md`: proposes dataset codes `gleif.lei`,
  `gleif.relationship`, `gleif.reporting_exception` (conflicts with the codes the code and merge
  rules use: see Q2). Level 1, RR and REPEX are one coordinated Golden Copy family. [repo-docs]
- `docs/specs/clean-mdm/company-policy.md`: Q1 scope (SEC Company universe plus approved
  GLEIF-only parents; not all global GLEIF Companies); Q14 ("an LEI does not establish a CIK
  crosswalk merely because both values exist"). [repo-docs]
- `docs/research/gleif-open-data-augmentation-2026-09-11.md`: "Never treat registeredAs as CIK
  unless both its Registration Authority and identifier semantics prove that it is a CIK";
  entity status and registration status stay separate. [repo-docs]
- `docs/research/sec-gleif-relationship-sources-2026-09-26.md`: which relationship each file
  supports; REPEX supports no edge. [repo-docs]
- `KINDS` (`evidence.py`): company, person, security, fund_structure, branch, government,
  international_organization, venue. [code]
- `rules/merge/kinds/company.yaml`: names `gleif.level1.v1` as a default source (SEC first) and as
  the source of both SEC-to-GLEIF name rules, which read GLEIF fields `name`,
  `gleif_last_update`, `gleif_entity_status`, `gleif_registration_status`, `jurisdiction` and
  `matching.headquarters_postal_code` / `matching.headquarters_country`. **It lists no fields
  otherwise** (see Skill gaps). [repo-docs/code]
- Company field names: `store.COMPANY_NAMED_FIELDS` and migration
  `037_clean_mdm_company_versions.sql` (name, sic, sic_description, state_of_incorporation,
  fiscal_year_end, description, jurisdiction, address, and 11 `gleif_*` fields). [code]
- **Existing code for this source:** `edgar_warehouse/mdm/clean/gleif_source.py` already reads
  these exact files (`inspect_archive`: JSON or XML zip, bounded, hash-checked;
  `record_evidence`: turns one record into an assertion or a deferred record). Its
  `dataset_contract(member)` reads the mapping from `rules/sources/gleif/source.yaml` by
  `adapter.native_member`, and that file is missing from this repo copy, so
  `tests/mdm/test_clean_gleif_source.py` failed 17 of 33 before I wrote it. The command that runs
  it: `edgar-warehouse mdm mastering --model clean --manifest <manifest with native_source>
  --run-id <id>` (`native_consumption.prepare_native`). So I map from *its* records and write no
  parser. Constraints the code imposes on the file:
  - `adapter.version` and `contract.schema_version` must both be `gleif-native-record-v1`
    (`record_evidence`, `native_consumption`). [code]
  - one entry per member, each with `adapter.native_member` in {level1, relationships,
    reporting_exceptions}; no `classification` (refused). [code]
  - RR paths name the record `record_evidence` builds: `start`, `end`, `relationship_type`,
    `valid_from`, `valid_to`, `status`, `registration_status` (plus `_native`, the raw record). [code]
  - REPEX records never reach the mapping: a valid exception is always set aside as
    `reported_parent_exception`. [code]
  - effective time is `Registration.LastUpdateDate.$`, set by `record_evidence`, not the contract. [code]
  - scope: only LEIs on the run's `native_contract.company_leis` list; others are deferred
    `outside_approved_company_scope`. [code]
- Tests that pin the mapping: `tests/mdm/test_clean_gleif_source.py` (jurisdiction, legal address
  with AdditionalAddressLine joined by newlines, `gleif_registration_status`, `name` from
  LegalName, category to kind / probable kind incl. SOLE_PROPRIETOR = none);
  `tests/integration/test_clean_four_companies.py` (`gleif_legal_form`, `jurisdiction` and
  `address` won by `gleif.level1.v1`; address is the LEGAL address: Apple's street2 "330 N. Brand
  Blvd\nSuite 700"); `tests/mdm/test_clean_matching.py` (the `matching` names). [code]
- Contract keys the code reads that REFERENCE.md does not document: `nonblocking_deferred_reasons`
  (contract level; `store.register_dataset`, `merge.py`, migration 030, `bookkeeping.reconcile`:
  an open blocking review keeps `end_to_end_complete` false). [code]
- Public documentation (never sec.gov):
  - GLEIF Golden Copy page (gleif.org/en/lei-data/gleif-golden-copy): three publications daily;
    full files "always contain all LEIs ever published"; deltas for 8h / 24h / 7d / 31d. [public-docs]
  - GLEIF Golden Copy and Delta Files Specification v2.2 (PDF, gleif.org; text in
    `scratch/golden-copy-spec-v2.2.txt`): RR unique by (StartNodeID, RelationshipType); REPEX
    unique by (LEI, ExceptionCategory); a relationship record replaces a REPEX of the same type;
    "LEI records ... are never deleted from the Golden Copy"; RR not PUBLISHED/LAPSED are removed
    and deltas carry a deletion flag in `Extension`; file publish times 0000/0800/1600 (made
    available 02:00/10:00/18:00 UTC). [public-docs]
  - GLEIF Registration Authorities List v1.8.1 (CSV from gleif.org, `scratch/ra-list-v1.8.1.csv`):
    `RA000665` = "EDGAR", Securities and Exchange Commission. [public-docs]
  - I did not open any sec.gov URL (the RR `ValidationReference` values and the RA list's
    website column point at sec.gov). No request to any SEC domain was made.

### Level 1 (LEI records) - 3,428,477 records [files]

Counts below come from `scratch/level1-table.tsv` (line pass, `scratch/l1table.py`) and
`scratch/level1-leis-fast.txt`; fill rates per path from `scratch/profile-level1.json` (see the
end of this section).

- Record key: `LEI.$`, 3,428,477 distinct, always filled; the file is sorted by LEI.
- LEI check: **256 LEIs fail mod 97**, and every one is an ANNULLED (255) or DUPLICATE (1)
  registration (GENERAL 178, SOLE_PROPRIETOR 78). `adapters._lei` refuses them, so
  `record_evidence` defers each as `invalid_lei_checksum`, **before** the scope check, so they
  would appear in every full run whatever the Company list.
- `Entity.EntityCategory.$` (always filled): GENERAL 3,043,262; FUND 248,988; SOLE_PROPRIETOR
  127,272; RESIDENT_GOVERNMENT_ENTITY 6,955 (the exact count the comment in `gleif_source.py`
  cites); BRANCH 1,913; INTERNATIONAL_ORGANIZATION 87. Nothing else, nothing missing.
- GENERAL only: `EntityStatus` ACTIVE 2,838,657, INACTIVE 197,918, the literal text "NULL" 6,687;
  `RegistrationStatus` ISSUED 1,725,449, LAPSED 1,112,345, RETIRED 197,915, DUPLICATE 5,585,
  ANNULLED 1,102, PENDING_TRANSFER 538, PENDING_ARCHIVAL 328.
- Legal form: 207,977 GENERAL records (6.8%) carry ELF code "8888" (no ISO 20275 code) with the
  real form as free text in `Entity.LegalForm.OtherLegalForm.$`; the rest carry an ELF code.
- Registration authority: 942 distinct RA codes; top RA999999 ("not in the RA list") 267,984.
  **RA000665 (EDGAR, SEC)**: FUND with series ids `S#########` 22,863; FUND with 10-digit ids
  (CIK-shaped, e.g. `0001052118`) 4,667; GENERAL 10-digit 305; GENERAL series 77; government
  10-digit 3; sole proprietor 1; other shapes 17 (e.g. `805-6204242689`). CIK-shaped by pattern
  only; nothing proves they are CIKs.
- Names: `Entity.LegalName.$` always filled for GENERAL. Organisation-shaped by construction
  (GLEIF registers legal entities); SOLE_PROPRIETOR records carry person-like names and are not
  a Company category in the code.
- Repeated groups: `OtherEntityNames.OtherEntityName[]` (previous, trading, alternative names),
  `LegalAddress.AdditionalAddressLine[]`, `LegalEntityEvents.LegalEntityEvent[]`.
- Keys that point at other records: `Registration.ManagingLOU.$` (an LEI of the issuer),
  `Entity.SuccessorEntity[].SuccessorLEI.$`; neither is an MDM relationship today.
- `Extension`: GLEIF geocoding (`gleif:Geocoding`, one object or a list), the policy
  conformity flag (`gleif:conformity.gleif:conformityflag.$`) and issuer-specific extensions
  (`leifr:SIREN`, `ext:CIF`, ...). Not mapped.
- Dates: `EntityCreationDate`, `InitialRegistrationDate`, `LastUpdateDate`, `NextRenewalDate`,
  all ISO 8601.
- Addresses: `LegalAddress` and `HeadquartersAddress` (FirstAddressLine, AdditionalAddressLine[],
  City, Region `US-MA`-style, Country ISO 3166, PostalCode, and rarely AddressNumber,
  AddressNumberWithinBuilding, MailRouting).
- Full ijson profile (`scratch/profile-level1.json`, 4,118 s): 271 paths; every leaf value is a
  string (so `field_shape: nullable_text` holds); no blank strings on any mapped path. Fill
  rates of mapped paths: LEI, LegalName, EntityCategory, EntityStatus, EntityLegalFormCode,
  LegalAddress FirstAddressLine / City / Country, HQ Country, RegistrationAuthorityID,
  RegistrationStatus, Initial/LastUpdate/NextRenewal dates, ManagingLOU: 100%;
  LegalJurisdiction 100% less 4 records; ValidationSources 99.99%; LegalAddress PostalCode 98.7%,
  HQ PostalCode 98.7%; RegistrationAuthorityEntityID 91.5%; EntityCreationDate 82.4%;
  LegalAddress Region 67.3%; AdditionalAddressLine 31.7% (always a list, max 3, which the
  address `lines` mapping requires). `OtherLegalForm` 11.7%; `OtherEntityNames` 12.2% (up to
  32 names); `LegalEntityEvents` 20.8%; `SuccessorEntity` 1.5%; conformity flag 99.9%.
  Whole-file EntityStatus: ACTIVE 3,167,365, INACTIVE 252,050, "NULL" 9,062.

## Step 4. Infer (per record type), with where each decision came from

### Level 1 -> `gleif.level1.v1`

| Decision | Value | From |
|---|---|---|
| Kind | `kind_field: Entity.EntityCategory.$`, `GENERAL: company` | code (`gleif_source` category list, tests), repo-docs (Company scope, CONTEXT) |
| Probable kinds | FUND fund_structure, BRANCH branch, RESIDENT_GOVERNMENT_ENTITY government, INTERNATIONAL_ORGANIZATION international_organization; SOLE_PROPRIETOR none | code (tests pin all five), files (the six categories are exactly these) |
| Record key | `LEI.$`, format `lei` | files (unique, always filled), code |
| Identifier | `lei: LEI.$`, format `lei` | files, code (`matching`/`binding` read `identifiers.lei`) |
| No `cik` identifier | RA000665 ids are not mapped as CIK | repo-docs (Q14; research memo), files (mixed series/CIK shapes); asked as Q9 |
| `name` | `Entity.LegalName.$` | code (test: GLEIF legal name fills `name`, SEC first), repo-docs (operator 2026-09-24 in test docstring) |
| `jurisdiction` | `Entity.LegalJurisdiction.$` | code (tests: "US-CA", "GB", "NL") |
| `address` | LegalAddress: FirstAddressLine, AdditionalAddressLine (lines), City, Region, PostalCode, Country | code (unit test and four-companies: Apple street2 is its legal address) |
| `gleif_legal_form` | `Entity.LegalForm.EntityLegalFormCode.$` | code (field exists; four-companies asserts GLEIF wins it), assumption on code vs text (Q7) |
| `gleif_entity_status` | `Entity.EntityStatus.$` | code (field; name rule reads it), files |
| `gleif_entity_creation_date` | `Entity.EntityCreationDate.$` | code (field name), files |
| `gleif_registration_authority`, `..._entity_id` | `Entity.RegistrationAuthority.RegistrationAuthorityID.$` / `...EntityID.$` | code (field names), files |
| `gleif_registration_status` | `Registration.RegistrationStatus.$` | code (test), files |
| `gleif_initial_registration`, `gleif_last_update`, `gleif_next_renewal` | `Registration.InitialRegistrationDate.$`, `LastUpdateDate.$`, `NextRenewalDate.$` | code (field names; `gleif_last_update` must be the raw text the Name Census holds) |
| `gleif_managing_lou` | `Registration.ManagingLOU.$` | code (field name), files |
| `gleif_validation_source` | `Registration.ValidationSources.$` | code (field name), files (FULLY_CORROBORATED etc.) |
| `field_shape: nullable_text` | every mapped value is a string or the address | files (every `$` value is a string), code |
| `matching` | `headquarters_postal_code`, `headquarters_country` from HeadquartersAddress | code (`company.yaml` postal rule, `test_clean_matching.py`) |
| Not mapped | OtherEntityNames, OtherLegalForm, HQ address as a field, events, successors, geocoding, conformity flag, other RA/VA ids | assumption (no Company field exists for them; a new field needs the operator) |
| effective_time | `Registration.LastUpdateDate` | code (`record_evidence` sets it) |
| semantics | `patch` | public-docs (LEI records are never deleted, so absence proves nothing), REFERENCE (only documented value), code (regression test treats "snapshot" as a change) |
| completeness | full = every LEI ever published; delta = changes; MDM takes only the approved Company list | public-docs, code (`company_leis` scope) |
| nonblocking reasons | outside_approved_company_scope, unsupported_identity_kind, invalid_lei_checksum | code (the key and its effect), assumption via Q6/Q10 |
| schema_version / adapter version | `gleif-native-record-v1` | code (required) |

### RR -> `gleif.relationships.v1`

| Decision | Value | From |
|---|---|---|
| Record key | `[start, relationship_type]` | files (unique), public-docs (GLEIF's own rule), code (`start`/`relationship_type` are what `record_evidence` emits). Not `[start, end, type]`: a parent change would then leave the old edge standing forever under `patch` (my reasoning, assumption) |
| Kind | `kind: company` | assumption, Q8; files (start category by type, below) |
| Identifier | `lei: start` | assumption: the only way in the contract language for an RR record to be bound to the Company holding its child LEI; nothing in the repo says how an RR record's subject binds (see Findings) |
| Relationship | `type_field: relationship_type`, six identity `type_values`, `target_key: [end]`, `target_source: gleif.level1.v1`, `valid_from`, `valid_to` | code (`relationships.CONTRACTS`, `dataset_contract(level1_source=)` rewrites `target_source`), files (six types) |
| Properties | `status`, `registration_status` | code (the two extra keys `record_evidence` emits), assumption (qualifiers, quantifiers and validation level not kept) |
| effective_time | the RR record's `Registration.LastUpdateDate` | code |
| completeness | current records only; absence is not proof | public-docs (spec s.1.3, s.1.5) |
| nonblocking reasons | outside_approved_company_scope, invalid_lei_checksum | assumption via Q6/Q10 |

Start and end category of each RR type (join to Level 1) [files]:

| Type | Start -> end, share |
|---|---|
| IS_FUND-MANAGED_BY (150,982) | FUND -> GENERAL 97.4%, FUND -> FUND 2.2%, GENERAL -> GENERAL 0.1% |
| IS_SUBFUND_OF (73,834) | FUND -> FUND 89.4%, FUND -> GENERAL 10.6% |
| IS_FEEDER_TO (1,381) | FUND -> FUND 99.8% |
| IS_DIRECTLY_CONSOLIDATED_BY (126,688) | GENERAL -> GENERAL 95.7%, FUND -> GENERAL 2.1% |
| IS_ULTIMATELY_CONSOLIDATED_BY (132,877) | GENERAL -> GENERAL 95.7%, FUND -> GENERAL 2.2% |
| IS_INTERNATIONAL_BRANCH_OF (1,959) | BRANCH -> GENERAL 90.3%, GENERAL -> GENERAL 9.4% |

### REPEX -> `gleif.reporting_exceptions.v1`

| Decision | Value | From |
|---|---|---|
| In scope as evidence only | every valid exception is set aside `reported_parent_exception` | code, repo-docs (a missing parent is not proof of no parent) |
| Record key | `[LEI.$, ExceptionCategory.$]` | files (unique), public-docs (spec s.1.3) |
| Identifier | `lei: LEI.$` | files; never used, since no REPEX record is mapped |
| No kind, fields or edges | adapter maps none | code (the mapping never runs) |
| effective_time | unknown: a REPEX record has no date | files (no date paths), code (`record_evidence` finds none) |
| nonblocking reasons | outside_approved_company_scope, reported_parent_exception, invalid_lei_checksum | assumption via Q6/Q10 |

### Whole file

| Decision | Value | From |
|---|---|---|
| Folder and `source:` | `rules/sources/gleif/`, `source: gleif` | code (`rules_files.source("gleif")`); conflicts with REFERENCE's `<provider>.<dataset>` |
| `bronze.family` and each `contract.family` | `gleif_golden_copy` | assumption (Q4) |
| Source codes | `gleif.level1.v1`, `gleif.relationships.v1`, `gleif.reporting_exceptions.v1` | repo-docs (`company.yaml` names `gleif.level1.v1`), code (tests), Q2 |
| Record types in scope | all three: Level 1 Companies; RR among Companies; REPEX as evidence | repo-docs (company-policy Q1, CONTEXT, domain-model, source-evidence). Not asked: the repo already decides it |
| No publication aggregate entry | `gleif.publication.v1` (native_contract, publication_contract) is not in the file | code (`dataset_contract` requires `native_member` on every entry); see Skill gaps |

## Step 5. Ask (operator unreachable: each question as I would ask it; my recommendation assumed)

Q1 is in step 1. The rest, one at a time:

**Q2. Dataset names.** "The Company merge rules already name GLEIF's LEI records
`gleif.level1.v1`, and the tests call the other two files `gleif.relationships.v1` and
`gleif.reporting_exceptions.v1`. An older spec table proposed `gleif.lei`,
`gleif.relationship` and `gleif.reporting_exception`. Which names should the three datasets
have? I recommend the first three, because the approved merge rules already use
`gleif.level1.v1`." Assumed answer: yes, the first three.

**Q3. Is it live already?** "The merge rules name `gleif.level1.v1`, so it may already be
registered in Clean MDM. If it is, its mapping is live, and this file can only become a new
version of it after a record-by-record comparison with the registered one, which I cannot read
from here. Is `gleif.level1.v1` registered? I recommend treating this file as a draft until
someone compares it with the registry." Assumed answer: treat as a draft; compare before any
activation.

**Q4. Bronze family.** "No acquisition family for GLEIF exists in the repo yet, and a Dataset
Contract has to name one that the acquisition registry covers. What should GLEIF's family be
called? I recommend `gleif_golden_copy`, one family for the three Golden Copy files, in the
snake_case the other families use (`adv_bulk_dataset`, `company_facts`)." Assumed: `gleif_golden_copy`.

**Q5. (Not asked.)** Which record types are in scope: the repo already answers it (Company
policy Q1, CONTEXT, domain model): Level 1 GENERAL records as Companies, the others waiting with
a probable kind; RR among approved Companies; REPEX kept as evidence only.

**Q6. Records MDM sets aside on purpose.** "A full Golden Copy holds 3.4 million LEI records,
6.4 million reporting exceptions and 488 thousand relationships, but MDM takes only the Companies
on its approved list. Everything else is kept as evidence and set aside: records outside the
list, LEI records whose category is not a Company (Fund, Branch, government, international
organisation, sole proprietor), and every reporting exception. Should those wait for a person?
I recommend no: mark those three reasons as not holding the run, because otherwise no full
GLEIF run can ever finish (each set-aside record opens a review that blocks completion)."
Assumed: yes, mark them non-blocking. (Found later: the integration test quoted under Q10 pins
`outside_approved_company_scope` as non-blocking, so that part is repo behaviour, not only my
recommendation.)

**Q7. Legal form.** "GLEIF gives a legal form as an ISO code, except for 6.8% of Company
records (207,977) where the code is 8888, meaning 'no code', and the real form is free text in
a second field. Which should `gleif_legal_form` hold? I recommend the ISO code only, as now,
and no new field for the free text; add one later if you want it." Assumed: the ISO code only.

**Q8. What kind is a relationship record?** "A GLEIF relationship record names two LEIs but
not what the child is. 46% of them start at a Fund (fund manager, sub-fund, feeder), 0.4% at a
Branch, and the consolidation ones start at a Company 96% of the time. MDM only takes a
relationship when both LEIs are on the approved Company list, so inside that list the child is a
Company. Should every relationship record be read as a Company's? I recommend yes, for now; when
Funds join the approved list this must change, and the rules language cannot yet take the
child's kind from its LEI record." Assumed: yes, `kind: company`.

**Q9. EDGAR numbers in GLEIF.** "GLEIF records registered with the SEC's EDGAR (authority
RA000665) carry an EDGAR number: 4,976 are 10 digits like a CIK and 22,940 are fund series ids.
Only 305 Company records carry a 10-digit one. Should MDM treat those as CIKs, which would link
GLEIF records to SEC Companies directly? I recommend no: the spec forbids inferring a CIK
crosswalk this way without proof, the rules language cannot limit it to RA000665, and the value
is already kept in `gleif_registration_authority_entity_id`." Assumed: no.

**Q10. GLEIF's own bad LEIs.** "256 LEIs in the LEI file (and 1 in the relationships file, 99 in
the exceptions file) fail the LEI check digit. All 256 are annulled or duplicate registrations.
MDM refuses them as LEIs, which is right, but it checks the digit before it checks the approved
list, so all of them would wait for a person in every full run. Should they? I recommend no:
keep refusing them as LEIs, keep them as evidence, and mark the reason non-blocking; nobody can
correct an LEI GLEIF annulled." Assumed: yes, non-blocking.
Evidence against this recommendation, found after writing it:
`tests/integration/test_clean_native_publications.py::test_excluded_evidence_is_retained_without_blocking_but_malformed_records_block`
pins that a Level 1 record outside the list does not block (`outside_approved_company_scope`,
which supports Q6) and that a malformed LEI (`"bad-lei"`, reason `invalid_lei`) does block. It
does not test `invalid_lei_checksum`, so the file does not contradict it, but its principle
("malformed records block") points the other way. If the operator follows that principle, remove
`invalid_lei_checksum` from the three lists; then no full Golden Copy run can finish until the
reader checks the approved list before the check digit. This answer matters more than the others.

(Not asked, because it is not a mapping choice: 421 relationship records GLEIF publishes out of
its own format would wait for a person if both their LEIs are on the approved list: 216 bad
intervals, 130 with an invalid status (the literal "NULL", or INACTIVE with no end date), 75
with no single relationship period. That is the reader's rule, it only bites inside the
approved list, so I left those reasons blocking. The 1 RR record with a bad LEI falls under Q10.)

## Step 6. Write

Wrote `repo/rules/sources/gleif/source.yaml` with `scratch/build_source_yaml.py`: the body is
a Python dict written with `files.dumps`; comment lines are inserted above keys, and the script
refuses to save unless `files.loads(text) == body` and then `files.source("gleif") == body`.

Load check (the skill's command, with `--no-sync` per the trial rules):
`uv run --no-sync python -c "from edgar_warehouse.rules import files; print(files.source('gleif'))"`
prints the three contracts (keys `gleif.level1.v1`, `gleif.relationships.v1`,
`gleif.reporting_exceptions.v1`).

Postgres integration tests (`tests/integration/test_clean_native_publications.py`,
`test_clean_four_companies.py`, `test_clean_mapping_review_regressions.py`) need PG16 and were not
run. I grepped them for the reasons I made non-blocking: only the test quoted under Q10 touches
blocking, and it agrees with the file for `outside_approved_company_scope` and `invalid_lei`.

Extra check (not in the skill): `uv run --no-sync pytest -p no:cacheprovider
tests/mdm/test_clean_gleif_source.py -q`: **33 passed** (17 failed before the file existed,
all with the file missing). `tests/mdm/test_clean_matching.py`, `test_clean_company_source.py`,
`test_clean_activation.py` and part of `test_clean_classification.py` cannot run in this copy:
they read `.scratch/company-mastering/research/08-rules.json`, which the copy does not have.

## Step 7. Check (dry run; `edgar-warehouse rules check` does not exist)

**The skill's literal instruction does not work for this source**, in two ways:
1. `normalize(..., publication={"member": "sample", "publication_key": "dry-run", "revision": 0})`
   raises `KeyError: 'artifact_sha256'` (the Shell record): `normalize` always reads
   `publication["artifact_sha256"]` when building provenance.
2. Bare `normalize` on a raw RR record gives `UnsupportedRecord: missing_record_identity`: the RR
   mapping reads the record `gleif_source.record_evidence` builds, not the raw one. Bare
   `normalize` also skips the native reader's approved-Company-list check, the RR reshaping and
   the REPEX set-aside (the Level 1 check digit still runs, through `record_key_format: lei`).

So the dry run (`scratch/dry_run.py`, output `scratch/dry-run.json`) puts each sample through
`gleif_source.record_evidence` (which calls `normalize` with the contract from the new file),
with `publication = {publication_key: "dry-run", revision: 0, artifact_sha256: <the zip's
real SHA-256>, member: <member>}`. Approved Company list for the dry run: every sampled LEI
(23), except `004L5FPTUREIWK9T2N63`, left out on purpose. Samples are real records from the
three files. It matches nothing against existing records. It is not a preview.

What MDM would receive (blocking status read from the final file):

| File | Record (ordinal) | What it is | MDM receives |
|---|---|---|---|
| level1 | 0 | 001GPB6A9XPE8XJICC14 FUND "Fidelity Advisor Leveraged Company Stock" | deferred: unsupported_identity_kind, probable kind fund_structure, non-blocking |
| level1 | 1 | 004L5FPTUREIWK9T2N63 GENERAL "Hutchin Hill Capital, LP" (left off the list) | deferred: outside_approved_company_scope, probable kind company, non-blocking |
| level1 | 3 | 00GBW0Z2GYIER7DHDS71 GENERAL "ARISTEIA CAPITAL, L.L.C." | assertion, kind company, 14 fields with a value, lei identifier |
| level1 | 549 | 029200640K7U6F5H6G54 RESIDENT_GOVERNMENT_ENTITY "CORPORATE AFFAIRS COMMISSION" | deferred: unsupported_identity_kind, probable kind government, non-blocking |
| level1 | 1036 | 097900BGE10000044681 SOLE_PROPRIETOR (a person's name) | deferred: unsupported_identity_kind, no probable kind, non-blocking |
| level1 | 1298 | 097900BHFR0000075034 BRANCH "J&T BANKA, a.s., pobočka ..." | deferred: unsupported_identity_kind, probable kind branch, non-blocking |
| level1 | 6258 | 0T1CG46EXJPKIM1GY234 INTERNATIONAL_ORGANIZATION "WORLD HEALTH ORGANIZATION (WHO)" | deferred: unsupported_identity_kind, probable kind international_organization, non-blocking |
| level1 | 113 | 0292001629A3Q7XJ0D13 GENERAL "SFC SECURITIES LIMITED" (bad check digit) | deferred: invalid_lei_checksum, non-blocking |
| level1 | 48921 | 21380068P1DRHMJ8KU70 GENERAL "SHELL PLC" | assertion, kind company, 14 fields (below) |
| relationships | 0 | 001GPB6A9XPE8XJICC14 IS_FUND-MANAGED_BY 5493001Z012YSB2A0K51 | assertion, kind company, key ["001GPB6A9XPE8XJICC14","IS_FUND-MANAGED_BY"], edge from 2012-11-29 |
| relationships | 1 | 001GPB6A9XPE8XJICC14 IS_SUBFUND_OF C7J4FOV6ELAVE39B7M82 | assertion, kind company, edge IS_SUBFUND_OF |
| relationships | 9 | 010PWNH4K3BLIC3I7R03 IS_DIRECTLY_CONSOLIDATED_BY 549300COKYB5EGSU1838 | assertion, kind company, edge from 2017-12-06, properties status ACTIVE, registration_status LAPSED |
| relationships | 10 | 010PWNH4K3BLIC3I7R03 IS_ULTIMATELY_CONSOLIDATED_BY 549300B2Q47IR0CR5B54 | assertion, kind company, edge IS_ULTIMATELY_CONSOLIDATED_BY |
| relationships | 233 | 097900BHFR0000075034 IS_INTERNATIONAL_BRANCH_OF 31570010000000043842 | assertion, kind company, edge IS_INTERNATIONAL_BRANCH_OF |
| relationships | 2379 | 2138001O58LK96K8IT10 IS_FEEDER_TO 213800GOZXIM63WT7K19 | assertion, kind company, edge IS_FEEDER_TO |
| relationships | 688 | IS_ULTIMATELY_CONSOLIDATED_BY, INACTIVE, no RelationshipPeriods at all | deferred: ambiguous_relationship_period, BLOCKING |
| relationships | 41826 | IS_DIRECTLY_CONSOLIDATED_BY, status "NULL" | deferred: invalid_relationship_status_interval, BLOCKING |
| relationships | 155811 | start 4469000001BG7ASKSB18 (bad check digit, ANNULLED) | deferred: invalid_lei_checksum, non-blocking |
| reporting_exceptions | 0 | 001GPB6A9XPE8XJICC14 DIRECT parent, NON_CONSOLIDATING | deferred: reported_parent_exception, non-blocking |
| reporting_exceptions | 1 | 004L5FPTUREIWK9T2N63 (left off the list) | deferred: outside_approved_company_scope, non-blocking |
| reporting_exceptions | 48 | 0292001156F2T0UFG565 DIRECT parent, NATURAL_PERSONS, **with gleif:Deletion** | deferred: reported_parent_exception, non-blocking (the deletion flag is ignored) |

Shell plc, in full (`gleif.level1.v1`, record key `21380068P1DRHMJ8KU70`, effective
2026-05-12T08:40:56.083Z): name "SHELL PLC"; jurisdiction "GB"; address {street "SHELL CENTRE",
city "LONDON", region "GB-LND", postcode "SE1 7NA", country "GB"}; gleif_legal_form "B6ES";
gleif_entity_status "ACTIVE"; gleif_entity_creation_date "2002-02-05T00:00:00Z";
gleif_registration_authority "RA000585"; gleif_registration_authority_entity_id "04366849";
gleif_registration_status "ISSUED"; gleif_initial_registration "2016-06-30T00:00:00Z";
gleif_last_update "2026-05-12T08:40:56.083Z"; gleif_next_renewal "2027-07-04T00:00:00Z";
gleif_managing_lou "213800WAVVOPS85N2205"; gleif_validation_source "FULLY_CORROBORATED";
identifiers {lei}; provenance {artifact_sha256, member level1, record_key, adapter_version,
matching {headquarters_postal_code "SE1 7NA", headquarters_country "GB"}}. This matches the
four-companies test's expectation for Shell (jurisdiction "GB").

The dry run shows the Q8 caveat directly: the Fidelity fund (a FUND in Level 1) was on the
dry-run list, so its two relationship records became **Company**-kind assertions. With a real
Company list a Fund LEI is not on it, and those records wait outside the list instead.

Whole-file accounting through the same reader, with the widest possible list (every Level 1
LEI) so the counts show what the mapping decides (`scratch/account.py`):
- RR, 487,721: 487,293 assertions; 216 invalid_relationship_interval, 130
  invalid_relationship_status_interval, 75 ambiguous_relationship_period (these 421 block, if
  both LEIs are on the list); 1 invalid_lei_checksum; 6 outside the list (an end LEI that is not
  in the Level 1 file at all).
- REPEX, 6,351,397: 6,351,298 reported_parent_exception; 99 invalid_lei_checksum. (The
  accounting runs started before I added `invalid_lei_checksum` to the non-blocking list, so
  their `blocking` line still counts those 100; under the final file they do not block.)
- Level 1 (from the category and check-digit counts, not a reader pass): 3,043,084 GENERAL
  records with a valid LEI could become Company assertions if on the list; 385,137
  other-category records wait as unsupported_identity_kind, non-blocking; 256 bad check digits
  (178 GENERAL, 78 SOLE_PROPRIETOR) wait as invalid_lei_checksum, non-blocking.

## Step 8. Preview: stopped here

`edgar-warehouse rules run gleif --target mdm --preview` does not exist, and the skill says
stop. Hand-over to the operator: the file `repo/rules/sources/gleif/source.yaml`, the dry run
above (`scratch/dry-run.json`), and this log. Nothing was registered, activated or run against
any MDM database, and nothing is approved. Step 9 needs the operator's approval of the file
(and of Q2-Q10), which I do not have.

## Every guess I made (assumptions)

1. `bronze.family` / `contract.family` = `gleif_golden_copy` (Q4).
2. Q2-Q10 answers are my recommendations, not the operator's.
3. RR `kind: company` (Q8), and RR `identifiers: {lei: start}` as the way an RR record's
   subject gets bound to the Company that holds its child LEI. Nothing in the repo says how an
   RR record's subject is meant to bind; no identifier rule for `gleif.relationships.v1` exists.
4. RR record key `[start, relationship_type]` rather than including `end` (my reasoning about
   `patch` and parent changes; GLEIF's own key agrees).
5. RR edge properties limited to `status` and `registration_status` (accounting-standard
   qualifier, consolidation percentage and validation level left out, though reachable through
   `_native.*` paths).
6. `effective_time`, `completeness`, `record_key`, `publication_key` plain-words text is mine.
7. No `source_record_provenance` (so each record keeps artifact hash and member, which the
   native path supplies), and no extra `provenance` paths.
8. Unmapped Level 1 content (other names, OtherLegalForm, HQ address as a field, events,
   successors, geocoding, conformity flag, SubCategory for government records) is left as
   evidence in the raw record only.

## Findings for the operator (not decisions I could make)

- **The REPEX full file carries `gleif:Deletion` on 257,509 records (4.05%).** GLEIF's spec
  describes deletion flags in delta files. The reader ignores `Extension` and keeps every one as
  a live `reported_parent_exception`. If those are removals, 4% of the exceptions MDM would keep
  are ones GLEIF has withdrawn. The contract language cannot express a deletion.
- **Check-digit check runs before the scope check** in `gleif_source.record_evidence`, so every
  full run defers 256 + 1 + 99 annulled/duplicate LEIs whatever the Company list is. Q10 made
  them non-blocking; the alternative is a reader change (check scope first), which is code.
- **GLEIF writes the literal text "NULL"** for EntityStatus (9,062 LEI records) and
  RelationshipStatus (345 RR records). The mapping takes "NULL" in `gleif_entity_status` as a
  value, not as unknown; the name rule's eligibility test refuses it anyway. The reader refuses
  RR "NULL" status as invalid (blocking).
- **The language cannot take an RR record's kind from its child's Level 1 record**, nor limit an
  identifier to one registration authority (RA000665), nor turn a sentinel value ("8888",
  "NULL") into unknown.
- **The publication aggregate has no home in the rules file.** `gleif.publication.v1` (its
  `native_contract` and `publication_contract`, which name the three record sources and the
  Company LEI list) is built in test code (`tests/integration/test_clean_native_publications.py`);
  `dataset_contract` would crash on an `mdm` entry without `adapter.native_member`, so I did not
  add one.

## Skill gaps (what in the skill was unclear or wrong)

1. **Folder / `source:` naming conflicts with the code.** REFERENCE says `source:
   <provider>.<dataset>` and the folder name (e.g. `acme.registry`); the worked example is
   `sec.submissions.company`. `gleif_source.dataset_contract` hardcodes `rules_files.source("gleif")`,
   so the file must be `rules/sources/gleif/` with `source: gleif`. The skill should say to check
   code for a required folder name.
2. **`rules/merge/kinds/company.yaml` does not list the kind's fields**, although the skill says
   it "gives each kind's fields and which source wins each one". It has only `defaults.sources`
   and rules. The field names live in `store.COMPANY_NAMED_FIELDS` and migration 037.
3. **REFERENCE.md omits `nonblocking_deferred_reasons`**, a contract-level key that decides
   whether a run can ever finish (`bookkeeping.reconcile`). For a bulk source like GLEIF it is
   load-bearing. The skill never mentions blocking vs non-blocking set-asides.
4. **Step 7's dry-run call is wrong:** the `publication` dict lacks `artifact_sha256`, which
   `normalize` requires (KeyError). And for a native source (the reader reshapes RR records,
   applies the approved-Company-list check and sets every REPEX record aside) the dry run must go
   through the reader (`gleif_source.record_evidence`), not bare `normalize`; the skill does not
   say so.
5. **"Existing code for this source" does not mention tests.** The tests
   (`test_clean_gleif_source.py`, `test_clean_four_companies.py`, `test_clean_matching.py`)
   pinned most of the mapping; they were the best evidence I had. The skill should say to read
   and run them, and step 6 should run them as part of the load check.
6. **REFERENCE's `schema_version` ("the record shape the mapping reads")** does not say a native
   reader may require an exact value (`gleif-native-record-v1` here, checked by
   `native_consumption`).
7. **REFERENCE documents only `semantics: patch`** and says nothing about full snapshots vs
   deltas, which is what GLEIF publishes. I kept `patch`; the skill should say whether a full
   file is ever a snapshot in MDM's sense.
8. **Adding vs changing is ambiguous here.** The approved merge rules already name
   `gleif.level1.v1`, so this "new" source may be live. The skill cannot see the registry and
   gives no way to tell "registered" from "named in the policy".
9. **No home for a multi-member publication contract** (`gleif.publication.v1`) in the file
   shape.
10. **The profile step at this size.** A 13 GB JSON member profiles in about an hour in pure
    Python; the skill's "short script" advice does not warn about it. A line-based join pass
    (`scratch/l1table.py`) took ~20 min under load; `grep` for one field took 2 min.
11. **Some referenced material is missing from the repo copy:** `docs/specs/clean-mdm/native-gleif.md`
    (linked from four docs and the code) and `.scratch/company-mastering/research/08-rules.json`
    (needed to even collect `test_clean_matching.py`, `test_clean_company_source.py`,
    `test_clean_activation.py`).
12. **Step 5 says "one question at a time"**, but the trial could not reach the operator, so the
    order mattered less than the dependency: Q6/Q10 change the file, Q8 needs the Level 1 join
    first. The skill could say which questions block writing and which can wait for review.
13. **Source codes in docs disagree** (`source-evidence.md` proposes `gleif.lei` etc.; code and
    policy use `gleif.level1.v1`). The skill does not say which wins.

## Question count

Logged questions: 10 (Q1-Q10). Q5 was not asked because the repo answers it, so 9 were asked
(Q1, Q2, Q3, Q4, Q6, Q7, Q8, Q9, Q10), each with my recommendation assumed. No approval was
assumed.

## Trial-rule notes

- Files written in `repo/`: only `rules/sources/gleif/source.yaml`. Importing the package and
  running pytest also rewrote bytecode caches in 16 `__pycache__` folders under `repo/` (some
  existed before the trial, so I left them).
- Outside the sandbox: the harness saved two oversized tool outputs under `~/.claude/.../tool-results/`
  (the first `cat CONTEXT.md`, and the Golden Copy spec PDF from a WebFetch). I never opened either;
  I re-read CONTEXT.md in chunks and downloaded the PDF into `scratch/` instead.
- External requests: two web searches (the RA000665 code; `gleif:Deletion`); one WebFetch of
  gleif.org/en/lei-data/gleif-golden-copy; a WebFetch attempt and a curl download of the GLEIF
  Golden Copy and Delta Files spec PDF (gleif.org); a WebFetch and curl download of the GLEIF
  Registration Authorities List CSV (gleif.org; a GLEIF code list, not Golden Copy data). No request
  to any sec.gov or other SEC domain. No request for the captured source's data.
- All background jobs finished; none left running.
