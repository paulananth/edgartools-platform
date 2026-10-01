# Onboarding log: sec.submissions.person (Person feed 1)

Skill: `skills/data-onboarding` (SKILL.md, REFERENCE.md, APPROVE.md), walked mode by mode.
Ticket: `.scratch/platform-validation/issues/05-onboard-person-feed-1.md`.
Worktree `claude-person`, branch `claude/person-feed-1`. Nothing committed.
Session: Claude, 2026-10-01, 06:55-07:12 ET.

**Operator's rule for this session: no coding, only configuring.** Only YAML under
`rules/`, this log and the ticket were edited. Only `edgar-warehouse rules ...` commands
and read-only inspection (`cat`, `ls`, `grep`, `head`, `shasum`, `unzip -p` to read a
workbook's text) were run. Every step the skill describes that needs Python, a script,
pytest or Docker is recorded below as **SKILL-GAP: needs code, not configurable**, with
the skill's exact wording, and was not done.

One slip: `python3 --version` (output discarded) was run once in a
read-only `sed` command, at 07:09 ET. It read and changed nothing. No other program was run.

Starting point: the round-2 trial drafts
(`.scratch/platform-validation/trials/round-2/data-onboarding-person/draft-rules/`),
copied into `rules/` and corrected (comments only, see map).

## Environment

- `RULES_DATABASE_URL`: **unset** (checked with `[ -n ... ]`, value never printed).
- `RULES_MIGRATION_DATABASE_URL`, `RULES_MDM_ACTIVATION_DATABASE_URL`,
  `OPENMETADATA_URL`: **unset**.
- So `rules init`, `migrate`, `status`, `save`, `record-proof`, `pending`, `approve`,
  `activate` and `catalog publish` were **not run**.
- CLI start-up was quick here: 7-17 s per `rules mapdoc`/`catalog` command (the skill
  says 30 s to 3 min).

## init / migrate

- Not run: `RULES_MIGRATION_DATABASE_URL` unset. The skill: "Set up the Rules Database
  first if it is not there (**init**)". Whether it is there cannot be checked without
  `RULES_DATABASE_URL`. **Blocked**: question Q10.

## identify (done)

- Files: `~/.local/share/edgartools/clean-mdm/captures/sec.submissions.company/all-76230/`.
  `receipts.jsonl` has 76,231 lines: **76,230** `submissions/sec/cik=<cik>/main/.../CIK<10>.json`
  documents, 0 pagination files, and **1 non-submissions file** (the ticker catalog
  `reference/sec/company_tickers_exchange/2026/09/02/company_tickers_exchange.json`).
  1.5 GB under `bronze/`. `manifest.json` says "every SEC filer in bronze".
- One document looked at (`head`): `CIK0001035350.json`, an SEC submissions document
  (`cik`, `entityType`, `name`, `ein`, `lei`, `addresses`, `formerNames`, `filings.recent`).
- These are the same files `rules/sources/sec.submissions.company` maps to Company. The
  skill's case: "Its files already feed one kind (e.g. SEC submissions -> Company), and
  you are adding another kind from them (e.g. Person): this is onboarding."
- Repo search (excluding `.scratch/**/trials/`): no `rules/sources/sec.submissions.person`,
  no reader loading it, no code naming `sec.submissions.person.v1`.
- Names, from the skill's own rule 4 (its example is exactly this feed): folder
  `sec.submissions.person`, code `sec.submissions.person.v1`, family `submissions`
  (`bronze.family` in `sec.submissions.company`).
- Registration (`rules status --source sec.submissions.person`): not run,
  `RULES_DATABASE_URL` unset. The skill says to log it and go on.
- **New domain: yes.** No `rules/merge/kinds/person.yaml` existed. `person` is in `KINDS`
  (`edgar_warehouse/mdm/clean/evidence.py`). Requirements: `docs/specs/person/consumer.md`.
- **Output:** "SEC EDGAR submissions documents of every filer, read for Person";
  source `sec.submissions.person`; code `sec.submissions.person.v1`; family
  `submissions`; new domain Person. Confirmation question: Q1.

## profile (SKILL-GAP)

- **SKILL-GAP: needs code, not configurable.** Skill: "`rules profile` is **not built
  yet**. Profile by hand, and log the gap: 1. Write a short script in your scratchpad that
  streams the files." Not done. The ticket's "profile: all 76,230 files" stays unticked.
- What was counted instead, by `grep` over the documents (inspection, not a profile;
  about 40 s a pass):

  | Count | Documents |
  |---|---|
  | `entityType: other` | 67,421 |
  | `entityType: operating` | 7,016 |
  | `entityType: investment` | 1,793 |
  | top-level `name` empty or one character | 0 of 76,230 |
  | `lei` filled | 392 (75,838 null) |
  | `ein` 9 digits | 42,456 (33,772 null, 2 malformed 8-digit values: `75163030`, `23903620`) |
  | `ein` = placeholder `000000000` | 15,061 (12,767 of them `entityType: other`) |
  | `formerNames` non-empty | 9,580 |

- Placeholder logged: `ein = "000000000"`. Not mapped here, so no fix is needed. **But**
  rule C-J's step 3 needs `ein` empty ("structurally empty"), so a person whose
  document carries `000000000` falls to step 4 (Steward). Up to 12,767 `other` filers
  are touched. Research 18 treated it the same way (`_structural_empty`, `18-classify.py`
  line 492), so this is coverage, not precision. Question Q11.
- 2 malformed EINs (8 digits): a defect in a value this contract does not map. Logged
  for the Company feed's reader ticket. It does not block this feed.

## map (done, with gaps)

- Research read: SKILL, REFERENCE, APPROVE; `docs/specs/person/consumer.md` (Source
  authority, rule C-J, Binding tiers, The Person projection); `rules/merge/kinds/company.yaml`;
  `rules/merge/policy.yaml`; `rules/merge/pending-proofs.yaml`;
  `rules/sources/sec.submissions.company/*`; `edgar_warehouse/mdm/clean/activation.py`
  (`ACCEPTED_BARS`, `_check_proof`); `classification.py`; `adapters.py`
  (`_classify`). Not re-read: `CONTEXT.md`, `docs/specs/clean-mdm/source-evidence.md`
  (the trial read the rest; no new decision depends on them).
- Reader: none for Person. The paths are the raw submissions JSON.
- **Written** (copied from the trial draft, then edited as text, comments only; no value changed):
  - `rules/sources/sec.submissions.person/source.yaml`: header says every filer is read
    and the rule decides; non-blocking comment names the 8,809 company documents;
    identifier comment replaced "ASSUMED (trial)" with the full-capture counts and
    "awaiting the operator"; `formerNames` comment uses the full-capture count.
  - `rules/sources/sec.submissions.person/quality.yaml`: header comment added.
  - `rules/merge/kinds/person.yaml`: header comment only. The classification rule
    `sec-person-candidate` 2026-09-30.1 and the `person-cik` matching rule are
    **byte-for-byte the trial's**, since the classification score is tied to that version.
- **SKILL-GAP: needs code, not configurable.** Skill: "Write the values with
  `files.dumps`, or both files at once with `files.write_source(body, folder)`" and "Check
  it: `files.source('<source>')` must equal what you passed to `files.dumps`." Not done.
  Files were edited as text. The only loaders run were `rules mapdoc write`, `mapdoc check`
  and `catalog plan`, which load every rules file and succeeded (below).
- Set-aside check (ticket item), done by **reading the code**: `adapters.py` raises
  `classification_<verdict>` for a verdict that is not a kind. So step 1 (`operating` or
  `investment`, `deferred`, probable kind company) raises `classification_deferred`, step 2
  raises `classification_entity_undetermined`, and step 4 raises `classification_deferred`.
  All three, plus `quality_legal_name_present`, are in `nonblocking_deferred_reasons`.
  **Company documents read as Person do not block the feed.** The one blocking reason
  is `classification_not_activated` (the person verdict before it is switched on),
  which is expected for a new kind.
- `nothing added to automatic_rules` in `policy.yaml`: checked (`git diff`).
- Silver target: no Person reader, and the general silver writer is not built
  (rules-skill ticket 05). MDM target only, as the skill says.
- Not mappable, logged for tickets:
  - `formerNames` -> `name_variants[]`: no list-shaped field syntax.
  - `ein`, `lei` as lookup-only identifiers: no syntax (also a Company-side decision, 2026-09-26).
  - Relationships: none in this document (issuer links are in Forms 3/4/5, feed 2).

## quality (done; on_fail awaits the operator)

- One check: `legal_name_present`, `present@1` on `fields.legal_name`, `on_fail: exception`.
  It touches **0 of 76,230** (grep: no empty top-level name). Question Q5.
- No fix: `ein` and addresses are not mapped.
- **SKILL-GAP: needs code, not configurable.** Skill: "Count, on the profile sample, how
  many records each would touch." Done by grep for this one check only. A general count
  needs the mapping applied, which needs code.

## metadata (done)

| Command | Time | Result |
|---|---|---|
| `rules mapdoc write --only sec.submissions.person` | 17 s | exit 0; wrote `rules/sources/sec.submissions.person/MAPPING.xlsx` |
| `rules mapdoc write --only person` | 7 s | exit 0; wrote `rules/merge/kinds/person.xlsx` |
| `rules mapdoc check` | 9 s | exit 0, silent. `company.xlsx` unchanged. |
| `rules catalog plan` | 8 s | exit 0; 25.7 KB JSON (scratchpad, not kept). It holds the `sec.submissions.person` schema, the `sec.submissions.person.v1` table, the `mdm.clean.person` table with `legal_name`, and lineage `name` -> `person.legal_name`. |

- The workbook text was read with `unzip -p`. **The two trial findings are still there:**
  1. `person.xlsx`, Classification sheet, step 3 (the person verdict) reads "token_match@1
     ... token_list: entity_legal_form; min_count: 1" with **no "not"**. The rule says the
     opposite (`negate: true`). Stewards would review a wrong rule.
  2. `person.xlsx`, Matching rules, `person-cik`: "The record's CIK is the one a
     **Company** holds; and Exactly one **Company** holds that CIK". "Company" is
     hard-coded.
  3. The "When" text for `token_match`/`name_shape` is raw args, not plain words.
- New: the catalog has **no lineage from the `submissions` feed to
  `sec.submissions.person.v1`**. The feed is declared only under the Company source's
  `acquisition`, and this source has none (the skill leaves `acquisition` to Bookkeeping).
- Step 2 (steward agreement): **blocked**, operator question Q6. Step 5
  (`catalog publish`): after merge only, and `OPENMETADATA_*` is unset.

## test (blocked; SKILL-GAPs)

- **Dry run. SKILL-GAP: needs code, not configurable.** Skill: "**Feed with no reader:**
  pass records through `edgar_warehouse.mdm.clean.adapters.normalize`: `contract=` your
  contract, `source_code=` your code, `policy=files.policy()`". Not done. The ticket's dry
  run over all files stays unticked. (The round-2 trial ran it on 300 files: 287
  `classification_not_activated`, 12 `entity_undetermined`, 1 `deferred`.)
- "Check the kind's merge rules accept the source ... for any other kind, check
  `defaults.sources` by hand": **done by reading.** `person.yaml` `defaults.sources` =
  `[sec.submissions.person.v1]`. The Person workbook's Preferred sources sheet shows the same.
- "Run the reader's tests, if any": no reader, and pytest is not allowed this session.
- **Proving run. SKILL-GAP: needs code, not configurable.** Skill: "Write it as a pytest
  file that uses the Clean MDM fixtures ... Run it with Docker (on macOS, Colima)". Not done.
- **Inputs and proof. SKILL-GAP: needs code, not configurable.** Skill: "**Digest, before
  saving:** `from edgar_warehouse.bookkeeping.clean.config import digest`" and "**Input
  manifest:** a JSON list of `{"member", "sha256", "bytes"}`". Not done. For a bronze
  capture the skill says to use the sha256 of `receipts.jsonl`:
  `3aee0205...d5c247` (shasum). That file also lists the ticker catalog, which is not a
  submissions document. Logged for Bookkeeping.
- **`rules save` / `rules record-proof`: not run.** `RULES_DATABASE_URL` is unset, and
  there is no test run to record. The version label would be
  `sec.submissions.person-2026-10-01.first`.

### Classification proof (recorded, not ready)

Measured earlier (2026-09-30, not redone):
`.scratch/onboarding/sec.submissions.person/classification-score.json`. That run scored
`sec-person-candidate` 2026-09-30.1 against research 18's labels: **1,380 labels**, the
1,220 in `18-sample.jsonl` plus the 160 in `18-extension-sample.jsonl`. The ticket says
1,220. Results: step 3 (person) 841/841, step 2 (entity_undetermined) 476/476, 0 wrong.
`population.json` (an interrupted run) was ignored.

- **Finding: the score file's lower bound uses the wrong z.** Its `wilson_lower_975`
  (0.9941) uses z = 2.2414, which is one-sided 0.9875. The engine (`activation.py`)
  takes z = `inv_cdf(0.975)` = 1.959964. With all correct, the bound is n/(n+z^2) =
  841/844.841459 = **0.99545304**. Worked by hand: z^2 = 3.841459, ratio
  3.841459/844.841459 = 0.00454696.
  - `_check_sample` refuses a stated bound that is above the recomputed one, or more than
    1e-5 below it. So both 0.9941 and 0.9955 would be refused.
  - Written: **0.995453**, cut off at six places. It clears the 0.99 bar. The operator's
    "agreed" (2026-09-20) cited "Wilson 95% lower bound 0.9955". That is the same z
    (two-sided 95% = one-sided 0.975), so the numbers agree.
- Written to `rules/merge/pending-proofs.yaml` as `sec-person-candidate`:
  - `n` 841, `correct` 841, `lower_bound` 0.995453.
  - `cohort.by_step."3"` with the same numbers. The engine requires one sample per step
    that emits the verdict, and only step 3 emits `person`.
  - `cohort.files`: sha256 of `18-sample.jsonl`, `18-extension-sample.jsonl`,
    `18-classify.py`, `score_classification.py` and `classification-score.json`, plus the
    capture's `receipts_sha256`.
  - `approved_by: null`, `approved_at: null`.
  - **`adversarial.fixture_sha256: null`**: no adversarial fixture exists for this rule.
    `_check_proof` refuses an entry with none, so `rules approve --rule` would refuse it
    as it stands. This is not invented and not borrowed. Question Q8.
- The labels are **an earlier session's own reading** (research 18: "Labels are **my own
  reading**"), not the operator's. They were drawn from **Form 3/4/5 reporting owners**,
  not at random from this feed's 76,230 filers. This feed also holds 13D/G, Form D and 144
  filers who never filed a Form 3/4/5. The skill says "records drawn at random from the
  files". Question Q7.
- **Population check. SKILL-GAP: needs code, not configurable.** The ticket item "people
  the rule finds that never filed a Form 3/4/5" needs a pass running the rule over all
  documents. Not done.

## approve / switch-on (not reached)

- Nothing approved, nothing activated, no words recorded. APPROVE.md, "Before you ask":
  "A version with no test run cannot be approved." No test run exists, and no Rules
  Database is configured.
- The order for a new domain (skill, "A new domain: the order of approvals"):
  1. classification proof
  2. the operator switches on `sec-person-candidate`, then `person-cik`
  3. merge version `platform` saved, proved, approved and activated
  4. source version tested, approved and activated.

  Step 1 is incomplete (Q7, Q8).

## CI risk from adding a kind (finding)

Adding `rules/merge/kinds/person.yaml` changes `files.policy()`, which
`company_source.POLICY` loads whole. Adding an entry to `pending-proofs.yaml` changes
`company_source.NAME_PROOFS`. Tests that pin these will fail. Tests were not run (not
allowed); found by reading:
- `tests/mdm/test_clean_company_source.py:421`: `assert set(company_source.POLICY["kinds"]) == {"company"}`.
- `tests/mdm/test_rules_config_digests.py:108`: `digest(company_source.NAME_PROOFS) == BEFORE["name_proofs"]`,
  plus the pinned policy digests.
- `tests/mdm/test_clean_activation.py:544-557`: `policy_layers.digests(POLICY)` pinned list.

- `tests/mdm/test_clean_cik_contract.py:36`, `test_each_feed_maps_only_the_identifiers_it_issues`:
  it walks every folder under `rules/sources/` and pins the set of identifier mappings
  to Company's CIK and GLEIF's LEI. `sec.submissions.person.v1 -> cik` adds a pair. Its
  issuer set comes from Company's Identifier Contract only, so the pair would read
  "not issued" anyway. Its docstring: "A feed that starts to must bring that change
  with it", meaning the Merge Stage's identifier-conflict count. That is a real
  question for Person's CIK, not just a pin.
- `tests/unit/test_rules_catalog.py:24` walks `sources/*/source.yaml` too, but compares
  against the catalog's own list, so it should hold.

Production code: `company_source.NAME_PROOFS` loads the whole `pending-proofs.yaml`, but
nothing in `edgar_warehouse/` iterates it (grep). It is read by rule id only, so the new
`sec-person-candidate` entry does not change how Company runs. **No command run in this
session parsed `pending-proofs.yaml` with the strict loader** (`mapdoc` and `catalog`
read the kind and source files). The new entry is YAML no command has checked; `rules
approve --rule` would be the first.

A config-only onboarding of a new kind cannot pass CI as the repo stands. It also changes
the live merge document's digest, so Company's own registered policy would differ.
Question Q9.

## SKILL-GAPs (most blocking first)

1. **Dry run needs code.** Skill: "pass records through
   `edgar_warehouse.mdm.clean.adapters.normalize`". Fix: build `rules check --source <s>
   --sample <n>` (rules-skill ticket 03) printing accepted / set aside by reason / quality counts.
2. **Proving run needs code and Docker.** Skill: "Write it as a pytest file that uses the
   Clean MDM fixtures". Fix: build Preview (rules-skill ticket 04) as a `rules` command.
3. **Digest and input manifest need code.** Skill: "`from
   edgar_warehouse.bookkeeping.clean.config import digest`" and "a JSON list of
   `{"member", "sha256", "bytes"}`". Fix: `rules save` prints the digest; add `rules
   manifest <capture>`.
4. **The proof entry's shape is incomplete in the skill.** Skill: "in the shape of the
   entries there: `method`, `one_sided_confidence`, `n`, `correct`, `lower_bound`,
   `adversarial` (`n`, `violations`), `cohort` ...". It omits `cohort.by_step.<step>` for
   every step emitting the verdict, and that `adversarial.fixture_sha256` is mandatory
   (`_check_proof`). The existing `pending-proofs.yaml` entries (name binding) have no
   `by_step`, so copying them fails. Fix: add both to SKILL.md step 1.
5. **Measuring the classification proof needs code.** Skill: "records drawn at random from
   the files, each labelled by hand". Drawing, and scoring a rule against labels, is a
   script. Fix: `rules measure --rule <id> --labels <file>`, which also computes z from
   `one_sided_confidence` (it would have caught the 0.9941 mislabel).
6. **Writing and checking the rules files needs code.** Skill: "Write the values with
   `files.dumps`" / "`files.source('<source>')` must equal what you passed". Fix: `rules
   validate [--source <s>]` (load, round-trip, `check_policy`). Edit-as-text plus `mapdoc
   check` is the only config-only path today.
7. **Profile needs code.** Skill: "Write a short script in your scratchpad that streams
   the files." Fix: `rules profile` (rules-skill ticket 06).
8. **Quality counts need code.** Skill: "Count, on the profile sample, how many records
   each would touch." Fix: part of `rules check`.
9. **Adding a kind breaks pinned CI tests, and the skill does not say so** (section above).
   Fix: scope those tests to the Company kind and to Company's proof entries, or warn in
   the skill that a new kind needs a test change (code).
10. **Mapping Document is wrong for this kind:** a negated step is shown without "not",
    "Company" is hard-coded in the matching rule text, and the args are raw. Skill: "Only
    an agreed mapping goes on to **test**." Fix: ticket the mapdoc writer.
11. **Catalog lineage is missing** for a second kind read from another source's feed.
    REFERENCE: "Lineage runs from a feed to the datasets that read its files". Fix: let a
    source name the feed it reads (`bronze.family` matched to the feed's family), or warn.
12. **The input manifest includes a non-feed file.** Skill: "For a bronze capture with a
    `receipts.jsonl` ... use the sha256 of that file". This one lists the ticker catalog
    too. Fix: say whether the batch hash must cover only the feed's own files.
13. The identify step's `rules status` and the init check both need `RULES_DATABASE_URL`;
    the skill says to log and go on. That is fine, but no step before **test** says the
    run will stop there. Fix: say up front which variables the whole walk needs.

## Questions for the operator

Asked in this order, each answered before the next. All are answered (2026-10-01); each
answer is quoted under its question. Nothing is assumed.

1. **Identify.** "These files are the SEC submissions documents of every SEC filer, 76,230
   of them (67,421 typed `other`), the same capture the Company feed reads, read again
   for Person as source `sec.submissions.person`, code `sec.submissions.person.v1`. Is
   that right?" Recommendation: yes.
   **Answered 2026-10-01 (operator): "yes".**
2. **Identifiers.** "Keep only the CIK as the Person's identifier, and leave SEC's EIN
   (15,061 of them the placeholder 000000000) and SEC's stated LEI (392) out, since they
   belong to firms?" Recommendation: yes. Lookup-only identifiers have no syntax yet
   (ticket). Adding one later is a new source code (v2).
   **Answered 2026-10-01 (operator): "yes".**
3. **Former names.** "SEC's former names (in 9,580 documents) should become Person's
   `name_variants`, but the rules cannot express a list field yet. Leave them out until
   that ticket lands?" Recommendation: yes, leave them out.
   **Answered 2026-10-01 (operator): "yes".**
4. **Effective date.** "SEC submissions carry no effective date. Let the Person rules
   accept records without one, as Company does (`allow_unknown_effective: true`)?"
   Recommendation: yes. Otherwise no SEC name could ever fill a field.
   **Answered 2026-10-01 (operator): "yes".**
5. **Missing name.** "A Person record with no name is set aside as an open exception:
   never merged, never stopping the run. None of the 76,230 has an empty name today. Agree?"
   Recommendation: yes.
   **Answered 2026-10-01 (operator): "yes".**
6. **Mapping Document.** "Here are the two workbooks (`MAPPING.xlsx` and `person.xlsx`).
   Note that `person.xlsx` shows the person step without its 'not' and says 'Company'
   for the CIK rule; those are tool bugs, and the rules file is right. Do you and the
   stewards agree the mapping?" Recommendation: agree the rules, and ticket the workbook bugs.
   **Answered 2026-10-01 (operator): "yes"** — the mapping is agreed as the rules files
   state it; the two workbook bugs are ticketed (rules mapdoc).
7. **Classification proof sample.** "The classification rule scored 841 of 841 people
   right and 476 of 476 firms right on 1,380 owners labelled in research 18. Those labels
   are an earlier session's own reading, and they come from Form 3/4/5 owners, not from
   this feed's 76,230 filers. Accept them as the proof, or label a fresh random sample from
   this capture (at least 381 the rule calls people, for 0.99 at 0.975)?" Recommendation:
   a fresh random sample from this capture, labelled by a person you name. This feed holds
   filers research 18 never saw. Drawing it needs code (SKILL-GAP 5).
   **Answered 2026-10-01 (operator): "B, agent drafts labels, I'll check".** A fresh random
   sample of this capture; an agent drafts each label, the operator checks every one. One
   small script draws the sample (the exception the question named).
8. **Adversarial fixture.** "The engine will not switch on a classification rule without
   an adversarial set: hard cases built to fool it, such as one-word surnames that are
   legal-form words, or trusts named after people. None exists for this rule. Build one?"
   Recommendation: yes, before switch-on. It needs code to build and score.
   **Answered 2026-10-01 (operator): "yes".** About 50 hard cases from real filers in this
   capture, drafted by the agent with the right answer, checked by the operator, scored
   before switch-on.
9. **Adding a kind changes Company's merge rules document.** "Adding `person.yaml` and its
    proof entry changes the digest of the whole merge document Company runs under, and
    four pinned tests will fail. One of them guards how the merge counts CIK conflicts
    when a second feed maps the CIK. Should these tests be changed (code) in this PR, or
    should `person.yaml` be held back until Person is ready to switch on?"
    Recommendation: a separate code ticket, before this PR merges. It pins Company's part
    only and decides the CIK-conflict count for Person.
    **Answered 2026-10-01 (operator): "A".** A separate code ticket, merged before this PR:
    the pinned tests pin Company's part of the merge rules only, and it settles how CIK
    conflicts are counted once a second feed carries a CIK.
10. **Rules Database.** "No Rules Database login is set in this session
    (`RULES_DATABASE_URL`), so nothing can be registered, saved or approved. Will you set
    it, and the migration and activation logins, outside the chat?" Recommendation: yes,
    once questions 1-9 are settled and a test run exists; not needed before.
    **Answered 2026-10-01 (operator): "yes".** The operator sets the three logins outside
    the chat when a test run exists; never pasted here.
11. **EIN placeholder and coverage (later, a rule change).** "Up to 12,767 `other` filers
    carry SEC's placeholder EIN 000000000, which makes the Person rule send them to a
    Steward instead of deciding. Treat 000000000 as empty in a later version of the rule
    (re-measured)?" Recommendation: yes, as refining-rules work after this version is proved.
    **Answered 2026-10-01 (operator): "yes".** A later rule version, through the Refining
    Rules skill, after this version is proved; scored again before it is switched on.
    Nothing changes in this version.

Approvals after these, each its own stop with your words, in the skill's order:
`sec-person-candidate` (classification), `person-cik` with its CIK Identifier Contract
(needs a proving run, which needs code), the merge version `platform`, then the source
version. None can be asked yet: no test run is recorded.

12. **Sample size (asked after the draw).** With 450 people one wrong call fails the bar
    (Wilson lower bound 449/450 = 0.9875 < 0.99). Recommendation: 570, which passes with
    one wrong call. **Answered 2026-10-01 (operator): "Agreed, do not ask me too many
    questions".** The draw is extended in the same seeded order to 570 people plus 150
    others (720); the first 600 are unchanged. Fixed before any label is compared.

## Fresh-sample test (2026-10-01 ET, operator: "Test adjust and delete and repeat until you get the rules right")

`sec-person-candidate` 2026-09-30.1 against the 720 agent-drafted labels (blind to the rule;
`fresh-labels-draft.jsonl` + `fresh-labels-draft-extension.jsonl`, key `fresh-sample-key.jsonl`).
Compared with jq; no rule or engine code run beyond the Q7 draw.

| Step (verdict) | Labelled person | Labelled entity |
|---|---|---|
| 3 (person) | 570 | 0 |
| 2 (entity_undetermined) | 0 | 102 |
| 1 (deferred, probably company) | 0 | 34 |
| 2-guard (deferred) | 0 | 1 |
| 4 (deferred, to a Steward) | 2 | 11 |

- Person step: 570 of 570, Wilson lower bound 0.99331 at z = 1.96, above the 0.99 bar.
  It still clears the bar with one wrong label (0.99013).
- Entity step: 102 of 102.
- The 2 people at step 4 (GOLD IRWIN, BRAMSON EDWARD J) carry a state of incorporation
  (NY), which a person should not. Sending them to a Steward is the cautious outcome;
  both labels were marked uncertain.
- **No adjustment made.** No step decides wrongly, and any edit is a new rule version
  whose score would have to start again. Iteration 1 is also the last.
- 6 labels in the person step are marked uncertain (2139956, 1593897, 1219204, 1299903,
  1183121, 1512398), most of them 13F filers with a personal name. They are the operator's
  first checks: each one judged an entity costs one correct call.
- Not yet the proof: the operator checks all 720 labels (Q7). Then the hard-case set
  (Q8) is scored, and `pending-proofs.yaml` takes these numbers.

## Hard-case set (2026-10-01 ET, Q8 "yes", then "Step 2")

57 real filers drafted by an agent from document evidence only (`hard-cases-draft.jsonl`;
the 2,100 proof-sample CIKs excluded), scored with `score_hard_cases.py` (the Q8 scoring
exception) into `hard-cases-scored.jsonl`.

- **No entity called a person** (0 of 20 entities). The precision the bar measures held.
- 22 decided right, 34 held back for a Steward (coverage, not error), 1 wrong call:
  **HOLDING FRANK B JR** (1065416), a person called `entity_undetermined` at step 2.
  HOLDING is a legal-form word not on the ambiguous list, and his document also carries
  SIC 6311, state NC and a fiscal year end. It is a missed person, not a false Person.
- **No adjustment made.** The fix (HOLDING on the ambiguous list) would only move him to
  step 4, and would hold back every real "X HOLDING" company that step 2 decides today.
- **Waits on the operator's check:** 7 uncertain cases the rule calls a person:
  - 4 "ET AL" group filers: WATSA V PREM, RANKIN ALFRED M, HARARI ELIYAHOU, GENDELL JEFFREY L;
  - Lloyd Barbara A (filed MA, a municipal-advisor registration);
  - PRESSLEY TAMIKA NIKOLE (only a TA-1, transfer-agent registration);
  - Kidder Stephen W.

  If the operator judges the ET AL filers not to be people, the adjustment is
  configuration: add `ET AL` to `entity_legal_form` and `ambiguous`, so those names are
  held back. That makes a new rule version, re-scored on both sets.
- **Finding against Q11:** several entities (Unisphere Establishment, Cantor Fitzgerald
  Europe, AWILHELMSEN AS, HOWARD HUGHES MEDICAL INSTITUTE) are held back only because
  the placeholder EIN 000000000 counts as filled. Treating it as empty, as Q11 planned,
  would turn them into false Persons unless the legal-form list first gains
  ESTABLISHMENT, INSTITUTE, PC, DST, GRAT, DBA, SONS and BROTHERS. Q11's later version
  must carry those words and be scored on this set.

## Ruling: relationships come with MDM (2026-10-01 ET)

Hard case 1558775 ("David BH Williams, Trustee UAD The Helen Charles Williams 2004 Trust"):
the CIK is the trust; David BH Williams is its trustee. Operator: **"Yes I think there has to
be relationship along with mdm it can not be separated".**

- What it means here: when a record names a person acting for an entity (a trustee, an
  attorney-in-fact, an "ET AL" group's lead), the Person domain must also carry that
  link (person, role, entity), mastered together with both records, not left to a later
  separate effort.
- Feed 1 reads one CIK's own document, so it cannot build the link (it has no second
  party's CIK). This is now a requirement on the Person domain, recorded in the ticket
  and owned by the feeds that name both parties (Forms 3/4/5 signatures and owner
  remarks, DEF 14A, ADV Schedule A/B).
- Operator, on sample batch 1 (row "Pirouette D 2026 I, a series of Capitalize Investments
  LLC"): **"Ok name has the relationship as well".** A filer's own name can state a
  relationship: "a series of <LLC>", "<person>, Trustee UAD <trust>", "<person> dba
  <business>", "ET AL". Feed 1 keeps the name as written; reading these links out of it
  belongs to the relationship work above (a Person or Company feed that masters both
  parties and the link together).

## Proof recorded (2026-10-01 ET)

Operator checks are in `operator-checks.jsonl`:
- 14 uncertain cases, one by one;
- 100 sample rows and 43 hard cases, in batches;
- the other 612 sample rows, accepted on the operator's words "Ok most your analysis is
  fine only ask the real harder once". They were screened for non-insider forms, earlier
  names and relationship words; none was hard.

`rules/merge/pending-proofs.yaml` now holds the fresh proof:
- n = 570, correct = 570, lower bound 0.993305;
- adversarial fixture `hard-cases-checked.jsonl`, 57 cases, 0 violations;
- research 18's numbers kept as a comment.

No approval. `rules pending` stopped at the missing `RULES_DATABASE_URL` (Q10).

## Approval 1: the classification rule (2026-10-01 09:39 ET)

Operator, asked "Do you approve switching on the Person classification rule,
`sec-person-candidate`?": **"Approved".**

`rules approve --merge platform --rule sec-person-candidate --by operator --words "Approved"`
added it to `rules/merge/policy.yaml` (approved_at 2026-10-01T13:39:16Z, i.e. 09:39 ET).

- The first try was refused, and nothing was written: "Proof lower bound 0.993306 does
  not reproduce from its sample". The bound must be cut to six places, not rounded:
  0.9933057 becomes 0.993305. `pending-proofs.yaml` was corrected, and the same words were
  recorded again.
- Person still decides nothing. The merge version `platform` that carries the rule must
  be saved, tested, approved and switched on.

## Proving run of person-cik (2026-10-01 ET, operator: "Yes" to the code exception)

`proving_run.py` reads every document with `adapters.normalize` under the Person Dataset
Contract and the repo's merge rules, then applies it with the Merge Stage on a disposable
PG16, twice. Two fixes were made on the way:
- Set-aside records (each carries its whole document) and readings go in separate
  batches. A batch that proposes new Persons is recorded whole as one match proposal,
  and a mixed batch of 25 MB was refused as unbounded.
- Log files in the cohort folder are skipped.

Small run, 300 documents (the lowest CIKs, mostly old companies): 49 Persons, all by
`person-cik`. Set aside: 157 `classification_deferred` (133 probably a company), 94
`classification_entity_undetermined`. 0 CIKs on two Persons, 0 overlaps with ticket 27's
Company cohort (6,726 CIKs), second pass unchanged. The full run started at 09:53 ET.

## Proving run result (2026-10-01 13:50 ET)

Report: `proving-report-sample-10000.json` (copy of
`~/.local/share/edgartools/clean-mdm/proving/person-feed-1/report-sample-10000.json`, sha256
c92b292f…b734). Cohort manifest: `cohort-10000.json` in that folder (sha256
cc9364f2670ae9d945ad62794ce88a8e220044db637f9175e4e6ee7bc0c22dd3): 10,000 documents, seed
20261001, as Company's ticket 05 used a cohort. The whole population did not fit (ticket 05b).
The run passed in 32 min 40 s.

- Cohort: 4,044 Persons, every one created by `person-cik` from its own CIK. 5,956 set
  aside: 1,486 `classification_deferred` (1,151 probably a company), 4,470
  `classification_entity_undetermined`.
- 0 CIKs on two Persons, 0 Persons with two CIKs. Second pass changed nothing.
- Population, rule only, no database, all 76,230:
  - step 3, person: 31,097;
  - step 2, entity: 34,038;
  - step 1, held back as a company: 8,809;
  - step 4, to a Steward: 2,251;
  - step 2-guard: 35.
- Person CIKs that are also in Company's ticket 27 cohort: 4, all of them controls, the
  non-companies Company held back:
  - SEMLER ERIC
  - MATLIN DAVID J
  - Clough Charles JR (the operator: a person)
  - Salzhauer Henry

  No CIK is a Person and a Company.
- `rules approve --rule` records measured proofs only. An identifier rule (deterministic)
  is approved on its Identifier Contract's `verification` (corpus sha256, by, at, reason)
  plus its `automatic_rules` entry, as Company's `company-cik` was (ticket 15).
  SKILL-GAP 14: APPROVE.md does not say this.

## Approval 2: person-cik and its CIK Identifier Contract (2026-10-01 17:12 ET)

Operator, asked "Do you approve the Person CIK rule and its CIK contract?": **"Approved".**

Recorded as Company's `company-cik` was, by hand in the files:
- `kinds/person.yaml`, `identifiers.cik.verification`: corpus_sha256 cc9364f2…2dd3 (the
  cohort manifest), approved_by operator, approved_at 2026-10-01T21:12:53Z, and the reason
  with the operator's words;
- `policy.yaml` `automatic_rules`: `person-cik`, deterministic, with a comment.

`check_policy` accepts the policy. Person still decides nothing until the merge version
`platform` is saved, tested, approved and switched on.

## Rules Database: local and throwaway (operator: "1 no login needed", "go ahead")

- Container `rules-local-person-feed-1` (postgres:16-alpine, `--rm`, a random local port),
  with database `rules`, the login `rules_agent`, the login `operator` and the role
  `rules_approver` granted to `operator`. Passwords are the local test value; nothing is
  hosted. The operator's two protected containers were not touched.
- `rules init`: 001–003 applied (2026-10-01 18:09 ET).
- `rules save --merge platform --version platform-2026-10-01.person-feed-1
  rules/merge/policy.yaml`: digest da4b5065…16cc, draft.
- `rules record-proof`: proof file
  `~/.local/share/edgartools/clean-mdm/proving/person-feed-1/proof-platform-person-feed-1.json`
  (sha256 1cf17a37…7b85). It names the digest, `batch_hash` (the cohort manifest), passed,
  the counts and the classification proof.
- `rules pending`: platform-2026-10-01.person-feed-1, passed, evidence_hash e0086517…9c32,
  changes "new: nothing of this name is active yet". This store holds no earlier
  platform version. Against Company's approved policy (75bd2b67…), the change is the
  Person kind and its two switched-on rules. Company's part is unchanged: the pinned
  tests compute it and pass.

## Approval 3: the merge version (2026-10-01 18:11 ET)

Operator, asked "Do you approve the merge rules version `platform-2026-10-01.person-feed-1`?":
**"approved".** `rules approve --merge platform --version platform-2026-10-01.person-feed-1
--evidence e0086517…9c32 --by operator --words "approved"`, made as the local `operator`
login (holding `rules_approver`), recorded approved_at 2026-10-01 22:11:54 UTC.

Source version saved: `sec.submissions.person-2026-10-01.first`, digest 386a3ec5…b8af. Proof
`proof-source-person-feed-1.json` (sha256 e8d2c634…4fec), the same Proving Run. `rules
pending`: passed, evidence_hash 5d5cb63e…818f.

## Approval 4: the source version (2026-10-01 18:18 ET)

Operator, asked "Do you approve the Person source version
`sec.submissions.person-2026-10-01.first`?": **"approved".** Recorded by `rules approve
--source … --evidence 5d5cb63e…818f --by operator --words "approved"` (approved_at 22:18:48
UTC). `rules status` shows both versions approved, by operator, approved_words "approved".

Not done yet: switch-on (`rules activate`). It needs `RULES_MDM_ACTIVATION_DATABASE_URL`, a
Clean MDM database to register into. The operator's `edgartools-clean-mdm-pg16` still
holds `mdm_v2`, which `mdm migrate` refuses, and recreating it is the operator's call.
