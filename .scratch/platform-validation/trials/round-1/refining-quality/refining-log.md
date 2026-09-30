# Refining log: SEC Company feed, data quality (change-quality mode)

Trial: cold, operator not reachable. Skill: skills/refining-rules/SKILL.md (+ data-onboarding SKILL.md, REFERENCE.md, APPROVE.md).
Repo: /Users/aneenaananth/projects/edgartools-platform-worktrees/claude-skills-4 @ 5d51e7d4 (read-only; nothing edited).
Capture: ~/.local/share/edgartools/clean-mdm/captures/sec.submissions.company/cm05-7000/
Work dir: ~/.local/share/edgartools/clean-mdm/trials/refining-quality/work/

## Mode choice
- Feed has rules/sources/sec.submissions.company/source.yaml and quality.yaml -> refining-rules, change-quality (skill line 11-12).
- Log location: skill says `<your scratchpad>/refining-log.md`; trial rules put it in work/. Used work/.

## Step 1: read quality.yaml and "the counts of its last runs"
- quality.yaml version `sec-company-quality-v1`, source code `sec.submissions.company.v1`:
  - fixes (in order): dc_state_is_empty (blank_values@1, state_of_incorporation in [DC]); state_from_name_tag (name_state_marker@1); standard_address (standardize_address@1 -> matching.address)
  - checks: name_present (present@1, exception); address_not_registered_agent (withhold); street_not_placeholder (placeholder@1 on matching.address.street, withhold); state_code_known (in_reference@1 sec-place-codes, flag)
- "The counts of its last runs": no command named; the Rules Database / Bookkeeping store is not available. NOT DONE (needs a database). See SKILL-GAP.

## Capture inventory
- receipts.jsonl is at the capture root (not inside bronze/ as the operator said): 7,001 lines = 1 ticker catalog (bronze/reference/sec/company_tickers_exchange/2026/09/02/company_tickers_exchange.json) + 7,000 submissions main documents (bronze/submissions/sec/cik=<cik>/main/2026/06/27/CIK<10>.json).
- copy.log: documents 7000, bytes 638,160,040, catalog_sha256 836140c5...
- Receipt keys are prefixed `warehouse/bronze/...`; the files live under `bronze/...` (strip `warehouse/`).

## The reader (map from its records, not the raw files)
- Reader = edgar_warehouse/mdm/clean/company_source.py; it reads landed silver parquet (sec_company, sec_company_filing, sec_company_address, sec_company_ticker), not bronze JSON.
- The capture holds only bronze JSON: no silver landing, no Name Census, no manifests. So the reader's bundle path (prepare_company_bundle) cannot run on it.
- Hand-built dry run (no second parser): silver rows from the repo's own loaders
  (edgar_warehouse/loaders/bronze_submission_extractors.py: stage_company_loader, stage_address_loader),
  business address via company_source.business_address, forms from filings.recent.form (as _filed_forms groups them),
  tickers from the pinned ticker catalog in the capture. Then adapters.normalize(contract=CONTRACT, policy=files.policy()).
  TEST INPUTS BUILT BY HAND: publication = {artifact_sha256: <receipt sha256 of the doc>, member: <key>, publication_key: "dry-run", revision: 0};
  sync_run_id "dry-run"; name_census omitted (None) - only matching.name_census reads it, no quality check does.
- Row keys aligned to the reader's rows: `sync_run_id` renamed `last_sync_run_id`; `business_address` via company_source.business_address; `forms`, `tickers` as the reader pins them. Ticker catalog: one list only (company_tickers_exchange); the reader's catalog run lands "both SEC ticker lists" - the second list is not in the capture (affects classification only, not quality).

## Step 2: dry run on a pinned sample (data-onboarding **test**, by hand; `rules check` not built)
- Timed 200 docs first: 1.4 s -> projected full pass ~50 s; ran the whole capture (7,000), since DC filers are rare.
- Every document's sha256 verified against receipts.jsonl: 7,000/7,000 match, 0 mismatches; catalog sha256 matches.
- Input manifest: work/input-manifest.txt (catalog + 7,000 "sha256 key" lines). batch_hash (sha256 of catalog sha + manifest) = a61bcfc8743fed947e8bb2f9e8da3eff735bc1306ce56cce53f5e4398fff2c24.
- Script: work/dry_run_quality.py. Results + up to 10 examples each: work/dry-run-7000.json (also dry-run-200.json from the timing run).
- Measured two ways, because `normalize` classifies BEFORE quality: a record the classification rule defers never reaches quality, so quality.counts() over normalize output undercounts filers (the cascade reads every filer through mapped_values).

| Fix / check (on_fail) | All 7,000 filers (mapped_values) | 6,414 MDM-bound (normalize; 586 classification_deferred) |
|---|---|---|
| fix dc_state_is_empty | 4 | 4 |
| fix state_from_name_tag | 12 | 11 |
| fix standard_address | 5,882 | 5,588 |
| check name_present (exception) | 0 | 0 |
| check address_not_registered_agent (withhold -> matching.address) | 9 | 6 |
| check street_not_placeholder (withhold -> matching.address.street) | 0 | 0 |
| check state_code_known (flag) | 0 | 0 |

Examples (full lists in dry-run-7000.json):
- registered agent: Phreesia (1521 CONCORD PIKE), N-able (1209 ORANGE ST), X-Energy (251 LITTLE FALLS DR), Neolara Corp. (C/O REGISTERED AGENTS INC).
- name tag: NORTHROP GRUMMAN CORP /DE/ -> DE; PARK OHIO INDUSTRIES INC/OH -> OH; OBRIEN JAMES J /KY -> KY (an individual filer, all-filer count only).
- standard address: MEDALLION FINANCIAL "437 MADISON AVE 38TH FLOOR" -> "437 MADISON AVE"; Mativ "100 KIMBALL PLACE"/"SUITE 600" -> "100 KIMBALL PL". Note it counts on 84% of filers: any case-insensitive difference counts, so the number says little.

## The DC fix: record by record, with vs without (dc_state_is_empty removed from an in-memory copy of the contract)
All 4 raw `stateOfIncorporation = DC` filers (description also "DC"):

| CIK | Name | Business address state | With fix | Without fix |
|---|---|---|---|---|
| 0000006951 | APPLIED MATERIALS INC /DE | CA | DE (blanked, then name tag) | DC |
| 0001306965 | Shell plc | none (foreign, SHELL CENTRE) | unknown | DC |
| 0001710366 | Core Natural Resources, Inc. | PA | unknown | DC |
| 0000070502 | NATIONAL RURAL UTILITIES COOPERATIVE FINANCE CORP /DC/ | VA | DC (blanked, then refilled by its /DC/ tag) | DC |

- Without the fix, state_code_known does NOT catch DC: sec-place-codes lists DC (US-DC). So the flag is no backstop; DC would reach MDM silently.
- Business address does NOT separate true DC from wrong DC: the /DC/-tagged filer (NRUCFC) has a VA business address. The evidence in the files is the name tag only: one /DE (Applied Materials), one /DC/ (NRUCFC), two with none (Shell, whose address is foreign; Core Natural Resources, where the files say nothing either way).
- Because fixes run in order, "keep DC when the name says /DC/" already happens (blank, then state_from_name_tag refills DC). But both fixes are then counted on a record whose value did not change: count 4 overstates the real change (3 records change).
- Risk that remains: an untagged filer truly incorporated in DC would lose its value. None is identifiable in this capture. Ticket ideas: net-change counting for fixes; a DC fix with an exception list, if the operator wants one (new code).
- Knowledge outside the files (from memory, not verified, no sec.gov): Applied Materials and Core Natural Resources are Delaware corporations, Shell plc is English, NRUCFC is a DC cooperative. Not used as evidence.

## Step 3: question for the operator (not reachable)
Q: "SEC writes DC as the state of incorporation for 4 of 7,000 filers in this capture. The DC fix blanks all 4. Applied Materials /DE then gets DE from its name tag; National Rural Utilities Cooperative Finance Corp gets DC back from its /DC/ name tag; Shell plc and Core Natural Resources are left unknown. Without the fix, all 4 keep DC and no check notices, because DC is a valid code. Keep the DC fix as it is? My recommendation: yes, keep it; open a ticket so a fix that a later fix undoes is not counted as a change."
ASSUMED answer: keep dc_state_is_empty unchanged. No on_fail changes proposed (the checks with 0 hits give nothing to decide on).

## Zero-hit checks proven able to fire (TEST INPUTS BUILT BY HAND, work/fire_checks.py, through mapped_values)
- empty entity_name -> exception quality_name_present
- business street "N/A" -> withheld matching.address.street
- state_of_incorporation "ZZ" -> flagged state_code_known
- street "1209 ORANGE ST" -> withheld matching.address
So the zeros in the 7,000 are measured zeros, not wiring errors.

## Input pin
- receipts.jsonl sha256 = b8553e6f16bd758239bff49187d83420c79de47c954abd09aed4dff0aa06b446 (primary batch identifier; all 7,001 receipts verified).
- derived batch_hash (catalog sha + sorted "sha256 key" lines) = a61bcfc8743fed947e8bb2f9e8da3eff735bc1306ce56cce53f5e4398fff2c24; secondary.
- dry-run-7000.json sha256 = 6edc7dc2b54ccfd215bac39c892232257d57b4649e836b0307cae8f5d55a416b (would be --proof-sha256).

## Step 4: new quality version
- No change proposed, so no new version name and no draft quality.yaml. (Had the fix been removed: `version: sec-company-quality-v2` in work/, never in the repo; a new source version.)
- mapdoc write/check: not needed without a rules change; not run (would write in the repo).

## test / approve / switch-on (NOT DONE: no database, and trial rules forbid)
- Would run: `rules save --source sec.submissions.company --version <v> rules/sources/sec.submissions.company/source.yaml` and `rules record-proof ... --proof-uri <dry-run-7000.json> --proof-sha256 <its sha256>` (needs RULES_DATABASE_URL). Not run.
- Would run `rules status --source sec.submissions.company` for last runs' counts (needs RULES_DATABASE_URL); unclear if it prints quality counts.
- Approve/switch-on: not applicable (no change), and forbidden in this trial.
- Repo: git status clean; nothing edited.

## SKILL-GAPs (most blocking first)
1. refining step 2 "Run the dry run (data-onboarding **test**) on a pinned sample: the files of one capture" + data-onboarding "run the reader on 5–10 sample records in the source's own format". The SEC reader reads landed silver parquet + Name Census + ticker manifests; the capture is bronze JSON only; no recipe from bronze to reader rows. Should give the recipe (stage_company_loader + stage_address_loader business row via company_source.business_address, filings.recent forms, catalog tickers, sync_run_id -> last_sync_run_id) or a `rules check --capture <dir>` command.
2. data-onboarding test "`normalize` runs the quality checks ... Report the counts (`quality.counts(records, deferred)`)". normalize classifies first; 586/7,000 deferred records never get quality, yet the cascade reads every filer through mapped_values. Should say: report all filers (adapters.mapped_values) and MDM-bound (normalize) separately.
3. refining step 3 "Ask the operator about its `on_fail`, with its count and two or three examples". A fix has no on_fail; data-onboarding says "each `on_fail` and each fix", refining drops fixes - yet "should this fix stay" is exactly this task. Should say: for a fix, ask keep/change/remove, with its count and examples.
4. refining step 3 "Pick the check or fix from REFERENCE.md ... using the same table as data-onboarding quality". Covers adding only; nothing on judging an existing fix. Should say: rerun with the fix removed from an in-memory copy of contract["quality"], show the record-by-record diff, and say whether any check catches the value without it.
5. refining step 1 "Read `rules/sources/<source>/quality.yaml` and the counts of its last runs." No command or place named; no fallback without a database. Should name it (`rules status --source <name>`? a Bookkeeping report?) and the fallback.
6. refining step 2 "Report the counts per check and fix". A fix counts when it fires even if a later fix restores the value (NRUCFC: DC blanked then refilled), so counts overstate. Should warn and report net changes.
7. refining step 2 "the files of one capture, named by their sha256" / data-onboarding "the input `batch_hash` (the captured files' manifest sha256)". A capture has receipts.jsonl (at the capture root, keys prefixed `warehouse/` that the folder lacks), no manifest. Should define batch_hash (e.g. sha256 of receipts.jsonl) and how receipt keys map to paths.
8. refining step 2 "Report the counts per check and fix". standardize_address counts whenever the matching copy differs beyond case (abbreviation, unit dropped, ZIP+4 cut): 84% of filers. Should say this count is expected to be high and is not a defect signal.
9. Hard stop "Request anything from `sec.gov` | Use the captured files and this repo". Judging a state-code fix needs truth the files lack (business address does not settle incorporation). Should say which in-repo evidence counts (name tag, GLEIF jurisdiction via the cascade) and to state when the files cannot settle it. (Also: the quality.yaml comment "The proving run lists every one for the operator" names no path.)
10. Shared "The log: `<your scratchpad>/refining-log.md`" while data-onboarding test says "Do this by hand and log it". Should say the refining log is used when data-onboarding steps run from refining-rules.
