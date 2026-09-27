# Rules log: onboarding the source in `inputs/` (phase A, steps 1-5)

Date: 2026-09-27. Skill: `repo/skills/rules/SKILL.md` + `REFERENCE.md`.
Sandbox paths are relative to the trial folder (`inputs/`, `repo/`, `scratch/`).
Source tags used below: **[files]** = the profile of `inputs/`; **[code]** = repo
code; **[docs]** = repo docs; **[public]** = public web documentation;
**[assume]** = my assumption, not verified.

## Step 1. Identify

Files seen [files]:
- `inputs/submissions/CIK##########.json`: 40 files, 1.4 KB to 185 KB, 1.2 MB total.
  One JSON object per file, one filer each: `cik`, `entityType`, `sic`, `name`,
  `tickers`, `exchanges`, `ein`, `lei`, `addresses`, `formerNames`,
  `filings.recent` (parallel arrays, one list per column), `filings.files`.
- `inputs/tickers/company_tickers.json` (795 KB): an object keyed "0".."N", each
  `{cik_str, ticker, title}`.
- `inputs/tickers/company_tickers_exchange.json` (521 KB): `{fields: [cik, name,
  ticker, exchange], data: [[...], ...]}`, a table as parallel columns per row.

Name: **SEC EDGAR submissions (one `CIK##########.json` per filer) plus SEC's two
company-ticker catalogs**. Provider SEC. Confirmation with the operator: asked in
the question list (Q1), not yet answered.

Is it new? [code] No. The repo already names this source:
- source code `sec.submissions.company.v1`: `edgar_warehouse/mdm/clean/company_source.py:31`,
  ranked first in `rules/merge/kinds/company.yaml` `defaults.sources`, and the
  source of the classification rule `sec-company-candidate` (version 2026-09-25.13,
  activated in `rules/merge/policy.yaml`) and the `holder_source` of both
  SEC-to-GLEIF name rules.
- rules folder `sec.submissions.company`: `company_source.py:36` loads
  `rules_files.mdm_contract("sec.submissions.company", SOURCE_CODE)`.
- the rules file `repo/rules/sources/sec.submissions.company/source.yaml` is
  **missing**. Only `rules/sources/gleif/source.yaml` exists.
- Consequence [code, run]: importing the reader fails today:
  `FileNotFoundError ... rules/sources/sec.submissions.company/source.yaml`. So
  `edgar-warehouse mdm prepare-clean-company`, `mdm name-census` and
  `mdm bronze-receipts` (all import `company_source`) cannot run until the file
  exists.
- Path taken, per the skill: "rules file missing -> follow every step, keep the
  repo's names". Folder `sec.submissions.company`, source code
  `sec.submissions.company.v1`.
- Registered in Clean MDM? `edgar-warehouse rules status` does not exist (see
  "Missing commands"). Asked the operator (Q2).

The reader (the existing code for this source) [code]:
- raw JSON -> silver landing rows: `edgar_warehouse/loaders/bronze_submission_extractors.py`
  (`stage_company_loader`, `stage_address_loader`, `stage_former_name_loader`,
  `stage_recent_filing_loader`, `is_individual_filer`), written by
  `SilverLandingStore.stage_submission` (`edgar_warehouse/silver_landing_store.py`)
  into landing tables `sec_company`, `sec_company_address`,
  `sec_company_former_name`, `sec_company_submission_file`, `sec_company_filing`.
- ticker catalogs -> `sec_company_ticker`: `_parse_company_ticker_rows` and
  `SilverLandingStore.replace_company_tickers` (adds `source_name`, `source_rank`).
- silver landing -> MDM records: `company_source.prepare_company_bundle`, run by
  `edgar-warehouse mdm prepare-clean-company` (`edgar_warehouse/mdm/cli.py:42`).
  It reads one `sec_company` Parquet member and pins three more beside it:
  `sec_company_filing` -> `forms`, `sec_company_address` -> `business_address`,
  `sec_company_ticker` (a separate run) -> `tickers`, plus the Name Census entry
  -> `name_census`, and `_origin` (member path, sha256s, row ordinal, manifest
  sha256, run ids, optional `bronze` object).
- MDM mapping must be from *that* record shape, not from the raw JSON.

## Missing commands (named by the skill, not in the repo)

| Command | Result |
|---|---|
| `edgar-warehouse rules status` | `invalid choice: 'rules'` (checked by calling `edgar_warehouse.cli.main(["rules","status"])`) |
| `edgar-warehouse rules profile <files>` | `invalid choice: 'rules'`; profiled with a scratch script instead (`scratch/profile.py`) |

Note: `python -m edgar_warehouse.cli ...` prints nothing and exits 0 (no
`__main__` guard), so a missing command can look like success that way. Use
`main([...])`.

## Step 2. Profile

Scripts: `scratch/profile.py` (raw files) and `scratch/reader_shape.py` (records in
the reader's shape). Outputs: `scratch/profile-full.txt`, `scratch/reader-shape.txt`,
`scratch/reader-records.jsonl`. Sample first (first/middle/last submissions file,
first/middle/last 50 catalog rows): 0.1 s. The whole input is 2.5 MB, so the full
pass (0.6 s) was used for every count below. No line-based pass was needed.

### Record type A: the filer (one per `CIK##########.json`), 40 records [files]
- `cik`: text, 10 digits zero-padded, 40/40 filled, 40 distinct, equals the file
  name every time. Checked with `\d{10}` and against the file name. Candidate
  record key.
- `name` 40/40; `entityType` 40/40, values `other` (33) and `operating` (7).
- `sic`, `sicDescription` 7/40 (empty text otherwise). `category` 7/40, values
  like `Large accelerated filer`, `Non-accelerated filer<br>Smaller reporting company`
  (an HTML `<br>` joins two categories). `ownerOrg` 7/40 (SEC office, `06 Technology`).
- `stateOfIncorporation` 18/40 (EDGAR codes: US states, `U0` Singapore; Shell plc
  says `DC` although its addresses are in London, `foreignStateTerritory: "DC"`).
  `stateOfIncorporationDescription` repeats the code for US states, a country name
  for others. `fiscalYearEnd` 20/40, `MMDD` text (`0926`, `1230`), null for persons.
- `ein` 19/40 filled, null 21/40. Checked `\d{9}`: all 19 pass, but 5 are the
  placeholder `000000000` (ASML, Shell, Arrowpoint, Moorstone, Fundamental Ventures).
- `lei` 1/40: `254900W3REVJHWYFN607` (Arrowpoint). Checked: 20 characters,
  `[A-Z0-9]{18}[0-9]{2}`, mod 97 == 1: passes.
- `tickers` / `exchanges`: parallel lists, 7/40 filled (Apple, Microsoft, ASML 2,
  Amazon, Shell 2, Editas, Open Lending).
- `description`, `website`, `investorWebsite`, `flags`: empty text in 40/40.
  `phone` 20/40. `insiderTransactionForOwnerExists`/`...ForIssuerExists`: 0/1 ints.
- `addresses.mailing`, `addresses.business`: `street1`, `street2`, `city`,
  `stateOrCountry`, `zipCode`, `stateOrCountryDescription`, `isForeignLocation`,
  `foreignStateTerritory`, `country`, `countryCode`. Business address filled for
  20/40 (entities), mailing 38/40. A foreign address leaves `stateOrCountry` null and
  carries `countryCode` (`X0`, `U0`) and `country`; ASML instead puts `P7` in
  `stateOrCountry`. Never both filled (checked).
- `formerNames[]` (`name`, `from`, `to`): 5/40 filers, 7 names. A repeated group.
- `filings.recent`: a table as parallel arrays, zipped into 7,013 rows; all
  columns equal length in every file; newest first in all 40 files.
  `accessionNumber` unique, format `\d{10}-\d{2}-\d{6}` (checked). Its first 10
  digits are the *submitting* CIK: own CIK in only 0-100% of a filer's rows
  (Apple 455/1002), so a filing's accession prefix names a filer agent or another
  party, not the record.
- `filings.files[]`: pagination files `CIK##########-submissions-NNN.json` named
  for 4 filers (Apple, Microsoft, Amazon, Shell). **Those files are not in
  `inputs/`**, so older filings of those 4 are missing here.
- Persons: 21/40 files are individuals by name shape (`KLEMP WALTER V`,
  `BURKE JAMES J JR`, `Solomon Kenneth A`), all `entityType: other`, no `sic`.
- Capture time: not in the file. Latest `acceptanceDateTime` per file ranges from
  2026-04-17 (Apple, a frequent filer, so its file is old) to 2026-09-14. The 40
  files were captured at different times, not as one snapshot.

Placeholders the source writes for "none" [files] (the contract cannot turn these
into unknown; logged as the skill asks):
- `ein: "000000000"` (5 of 19 filled EINs).
- empty text `""` for `sic`, `sicDescription`, `category`, `stateOfIncorporation`,
  `description`, `website`, `flags`, `reportDate`, `act`, `fileNumber`: the adapter
  already reads blank text as unknown (`adapters.mapped_field`), so no gap there.
- Surprising value, not a placeholder: Shell `stateOfIncorporation: "DC"` with a UK
  address; `names.edgar_jurisdiction("DC")` reads it as a US jurisdiction.

### Record type B: `company_tickers.json` and C: `company_tickers_exchange.json` [files]
- B: object keyed `"0"`..`"10390"` in order; each `{cik_str:int, ticker, title}`.
- C: `{fields: [cik, name, ticker, exchange], data: [[...]]}`, zipped into rows.
- Both: 10,391 rows, 10,391 distinct tickers (ticker unique, always filled),
  8,001 distinct CIKs, 1,445 CIKs with more than one ticker (max 32). CIK is an int
  of up to 7 digits (not zero-padded).
- B and C hold the **same 10,391 (cik, ticker) pairs in the same order**; the
  name/title agrees for every CIK. C adds `exchange`: Nasdaq 4,361, NYSE 3,300,
  OTC 2,494, CBOE 35, null 201.
- Against the 40 filers: 6 of the 7 filers with tickers in submissions have the
  same tickers in both catalogs. **Open Lending (CIK 1806201) lists `LPRO` in its
  submissions file but is in neither catalog**, so the reader gives it no tickers.
- Candidate key: `ticker` (unique). A ticker names a listed security, so these
  rows belong to Security/Venue, not Company (see step 4).

### Records in the reader's shape [code + files]
Built by `scratch/reader_shape.py` with the repo's own extractors (see its
docstring). **Built by hand in the reader's output shape, not by the reader**:
the reader cannot import (missing rules file), reads landing Parquet, and needs
a Name Census built from a full GLEIF Golden Copy, which is not in `inputs/`.
`name_census` is left null; `_origin` holds scratch values.
- `is_individual_filer` drops 21 of 40 before silver. 20 are people. **One is not:
  `ICONIQ Strategic Partners V TT GP, Ltd.` (CIK 1825921)** is an entity (a GP,
  `Ltd.`, state DE) that files only Forms 3/4 with no SIC and no ticker, so the
  reader treats it as an individual and it never reaches MDM.
- 19 records remain. Keys: `cik` (int), `entity_name`, `entity_type`, `sic`,
  `sic_description`, `state_of_incorporation`, `state_of_incorporation_desc`,
  `fiscal_year_end`, `ein`, `description`, `category`, `raw_object_id` (sha256 of
  the submissions document), `sync_run_id`, `first_sync_run_id`,
  `last_sync_run_id`, `last_synced_at`, `load_mode`, `forms`, `business_address`
  {street, street2, city, region, postal_code, country}, `tickers`, `name_census`,
  `_origin`.
- Company rule `sec-company-candidate` 2026-09-25.13 on these 19: step 8
  (company) 5, step 10 (company) 2, step 11 (deferred) 12. Held back: Form D
  issuers, 13F managers, a trust, and Arrowpoint.

## Step 3. Research

- Terms [docs]: `CONTEXT.md` (Company Identity, Source Stage, Probable Kind,
  Dataset Contract, Security Identity: "A 13F CUSIP is that identity").
- Clean MDM [docs]: `docs/specs/clean-mdm/source-evidence.md`, `company-policy.md`,
  `local-operations.md` ("Prepare a native Company sample", "Name each record's
  bronze object"), `security-identity.md`, `state-of-build.md`.
- Kinds [code]: `KINDS` = company, person, security, fund_structure, branch,
  government, international_organization, venue.
- Company fields [code]: `COMPANY_NAMED_FIELDS` = name, sic, sic_description,
  state_of_incorporation, fiscal_year_end, description, jurisdiction, address,
  plus 12 `gleif_*` fields.
- Merge rules [code]: `rules/merge/kinds/company.yaml` ranks sources only at kind
  level (`defaults.sources: [sec.submissions.company.v1, gleif.level1.v1]`); there is
  no per-field rank. The GLEIF file's comment adds: `name` is shared, SEC first;
  `jurisdiction` is GLEIF's alone (operator, 2026-09-24).
- What the merge rules read from an SEC record [code]:
  - classification (`primitives.value` on the reader's record): `sic`, `category`,
    `entity_type`, `entity_name`, `tickers`, `forms`.
  - name rules (`matching.py` `_read`): fields `name`, `state_of_incorporation`;
    `provenance.matching.name_census`, `matching.business_postal_code`,
    `matching.business_country`.
- Identifier namespaces that can bind [code]: `activation.NAMESPACES = {cik, lei}`;
  `binding.py`: "an SEC record carrying an LEI holds no LEI" (only the issuing
  source's identifier binds). Any other namespace is lookup-only.
- Protected parts [code]: `store.PROTECTED_ADAPTER_PARTS` = record_key,
  record_key_format, **identifiers**, identifier_formats. Changing any of them on a
  registered source code is refused: "register a new source code". So an
  identifier added after registration forces `sec.submissions.company.v2`.
- Formats [code]: `FORMATS` = `sec_cik` (digits, up to 10, not 0, zero-padded to 10),
  `lei` (mod 97).
- Registration [code]: `register_dataset` checks the contract's `family` against
  the acquisition registry's `source_family`. The submissions family is
  `submissions` (`acquisition/submissions_discovery.py:44`); the ticker catalogs are
  family `reference_catalog`.
- Relationships [docs]: `docs/research/sec-gleif-relationship-sources-2026-09-26.md`
  row "Company submissions ... Relationship it can support: None. It identifies the
  Company. It does not link a parent, a holder, or a security."
- Securities [docs]: ADR 0015 / `security-identity.md`: the Security identity is the
  13F CUSIP. A ticker is not a Security identity, so a ticker catalog cannot mint
  Securities.
- Time [docs]: `state-of-build.md`: "`last_synced_at` is observation time, not
  source effective time; the candidate policy explicitly permits unknown effective
  time." `company.yaml` `allow_unknown_effective: true`.
- Business hashes [docs]: `source-evidence.md`: "Exclude wall-clock ingest time,
  attempt IDs, transport paths, and delivery ordering from business hashes."
  `adapters.normalize`: delivery member paths, hashes and line positions "remain
  pinned in the input manifest". Ticket 10 (`local-operations.md`): the bronze
  object travels beside the reading as an occurrence, "The record itself is
  unchanged."
- Confidence bands [docs]: `company-policy.md` (operator, 2026-09-24): 50-95% "Waits
  in the Stage with no kind or link. No Steward."
- Reader tests: none in the sandbox (`tests/` absent), so none to run.
- Public documentation [public]: SEC's own documentation of these files is on
  `sec.gov`, which is blocked. Per the skill, relied on the files and the repo; no
  third-party pages used. Nothing below rests on public docs.

## Step 4. Infer (one record type in scope: the filer, as the reader shapes it)

Each line ends with where it came from.

Fixed by the repo (not asked):
- Folder `sec.submissions.company`, source code `sec.submissions.company.v1`. [code: `company_source.py:31,36`, `company.yaml`]
- `bronze.family` and `contract.family`: `submissions` (the acquisition family `register_dataset` checks). [code: `submissions_discovery.py:44`, `store.register_dataset`]
- Kind: not stated in the contract. The contract names the classification rule
  `{kind: company, rule_id: sec-company-candidate, version: <the Account hold-back version>}`,
  and carries no `kind` or `kind_field` (`register_dataset` refuses both together).
  The rule is written for this source code (`source: sec.submissions.company.v1`), and
  `classify_record` refuses it for any other code. [code: `store.py`, `adapters.classify_record`, `company.yaml`, `policy.yaml`]
- Record key: `[cik]` with `record_key_format: sec_cik`. **Required, not a preference**:
  the reader's `cik` is an int (320193), `sec_cik` pads it to `0000320193`, and the
  name matching rule requires the census entry's `ciks == [record_key]`, where the
  census writes CIKs as `f"{int(cik):010d}"`. [code: `adapters._sec_cik`, `matching._census_match`, `company_source.census_filers`]
- Identifier `cik: cik`, format `sec_cik`. Only `cik` and `lei` can join records; SEC
  issues the CIK. [code: `activation.NAMESPACES`; skill hard rule]
- Fields with names the merge rules fix: `name: entity_name`,
  `state_of_incorporation: state_of_incorporation` (the name matching rules read both
  as fields). [code: `matching._read`, `company.yaml` `sec_field: state_of_incorporation`]
- Other existing Company fields SEC carries: `sic: sic`, `sic_description:
  sic_description`, `fiscal_year_end: fiscal_year_end`, `description: description`
  (empty in 40/40 here, still mapped: an existing MDM field). [code: `COMPANY_NAMED_FIELDS`; files]
- `jurisdiction`: not mapped; GLEIF's alone. [code comment in `rules/sources/gleif/source.yaml`, operator 2026-09-24]
- `address`: open, see Q5. [code: reader builds it; docs: company-policy Q8]
- `matching` (kept with the record, outside its fields), names fixed by the merge
  rules: `name_census: name_census`, `business_postal_code: business_address.postal_code`,
  `business_country: business_address.country`. [code: `company.yaml` `matching.*`, `matching._census_match`, `local-operations.md`]
- Relationships: none. The submissions file "identifies the Company. It does not link
  a parent, a holder, or a security." [docs: `docs/research/sec-gleif-relationship-sources-2026-09-26.md`]
  Candidate links seen in the files, all out: CIK -> ticker (a ticker is not a
  Security identity; ADR 0015); ticker -> exchange (Venue); accession prefix ->
  submitting agent's CIK (a filing is evidence, not a master record; CONTEXT.md).
- Filings (`filings.recent`, pagination files): evidence, not a kind; they reach the
  record only as `forms` for the Company rule. [docs: CONTEXT.md "A filing ... is evidence"]
- Former names: feed the Name Census only; not in the record. [code: `company_source.census_filers`]
- Tickers, exchanges: belong to Security / Venue. Kept out of Company, read only by
  the Company rule (`tickers`). **Logged for the Security and Venue kinds.** [skill hard rule; docs: security-identity.md]
- Publication [docs + code]: `semantics: patch; absence never retires an identity`
  (REFERENCE default; `local-operations.md`: "a sample never retires absent
  records"). `completeness`: each submissions file is a complete current snapshot
  of one filer; one publication is one capture run's bounded `sec_company` member,
  not the whole SEC universe (`scope.whole_source_complete: false`).
  `publication_key`: the capture run id, the Company member's sha256, and each pinned
  member's run and sha256 plus the Name Census digest (`company_source.py:454`).
  `effective_time: unknown` (`last_synced_at` is observation time, `state-of-build.md`;
  `allow_unknown_effective: true`). `publication_families`: none (not a numbered
  native release).
- Non-blocking reasons: `classification_deferred` (the exact string from
  `f"classification_{verdict}"`, `adapters.py:182`). The operator's confidence bands
  (2026-09-24, `company-policy.md`) say a held-back record "waits in the Stage with no
  kind or link. No Steward", so it must not stop its batch. In this sample 12 of 19
  records are held back: a blocking reason would stall nearly every batch.
  `classification_not_activated` stays blocking (it means the policy state is wrong).
  [docs + code + files]
- Defaults kept: `retain_deferred: true`, `source_record_provenance: true`,
  `field_shape: nullable_text`. The reader's `sic`, `fiscal_year_end` etc. are text or
  null (checked on the 19 records). [REFERENCE; files]
- `schema_version` = `adapter.version`: proposed `sec-company-landing-record-v1`
  (the record shape is a `sec_company` landing row plus the reader's pinned
  evidence). **[assume]** No name is fixed in the repo; replaced by the registered one
  if Q2 says it is registered.
- Trace fields: open, see Q6. The skill and the Clean MDM spec disagree:
  - skill step 4 / REFERENCE "Defaults": put every trace field the reader attaches
    (file hashes, run ids, observed time, raw object ids) into `provenance`;
  - `docs/specs/clean-mdm/source-evidence.md`: "Exclude wall-clock ingest time, attempt
    IDs, transport paths, and delivery ordering from business hashes"; ticket 10
    (`local-operations.md`): the bronze object travels beside the record, "The record
    itself is unchanged"; `adapters.normalize`: delivery paths/hashes "remain pinned in
    the input manifest".
  - Provenance is hashed into each fact's fingerprint (`evidence.assertion`), so
    `last_synced_at`, run ids and `_origin.row_ordinal` would give identical facts new
    fingerprints on every capture. Neither is marked as an operator decision, so the
    "later operator decision wins" rule does not settle it: asked.
- Identifiers beyond `cik`: `ein` and SEC's `lei`: open, see Q3 and Q4. Both are
  fixed once registered (`PROTECTED_ADAPTER_PARTS`), which is why they are asked now.

Kinds not settled: individual filers (Person). Left unnamed, asked (Q7).

Reader defects found (code fixes, not rules-file changes; logged for the operator):
- `is_individual_filer` drops `ICONIQ Strategic Partners V TT GP, Ltd.` (CIK 1825921),
  an entity, as a person.
- `stage_company_loader` does not read `lei`; silver `sec_company` has no column for it.
- `company_source._catalog_tickers` does not filter by `source_name`; if one ticker
  run lands both catalogs, every ticker appears twice in `tickers`. The two catalogs
  hold identical pairs here; the store's default `source_name` is
  `company_tickers_exchange`.
- Open Lending (CIK 1806201) states `LPRO` in its submissions file but is in neither
  catalog, so the reader gives it no tickers (the Company rule still says company,
  step 8).

## Step 5. Questions (asked in the phase A reply, one decision each)

| # | Question (short) | My recommendation | Answer |
|---|---|---|---|
| 1 | These are SEC submissions files + SEC's two ticker lists, the source the repo already reads as `sec.submissions.company` / `sec.submissions.company.v1`. Right? Write the missing file under those names? | Yes | pending |
| 2 | Is `sec.submissions.company.v1` already registered in Clean MDM? If so, send its registered contract. | Probably not (state-of-build's last check: no datasets), but I cannot check | pending |
| 3 | Keep the EIN as look-up-only `sec_ein`? 5 of 19 filled values are `000000000` and would be stored as that text. | Keep it now, no format check; log the placeholder | pending |
| 4 | Keep SEC's stated LEI as look-up-only `sec_lei`, read from a `lei` column the code does not produce yet, with the LEI check (a bad one stops that Company record)? | Yes, both; ticket the loader change | pending |
| 5 | Put SEC's business address into MDM's one `address` field (SEC outranks GLEIF's legal address)? | No: keep it for matching only (company-policy Q8, different concepts in separate fields) | pending |
| 6 | What does each fact carry back to its file: (a) the submissions file's sha256 inside the record, or (b) nothing inside, the file named beside it (needs `--bronze-receipts`)? | (b) | pending |
| 7 | Keep individual filers out of this source until Person mastering is settled? Ticket the ICONIQ drop as a code fix? | Yes and yes | pending |
| 8 | Any of the SEC values with no Company field (filer type, filer category, state description, phone, website, SEC office, insider flags) wanted as a new field? | None now | pending |

## Guesses I made

- `schema_version`/`adapter.version` name `sec-company-landing-record-v1`: no name is fixed in the repo.
- Q4's column name `lei` in the reader's record: the loader does not produce it yet; the name is an assumption until the loader and silver schema change.
- Shell's `stateOfIncorporation: "DC"` read as a surprising value, not a placeholder.
- "Captured at different times" is inferred from each file's latest filing time; the files carry no capture time.
- Records in the reader's shape were built by hand from its code (it cannot run; see step 2).

## Gaps in the skill found in this run

1. The whole `edgar-warehouse rules` group is missing (`status`, `profile` reached; `check`, `run`, `activate`, `init`, `migrate` will be missing too).
2. The skill runs `edgar-warehouse ...`; this trial allows only `uv run --no-sync python ...`, and `python -m edgar_warehouse.cli ...` is a silent no-op (no `__main__` guard), so a missing command can look like success. Only `main([...])` shows the error.
3. Log path: the skill says `<your scratchpad>/rules-log.md`; the trial says `<sandbox>/rules-log.md`.
4. A known source whose rules file is missing: its reader loads that file at import, so the reader (and `mdm prepare-clean-company`, `mdm name-census`, `mdm bronze-receipts`) cannot run before step 6. Step 3's "profile a few records in its shape" had to be done by hand.
5. The reader reads silver landing Parquet and a Name Census built from a full GLEIF Golden Copy, not the raw files in `inputs/`. The skill does not say how to get from raw captured files to the reader's input.
6. "A field ranked for this source is one it supplies" is undefined when the merge rules rank only at kind level (`defaults.sources`): read literally, SEC supplies `jurisdiction`, which the operator gave to GLEIF alone.
7. Provenance: step 4 and REFERENCE "Defaults" say put run ids, observed time and file hashes in `provenance`; `source-evidence.md` and ticket 10 say keep them out of what is hashed. Provenance is hashed into each fact's fingerprint.
8. The skill never says that the record key and identifiers are fixed at registration (`PROTECTED_ADAPTER_PARTS`); "keep every identifier" then means every identifier must be settled before the first registration, or it forces a new source code.
9. No guidance for a reader that drops an identifier the raw file carries (SEC's `lei`): "map from the reader's records" and "keep every identifier" conflict.
10. No guidance for a placeholder inside an identifier (`ein: 000000000`): it passes any format check and would be stored as a value.
11. Step 4 says which relationships are in scope "is a question for the operator"; the hard rules say ask only what the repo cannot tell. Here a repo research doc answers it.
12. Address components work only for the field named `address` (`adapters.mapped_field`), so a second kind of address cannot become a new field. REFERENCE does not say.
13. REFERENCE does not say a `classification` contract must not also state `kind`/`kind_field` (`register_dataset` refuses it), nor list the deferral reason strings a classification rule produces (`classification_deferred`, `classification_not_activated`).
14. A contract has one `family`, but this reader pins evidence from two acquisition families (`submissions`, `reference_catalog`); REFERENCE does not say how to record the second.
15. Step 7 says run the reader's tests; there is no `tests/` folder in this repo copy.

## Operator answers (received for phase B, 2026-09-27)

| # | Answer |
|---|---|
| 1 | Yes: write the missing file under the repo's names. |
| 2 | Not registered; nothing can be recovered. Treat as new, with fresh version names. |
| 3 | Keep EIN as lookup-only (operator, 2026-09-26: "must be on mdm for cross reference id for lookup any document only with ids"), named by the skill's rule for an identifier another authority issues: `sec_ein`. No format check; log `000000000`. |
| 4 | Keep SEC's LEI as lookup-only `sec_lei` (operator, 2026-09-26: it never joins records), but **do not map a path the reader does not produce today** (records would change under the same version the day it does). Write a comment with the future mapping; log a code ticket. |
| 5 | Yes. Operator, 2026-09-24: name, jurisdiction and address are one field each across SEC and GLEIF, SEC first when both have a value; the master takes every field from every source. SEC's business address fills `address`. Same day: SEC's state of incorporation is SEC's own field, as SEC writes it; jurisdiction is GLEIF's alone. |
| 6 | (b), today: file hash, run id and sync time stay out of the record; each batch names the bronze file beside the record (bronze receipts, ticket 10). Map no capture-specific trace field into `provenance`. |
| 7 | People stay out. ICONIQ already logged as a code ticket. |
| 8 | None. |

Two written decisions that disagree, cited both (hard rule): my recommendation on Q5
(keep business address out, company-policy.md Q8 "Keep different concepts in separate
fields", 2026-09-19) vs the operator's 2026-09-24 decision (address is one field across
SEC and GLEIF, SEC first). The later operator decision wins: SEC maps `address`.
Within the 2026-09-24 answer, "name, jurisdiction and address are one field each across
SEC and GLEIF" and "jurisdiction is GLEIF's alone": read together, SEC does not map
`jurisdiction` (it has no jurisdiction value of its own; its state of incorporation is its
own field). Matches the GLEIF file's comment.

## Step 6. Write

- File: `repo/rules/sources/sec.submissions.company/source.yaml`. Value built in
  `scratch/build_rules.py`, dumped with `files.dumps`, saved as JSON in
  `scratch/rules-value.json`; comments added by hand between keys.
- Check: `files.source('sec.submissions.company') == ` the value passed to `files.dumps`:
  **True**. The reader now imports (`company_source.FIELDS` = name, sic,
  sic_description, state_of_incorporation, fiscal_year_end, description, address).
- Choices written into comments: family; non-blocking `classification_deferred`; no
  `provenance` (Q6); classification instead of a kind; `sec_cik` record key (census);
  `sec_ein` with its placeholder (Q3); `sec_lei` future mapping `sec_lei: lei`, not
  mapped (Q4); SEC-first shared fields, `jurisdiction` left out, business address (Q5).
- Versions: `schema_version` = `adapter.version` = `sec-company-landing-record-v1`;
  not found anywhere else in the repo (grep), fresh as the operator asked (Q2).

**Code tickets logged for the operator (not rules-file changes):**
1. `sec_lei`: `stage_company_loader` should land SEC's `lei` on the `sec_company` row
   (silver schema `edgar_warehouse/silver_schema.py`, landing DDL
   `infra/snowflake/sql/bootstrap/11_silver_landing_schema.sql`). Then add
   `sec_lei: lei` to the contract; identifiers are fixed once registered, so that is a
   new source code (`sec.submissions.company.v2`). Its format check is not decided yet.
2. ICONIQ (CIK 1825921) dropped as a person by `is_individual_filer` (already logged by
   the coordinator).
3. `company_source._business_addresses` puts an EDGAR country code in `region` when
   `stateOrCountry` holds one (ASML: `region: P7`, a Netherlands code, not a region).
4. `company_source._catalog_tickers` ignores `source_name` (both catalogs in one run
   would double every ticker).

## Step 7. Check (dry run)

`edgar-warehouse rules check` does not exist. Script: `scratch/dry_run.py`; output
`scratch/dry-run.txt`, `scratch/dryrun/dry-run-output.json`, bundle `scratch/dryrun/bundle/`.

How the sample was built (all local, no database, no network):
- 10 captured submissions files (Apple, ASML, Shell, Open Lending, Arrowpoint,
  Fundamental Ventures, Contraline, Kaydan, the person Solomon Kenneth A, ICONIQ) put
  through the repo's own capture writer (`SilverLandingStore.stage_submission`) and
  flushed by `write_landing_export` to local Parquet + landing manifest. No pagination
  files (not in inputs/).
- Ticker run: `replace_company_tickers` over the whole captured
  `company_tickers_exchange.json` (10,391 rows).
- **TEST Name Census** (labelled test-only): SEC side counted by the reader's own
  `census_filers` over this 10-file capture; **no GLEIF side** (no Golden Copy in
  inputs/), so every entry has 0 LEIs. It is not a real census.
- **TEST bronze receipts**: `bronze_receipts` over the 10 files with sandbox paths
  (`inputs/submissions/...`), not real bronze keys.
- The reader ran through its command: `edgar_warehouse.cli.main(["mdm",
  "prepare-clean-company", ...])`, exit 0, bundle written. Then the mapping ran as
  `clean.cli.batch_input` runs it (normalize, deferred records, occurrences), with the
  contract read from the rules file instead of the database. The bundle's pinned
  `dataset.json` equals the rules file's contract.

Results:
- 10 files -> 8 `sec_company` rows (the reader drops Solomon Kenneth A and ICONIQ as
  individuals) -> **4 Companies, 4 held back, 0 blocking**.
  - Companies: Apple (rule step 8), ASML (step 10), Shell (step 10), Open Lending (step 8).
  - Held back (`classification_deferred`, step 11, no probable kind, non-blocking):
    Arrowpoint, Fundamental Ventures, Contraline, Kaydan.
- What MDM would receive (Apple): `record_key 0000320193`; identifiers
  `cik 0000320193`, `sec_ein 942404110`; fields name, sic, sic_description,
  state_of_incorporation `CA`, fiscal_year_end `0926`, description unknown, address
  {street, city, region `CA`, postcode, country `US`}; kept outside fields: the name
  census entry, business postcode and country.
- Q6 holds: each record's trace block has only `record_key`, `adapter_version`,
  `classification`, `matching`: no file hash, run id or sync time. Each record's
  bronze file is named beside it (4 occurrences, locator `$`).
- Q3 as decided: ASML and Shell carry `sec_ein: 000000000` as text.
- Values to look at: Shell `state_of_incorporation: DC` (SEC's own value, kept as SEC
  writes it); ASML `region: P7` (ticket 3 above); ASML and Open Lending have no state of
  incorporation (SEC leaves it empty) -> unknown.
- `check_policy`, `check_company_sources` (SEC is in the Company ranks) and
  `validate_assertion` pass. `register_dataset`'s checks that need no database pass
  (stopped at the registry read with a stub connection).
- Record count accounting: 4 + 4 = 8 = `record_count`.

What the dry run shows beyond the rules file (for the operator):
- Each fact's fingerprint still changes with every capture, even with Q6's choice:
  the reader's `publication_key` holds the capture run id and member hashes, and the
  publication key is part of every fact's fingerprint (`evidence.assertion`); the name
  census entry kept for matching carries the census digest too. That is the reader's
  design, not the rules file.
- A held-back record keeps the reader's whole row as its raw record, including
  `_origin` (run ids, member paths, row number) and `last_synced_at`.

Gaps: this dry run is not a preview; it matched nothing against existing records or
GLEIF (no census LEIs), so SEC-first field choice was not exercised. No tests to run
(no `tests/` folder). Step 8 (`rules run ... --preview`) is not built: stopped there.

## Gaps in the skill found in steps 6-7

16. `files.dumps` writes the classification rule's version `2026-09-25.13` unquoted; it
    reads back as text, but a reader of the YAML can't tell that from the file.
17. Step 6 says "add a short YAML comment by hand"; nothing checks that a comment sits
    between keys rather than inside a folded value. The equality check catches a
    comment that changes a value, not one that makes the file misleading.
18. The skill has no way to write down a mapping the operator wants later (`sec_lei`)
    except a comment. And it doesn't say that adding it later is a new source code
    (identifiers are fixed once registered).
19. Step 7's `normalize` recipe (`publication_key: "dry-run"`, `artifact_sha256` of the
    sample file) skips what the reader adds: its publication key, record locators,
    deferred records, bronze occurrences. The faithful dry run is the loop in
    `clean.cli.batch_input`, which needs a database for `current_reading`; I copied the
    loop in scratch. A database-free `batch_input(contract=...)` would make this a command.
20. The reader needs three inputs the skill never mentions building: a landing
    manifest plus Parquet (made with `write_landing_export`), a separate ticker run,
    and a Name Census. A real census needs a full GLEIF Golden Copy, so the dry run
    used a test census with no GLEIF side. Name matching could not be exercised.
21. "The file hash, run id and sync time stay out of the record" (Q6) doesn't fully
    hold. The reader's publication key and the census digest in `matching` still make
    every capture a new fingerprint. The skill treats trace fields as a rules-file
    matter only.
22. Step 7 says the dry run is "not a preview" but gives no way to see SEC-first
    survivorship or the name matching rules. With only one source in the sample,
    nothing in the dry run exercises the merge rules the operator's Q5 answer relies on.
23. `register_dataset`'s database-free checks (a classification contract carrying no
    kind; formats; distinct non-blocking reasons) are not callable alone. I reached
    them with a stub connection. A `rules check` should run them.
