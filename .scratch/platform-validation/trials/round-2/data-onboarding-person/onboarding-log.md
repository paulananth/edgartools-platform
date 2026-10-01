# Onboarding log — person-feed-1 (trial, work2)

Skill: skills/data-onboarding (claude-skills-4 worktree). Operator not reachable: questions are
written with a recommendation, then ASSUMED. Drafts in work2/rules (copy of repo rules/).
Log path stand-in: work2/onboarding-log.md (skill says .scratch/onboarding/<source>/onboarding-log.md).

## Trial-integrity note
- While searching the repo for `submissions.person` (identify step 2), my grep hit files under
  `.scratch/platform-validation/trials/round-1/...` (an earlier trial) before I excluded it. I saw
  a few grep lines (names, one quality version name). I did not open those files and excluded the
  path from all later searches. Decisions below are derived from the repo's own names
  (the skill's example `sec.submissions.person`) and the Person spec.
- A sibling `person-feed-1/work/` folder exists; not read.

## Mode: init / migrate
- Not run. No Rules Database in this trial (`RULES_MIGRATION_DATABASE_URL` unset). Skill says run init
  "if it is not there"; registration is only needed at **test**, so skipped and logged.

## Mode: identify
- Files: 300 JSON files `CIK##########.json`, 2.96 MB total, each an SEC EDGAR submissions document
  (`cik`, `entityType`, `name`, `addresses`, `formerNames`, `filings.recent` parallel arrays,
  `filings.files` empty in all 300). All 300 are `entityType: other`; forms filed are Form 4 (12,584),
  3, 144, 13G/13D — i.e. the submissions documents of **reporting owners** (insider filers).
- Q1 (would ask): "These look like SEC EDGAR submissions files for 300 reporting owners — mostly
  individual insiders who file Forms 3/4/5 — captured from the SEC submissions feed. Is that right?"
  Recommendation: yes. **ASSUMED yes.**
- Repo search (excluding .scratch/platform-validation): `rules/sources/sec.submissions.company` already
  maps these same files (SEC submissions) to **Company**. No code names `sec.submissions.person`;
  no reader loads a person rules file (`rules_files.source(`/`mdm_contract(` only in
  company_source.py and gleif_source.py). => skill case "files already feed one kind, adding another
  kind (Person)" => onboarding, own folder.
- Names (skill's rule 4, its own example): folder `sec.submissions.person`, source code
  `sec.submissions.person.v1`, family `submissions` (the family the repo already names for these files,
  `bronze.family` in sec.submissions.company). Logged.
- Registration: `rules status --source sec.submissions.person` -> `KeyError: 'RULES_DATABASE_URL'`
  (full traceback, ~30 s start). Logged; continued as the skill says.
- New domain: yes. `rules/merge/kinds/person.yaml` does not exist; `person` IS in `KINDS`
  (evidence.py). Requirements: `docs/specs/person/consumer.md`.
- **Output:** name "SEC EDGAR submissions, reporting-owner filers"; source `sec.submissions.person`;
  code `sec.submissions.person.v1`; family `submissions`; NEW DOMAIN Person.

## Mode: profile
- `rules profile` not built (rules-skill ticket 06): profiled by hand, work2/profile.py ->
  work2/profile.json (per path) + work2/profile-rows.json (per record). 2.96 MB < 100 MB, so one full
  pass (1.2 s).
- One record type (the submissions document). `filings.recent` is a table stored as parallel arrays:
  checked every column has equal length (0 ragged files); rows not needed for the Person mapping.
- Record key: `cik` — 300/300 filled, 300 distinct, all 10-digit zero-padded strings, and all equal
  the file name's CIK (checked by regex + filename compare). No other always-filled unique path
  besides `name` (300 distinct).
- Identifiers: `cik` (checked: `^\d{10}$`, 300/300). `lei` 1/300 (`549300TVM2FDH7X07T06` on
  "Man Investments Finance Inc." — 20 chars, passes mod 97, checked). `ein` 7/300, **5 of them are the
  placeholder `000000000`**, the 2 real ones on "Bexil Securities LLC" and "RYPS, LLC" (entities).
- Names: 300/300 filled; 287 look like people in EDGAR conformed form (`SHAMASH YACOV A`,
  `LAST FIRST MIDDLE`), 12 carry a legal-form token (LLC, Ltd, Inc, SAS, HOLDINGS...), plus
  "Kapitalo SND Master Fundo de Investimento Multimercado" (a fund). 0 single-token names.
- "Structurally empty" (C-J: sic, stateOfIncorporation, ein, tickers, ownerOrg, fiscalYearEnd all
  empty): 287/300; the 13 non-empty ones are exactly the 13 entity-looking names.
- Always-empty paths (300/300): sic, sicDescription, ownerOrg, category, description, website,
  investorWebsite, flags, tickers, exchanges, insiderTransactionForIssuerExists (=0).
- Addresses: mailing 295/300 filled, business 13/300. Person spec: owner addresses are "Never captured
  into MDM" — noted, not profiled further. `stateOrCountry` uses both `None` (17) and `''` (8 business).
- `formerNames`: 6/300 non-empty (list of {name, from, to}) — candidate `name_variants`.
- Relationships: no keys to other records in the document itself (issuer CIKs live in the Form 3/4/5
  artifacts, not here). `filings.recent.accessionNumber` points at filings, not records.
- Placeholders logged: `ein = "000000000"` (5); `''` vs `None` for empty.
- Defects: 0 (no missing key, malformed CIK, ragged array, bad LEI check digit).

## Mode: map
- Research read: SKILL/REFERENCE, `KINDS`, docs/specs/person/consumer.md (Source authority, rule C-J,
  Binding tiers, The Person projection), rules/merge/kinds/company.yaml, policy.yaml,
  activation.py (ACCEPTED_BARS: person classification 0.99 @ 0.975), classification.py,
  primitives.py, the C-J prototype `.scratch/mastering-policy-language/prototype/policy-person.json`.
  Not read (time-box): CONTEXT.md, docs/specs/clean-mdm/source-evidence.md, company-policy.md — logged.
- Reader: none (no code loads a person rules file or names the source code) => mapped raw JSON paths.
- Kind: Person, but SEC types people and firms alike as `other` (300/300) => classification rule.
- Record key: [`cik`], format `sec_cik`. Identifier: `cik` (issued by SEC, joins records).
- Fields: `legal_name <- name` (Person projection name). `display_name` is derived by the policy.
  `formerNames` -> `name_variants[]` NOT mappable: `field_shape: nullable_text` has no list field.
  Logged for a ticket (new-field/shape work). Addresses deliberately unmapped (spec: never captured).
- Relationships: none in this document (issuer links come from Form 3/4/5 artifacts) — logged for
  the ownership source.
- Values of another kind: `lei`/`ein` sit only on entity records here -> not Person values.
- Provenance: none mapped (no reader keeps a native record; capture hashes stay beside the record).
- Publication: semantics patch; completeness "one filer per document, no retirement by absence";
  effective_time unknown.
- Questions (would ask, one at a time; all ASSUMED):
  - Q2 "Shall the Person records from these files be a new source `sec.submissions.person`, code
    `sec.submissions.person.v1`, family `submissions`?" Rec: yes (skill's own naming rule). ASSUMED.
  - Q3 "SEC marks all 300 `other`; 287 look like people, 13 are firms or funds. Shall each record be
    classified by the Person rule C-J rather than calling every record a Person?" Rec: yes. ASSUMED.
  - Q4 "Keep only the CIK as the Person's identifier; leave SEC's `ein` (5 of 7 are 000000000) and
    `lei` (1 record) out, since here they appear only on firm records?" Rec: yes; lookup-only syntax
    does not exist (ticket). ASSUMED.
  - Q5 "Shall `formerNames` wait for a list-shaped `name_variants` field (a ticket), rather than be
    squeezed into text?" Rec: wait. ASSUMED.
  - Q6 "The Person rules take a record with no effective date (`allow_unknown_effective: true`), as
    Company does; SEC submissions state none. Agree?" Rec: yes; the C-J prototype had `false` for
    person_name, which would make every SEC name unusable. ASSUMED.
- Written (work2/rules only): sources/sec.submissions.person/source.yaml, merge/kinds/person.yaml,
  by work2/build_rules.py (`files.dumps`/`files.write_source`), then comments inserted by
  work2/add_comments.py. `files.source(...)` equals the dict passed (before and after comments);
  person.yaml loads equal; `check_policy(files.policy(root=work2/rules))` passes.
- C-J port (for the operator): new id `sec-person-candidate` 2026-09-30.1 (source must equal the
  contract's code); step 0 dropped (the record is the submissions document); step 1 turned from
  verdict `company` into `deferred` + probable_kind company (a person-kind rule's `company` verdict
  can never be activated there and would raise the BLOCKING `classification_not_activated`);
  paths `owner_name` -> `name`, `sec.submissions.*` -> raw keys. Lists copied from the prototype.
- `person-cik` binding rule declared (shape of company-cik), Identifier Contract `cik` without
  `verification`. Nothing added to policy.yaml `automatic_rules`.
- Silver target: no reader, and the general silver writer is not built (rules-skill ticket 05):
  MDM target only. Logged.

## Mode: quality
- Candidates from the profile, counted on all 300:
  - `legal_name` missing -> `present@1`, `on_fail: exception` (critical data element): 0/300 touched.
    Listed `quality_legal_name_present` as non-blocking. Q7 (would ask): "A Person with no name is
    set aside as an open exception, never merged, never stopping the run — 0 of 300 here. Agree?"
    Rec: yes. ASSUMED.
  - `ein = 000000000` placeholder (5): not mapped, so no fix. Logged.
  - No address, no state code mapped -> no address checks.
- Written work2/rules/sources/sec.submissions.person/quality.yaml (`sec-person-quality-v1`);
  `files.source` loads it inside the contract.

## Mode: metadata
- `rules mapdoc write --only sec.submissions.person --root work2/rules` -> MAPPING.xlsx (exit 0).
- `rules mapdoc write --only person --root work2/rules` -> merge/kinds/person.xlsx (exit 0).
- `rules mapdoc check --root work2/rules` -> exit 0, silent.
- `rules catalog plan --root work2/rules` -> work2/catalog-plan.json (exit 0). Publish not run (after
  merge only; no OPENMETADATA_*; no network).
- Steward agreement (step 2): operator unreachable. Q8: "Here are the two workbooks; do the stewards
  agree the mapping?" ASSUMED agreed, for the trial only.
- **Tool findings (tickets):**
  1. person.xlsx Classification sheet renders step 3's NEGATED `token_match@1` without "not": the
     workbook says step 3 needs a legal-form token, the opposite of the rule. Stewards would review a
     wrong rule. (`negate` ignored by the mapdoc writer.)
  2. person.xlsx Matching rules describes `person-cik` as "the CIK a **Company** holds" — Company is
     hard-coded.
  3. Classification "When" for token_match/name_shape is raw args, not plain words.
  4. Each `rules` command took 1-3 minutes here (skill says ~30 s).

## Mode: test
- Dry run by hand (`rules check` not built, ticket 03). No reader -> `normalize` with the draft
  contract, `files.policy(root=work2/rules)`, publication {artifact_sha256 of each file, member,
  "dry-run", 0}; all 300 files (cheap). Script work2/dry_run.py -> work2/dry-run.json.
  - As written: accepted 0; deferred `classification_not_activated` 287 (BLOCKING, expected for a new
    kind), `classification_entity_undetermined` 12 (step 2), `classification_deferred` 1 (step 4,
    "Kapitalo SND Master Fundo de Investimento Multimercado").
  - TEST INPUT pass (person verdict added to automatic_rules in memory only): accepted 287, blocking 0,
    same 13 held back. Quality counts: none fired (0 exceptions).
  - The split equals the profile's 287/13 exactly; by my own reading of names all 287 are people and
    all 13 firms/funds (researcher's reading, not an operator label).
  - Merge rules accept the source: `sec.submissions.person.v1` is in person `defaults.sources`
    (checked by hand; no Person analogue of `check_company_sources`).
  - Reader tests: none (no reader).
- Classification proof: NOT measured. This corpus cannot clear the Person bar on its own: 287/287
  gives Wilson LCB(97.5%) = 0.9868 < 0.99; >= ~381 person-labelled records needed, per step, plus an
  adversarial fixture and operator-held labels. Nothing written to pending-proofs.yaml.
- Proving run: work2/test_person_proving_run.py (core fixtures, disposable postgres:16). TEST INPUTS:
  contract `kind: person` in memory; placeholder `verification` on the cik Identifier Contract;
  person-cik activated in memory. Run started, printed nothing and did not finish within the
  5-minute budget (`timeout 290` on `uv run` did not stop pytest). Killed pytest; removed its
  container `clean-mdm-test-3fb8ac4565` by hand (the fixture's cleanup never ran). No result.
  **Blocked here.** Not diagnosed (time-box).
- Inputs and proof (not saved): work2/input-manifest.json (sorted {member, sha256, bytes}); its sha256
  is the batch_hash; draft proof work2/proof-draft.json (`passed: false`). Version label would be
  `sec.submissions.person-2026-09-30.first`. `rules save` / `rules record-proof` NOT run (trial rule;
  no Rules Database).

## Mode: approve / switch-on
- Not done (trial rule). Would need, in order: C-J proof -> operator switches on sec-person-candidate
  then person-cik -> merge version `platform` saved/proved/approved/activated -> source version.
- Digests (not saved): source 386a3ec5…b8af; policy 9a4435ad…c337; batch_hash 5ae02088…7339;
  proof-draft sha256 b154ebc3…4bee.

## SKILL-GAPs (most blocking first)
1. **New-domain proving run is circular / unrunnable.** "A proving run, for anything that matches
   records" + "Leave out `verification`: it is filled in when the operator approves the contract on its
   proving corpus" + order "1. Measure the classification rule's proof ... 2. The operator switches on".
   `register_policy` refuses activations without proof/verification, and without activation every
   Person record is `classification_not_activated`, so a proving run needs test-only activations the
   skill never describes. Fix: give the new-domain proving-run recipe (in-memory kind + placeholder
   verification, labelled test input), or say the proving run comes after classification switch-on.
2. **Proving run gives no time/progress guidance or cleanup rule.** "Run it with Docker ...
   `uv run --no-sync pytest -q -s <file>`". Mine hung silently >5 min; `timeout` on `uv run` did not
   stop pytest and the container was left behind. Fix: say expected runtime, use `timeout -s KILL` on
   pytest directly, and "after a killed run, `docker rm -f clean-mdm-test-*`".
3. **Classification proof needs labels and a sample size the skill doesn't state.** "Measure the
   classification rule's proof on this source: a labelled sample, at the kind's
   `bars.classification`." Who labels, how many (0.99 @ 0.975 needs >= ~381 correct/step), what goes in
   pending-proofs.yaml. Fix: add the minimum n and the pending-proofs entry shape.
4. **Porting a rule whose verdict is another kind.** "port it under a new id" — C-J step 1 emits
   `company`; under the person kind that verdict can never activate and blocks. Fix: say "a verdict of
   another kind becomes `deferred` + `probable_kind`".
5. **`files.write_source(body, folder)` body shape unstated.** "`files.write_source(body, folder)`
   writes both files." I first put `quality` at the top level; it silently wrote source.yaml only.
   Fix: "put each block in `mdm.<code>.contract.quality` with `version`".
6. **List-shaped Person fields.** "Fields: use the kind's names" — `name_variants[]` is a list;
   `field_shape: nullable_text` cannot carry it. Fix: say to log it and leave it out.
7. **Mapping Document is wrong for a new kind** (negated step shown without "not"; "Company"
   hard-coded) but the skill says "Only an agreed mapping goes on to **test**". Fix: warn, ticket.
8. "The CLI takes about half a minute to start" — here 1-3 min per command. Fix: say "up to a few
   minutes; run in background".
9. "Keep `.scratch/onboarding/<source>/onboarding-log.md` on your branch" vs trials: no sandbox log
   path. Fix: "in a trial, beside your draft folder".
10. `allow_unknown_effective` for a new kind is not mentioned; copying the prototype (`false`) would
    make every SEC name unusable. Fix: name it in the kind-file checklist.
11. Identify step 2 "Search ... the repo" hits earlier trial output under .scratch/platform-validation.
    Fix: name paths to exclude.
