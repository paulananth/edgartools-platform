# The skill, then Company trials

Type: task
Status: claimed (Claude, branch `claude/rules-07-skill`, 2026-09-26 16:28 ET)
Blocked by: none (01 merged 2026-09-26 17:06 ET)

## Outcome

`skills/rules/SKILL.md` plus `agents/openai.yaml`, linked into
`~/.agents/skills/rules`. It has three modes: init, migrate and add.

Add works on any source. It:
- identifies the source and confirms it, or asks for its name;
- profiles the files;
- researches the repo and the source's public docs (never `sec.gov`);
- proposes kinds, identifiers, fields and relationships;
- asks one plain question at a time, each with a recommendation;
- writes the files;
- previews, validates, asks for approval, activates and deploys, to MDM first
  and then to silver.

Skill first (operator, 2026-09-26, answered between 16:15 and 16:21 ET): "skill first, however must test skill on company entity for each source from scratch and fine tune and fix the skill, the incorporate all company data pipelines and test".

## Checklist (times ET)

- [x] The skill, and a link script (2026-09-26 16:29 ET): `skills/rules/SKILL.md`,
  `REFERENCE.md`, `agents/openai.yaml`, `link.sh` (shellcheck clean). Commands
  not built yet are marked, each with a fallback or a stop.
- [ ] Trials, one per source that feeds Company, each from scratch:
  - SEC submissions Company;
  - GLEIF Level 1, relationships and reporting exceptions.

  How each trial runs:
  - A fresh agent gets only the skill and a `git archive` export with the
    source's `rules/sources/<source>/` folder deleted, plus the tests that
    restate its values. It keeps the parsers.
  - Inputs are captured files only: the three local GLEIF zips, and a small
    sample of SEC submissions copied from bronze (Apple, Microsoft, Shell,
    ASML and a few dozen more). There are zero SEC requests.
  - It logs every question it asks. Answers give facts only, and each
    question is tagged "the skill should have inferred it" or "a real
    operator decision". An approval is never simulated.
  - It is scored against the proven files: digest-equal is best; otherwise
    diff the kind, identifiers, fields, ranks and relationships.
  - Every difference is a skill fix, never an edit to the answer. Rounds
    repeat until a round needs no fix.
- Round 1 (started 2026-09-26 16:41 ET), two sandboxes built from a
  `git archive` of `claude/rules-p1-files`, with `.scratch/`, `.planning/`,
  the digest test and the source's own rules folder removed:
  - SEC: the latest submissions JSON for 40 CIKs from prod bronze (Apple,
    Microsoft, Amazon, Shell, ASML and 35 random ones, seed 20260926) and
    both ticker lists (2026-09-02);
  - GLEIF: the three 2026-09-11 16:00 UTC Golden Copy zips; also removed
    `docs/specs/clean-mdm/native-gleif.md` and `docs/specs/source-contract/`,
    which restate its mapping.

  A leak check found the draft reference page used GLEIF's real values as
  examples; they were replaced with neutral ones before the round started.
  Agents cannot reach the operator: each logs its questions with a
  recommendation, assumes it, and stops at approval.
- [x] Round 1 results (2026-09-26 18:00 ET). **Not a from-scratch
  measurement:** both agents read repo tests that restate the mapping
  (`test_clean_company_source.py`, `test_clean_gleif_source.py`,
  `test_clean_four_companies.py` and others), and the SEC agent read
  `docs/specs/source-contract/` §13.1.
  - SEC: 26 of 34 scored keys equal, 0 different, 8 missing (all
    `provenance`). 9 questions, 12 skill gaps.
  - GLEIF: 50 of 85 equal, 5 different, 20 missing, 10 extra. Level 1's
    kind, key, identifiers and every field are equal. Misses: the defaults
    (`retain_deferred`, `source_record_provenance`, `field_shape`,
    `provenance.native_record`, `publication_families`) on all three
    members; a bad LEI check digit made non-blocking (an assumed answer); 4
    extra relationship types (an assumed answer); the relationship key.
    10 questions, 13 skill gaps.
  - No command was blocking once the dry-run text bug was fixed; none is
    built yet.
  - Skill fixed (18:05 ET): the dry run's `artifact_sha256`; check whether
    a source is new and keep the repo's names; version names are identity;
    a Defaults section; defects always block; the envelope keys; full files
    vs changes; dry run through the reader; where Company field names live;
    profile a bounded sample first; parallel arrays; comments; blocked docs.
- **Round 2 pass bar and cap** (written 2026-09-26 18:05 ET, before round 2):
  - **Sandbox:** a `git archive` of `claude/rules-07-skill` with all of
    `tests/`, `.scratch/`, `.planning/`, `docs/specs/source-contract/` and
    the source's `rules/sources/<source>/` removed, plus any other file a
    grep for the proven file's leaf values finds outside reader and
    target-model code. Reader code, the MDM target model
    (`COMPANY_NAMED_FIELDS`, the Company table, the merge rules) and names
    hard-coded in code stay; a key only they give away is scored "given by
    the target", not "inferred".
  - **Two phases:** phase A runs steps 1–5 and returns numbered questions,
    each with a recommendation. Claude answers each from the written record
    only (the proven file's comments, the decision tickets), as a decision or
    a fact, never as a file path, and tags it "should have inferred" or
    "real operator decision". The new-or-live question is answered "not
    registered; treat it as new". An approval is never answered. Phase B
    continues the same agent to write the file and run the dry run.
  - **Each difference is sorted:** a skill gap (fix the skill), an assumed
    answer (phase B removes it), or the proven file may be wrong (reported
    to the operator; the answer is never edited).
  - **Pass:** every scored key equal after phase B, except differences
    reported as "the proven file may be wrong"; no defect non-blocking; zero
    "should have inferred" questions. Envelope text is read, not scored.
  - **Cap:** at most rounds 2 and 3. After round 3 the results go to the
    operator, pass or not.
  - **What a pass proves:** the skill onboards reader-backed sources, which
    is all of Company core. It does not prove "any source"; that needs the
    non-SEC cold trial on the engine later.
- [x] Round 2 (2026-09-26 18:40 – 20:15 ET), under the pass bar above:
  - **SEC:** 25 of 34 equal, 0 different, 9 missing (all `provenance`),
    1 extra (EIN, the operator's new decision). 5 questions, 1 of them
    "should have inferred" (the address).
  - **GLEIF:** 64 equal, 2 different, 9 missing, 11 extra. 9 questions, 3 of
    them "should have inferred".
  - **Operator decisions during the round:** EIN and SEC's own LEI are
    lookup-only identifiers; tickers belong to Security; SEC's LEI is lookup
    only (company mastering ticket 19 measured matching on it).
  - **Not a pass.** The skill was fixed for round 3 in `12c59020`. Evidence is
    in `trials/round-2/`.
- [x] Round 3 (2026-09-27 04:47 – 13:14 ET), the last round under the cap:
  - **SEC:** 25 equal, 0 different, 9 missing, 2 extra. All 11 follow the
    operator's later decisions (trace beside the record; EIN lookup only)
    except one: held-back filers made non-blocking. 8 questions, 0 "should
    have inferred".
  - **GLEIF:** 69 equal, 6 different, 0 missing, 3 extra. 12 questions, 4
    "should have inferred". The differences: `unsupported_relationship_type`
    non-blocking on all three members (a real question; the proven file may be
    wrong), the relationship key order, and the relationship scope label.
  - **Operator decision during the round:** SEC trace stays beside the record
    (05:21 ET).
  - **Not a pass.** Evidence and the sorted differences are in
    `trials/round-3/` and the trials README. The results go to the operator.
- [x] Operator (2026-09-27, received before 13:28 ET, after the round 3 results): "fix the skill gaps
  and move on". No round 4.
- [x] Round 3 skill fixes (2026-09-27 13:28 ET, branch rebased onto `main` after #732,
  #734 and #735):
  - **Commands:** the skill names the `rules` commands Codex built (`status`,
    `save`, `record-proof`, `approve`, `activate`, `init`, `migrate`, `run`).
    `profile`, `check` and a preview are still missing, each with a fallback.
    The run itself is the Bookkeeping skill's work; the rules skill leaves a
    file's `bookkeeping` section alone.
  - **Names:** one folder per source; one source code per file in the
    pattern the merge rules use; the capture family is the repo's, else the
    folder name.
  - **Defects:** never ask whether one blocks; count it and log it for a
    reader ticket.
  - **Non-blocking reasons:** a table of the codes the code raises, with
    defaults. The three the record decides; a classification hold-back and an
    unmapped relationship type block until the operator rules.
  - **Provenance:** trace stays beside the record (operator, 2026-09-27).
  - **Ranks:** per kind, not per field; shared-field decisions are comments in
    the kind file.
  - **Record key order** follows the source's own key; the relationship
    `scope` label is `<Provider> <relationship family>`.
  - **Profiling:** a zip member is one stream; time it first; check list paths
    in every format the reader accepts.
  - **Dry run:** how to call a native reader, and the `defaults.sources`
    check.
  - **Missing documents:** go on and log.
  - **Record fix:** `rules/merge/kinds/company.yaml` now records the shared
    field decisions as comments. The policy digest is unchanged
    (`3520e890…`).
- [x] Moved out of this ticket, so its PR carries only the skill (one branch
  per ticket):
  - the commands the trials showed missing: `profile` is ticket 06; `check`
    and a preview belong to ticket 04. Codex's #732 already built `save`,
    `status`, `approve`, `record-proof`, `activate`, `migrate` and `run`;
  - the Company core pipelines on the skill: ticket 10.
- [x] Test: every `rules` command and flag the skill names exists, or the
  skill marks the command not built (`tests/unit/test_rules_skill_commands.py`).
- [x] The SEC worked example is marked where it is behind the operator's
  later decisions (EIN and SEC's LEI lookup-only; trace beside the record),
  so an agent does not copy it. Its digest is unchanged (`742e73c7…`).
- [x] `CLAUDE.md` Quick Navigation entry for the skill.
- [ ] Three-axis `/code-review` of any code, then PR and CI.
