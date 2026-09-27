# Rules log: onboarding the files in `inputs/` (Phase A, steps 1-5)

Sandbox: `trials/round-2/gleif`. Started 2026-09-26.

Provenance tags used below: [files] = profile of the captured files;
[code] = repo code; [docs] = repo docs; [public] = public web docs;
[assumption] = my guess, not yet confirmed.

## Step 1: Identify

- Inputs: three zip files, one JSON member each [files]:
  - `01-20260911-1600-gleif-goldencopy-lei2-golden-copy.json.zip`: 928 MB zipped,
    13.25 GB unzipped. Top level `{"records":[ ... ]}`. Each record has `LEI`,
    `Entity`, `Registration` (LEI-CDF shape, `{"$": value}` wrappers).
  - `01-20260911-1600-gleif-goldencopy-rr-golden-copy.json.zip`: 35 MB zipped,
    1.12 GB unzipped. Top level `{"relations":[ ... ]}`. Each item is a
    `RelationshipRecord` with `Relationship` (StartNode, EndNode,
    RelationshipType, RelationshipPeriods, RelationshipStatus) and
    `Registration` (RR-CDF shape).
  - `01-20260911-1600-gleif-goldencopy-repex-golden-copy.json.zip`: 64 MB
    zipped, 1.55 GB unzipped. Top level `{"exceptions":[ ... ]}`. Each item has
    `LEI`, `ExceptionCategory`, `ExceptionReason` (Reporting Exceptions).
- Identification: GLEIF (Global Legal Entity Identifier Foundation) Golden
  Copy, full concatenated files published 2026-09-11 16:00 (UTC per the file
  name). Three datasets: LEI Level 1 records (LEI-CDF, "lei2"), Level 2
  relationship records (RR-CDF, "rr"), Level 2 reporting exceptions ("repex").
  [files; file names]

### Is it new? No: the repo already knows this source [code]

- Reader exists: `edgar_warehouse/mdm/clean/gleif_source.py`. `record_evidence()`
  calls `normalize()`; `inspect_archive()` streams the JSON zip; driven by
  `native_consumption.prepare_native()` (run via `edgar-warehouse mdm mastering
  --model clean --manifest ...` per docs/specs/clean-mdm/local-operations.md).
- The reader reads its mapping with `rules_files.source("gleif")`, so the rules
  folder is fixed: `rules/sources/gleif/source.yaml`. That folder does NOT exist
  in this repo copy (only `rules/sources/sec.submissions.company/`). So
  `gleif_source.dataset_contract()` currently raises FileNotFoundError.
- Names the code fixes [code]:
  - `adapter.version` must be `gleif-native-record-v1` (VERSION), else
    record_evidence raises "Unregistered native GLEIF interpretation".
  - `contract.schema_version` must also be `gleif-native-record-v1`
    (native_consumption.py checks `contract.get("schema_version") != VERSION`).
  - `adapter.native_member` is one of `level1`, `relationships`,
    `reporting_exceptions` (FORMATS keys); one contract per member.
  - `adapter.classification` is refused for native GLEIF.
  - Publication family must be `golden_copy` (validate_release), and the dataset's
    `publication_families` must contain it (source_publications.verify).
  - `contract.family` must equal the acquisition manifest's `source_family`. No code
    or doc in the repo names GLEIF's acquisition source family. [gap]
  - CDF versions the reader accepts: `LEI_3.1`, `RR_2.1`, `REPEX_2.1`.
- Source code names:
  - `gleif.level1.v1` is live in `rules/merge/kinds/company.yaml`
    (`defaults.sources` rank 2 after SEC; source of both SEC-to-GLEIF name rules).
  - Relationship and REPEX source codes are named nowhere in code or rules.
    `docs/specs/clean-mdm/source-evidence.md` lists "proposed dataset codes"
    `gleif.lei`, `gleif.relationship`, `gleif.reporting_exception` (conflicts with
    the live `gleif.level1.v1` pattern). [docs]
- Referenced but missing from this repo copy: `docs/specs/clean-mdm/native-gleif.md`,
  every `.scratch/...` link (gleif-company-augmentation issues 13/15/16, the
  source-file catalog, ticket12 acceptance). [docs gap]

### Commands the skill names that do not exist

- `edgar-warehouse rules status` (step 1): no `rules` subcommand in
  `edgar_warehouse/cli.py` (grep of every add_parser). Skill says "Not built yet: ask".
- `edgar-warehouse rules profile` (step 2): same. Fallback used: scratch script.
- Note: running `python -m edgar_warehouse ...` to probe took >120 s just to import
  (heavy imports); grep of the parser was the practical check.

## Step 2: Profile [files]

Scripts: `scratch/profile.py` (every path, first 10,000 records per file) and
`scratch/fullcount.py` (lean pass that mirrors the reader's pre-normalize checks,
timed on 50,000 records first). Outputs: `scratch/profile-*-10k.json`,
`scratch/timing-*.json` (50k), `scratch/full-*.json` (full pass).

Timing on the sample: profiler 16.6 s / 10k Level 1 records (~90 min full, not
run); lean pass 31 s / 50k Level 1 (~35 min full), 18.6 s / 50k RR, 5.3 s / 50k
REPEX. Full passes run only for counts that decide something: how many records
each blocking reason hits, RR record-key uniqueness, REPEX volume.

### Level 1 (`lei2`, member `level1`), wrapper `records`, CDF LEI 3.1 shape
- Every value is wrapped `{"$": ...}`; attributes as `@name` (`@xml:lang`, `@type`).
- Record key candidate: `LEI.$`, 100% filled, unique in sample. LEI check = the
  reader's own `format_value(v, "lei")` (20 chars `[A-Z0-9]{18}[0-9]{2}`, ISO 7064
  mod 97 == 1). 10k sample: 9,997 pass, **3 fail the checksum**; all three are
  `GENERAL`, `EntityStatus` `NULL`, `RegistrationStatus` `ANNULLED`, same managing
  LOU `029200067A7K6CH0H586`, registered 2015-11-23 (e.g. `0292001629A3Q7XJ0D13`
  SFC SECURITIES LIMITED).
- `Registration.ManagingLOU.$`, `Entity.SuccessorEntity[].SuccessorLEI.$`, LEIs in
  `LegalEntityEvent[].AffectedFields` all pass mod 97 in the sample.
- 50k: EntityCategory GENERAL 46,084 / FUND 3,588 / SOLE_PROPRIETOR 187 /
  RESIDENT_GOVERNMENT_ENTITY 101 / BRANCH 39 / INTERNATIONAL_ORGANIZATION 1.
  EntityStatus ACTIVE / INACTIVE / literal text `NULL` (137).
  RegistrationStatus LAPSED, ISSUED, RETIRED, DUPLICATE, ANNULLED, PENDING_TRANSFER,
  PENDING_ARCHIVAL.
- Fields always filled: LegalName, LegalJurisdiction (ISO 3166 country or
  subdivision, `US`, `US-DE`), EntityLegalFormCode (ELF code; `8888` = see
  `OtherLegalForm` text, 10.9%), Registration dates, ManagingLOU,
  RegistrationAuthorityID (RA code). EntityCreationDate empty in ~36% (50k).
- Addresses: `LegalAddress` and `HeadquartersAddress`, each FirstAddressLine,
  AdditionalAddressLine (a **list** of `{"$"}`, absent in ~53%), City, Region
  (44%, ISO 3166-2), Country (100%), PostalCode (~99.9%), MailRouting (~10%),
  AddressNumber, AddressNumberWithinBuilding (rare). HQ postcode empty in 821/50k.
- Names: `OtherEntityNames.OtherEntityName[]` (5%, typed PREVIOUS_LEGAL_NAME,
  TRADING_OR_OPERATING_NAME, ALTERNATIVE_LANGUAGE_LEGAL_NAME),
  `TransliteratedOtherEntityNames` (14.5%). Names are organisation-shaped
  (funds, LPs, trusts); SOLE_PROPRIETOR records are person-shaped.
- Shape surprise: `Extension.gleif:Geocoding` is an object in ~35% and a list in
  ~2%. `Extension` is GLEIF-added geocoding/conformity, not LEI-CDF content.
- Repeated groups: LegalEntityEvents (17%), OtherEntityNames, SuccessorEntity (1%).
- Keys pointing at other records: SuccessorLEI, ManagingLOU (an LOU's own LEI).
- Identifier-like values besides the LEI: `RegistrationAuthorityEntityID` under
  182 RA codes. Digits-only <= 10 chars under many RAs (RA000585 7,884/50k,
  Delaware RA000602 file numbers). **None of these is a CIK by shape alone.**
  Under RA000665 the IDs look like SEC series IDs (`S000005113`). No CIK was taken
  from the files; none is needed.

### RR (`rr`, member `relationships`), wrapper `relations`, RR-CDF 2.1 shape
- Each item is `{"RelationshipRecord": {"Relationship": ..., "Registration": ...}}`.
- StartNode/EndNode NodeID: 100% filled, 100% pass mod 97 (10k); NodeIDType only
  `LEI` in sample.
- RelationshipType (50k): IS_FUND-MANAGED_BY 14,473, IS_ULTIMATELY_CONSOLIDATED_BY
  13,463, IS_DIRECTLY_CONSOLIDATED_BY 12,933, IS_SUBFUND_OF 8,882,
  IS_INTERNATIONAL_BRANCH_OF 204, IS_FEEDER_TO 45. All six are in
  `relationships.CONTRACTS`.
- RelationshipPeriods.RelationshipPeriod: an object (44%) or a list of 2-3 (56%),
  PeriodType RELATIONSHIP_PERIOD / ACCOUNTING_PERIOD / DOCUMENT_FILING_PERIOD.
- RelationshipStatus: ACTIVE, INACTIVE and literal `NULL` (2 in 50k).
- Qualifiers (accounting standard IFRS / US_GAAP / OTHER, ~50%), Quantifiers
  (percentage, ~3%). The reader's reshaped row drops both (kept only in `_native`).
- `(start, type)` and `(start, end, type)` both unique in 50k.
- Registration.ValidationReference often points at sec.gov URLs (data only; not
  fetched).

### REPEX (`repex`, member `reporting_exceptions`), wrapper `exceptions`
- 5 paths: LEI, ExceptionCategory, ExceptionReason[] (always a list of 1 in
  sample), ExceptionReference[] (rare free text), Extension.gleif:Deletion (null).
- First 10k all DIRECT_ACCOUNTING_CONSOLIDATION_PARENT: file appears sorted by
  category then LEI [assumption until full pass].

## Step 3: Research

- Terms [docs: CONTEXT.md]: GLEIF Fund Link keeps GLEIF direction and does not
  replace MANAGES_FUND; Accounting parent: "a missing parent is not proof of no
  parent"; IS_INTERNATIONAL_BRANCH_OF is Branch to head office.
- Company policy [docs: company-policy.md]: Q1 SEC universe plus approved GLEIF-only
  parents, not all global GLEIF; Q7 unsupported kinds remain evidence; Q14 "an LEI
  does not establish a CIK crosswalk merely because both values exist".
- Field semantics [docs: company-completion.md]: project LEI/link status, legal
  form/jurisdiction, entity/registration status, registration dates/authority,
  managing LOU, validation source, creation date; "Initially retain GLEIF names,
  addresses, legal events, expiration and successor LEIs as separate source
  evidence." SEC incorporation and GLEIF jurisdiction stay separate fields.
- KINDS [code: evidence.py]: company, person, security, fund_structure, branch,
  government, international_organization, venue.
- Company fields [code: store.COMPANY_NAMED_FIELDS]: name, sic, sic_description,
  state_of_incorporation, fiscal_year_end, description, jurisdiction, address, and
  eleven `gleif_*` fields (legal_form, entity_status, registration_status,
  initial_registration, last_update, next_renewal, managing_lou,
  validation_source, registration_authority, registration_authority_entity_id,
  entity_creation_date). So the GLEIF fields already exist; no new field needed.
- Ranks [rules/merge/kinds/company.yaml]: `defaults.sources` = SEC first, then
  `gleif.level1.v1`. No per-field overrides. So a GLEIF value wins only where SEC
  has none (GLEIF-only fields, or a GLEIF-only Company).
- Matching rules read from the GLEIF record [code: matching.py]: identifiers.lei;
  fields `name`, `gleif_last_update` (must equal the census's raw
  `Registration.LastUpdateDate.$`, name_census.py), `gleif_entity_status`,
  `gleif_registration_status`, `jurisdiction`; `matching.headquarters_postal_code`,
  `matching.headquarters_country`; kind must be `company` and only GENERAL may be
  company ("The GLEIF contract admits only GENERAL as a Company").
- `merge.check_company_sources` [code]: a Company assertion from a source code not
  in `defaults.sources` fails the whole batch. So an RR contract of kind company
  needs its code added to company.yaml (a merge-rules change).
- Relationship projection [code: relationships.py, merge.py]: a relationship claim
  projects only when the claiming record's own subject is bound; the subject is
  `digest([source_code, record_key])`, so RR records need their own binding. The
  only binding paths are identifier rules (family `binding`, namespace cik|lei) and
  the name rules; company.yaml has no `binding` rule today. So RR relationships
  would wait with `binding_required` until one exists.
- Reader scope [code: gleif_source.record_evidence]: records outside the
  manifest's `company_leis` defer as `outside_approved_company_scope`. Level 1 and
  REPEX check the LEI format BEFORE scope; RR checks format and NodeIDType before
  scope, and periods/status after scope. Every valid REPEX record defers as
  `reported_parent_exception` by design.
- Public docs [public: gleif.org]:
  - Golden Copy: released three times a day (page: 02:00, 10:00, 18:00 UTC; the
    file name says 1600, and pending-proofs.yaml calls this copy "2026-09-11 16:00
    UTC"). Contains "all LEIs ever published", i.e. historical as well as current
    records, so lapsed, retired and annulled LEIs are included. Delta files: 8 h,
    24 h, 7 d, 31 d windows. Formats JSON, XML, CSV.
  - LEI-CDF 3.1: EntityStatus `NULL` = "not applicable", applied to ANNULLED or
    DUPLICATE LEIs and to FUND LEIs. ANNULLED = "marked as erroneous or invalid
    after it was issued". This explains the 3 bad-checksum LEIs.
  - RA000665 = U.S. SEC, RA000602 = Delaware Division of Corporations: third-party
    hint only (Federal Reserve FEDS 2023-011 paper). GLEIF's own RA list is a
    PDF/CSV download; the PDF fetch landed outside the sandbox, so it was not
    opened. Consistent with the files (S0000xxxxx series IDs under RA000665).
  - Did not use api.gleif.org: it is the source's own data API (trial rule 4).

### Full-pass counts [files]
- RR (Python pass, 312 s CPU): 487,721 records. `(start, type)` unique across the
  whole file (0 duplicates), so is `(start, end, type)`. Types: IS_FUND-MANAGED_BY
  150,982; IS_ULTIMATELY_CONSOLIDATED_BY 132,877; IS_DIRECTLY_CONSOLIDATED_BY
  126,688; IS_SUBFUND_OF 73,834; IS_INTERNATIONAL_BRANCH_OF 1,959; IS_FEEDER_TO
  1,381. RelationshipStatus ACTIVE 487,316 / NULL 345 / INACTIVE 60.
  Reader reasons if every record were in scope: invalid_relationship_interval 216,
  invalid_relationship_status_interval 130, ambiguous_relationship_period 75 (no
  RELATIONSHIP_PERIOD at all), invalid_lei_checksum 1 (start node
  `4469000001BG7ASKSB18`, checked before scope, so it blocks whatever the scope).
- Public docs [public: RR-CDF 2.1 page]: RelationshipStatus `NULL` = "The
  relationship status is not applicable", a valid value. The reader treats
  status NULL as `invalid_relationship_status_interval` (a defect). Reader gap.
- Level 1 and REPEX: the Python pass was stopped (the machine was at load average
  ~180 on 4 CPUs, so ~3 h wall). Replaced by `unzip -p | grep -F -A1 | python`
  (`scratch/l1count.py`, `scratch/repexcount.py`), which reads the pretty-printed
  layout, not JSON. Cross-checked: on the first 200 MB it gives exactly the
  Python pass's result (51,820 records, same 3 bad LEIs). BSD awk was tried first
  and was too slow (76 s CPU per 200 MB).

## Step 4: Infer

Source name and folder: `gleif` (fixed by `rules_files.source("gleif")`) [code].
One `mdm` entry per member; the reader needs all three registered together
(`validate_release`: "Golden Copy requires L1, RR and REPEX together";
`record_sources` must cover all three FORMATS keys) [code].

Common to all three contracts [code unless marked]:
- provider GLEIF; `schema_version` and `adapter.version` `gleif-native-record-v1`;
  `publication_families: [golden_copy]`.
- `family`: the acquisition source family the GLEIF capture will use. Nothing in
  the repo names it. Convention is snake_case (`adv_bulk_dataset`,
  `company_facts`). Proposed `gleif_golden_copy` [assumption -> question].
- publication_key: the Golden Copy publication time (content date, here
  2026-09-11T16:00Z) as its sequence (`release_sequence`), plus the manifest.
- effective_time: the record's `Registration.LastUpdateDate` (the reader passes it
  as `effective_at`).
- semantics `patch`; completeness: a full Golden Copy file holds every LEI ever
  published, current and historical [public]; a delta holds changes only; the
  reader admits only records whose LEIs are in the manifest's approved Company
  scope (`company_leis`). No retirement by absence.
- Defaults: retain_deferred, source_record_provenance, field_shape nullable_text,
  `provenance.native_record: _native` (the reader keeps the raw record under
  `_native`) [skill REFERENCE Defaults + code].

Level 1 -> source code `gleif.level1.v1` (fixed by company.yaml) [rules]:
- Kind: `kind_field: Entity.EntityCategory.$`, `kind_values: {GENERAL: company}`
  only (matching.py: "The GLEIF contract admits only GENERAL as a Company") [code].
  `probable_kind_values`: FUND fund_structure, BRANCH branch,
  RESIDENT_GOVERNMENT_ENTITY government, INTERNATIONAL_ORGANIZATION
  international_organization [code KINDS + public], SOLE_PROPRIETOR person
  [public: "an individual acting in a business capacity"].
- Record key `[LEI.$]`, format `lei`; identifiers `lei: LEI.$`, format `lei`.
  The record key must be the bare LEI so an RR target_key `[end]` lands on the
  same subject (`subject_key(gleif.level1.v1, lei)`) [code].
- Fields (existing Company fields, no new ones):
  name Entity.LegalName.$; jurisdiction Entity.LegalJurisdiction.$;
  gleif_legal_form Entity.LegalForm.EntityLegalFormCode.$ [question: code vs text];
  gleif_entity_status Entity.EntityStatus.$ (kept as GLEIF writes it, including
  the text `NULL`: the language has no value mapping);
  gleif_registration_status Registration.RegistrationStatus.$;
  gleif_initial_registration Registration.InitialRegistrationDate.$;
  gleif_last_update Registration.LastUpdateDate.$ (must be the raw string: the
  Name Census stores it raw and the rule compares for equality);
  gleif_next_renewal Registration.NextRenewalDate.$;
  gleif_managing_lou Registration.ManagingLOU.$;
  gleif_validation_source Registration.ValidationSources.$;
  gleif_registration_authority Entity.RegistrationAuthority.RegistrationAuthorityID.$;
  gleif_registration_authority_entity_id
    Entity.RegistrationAuthority.RegistrationAuthorityEntityID.$;
  gleif_entity_creation_date Entity.EntityCreationDate.$.
  `address`: [question: leave out, HQ, or legal]. Docs say GLEIF addresses are
  retained as separate source evidence at first [docs].
  `name` is mapped even though the docs say GLEIF names are "retained as separate
  evidence": the name rules read `fields.name` [code wins; SEC outranks GLEIF, so
  it fills only a GLEIF-only Company].
- matching: headquarters_postal_code Entity.HeadquartersAddress.PostalCode.$,
  headquarters_country Entity.HeadquartersAddress.Country.$ (read by
  sec-gleif-name-postal) [rules + code].
- Not mapped: OtherEntityNames, transliterations, events, successor LEIs,
  Extension (geocoding, conformity flag), ValidationAuthority (usually equal to
  RegistrationAuthority). All stay in the native record [docs: retained evidence].

RR -> source code [question; proposed `gleif.relationships.v1`]:
- The reader reshapes each record to {start, end, relationship_type, valid_from,
  valid_to, status, registration_status, _native} [code]. Map from that shape.
- Kind `company` (every admitted record has both ends in the Company LEI scope).
- Record key `[start, relationship_type]`, unique over the whole file [files];
  a changed parent is then a new version of the same record, not a second edge
  that absence can never retire. Identifier `lei: start`, format lei, so an LEI
  binding rule could bind the record to its Company later.
- Relationship: `type_field: relationship_type`, `type_values` the six GLEIF types
  unchanged (all are in relationships.CONTRACTS, same spelling) [code];
  `target_key: [end]`, `target_source: gleif.level1.v1`; `valid_from: valid_from`,
  `valid_to: valid_to`; properties status, registration_status. `scope` is a literal
  in the language, not a path, so the accounting-standard qualifier stays in the
  native record only.
- Consequences [code]: (a) a Company assertion from a code missing from
  company.yaml `defaults.sources` fails its batch, so the RR code must be added
  there (merge-rules change, operator); (b) the RR record's own subject must be
  bound before its edge projects, and there is no `binding` rule in company.yaml,
  so edges will wait with `binding_required`.

REPEX -> source code [question; proposed `gleif.reporting_exceptions.v1`]:
- Every valid record is set aside by the reader as `reported_parent_exception`
  (evidence, never an assertion) [code]. A contract is still required.
- Kind `company` nominally (no assertion is ever produced), record key `[LEI.$]`
  format lei. [assumption: kind is never used]
- `(LEI, ExceptionCategory)` is the natural key: one LEI can hold a DIRECT and an
  ULTIMATE exception [files, full count pending].

Non-blocking reasons (expected, explained exclusions only):
- Level 1: `outside_approved_company_scope`, `unsupported_identity_kind`.
- RR: `outside_approved_company_scope`.
- REPEX: `outside_approved_company_scope`, `reported_parent_exception`.
Everything else stays blocking, including `invalid_lei_checksum`, `invalid_lei`,
`invalid_identity_kind`, the RR interval/status/period reasons,
`unsupported_relationship_endpoint`, `invalid_exception_reason`,
`missing_exception_reason`, `unsupported_exception_category`,
`invalid_native_field`, `missing_record_identity`.

### Level 1 full count [files, grep pass]
- 3,428,477 records; 0 duplicate LEIs. Categories: GENERAL 3,043,262; FUND
  248,988; SOLE_PROPRIETOR 127,272; RESIDENT_GOVERNMENT_ENTITY 6,955; BRANCH 1,913;
  INTERNATIONAL_ORGANIZATION 87. The 6,955 equals the figure in the comment in
  `gleif_source.py` for "the 2026-09-11 Golden Copy": cross-check that the count
  is right and that this is the publication the repo already measured.
- **256 LEIs fail the reader's checksum**: GENERAL/NULL/ANNULLED 177,
  SOLE_PROPRIETOR/NULL/ANNULLED 78, GENERAL/NULL/DUPLICATE 1. The reader checks
  the LEI before scope, so each is a blocking `invalid_lei_checksum` deferral in
  every full Golden Copy, whatever the approved scope. No rules-file setting can
  fix that without listing a defect as non-blocking, which the skill forbids.
  Fix belongs in the reader (check scope first, or set aside GLEIF-annulled or
  duplicate records as out of scope). Same for RR start node
  `4469000001BG7ASKSB18`.

### Reader bounds vs this publication [code + files]
- `inspect_archive` default `max_compressed` 1 GiB (1,073,741,824). Level 1 zip is
  927,550,946 bytes = 86% of it. A later Golden Copy may exceed it.
- `max_expanded` 16 GiB; Level 1 expands to 13,252,301,819 = 77%.
- `validate_metadata` caps `record_count` at 10,000,000. Level 1 3.43M, RR 0.49M,
  REPEX pending (~6.3M estimated).

### Registration: what the registered body must hold [code]
- `store.register_dataset(conn, code, registry_version, body)`: no caller in this
  repo copy. It needs an active acquisition-registry coverage row for
  `body["family"]`. `record_key`, `publication_key`, `adapter.record_key`,
  `adapter.record_key_format`, `adapter.identifiers`, `adapter.identifier_formats`
  are protected: changing them needs a new source code.
- `source_publications.verify(source_code=...)` reads the publication-level
  dataset from `mdm_v2.dataset` (append-only: its FIRST registered body). That
  body must carry keys REFERENCE.md never mentions:
  - `publication_families` containing `golden_copy`;
  - `publication_contract`: {version 1, format `clean-mdm-publication-v1`,
    continuity `sequence-predecessor-sha256-v1`, publication_family `golden_copy`,
    required_members (the three members), revision_versions {contract_version,
    parser_version, schema_version, configuration_version}, with parser and
    contract versions `gleif-native-record-v1`, replacement_scope <text>};
  - `native_contract`: {version `gleif-native-record-v1`, record_sources
    {level1: <code>, relationships: <code>, reporting_exceptions: <code>},
    company_leis: [explicit, unique list of LEIs]}.
- Which source code carries the publication-level contract is not named anywhere.
  `gleif_source.dataset_contract()` reads `contract["adapter"]["native_member"]`
  from every `mdm` entry, so a fourth entry without an adapter would raise
  KeyError when reached. It is safe only if listed after the three.
- **Correction to Step 3**: the approved Company scope `company_leis` is in the
  registered dataset contract (`native_contract`), not in the run manifest.
  Because `verify()` reads the append-only first body, changing that scope later
  needs a new publication source code, not a new mapping version.
- The scope is an explicit LEI list. The skill forbids guessing identifiers, and
  nothing in the repo holds the list. Question for the operator.

## Step 5: Ask (Phase A stops here; answers pending)

Asked in this order, one decision each, with my recommendation:
1. Identity: GLEIF Golden Copy full files, 2026-09-11 16:00 UTC, Level 1 + RR + REPEX?
   Rec: yes. Answer: pending.
2. Is any GLEIF source code (`gleif.level1.v1` at least) registered in Clean MDM,
   and if so what is its registered contract? `rules/sources/gleif/` is missing.
   Rec: if registered, copy it exactly; if not, write all as first versions.
   Answer: pending.
3. Source codes: RR `gleif.relationships.v1`, REPEX `gleif.reporting_exceptions.v1`,
   and a fourth, publication-level `gleif.golden_copy.v1` that carries the scope and
   publication contract (listed last in the file). Answer: pending.
4. Acquisition family name. Rec: `gleif_golden_copy`, one for all three files.
   Answer: pending.
5. Approved Company LEI scope (`company_leis`): where does the list come from?
   Rec: an approved, reproducible rule over these files (Name Census one-to-one
   pairs plus the accounting parents those LEIs name in RR), never hand-picked
   LEIs. Answer: pending.
6. Add the RR code to Company `defaults.sources` (last) in the merge rules; accept
   that RR edges wait until an LEI binding rule is approved. Rec: yes, add it
   last; binding rule is a separate change. Answer: pending.
7. Address: leave out, HQ, or legal? Rec: leave out; HQ postcode and country go to
   `matching` only. Answer: pending.
8. Legal form: ELF code or free text? Rec: code. Answer: pending.
9. The 356 bad-checksum records (256 Level 1, 1 RR, 99 REPEX) block every full run; the 422 RR records the reader
   rejects (345 with GLEIF-valid status NULL) block only if in scope. Rec: keep all
   blocking in the rules file; fix the reader first as a separate code change.
   Answer: pending.

## Gaps in the skill (for whoever fixes it)

Commands named that do not exist: `edgar-warehouse rules status`, `rules profile`
(and, by the skill's own note, `rules check`, `rules run`, `rules activate`, `rules
init`, `rules migrate` are not built; not reached in Phase A).

Unclear or wrong:
- Step 1 sends a source the repo already knows to "Change a source" (steps 3-9 plus
  a before/after record diff). Here the repo knows GLEIF but its rules file is
  missing, so there is no "before" and steps 2 and 4 (profile, infer) are still
  needed. The skill has no path for "known to the code, no rules file".
- REFERENCE.md omits constraints the native reader imposes: `schema_version` must
  equal `adapter.version` (`gleif-native-record-v1`); `contract.family` must equal
  the acquisition source family; `publication_families` must include
  `golden_copy`; `classification` is refused; `native_member` values are fixed.
- REFERENCE.md never mentions `native_contract` (`record_sources`,
  `company_leis`) or `publication_contract`, which the verifier requires in the
  registered body, nor which source code carries them.
- REFERENCE.md lists relationship `scope` among path keys; `normalize` reads it as
  a literal string.
- Neither file says `merge.check_company_sources` fails a whole batch when a
  Company-kind source code is missing from `defaults.sources`: adding a Company
  source always needs a merge-rules change.
- Neither says a relationship record from its own source needs its own subject
  binding before an edge projects; without a binding rule, relationships only wait.
- "A defect always blocks" has no path for records that are valid in the source
  but that the reader calls defects: GLEIF-annulled LEIs with bad check digits
  (published by GLEIF itself), RR `RelationshipStatus` `NULL` (valid in RR-CDF 2.1).
  It also does not say that the reader's check order (format before scope) makes
  some defects block even for records outside scope.
- Step 2 suggests "the first 10,000 records"; a sorted file (REPEX sorted by
  category) makes the first N unrepresentative. Worth saying: also sample from the
  middle or tail, or stratify.
- Step 2 gives no fallback when a full JSON pass is too slow; a grep over the
  pretty-printed layout, cross-checked against the JSON pass, was 30x faster.
- Research step: repo docs link `docs/specs/clean-mdm/native-gleif.md` and many
  `.scratch/` files that are absent in this copy.
  `docs/specs/clean-mdm/source-evidence.md` proposes codes (`gleif.lei`,
  `gleif.relationship`, `gleif.reporting_exception`) that conflict with the live
  `gleif.level1.v1`. The skill does not say which wins (I took the live rules).
- The skill does not separate the source's documentation from its data API
  (`api.gleif.org`); I treated the API as "the source" and did not call it.
- "Never guess an identifier" does not say how an approved scope list of
  identifiers is to be produced when the reader requires one.
- Running `python -m edgar_warehouse ...` to probe for commands took >120 s just to
  import; a cheap `rules --help` would help.

### REPEX full count [files, grep pass] (added after the questions were drafted)
- 6,351,397 records = 64% of the reader's 10,000,000 record cap
  (`validate_metadata`). DIRECT 3,179,314 / ULTIMATE 3,172,083. `(LEI, category)`
  unique; one LEI can hold both categories, so the natural record key is
  `[LEI.$, ExceptionCategory.$]`, not the LEI alone (corrects the Step 4 draft).
- ExceptionReason: NATURAL_PERSONS 2.36M, NON_CONSOLIDATING 2.20M, NO_KNOWN_PERSON
  1.34M, NO_LEI 243k, NON_PUBLIC 217k, and five rare reasons; all in the reader's
  EXCEPTION_REASONS. A list of 1 in 99.8%, up to 8.
- 99 records carry an LEI failing the checksum (e.g. `4469000001BG7ASKSB18`, the
  same LEI as the bad RR start node; others under the `5555001...` prefix). Checked
  before scope, so they block every full run too. Total blocking bad-checksum
  records across the three files: 256 + 1 + 99 = 356.
- `Extension` present on 257,509 records (`gleif:Deletion`, null in the sample).

## Step 5: operator's answers (Phase B)

1. Yes: GLEIF Golden Copy full files, 2026-09-11 16:00 UTC.
2. Nothing is registered and nothing can be recovered: treat as new, keeping every
   name the code already fixes.
3. Use `gleif.relationships.v1` and `gleif.reporting_exceptions.v1` beside
   `gleif.level1.v1`. No fourth contract in this rules file: the publication-level
   contract (approved Company LEI list, publication details) has no home in
   `rules/` today. -> logged as a gap below.
4. One capture family for all three files, named after the source, as the rules
   folder is named -> `gleif`.
5. The approved Company LEI list is not part of this rules file. The record says
   the first slice uses "manually approved or deterministic Company-to-LEI source
   links"; no production list exists. Do not make one up; log my recommendation
   as a proposal.
6. Do not change the merge rules in this trial. Log the exact code that makes a
   relationship batch fail without it.
7. GLEIF's LEGAL address fills Company `address`, behind SEC (operator decision
   2026-09-24: name, jurisdiction and address are one field each across SEC and
   GLEIF, SEC first; the master takes every field from every source; later than
   the GLEIF field ticket, so it wins). HQ postcode and country go to matching only.
8. The legal-form code.
9. Keep all defects blocking. The reader fixes (scope before check digit, annulled
   and duplicate LEIs, "NULL" status) are already a separate code ticket.

### Proposal only (answer 5): how the approved Company LEI list could be built
Not a list, and not used by the rules file. A reproducible rule over pinned inputs,
approved on its own: (a) LEIs bound deterministically or manually to an SEC Company
(the first slice's "manually approved or deterministic Company-to-LEI source
links"), plus (b) the LEIs the Name Census pairs one-to-one with an SEC Company
(so the name rules can decide them), plus (c) the direct and ultimate accounting
parents those LEIs name in the RR file (Company Q1). Every LEI taken from the files,
checked by `format_value(..., "lei")`, frozen with the digest of the inputs.

### Gap (answer 3): the publication-level contract has no home in `rules/`
`source_publications.verify(source_code=X)` reads ONE registered dataset body that
must carry, beyond a record contract: `family` (`gleif`), `publication_families`
[`golden_copy`], `publication_contract` {version 1, format
`clean-mdm-publication-v1`, continuity `sequence-predecessor-sha256-v1`,
publication_family `golden_copy`, required_members [level1, relationships,
reporting_exceptions], revision_versions {contract_version, parser_version (both
`gleif-native-record-v1`), schema_version, configuration_version},
replacement_scope <text>}, and `native_contract` {version
`gleif-native-record-v1`, record_sources {level1: gleif.level1.v1, relationships:
gleif.relationships.v1, reporting_exceptions: gleif.reporting_exceptions.v1},
company_leis [...]}. What a home would need:
- a place in `rules/sources/gleif/` that `gleif_source.dataset_contract()` does not
  iterate as a record contract (it reads `contract["adapter"]["native_member"]`
  from every `mdm` entry and would KeyError on an entry without it), e.g. a
  separate `publication:` section or file;
- a reader in `edgar_warehouse.rules.files` for it, and REFERENCE.md keys;
- a separate, approved, versioned home for `company_leis` (a pinned identifier
  list, not hand-edited YAML), because `verify()` reads the append-only first body
  from `mdm_v2.dataset`: changing the scope later needs a new publication source
  code, not a new mapping version.

## Step 6: Write

- Values built in `scratch/build_rules.py`, dumped with `files.dumps`; the script
  asserts `files.loads(dumps(doc)) == doc`. Comments then added by hand in
  `repo/rules/sources/gleif/source.yaml`.
- Check: the skill's command `files.source('gleif')` loads; the hand-commented file
  equals the dumped document exactly; `gleif_source.dataset_contract(member)` (the
  reader's own lookup) returns each of the three contracts with the member,
  version, schema_version and family the consumer checks.
- Choices beyond the operator's answers (each has a comment in the file):
  - RR `record_key` [start, relationship_type] [files: unique over 487,721];
    `identifiers.lei: start` so a later LEI binding rule can bind the record.
  - REPEX `record_key` [LEI.$, ExceptionCategory.$] [files: one LEI can hold both];
    no `kind` (no exception becomes an MDM record) [code]; `effective_time`
    unknown (REPEX has no Registration block, so the reader passes None) [code].
  - `probable_kind_values.SOLE_PROPRIETOR: person` [public: GLEIF definition].
  - Address components: MailRouting, AddressNumber, AddressNumberWithinBuilding
    left out (no component in the language) [code: ADDRESS_COMPONENTS].
  - `publication_families: [golden_copy]` on each record contract [code:
    validate_release; skill REFERENCE].
- Guesses: none about identifiers. `publication_key` and `completeness` are plain
  words from the code and public docs.

## Step 7: Check (dry run on a bounded sample)

- `edgar-warehouse rules check gleif`: does not exist (no `rules` command). Used
  the skill's fallback: ran the source's reader on a sample.
- Sample (`scratch/select_sample.py`, first 60,000 records of Level 1 and RR only,
  plus two REPEX records located by line number because REPEX is sorted by
  category): 17 Level 1 (one of each category, an annulled bad-check-digit LEI, a
  record left out of scope, and the Level 1 records of every RR endpoint picked),
  8 RR (one per type with both ends in the sample, one with no
  RELATIONSHIP_PERIOD, one with status NULL, one outside scope), 7 REPEX (direct,
  ultimate for the same LEI, NON_PUBLIC, two reasons, bad check digit, out of
  scope). More than the skill's 5-10 records: RR endpoints need their Level 1
  records to check the relationship target.
- How (`scratch/dryrun.py`): each member's picks are written in Golden Copy JSON
  shape to `scratch/sample/<member>.dry-run.json.zip`; the reader's own
  `inspect_archive` verifies it (sha256, one member, record count, JSON parser that
  refuses duplicate keys; `tempfile.tempdir` pointed into scratch); each record
  goes through `gleif_source.record_evidence` (the reader), which reshapes RR,
  applies its checks and calls `normalize` with this rules file's contract.
  Publication as the skill says: {artifact_sha256: sha256 of the sample zip,
  member: file name, publication_key "dry-run", revision 0}. The sample zip's
  digest is not the real file's.
- Scope: the reader needs `eligible_leis`. There is no approved list (operator), so
  the dry run uses a labelled FIXTURE taken from the sample's own LEIs, in two
  variants: every sample LEI (`scratch/dry-run.json`) and Company-only, i.e. Level
  1 GENERAL LEIs (`scratch/dry-run-general-only.json`). It is not a proposal.
- No database: `store.register_dataset`'s own checks (reasons distinct, probable
  kinds in KINDS, formats known) were run with a stub connection that stops at the
  registry query. All three contracts pass them. The consumer's contract check
  (native_member, version, schema_version, family) passes for all three.

### What MDM would receive (Company-only scope)
- Level 1 (17): 7 Company assertions; 9 set aside `outside_approved_company_scope`
  (non-blocking; probable kinds fund_structure, branch, person, government,
  company); 1 set aside `invalid_lei_checksum` (BLOCKS: `0292001629A3Q7XJ0D13`,
  GLEIF-annulled).
  A Company assertion carries: identifiers {lei}; fields name, jurisdiction
  (`US-DE`), address from the LEGAL address (street, street2 = additional lines
  joined by newline, city, region `US-DE`, postcode, country), the eleven gleif_*
  fields (empty EntityCreationDate becomes `unknown`, not a value);
  provenance.matching {headquarters_postal_code, headquarters_country} (e.g.
  legal postcode 19808 vs HQ 10106 for `004L5FPTUREIWK9T2N63`, so both are kept
  apart as intended); provenance.source.native_record = the whole raw record;
  effective_at = LastUpdateDate. About 3 KB each.
- RR (8): 2 assertions (IS_DIRECTLY_ and IS_ULTIMATELY_CONSOLIDATED_BY, start
  `0292001568C3M3WGI292` -> end `0292004558B0R5B7I133`, valid_from 2014-04-28,
  properties status ACTIVE, registration_status PUBLISHED); 4
  `outside_approved_company_scope` (the fund, sub-fund, branch links: their start
  is not a Company); 1 `ambiguous_relationship_period` (BLOCKS); 1
  `invalid_relationship_status_interval` for GLEIF's valid status NULL (BLOCKS).
- REPEX (7): 3 `reported_parent_exception` (non-blocking evidence), 3
  `outside_approved_company_scope`, 1 `invalid_lei_checksum` (BLOCKS:
  `4469000001BG7ASKSB18`).
- Blocking in the sample is exactly the defects the operator kept blocking.

### Cross-checks [code]
- Every relationship's `target_subject` equals `subject_key("gleif.level1.v1",
  end LEI)`, i.e. the subject of the end's Level 1 record (5/5).
- Every assertion and deferral passes `validate_assertion` / `validate_deferred`;
  reading each record twice gives the same id (stable).
- Name rules: `matching._value(a, "gleif_last_update")` is byte-equal to the raw
  `Registration.LastUpdateDate.$` the Name Census stores (7/7); `_eligible` reads
  the status fields (RETIRED/INACTIVE record fails, others pass); `_read` finds
  `matching.headquarters_postal_code` / `_country`.
- `merge.check_company_sources(files.policy(), ...)`: Level 1 passes; REPEX passes
  (no assertions); **RR FAILS: "Company policy has no source priority for:
  gleif.relationships.v1"**. The code (answer 6), `edgar_warehouse/mdm/clean/merge.py`
  lines 33-49, called at line 424 inside the Merge Stage commit path:
      declared = set(defaults.get("sources", []))
      present = {a["source_code"] for a in assertions if a["kind"] == "company"}
      missing = present - declared
      if missing:
          raise Conflict("Company policy has no source priority for: " + ...)
  It fails the whole batch. Fix (not made; needs the operator's own approval): add
  `gleif.relationships.v1` to `rules/merge/kinds/company.yaml` `defaults.sources`.
- Found by the all-sample-LEIs variant: when the scope holds a FUND or BRANCH LEI,
  RR records starting there become `company` assertions (the contract states
  `kind: company`; the reader checks only that both ends are in scope). So the RR
  contract is right only if the approved scope holds Company (GENERAL) LEIs only.
  Nothing enforces that. Recorded for the publication-contract gap and the reader
  ticket.
- Tests: the repo copy has no tests, so none for the reader were run.
- This dry run is not a preview: it matches nothing against existing records,
  binds nothing, and runs no Merge Stage.

## Step 8: Preview
`edgar-warehouse rules run gleif --target mdm --preview`: does not exist. Stopped
here, as the skill says. Handed over: the rules file, the dry run
(`scratch/dry-run-general-only.json`, `scratch/dry-run.json`) and this log.

## Gaps in the skill found in steps 6-7
- `rules check` and `rules run --preview` do not exist.
- Step 7's fallback assumes the reader takes a record and a contract. This reader
  also needs an approved identifier scope (`eligible_leis`) and pinned publication
  metadata (record count, content date, archive sha256, CDF version). The skill
  does not say what to use when no approved scope exists. The fixture chosen
  changes the result: with fund and branch LEIs in scope, RR records became Company
  assertions.
- Running the reader on the real file is not bounded: `inspect_archive` hashes and
  snapshots the whole 928 MB zip into the system temp directory and parses all
  13 GB before it returns. I built small sample zips in Golden Copy shape and
  pointed `tempfile.tempdir` into scratch. The skill could say "sample archive in
  the source's own shape".
- Step 7 says pass `policy=files.policy()` to `normalize`; the reader's
  `record_evidence` takes no policy (native GLEIF refuses classification). The
  direct-`normalize` route would also skip the reader's RR reshaping, so it would
  test the wrong record shape.
- Step 7's `publication.member` = file name; this reader passes the member name
  (`level1`). Harmless here (`source_record_provenance` drops it), but the two
  disagree.
- Registration checks need a database; the skill offers no offline check. A stub
  connection runs `register_dataset`'s own checks. A `rules check` should do that.
- REFERENCE Defaults' `provenance.native_record: <key>` does not say how to find
  the key; it is `_native`, found only in `record_evidence`.
- REFERENCE: `street2: lines:` needs a list of `{"$": text}` objects (GLEIF shape),
  not a list of strings. The reader's XML path turns a single AdditionalAddressLine
  into an object, not a list, which `mapped_field` refuses as `invalid_field_shape`
  (blocking). Fine for JSON, which this capture is.
- REFERENCE has no way to state a relationship record's kind from the other
  file's category (the start node's Level 1 EntityCategory); `kind: company` is
  only correct under a Company-only scope.
- Step 6's "check that it still loads" catches YAML errors only. Also worth doing:
  compare the hand-commented file with the dumped values (a comment added inside
  a folded multi-line value would silently change it); I did.
- `files.dumps` folds long plain-word values over several lines, so a hand comment
  can only go between keys, not beside a long value.
- Process slip (mine): once I invoked `repo/.venv/bin/python` directly with an
  empty script instead of `uv run --no-sync python`. It ran nothing.

## Current state (read this first; it supersedes earlier drafts above)

Superseded lines in Steps 3-4: family `gleif_golden_copy` (now `gleif`, operator);
address as an open question (now the LEGAL address, operator); REPEX key
`[LEI.$]` (now `[LEI.$, ExceptionCategory.$]`, full count); REPEX "kind company
nominally" (now no kind); "the manifest's `company_leis`" (it is in the
registered publication-level dataset body, which has no home in `rules/`).

- File: `repo/rules/sources/gleif/source.yaml`, three contracts
  (`gleif.level1.v1`, `gleif.relationships.v1`, `gleif.reporting_exceptions.v1`).
  Loads; equals the `files.dumps` values; passes register_dataset's own checks
  and the consumer's contract check. NOT approved.
- Identity choices that are frozen once registered (a change needs a new source
  code, `store.PROTECTED_*`), mine, for the operator to approve explicitly:
  RR `record_key [start, relationship_type]` (unique over the full RR file);
  RR `identifiers.lei: start` (checked: no holder lookup reads it, all are scoped
  to the issuing source); REPEX `record_key [LEI.$, ExceptionCategory.$]`
  (unique over the full REPEX file). Level 1 `record_key [LEI.$]`, format `lei`,
  and `identifiers.lei` follow from the code and the merge rules.
- Before a real run, outside this file: (1) operator approval; (2)
  `gleif.relationships.v1` in company.yaml `defaults.sources` (else every RR batch
  fails); (3) a home for the publication-level contract and the approved Company
  LEI list, Company (GENERAL) LEIs only; (4) the reader ticket (356 bad-check-digit
  records stop every full run; status NULL); (5) an LEI binding rule, without
  which RR edges only wait.
- Data note: GLEIF regions are ISO 3166-2 (`US-DE`), SEC's are bare (`DE`); with
  address one field, SEC first, a GLEIF-only Company shows the ISO form.
