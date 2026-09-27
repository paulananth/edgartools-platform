# Rules skill log — onboarding the source in inputs/ (trial round 2, Phase A)

Operator reads this. Sources of each inference are tagged:
[profile] = the captured files, [code] = repo code, [docs] = repo docs,
[public] = public web docs (never sec.gov), [assumption] = my guess.

## Step 1 — Identify

- inputs/submissions/: 40 JSON files named CIK##########.json (1.4 KB–185 KB).
  One JSON object each: cik, entityType, sic, name, tickers, exchanges, ein,
  lei, addresses{mailing,business}, formerNames[], filings{recent{...parallel
  arrays...}, files[]}. [profile]
- inputs/tickers/company_tickers.json (795 KB): object keyed "0".."N", each
  {cik_str, ticker, title}. [profile]
- inputs/tickers/company_tickers_exchange.json (521 KB): {fields:[cik,name,
  ticker,exchange], data:[[...],...]} — a table as parallel rows. [profile]
- Looks like: SEC EDGAR "submissions" API documents (one per filer/CIK) plus
  SEC's company-ticker catalogs. [profile + general knowledge; sec.gov not
  consulted per hard rule]

## Commands the skill names that did not exist

- `edgar-warehouse rules status` (step 1): `edgar-warehouse --help` lists no
  `rules` subcommand. `edgar-warehouse rules --help` did not even fail fast:
  it hung past a 120 s timeout (exit 124) — the whole CLI import is slow.
  Did instead: asked the operator (question below).
- `edgar-warehouse rules profile <files>` (step 2): does not exist. Did
  instead: a scratch script, `scratch/profile.py`.
- `edgar-warehouse rules check`, `rules run`, `rules activate`, `rules init`,
  `rules migrate` (steps 7–9): not reached in Phase A; the CLI has no `rules`
  group at all, so all are missing.

## Step 1 — Is it new? No: the repo already names this source

- `rules/merge/kinds/company.yaml` ranks `sec.submissions.company.v1` first in
  `defaults.sources`, and its classification rule `sec-company-candidate`
  (2026-09-25.13) and both name rules name it as `source`/`holder_source`. [code]
- The reader exists: `edgar_warehouse/mdm/clean/company_source.py`
  (`SOURCE_CODE = "sec.submissions.company.v1"`, line 36:
  `rules_files.mdm_contract("sec.submissions.company", SOURCE_CODE)`). So the
  folder name `sec.submissions.company` and source code
  `sec.submissions.company.v1` are fixed. [code]
- The rules file that line reads, `rules/sources/sec.submissions.company/source.yaml`,
  is ABSENT from this repo copy. Consequence, verified: `import
  edgar_warehouse.mdm.clean.company_source` fails with FileNotFoundError, so
  `mdm prepare-clean-company`, `mdm name-census` and `mdm bronze-receipts`
  cannot run until the file exists. [code, verified]
- The reader does not read the raw JSON. Its command is `edgar-warehouse mdm
  prepare-clean-company` (edgar_warehouse/mdm/cli.py:42), reading silver
  landing Parquet: `sec_company` rows plus, per CIK, `forms`
  (`sec_company_filing`), `business_address` (`sec_company_address`, type
  business), `tickers` (`sec_company_ticker`, ordered by `source_rank`),
  `name_census` and `_origin`. Raw JSON -> silver rows is
  `edgar_warehouse/loaders/bronze_submission_extractors.py`
  (`stage_company_loader` etc.) and `silver_landing_store._parse_company_ticker_rows`.
  Normalize is called from `mdm/clean/cli.py::batch_input` on the bundle's
  records.jsonl. So the mapping maps from the reader's record, not the JSON. [code]
- Skill says: not new -> follow "Change a source" (steps 3–9). The trial asks
  for "Add a source" 1–5; I did steps 2–5 anyway and treat this as writing
  the missing file for a known source. Registered-or-not is question 2.

## Step 2 — Profile (scratch/profile.py, scratch/classify_preview.py)

Everything read whole: files are small (40 × ≤185 KB; catalogs 0.8 MB and
0.5 MB). Full pass took ~10 s including uv start-up. Output: scratch/profile.txt,
scratch/classify_preview.txt. All [profile].

Record types found:
1. Filer header (one per submissions file, 40): same 24 top-level keys in all
   40. Candidate key `cik` (10-digit zero-padded string, 40/40 filled,
   distinct, equals the file name). `name` also distinct here, not a key.
   entityType: other 35, operating 5. sic/sicDescription/category/tickers/
   exchanges filled only 7/40. stateOfIncorporation 18/40 (includes `U0`, an
   EDGAR foreign code, for a Singapore firm). fiscalYearEnd 20/40 (MMDD text,
   e.g. "0926"). description, website, investorWebsite, flags: 0/40 filled.
   phone 20/40. ownerOrg 7/40.
2. addresses (mailing + business per filer, 80): street1/2, city,
   stateOrCountry, zipCode, stateOrCountryDescription, isForeignLocation,
   foreignStateTerritory, country, countryCode. Foreign: countryCode X0/U0
   with stateOrCountry empty (matches the reader's comment).
3. formerNames[] (7 rows, 5 filers): keys `name`, `from`, `to` (ISO
   timestamps). NOTE: `stage_former_name_loader` reads `entry.get("date")`,
   a key the files never have, so silver `date_changed` is always null.
   Reader defect for silver; MDM does not read it. [profile + code]
4. filings.recent: a table as parallel arrays (16 columns, equal lengths in
   all 40 files); zipped to 7,013 rows. Key `accessionNumber` (unique).
   `core_type` and `isXBRLNumeric` exist in the files but the silver loader
   drops both. The reader uses only the distinct `form` set per CIK.
5. filings.files[] (6 rows, 4 filers): pagination documents (name,
   filingCount, filingFrom, filingTo). Their contents are NOT in inputs/, so
   the reader's `forms` for Apple, Microsoft, Amazon, Shell would include
   forms these captured files cannot show.
6. company_tickers.json: 10,391 rows {cik_str int, ticker, title}; keyed
   "0".."10390". `ticker` unique; cik_str 8,001 distinct (1–8 tickers each).
7. company_tickers_exchange.json: {fields:[cik,name,ticker,exchange], data}
   parallel rows, zipped to 10,391. Same (cik,ticker) pairs and same names
   as file 6, but in a DIFFERENT ROW ORDER. exchange: Nasdaq 4361, NYSE 3300,
   OTC 2494, CBOE 35, null 201.

Identifiers checked:
- CIK: all 40 are ^\d{10}$ and match their file names; catalog ciks are ints
  (up to 7 digits here), zero-padding makes them comparable. Checked by regex
  and by the repo's `_sec_cik` rule (digits, ≤10, nonzero).
- LEI: 1 of 40 filers carries `lei` = 254900W3REVJHWYFN607 (CIK 0002032331,
  Arrowpoint Investment Partners (Singapore) Pte. Ltd.); 20 chars, passes
  mod 97 (repo `_lei` algorithm). The silver loader does NOT land `lei`.
- EIN: 19/40 filled, all 9 digits; `000000000` five times (a placeholder, not
  an identifier). Not an MDM namespace (FORMATS has sec_cik and lei only).
- Tickers: submissions `tickers` vs the catalogs agree for 39/40; CIK
  0001806201 (Open Lending Corp) lists LPRO in its submissions file but is in
  neither catalog. The reader takes tickers from the catalog only.
- Only 6 of the 40 CIKs appear in the catalogs.

Names: 5 operating + 2 foreign-private `other` filers are companies (Apple,
Microsoft, Amazon, Editas, Open Lending, ASML, Shell). 21 `other` filers are
person-shaped ("KLEMP WALTER V", "Gupta Mahendra R", forms 3/4/144 only).
The rest are 13F managers, Form D issuers/SPVs/funds, a trust.

Candidate relationships: catalog cik -> filer cik (a join key the reader
uses to pin tickers, not an MDM relationship). No filer-to-filer keys in
submissions. formerNames = earlier names of the same CIK (aliases).

Classification preview: records built BY HAND in the reader's shape from
the JSON (the reader needs silver landing Parquet I do not have; forms from
filings.recent only), run through the live rule `sec-company-candidate`
2026-09-25.13 with `classification.fired`: step 8 company 5, step 10
company 2, step 9 deferred (person) 2, step 11 deferred 31. [profile + code]

## Step 3 — Research

- CONTEXT.md: Company Identity, Probable Kind, Source Stage, Name Census,
  Dataset Contract, Identifier Contract, Mastering Policy. A rename stays one
  Company; the old name is an alias. [docs]
- docs/specs/clean-mdm/source-evidence.md: source_code is a dataset; missing
  effective time stays explicit; a limit-bound sample never proves absence;
  transport paths stay out of business hashes. [docs]
- docs/specs/clean-mdm/company-policy.md: confidence bands (2026-09-24) —
  50–95% "waits in the Stage with no kind or link. No Steward"; Q8 "keep
  different concepts in separate fields"; Q14 identifier binding needs an
  Identifier Contract. [docs]
- docs/specs/clean-mdm/local-operations.md "Prepare a native Company sample":
  the bundle, its pinned members, and "each record carries its postcode,
  country and census entry in provenance.matching". [docs]
- KINDS (evidence.py): company, person, security, fund_structure, branch,
  government, international_organization, venue. [code]
- COMPANY_NAMED_FIELDS (store.py): name, sic, sic_description,
  state_of_incorporation, fiscal_year_end, description, jurisdiction,
  address, + 12 gleif_* fields. Identifier columns: cik, lei. [code]
- Merge rules: defaults.sources = [sec.submissions.company.v1,
  gleif.level1.v1] for every field. GLEIF file comment: "`name` is shared
  with SEC, SEC first where both supply it. `jurisdiction` is GLEIF's alone
  (operator, 2026-09-24)." [repo rules file]
- Classification: fields the rule reads from the reader's record: sic,
  category, tickers, entity_type, entity_name, forms. Name rules read fields
  `name`, `state_of_incorporation` and `matching.business_postal_code`,
  `matching.business_country`; matching.py reads `matching.name_census`. [code]
- store.register_dataset refuses a contract with both `classification` and
  `kind`/`kind_field` (one writer of the kind). [code]
- merge.py: a deferred record is a review, `blocking` unless its reason is
  in the contract's `nonblocking_deferred_reasons`. normalize raises
  `classification_deferred` for a held-back record,
  `classification_not_activated` for an unactivated company verdict. [code]
- `publication_families` is read only by source_publications.py (native,
  numbered, verified publications, e.g. GLEIF golden_copy). The SEC reader
  does not go through it. [code]
- Bronze families: `submissions` and `reference_catalog`
  (acquisition/source_family_registry.py). [code]
- Public docs: SEC's own documentation is on sec.gov (blocked). Third-party
  hint only (apis.io / sec-edgar-api pages): submissions JSON = filer header
  + recent filings inline + `files` for older pages, one document per CIK,
  current state. No page says when a header field took effect. [public,
  third-party, hint only]

## Step 4 — Inferences (one record type maps to MDM: the filer)

| Item | Inference | Source |
|---|---|---|
| Folder / source code | `sec.submissions.company` / `sec.submissions.company.v1` | code (fixed by the reader) |
| Record type in scope | the filer header, as the reader's record | code |
| Kind | not stated: `classification: {kind: company, rule_id: sec-company-candidate, version: "2026-09-25.13"}` | code + rules/merge |
| Record key | `[cik]`, `record_key_format: sec_cik` (10 digits zero-padded; Name Census compares to it) | code + profile |
| Identifiers | `cik: cik`, format `sec_cik` | code + profile |
| Fields | name: entity_name; sic: sic; sic_description: sic_description; state_of_incorporation: state_of_incorporation; fiscal_year_end: fiscal_year_end; description: description (0/40 filled; blank reads as unknown) | code (COMPANY_NAMED_FIELDS) + profile |
| Not mapped | jurisdiction (GLEIF's alone, operator 2026-09-24); address (question 4); gleif_* | repo rules file |
| Matching | business_postal_code: business_address.postal_code; business_country: business_address.country; name_census: name_census | code + docs |
| Relationships / profiles | none | profile + code |
| Provenance | no `provenance` map: the reader keeps no native record; the bronze object travels as `_origin.bronze`, an occurrence outside the hash | code |
| semantics | patch; absence never retires an identity | REFERENCE + docs |
| completeness | one capture run's sec_company landing with its filings, business addresses, ticker catalog and Name Census; prepare-clean-company takes a bounded sample (limit ≤1000), never whole-source complete | code (scope.whole_source_complete false) |
| effective_time | unknown (reader sets effective_at null; SEC states no effective date for header fields) | code + docs + profile |
| publication_key | capture run id + sha256 of its pinned landing members, the ticker run, and the Name Census | code |
| family / bronze.family | `submissions` (tickers come from `reference_catalog`, which the envelope cannot name) | code |
| publication_families | omit (not a numbered native release) | code + REFERENCE |
| schema_version / adapter.version | UNKNOWN — depends on question 2 | — |
| nonblocking_deferred_reasons | question 3 | — |

Guesses so far (marked [assumption]):
- That the ticker catalogs in inputs/ are evidence for this one contract
  (classification), not a source of their own. The repo agrees (reader pins
  them; no ticker field; ADR 0015: a Security is a 13F CUSIP), but whether
  a ticker/exchange field is wanted is the operator's call (question 5).
- That `description` should be mapped although 0/40 are filled.
- Searched the whole sandbox repo (all file types except uv.lock, incl.
  crates/ and infra/) for the old contract body or a `dataset.json` from an
  earlier bundle: none. Only company.yaml, company_source.py and
  docs/specs/mdm/policy-language.md name the source. [code]

## Reader findings (not questions; for whoever owns the reader)

- `stage_former_name_loader` reads `formerNames[].date`; the files carry
  `from`/`to`, so silver `date_changed` is always null. [profile + code]
- `_catalog_tickers` (company_source.py) does not filter `sec_company_ticker`
  by `source_name`. `_sync_reference_data` lands both catalogs in one run, so
  a CIK's tickers can appear twice, with ranks from two catalogs whose row
  order differs (profile: same pairs, different order). Harmless for the
  Company rule (it only tests "no tickers"), but "the catalog's rank order"
  is not one order. [profile + code]
- `edgar-warehouse rules --help` hung >120 s (exit 124) instead of failing.

## Skill gaps found in this trial

- A known source whose rules file is missing fits neither "Add" nor
  "Change": the "not new" branch jumps to step 3 and would skip profiling.
- Step 3 says find the reader "by the code that calls `normalize`". For SEC,
  `normalize` is called generically from mdm/clean/cli.py::batch_input; the
  reader was found through `SOURCE_CODE` / `rules_files.mdm_contract`.
- Step 2 profiles raw files, but the mapping reads the reader's record
  (silver landing rows + pinned evidence). The skill never says to profile
  that shape, nor how to get it without a landing run.
- Nothing says where a registered `schema_version`/`adapter.version` lives
  (mdm_v2.dataset, a bundle's dataset.json, git history).
- The envelope's one `family` cannot name a second bronze family
  (`reference_catalog` for tickers).
- The contract language has no way to map former names to aliases.
- The skill says the log goes in "your scratchpad"; the trial says the
  sandbox root. Followed the trial.

## Step 5 — Questions (answers pending)

1. Identify: SEC EDGAR submissions files + SEC company-ticker lists, i.e. the
   repo's `sec.submissions.company.v1`? Recommend: yes, keep the names.
2. Is `sec.submissions.company.v1` registered in the local Clean MDM, and can
   its registered contract be recovered (MDM dataset table, an earlier
   bundle's dataset.json, git history)? Recommend: recover it and match it
   exactly; else write a new first version with fresh version names.
3. (only if not recovered) Held-back filers (33/40 here): wait quietly in
   the Stage, or stop the batch? Recommend: wait quietly; keep "rule not
   switched on" and every defect blocking.
4. (only if not recovered) SEC business address into the Company address
   (SEC ranks first, would replace GLEIF's legal address)? Recommend: no;
   postcode and country go to the matching rules only.
5. (only if not recovered) Leave out EIN, phone, website, tickers/exchange,
   former names, and SEC's own LEI for version 1? Recommend: yes.

## Step 5 — Operator's answers (Phase B start)

1. Yes: SEC submissions files plus SEC's two ticker lists. Keep every repo name.
2. Not registered in Clean MDM; nothing recoverable. Treat as new, keep the
   repo's names, choose fresh version names for the first version.
3. No decision makes held-back SEC filers non-blocking (the "wait quietly"
   ruling was recommended, never made). Keep today's rule: every record the
   Company rule sets aside opens a review and blocks, as does every defect.
   List no non-blocking reasons.
4. Yes, SEC's business address fills `address`. Operator decision
   2026-09-24: name, jurisdiction and address are one field each across SEC
   and GLEIF, SEC first when both have a value; the master takes every field
   from every source. Same day: SEC's state of incorporation is SEC's own
   field, written as SEC writes it; jurisdiction is GLEIF's alone.
   (My Phase A recommendation "no" was wrong: it came from the GLEIF file's
   comment, which names only `name` as shared. The repo does not record the
   address half of that decision anywhere I found.)
5. Leave out EIN, phone, website, tickers/exchange, former names. SEC's own
   LEI is not an identifier path (filled for 392 of 76,230 filers, 4 of them
   operating companies): do not map it.

## Step 6 — Write

- Wrote repo/rules/sources/sec.submissions.company/source.yaml. Values
  generated with `files.dumps` (scratch/step6/gen.py -> dumped.yaml,
  round-trip asserted), then comments added by hand. The file with comments
  loads through `files.source('sec.submissions.company')` and equals the
  dumped value exactly. `import edgar_warehouse.mdm.clean.company_source`
  now succeeds (it failed before). [verified]
- Choices, each with its source:
  - folder `sec.submissions.company`, code `sec.submissions.company.v1`:
    fixed by the reader. [code]
  - schema_version = adapter.version = `sec-company-landing-record-v1`: fresh
    names (operator: new first version). Same string for both, as GLEIF does.
    The reader checks no schema_version. [assumption on the exact spelling;
    operator approves it with the file]
  - `family: submissions`: `store.register_dataset` looks the family up in
    the acquisition registry's `source_registry_coverage.source_family`;
    `submissions` is SUBMISSIONS_SOURCE_FAMILY. [code]
  - classification, not `kind`: register_dataset refuses both. [code]
  - `nonblocking_deferred_reasons: []` written explicitly, with the
    operator's reason beside it (answer 3). [operator]
  - address = the reader's `business_address` (answer 4). [operator + code]
  - matching: the three paths the name rules and matching.py read. [code]
  - no `provenance` map: the reader keeps no native record. [code]
  - no `publication_families`: not a numbered native release. [code]
  - `description` mapped although 0/40 filled in the sample (a Company
    column; blank reads as unknown). [code + assumption]

## Step 7 — Check (dry run; `rules check` does not exist)

Script: scratch/step7/dry_run.py; output scratch/step7/dry_run.txt; the
bundle, assertions.json and deferred.json under scratch/step7/out/.

How the sample records were built (no databases, local files only):
- The captured files were landed by the repo's OWN writers into a local
  landing root: `SilverLandingStore.stage_submission` per submissions file
  (one capture run, `pagination_payloads=[]` because the `files` pages are
  not captured), `replace_company_tickers` for both catalogs (one ticker
  run, as `_sync_reference_data` does), flushed with `write_landing_export`.
  [code, run]
- The Name Census was BUILT BY HAND: `mdm name-census` needs a full GLEIF
  Golden Copy, which the trial does not have. The SEC side was counted with
  the real code (`census_filers` + `sec_keys`); the GLEIF side is empty, so
  every entry has lei_count 0. Over 19 filers, every name looks unique
  (cik_count 1) — meaningless for the real census. [assumption, logged]
- No bronze receipts: `mdm bronze-receipts` reads the bookkeeping database.
  So no record carries `_origin.bronze`.
- Then the real reader ran: `company_source.prepare_company_bundle`
  (limit 1000, revision 0, as_of 2026-09-26T00:00:00Z). The bundle's
  `dataset.json` equals the rules file's contract. [run]
- Every bundled record went through `adapters.normalize` with the contract,
  `files.policy()` (after `check_policy`) and the skill's dry-run
  publication (sha256 of records.jsonl, member records.jsonl, key
  "dry-run", revision 0). [run]
- Repo tests for the reader/loaders: none in this sandbox copy ("no tests").

What MDM would receive (40 files -> 19 landed -> 7 Companies, 12 set aside):
- 21 of 40 filers are never landed as `sec_company` (`is_individual_filer`:
  `other`, only ownership forms, no SIC, no ticker). They reach MDM neither
  as a record nor as a review. One is company-shaped: 0001825921 "ICONIQ
  Strategic Partners V TT GP, Ltd." (forms 3/4 only) is dropped as a person.
- 7 Company assertions (kind company, identifier cik, schema and adapter
  version sec-company-landing-record-v1):
  Apple (step 8), Microsoft (8), ASML (10), Amazon (8), Shell (10),
  Editas (8), Open Lending (8). Fields filled: name, sic, sic_description,
  fiscal_year_end, address; state_of_incorporation for 5 (ASML and Open
  Lending have none; Shell's is "DC", as SEC writes it); description empty
  for all 7. Matching carries business postcode + ISO country + census entry.
- Address shapes: US -> region = state, country US. ASML -> region "P7"
  (EDGAR's Netherlands code, not a region), country NL. Shell -> no region
  (stateOrCountry empty, countryCode X0), country GB. Shell and Open Lending
  carry street2.
- 12 set aside, all `classification_deferred` at step 11 (the catch-all),
  no Probable Kind: 13F managers (Axiom, Redwood, Kaydan, Arrowpoint),
  Form D issuers and funds (Contraline, Lord Abbett trust, Moorstone,
  SCA Murrells Inlet, Hempel, Grove Lynnwood, 2am Ventures, Fundamental
  Ventures SPV). With no non-blocking reasons (operator), each opens a
  blocking review: this sample's batch would stop until 12 reviews close.
- Defect probes on a copy of Apple's record: cik missing ->
  missing_record_identity; 11 digits -> invalid_cik; 0 -> invalid_cik;
  name a number -> invalid_field_shape. All blocking.
- Reader defect confirmed: every CIK's `tickers` is doubled (Apple
  ['AAPL','AAPL'], ASML ['ASML','ASML','ASMLF','ASMLF']) because both catalogs
  land in `sec_company_ticker` and `_catalog_tickers` does not filter by
  `source_name`. Harmless to the Company rule today (it only tests "no
  tickers"), wrong as data.
- Not a preview: nothing was matched against existing MDM records (no
  store). The gap is logged as the skill says.

## Step 8 — Preview: `rules run --target mdm --preview` does not exist. Stopped here.

## Skill gaps found in steps 6–7

- Step 6 "Start from its Defaults" includes `provenance.native_record`; the
  SEC reader keeps no native record. The skill does not say to drop it.
- REFERENCE lists `completeness` in the file shape, but the GLEIF worked
  example has none; unclear whether it is required.
- The skill never says `family` must be an acquisition-registry source
  family (`register_dataset` looks it up in `source_registry_coverage`).
- No offline way to run register_dataset's own checks (one kind writer,
  formats, reason names); they sit inside a database call.
- Nothing says how to name `schema_version` vs `adapter.version` (same
  string, as GLEIF, or two names).
- `files.dumps` wraps long plain strings over several lines (width 88); it
  reads back exactly, but hand comments must not be put inside them.
- Step 7 says "run the reader on the sample", but this reader needs a
  silver landing run, a ticker run, a Name Census (needs a full GLEIF Golden
  Copy) and bronze receipts (needs the bookkeeping database). The skill does
  not say how to build a landing from captured files; I found
  `SilverLandingStore` + `write_landing_export` myself.
- Step 7's normalize call is not what production runs: `batch_input` also
  rejects NaN/Infinity, caps 1000 records, checks record_count and keeps
  deferred records with a locator. It needs a store for `current_reading`.
- The skill's "defect always blocks" view misses a gate before the mapping:
  `is_individual_filer` drops 21 of 40 filers at landing, so they never
  become records or reviews. The dry run of the mapping alone cannot see it.
- No step asks for a check that the mapping's matching paths agree with
  what the policy's rules read (`matching.business_postal_code` etc.).
- A reader defect found in the dry run (doubled tickers) has nowhere to go
  in the skill besides the log.

## Close of Phase B

- Two file comments corrected after review: the address comment now says
  only SOME foreign filers get an EDGAR code in `region` (ASML P7; Shell has
  none), and the U0 example is credited to the captured files, not the
  operator. Re-checked: the file loads and equals the dumped value.
- Repo changes: since this session's first script (19:21 local), the only
  change under repo/ is rules/sources/sec.submissions.company/. The
  `edgar_warehouse/__pycache__`, `edgar_warehouse/rules/__pycache__` and
  `.venv` found under repo/ date from 18:08, the trial setup. All landing,
  bundle and census output is under scratch/step7/out/.
- Approval: NOT given. The file and the version name
  `sec-company-landing-record-v1` wait for the operator's approval (step 9).

## Correction to answer 5 (received in three parts during Phase B)

Operator, 2026-09-26: "must be on mdm for cross reference id for lookup any
document only with ids — keep ein, tickers, lei"; then: EIN, tickers and
SEC's own LEI are LOOKUP ONLY, never join two records by themselves; put
SEC's LEI under its own name (e.g. `sec_lei`) because the merge code joins
SEC and GLEIF on `lei`; then: "ticker must be at security entity not in
company" — tickers are not Company ids. Phone, website, former names stay out.

What the file now does (regenerated with files.dumps from
scratch/step6/gen.py, comments re-added; loads and equals the dump):
- `ein: ein` added to `identifiers`, no format. [operator + code]
- SEC's LEI: NOT mapped; the intended mapping is written as a comment.
- tickers: NOT mapped; comment says they belong to the Security and are
  only the Company rule's classification input.
- Version names unchanged (`sec-company-landing-record-v1`): nothing was ever
  registered under them, so no registered content is being reused.
  [assumption; would be wrong if a registration happened in between]

What is missing, item by item, and what would fix it:
- EIN placeholder `000000000` (5 of 19 landed filers, 2 of them Companies:
  ASML, Shell). The contract cannot say "this value means none":
  `identifier_formats` names only FORMATS (`sec_cik`, `lei`), and a format can
  only return a value or raise (a raise is a blocking defect; it would block
  ASML and Shell). Kept as written, so a lookup by EIN 000000000 finds five
  filers. Fix: a `sec_ein` format (9 digits) plus a way for a format to read
  SEC's placeholder as no value (adapters.normalize change); records then
  change, so a new version.
- SEC's own LEI. Reader: `stage_company_loader` does not read `lei`, and
  `sec_company` has no `lei` column (silver_schema.py and the landing DDL
  `11_silver_landing_schema.sql`, held equal by a snapshot test). Fix: land
  `lei`; prepare_company_bundle passes whole rows, so it then reaches the
  record; map `sec_lei: lei`, format `lei` (a failed check digit then blocks
  the record as a defect). New version. I did not write the path now: it
  would read nothing today and would silently change records under the same
  version the day the reader starts carrying it.
- Tickers (now a Security matter, not this contract): the catalogs carry
  CIK, ticker, exchange (null on 201 rows) and a name, but no CUSIP, and a
  Security's identity is the 13F CUSIP (ADR 0015). A Security mapping needs
  a CUSIP source to attach a ticker to a Security; the catalog alone can at
  most say "this CIK has these tickers". It would also need: tickers as dated
  values (SEC reassigns tickers; the catalog is a current snapshot), the
  reader's doubled tickers fixed (`_catalog_tickers` must filter
  `source_name`), and a way to map a list (an identifier path reads one
  scalar, `value()` cannot index a list, and `format_value` would turn a list
  into the text "['AAPL', 'AAPL']").

How the mapping keeps these ids from joining records (evidence: code +
scratch/step7/compare.py, run):
- A join by identifier needs a binding rule. `activation.check_binding_rule`
  accepts only namespaces in NAMESPACES = {cik, lei}: probe rules on `ein`,
  `sec_lei` and `ticker` were refused; one on `lei` was accepted. So `ein`
  and a future `sec_lei` cannot join anything. `binding.holders` also raises
  for any other namespace, and counts a value only through the namespace's
  issuing source (Identifier Contract `sources`; none are declared yet).
- One effect they DO have: merge.py treats every namespace as authoritative.
  If one Company's records carry two different values in a namespace, the
  Company goes to review with `authoritative_identifier_conflict` and its
  fields are emptied. That is a veto, not a join. For `ein` it can fire only
  if a Company holds two SEC records, where `cik` already conflicts. For SEC's
  LEI under `lei` it WOULD fire whenever SEC's LEI disagreed with GLEIF's on a
  bound Company; `sec_lei` avoids that. The contract language has no way to
  mark a namespace "lookup only" and exempt it from this check: that is
  engine code (merge.py), not a rules-file setting.

Lookup itself (the operator's goal) is not served yet:
- The Company table has columns for `cik` and `lei` only; `ein` lives in the
  `identifiers` JSON. Indexes exist for `cik` and `lei` only (migrations
  035, 039). The v2 API (`mdm/api/routers/clean.py`) looks up by entity id
  only, with no lookup by identifier. [code]

Dry run rerun (scratch/step7/out2/, dry_run2.txt, compare.txt):
- Same landing, same 19 records, same 7 Companies and 12 set aside.
- Each of the 7 Companies now carries `ein`: Apple 942404110, Microsoft
  911144442, Amazon 911646860, Editas 464097528, Open Lending 845031428,
  ASML 000000000, Shell 000000000.
- All 7 assertion ids changed, as they must: identifiers are in the hashed
  body.
- The only other difference is `provenance.matching.name_census.census`,
  the census digest. Landing the same captured files twice writes different
  Parquet bytes (`last_synced_at` is stamped with the clock), so the member
  sha256, the census and every assertion id differ between re-landings of
  identical source files. That comes from the landing writer, not from the
  mapping. [run + code]

## Skill gaps found applying the correction

- The skill has no notion of a lookup-only identifier, and neither has the
  contract language: every `identifiers` entry is authoritative to the merge.
- The skill says "Never guess an identifier" but says nothing about a
  source's placeholder values (EIN 000000000) or how to treat them.
- The skill's step 4 ("Identifiers: each namespace with its format") does
  not say that only NAMESPACES {cik, lei} can ever bind, nor that only cik
  and lei are indexed and shown as Company columns.
- No guidance for a value that belongs to another kind (tickers -> Security)
  seen in a Company source: where to record it, and when it needs its own
  contract.
