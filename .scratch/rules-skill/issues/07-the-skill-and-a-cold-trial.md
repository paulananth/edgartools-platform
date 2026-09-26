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
- [ ] Build only the commands a trial round shows the skill needs (tickets
  02–06 as a menu).
- [ ] All Company data pipelines on the skill, tested.
- [ ] Test: every command the skill names exists.
- [ ] `CLAUDE.md` Quick Navigation entries for the skill.
- [ ] Three-axis `/code-review` of any code, then PR and CI.
