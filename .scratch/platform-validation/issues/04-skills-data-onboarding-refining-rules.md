# Split the rules skill into Data Onboarding and Refining Rules

Type: task
Status: resolved: merged in #765 (2026-10-02 audit, mastering to-do 01).
Was: in progress (Claude, branch `claude/skills-data-onboarding-refining-rules`)

## Operator rulings (2026-09-30)

- "it cannot be called a rules skill": the name is **Data Onboarding**.
- Split in two ("Split as above"). **Data Onboarding** brings in a new feed
  or domain; **Refining Rules** changes what is live.
- "make sure data-onboarding and refining-rules are super clear for agents,
  agents will be extensively using to onboard data to mdm and to silver".
- Mode names ("Adopt as proposed"):
  - **Bookkeeping:** init, migrate, plan, validate, run, status, recover.
  - **Change Journal:** init, migrate, plan, validate, deploy, status,
    recover-delivery.
  - **Data Onboarding:** init, migrate, identify, profile, map, quality,
    metadata, test, approve, switch-on.
  - **Refining Rules:** change-mapping, change-quality, change-matching,
    test, approve, switch-on.
  - `rules migrate` becomes `rules load` / `rules unload`.

## Done

- `skills/data-onboarding/` (SKILL.md, the shared REFERENCE.md and
  APPROVE.md) and `skills/refining-rules/`. Each has:
  - a "use the other skill when" check;
  - a hard-stops table;
  - one command per step, with its environment, output and failure;
  - the MDM and silver targets;
  - a table of the commands that are not built yet, with what to do instead
    and which ticket builds them.
- The CLI: `rules migrate` upgrades the schema (as `rules init` does), and
  `rules load` / `rules unload` move files ⇄ database.
- Bookkeeping: `deploy` is renamed `run` (DEPLOY.md is now RUN.md), and
  there are new status and recover sections. Change Journal: status and
  recover-delivery sections.
- The two stale references are fixed (`COMPANY_NAMED_FIELDS`,
  `CHANGE_LEDGER_DATABASE_URL`).
- `tests/unit/test_rules_skill_commands.py` checks every command and flag
  both skills and APPROVE.md name.

## Cold trials, round 1

Fresh agents were given only the skill, the repo and captured files. The
logs are in `trials/round-1/`.

- **Data Onboarding, Person feed 1** (300 SEC individual filers):
  - It reached **test**. The Person classification rule, ported, splits the
    files into 287 people, 12 entities and 1 deferred fund.
  - With that rule switched on in memory, all 287 are accepted as Persons.
  - 24 skill gaps were found and fixed. The biggest: routing for a new kind
    from files an existing feed already reads, classification rules and
    the order of approvals, drafting with `root=`, the digest before save,
    the input manifest, a recipe for a disposable PG16, and the
    `rules save --merge platform` command.
- **Refining Rules, SEC quality** (all 7,000 files of the cm05 capture):
  - Counts: `standard_address` 5,882, `state_from_name_tag` 12,
    `dc_state_is_empty` 4 (3 net changes), `address_not_registered_agent`
    9, and the others 0 (each shown able to fire).
  - Recommendation: keep the DC fix.
  - 10 skill gaps were fixed, among them: rebuilding reader rows from raw
    files, counting all filers vs what MDM receives, a fix has no
    `on_fail`, and gross vs net counts.

## Cold trials, round 2

The logs are in `trials/round-2/`.

- **Refining Rules** (a new "missing postcode" check, all 7,000 files):
  - Nothing blocked the trial. The check would flag 403 of the 6,414
    records MDM receives (659 of all filers).
  - 7 gaps were fixed: tickers in the row recipe, the receipt path, text
    edits that keep comments, the publication and deferred shapes, timing,
    what `present@1` tests, and the sandbox log.
- **Data Onboarding** (Person feed 1):
  - It reached **test**. The proving run hung: nothing can be switched on
    before approval, and the skill did not say how to prove a new domain
    before that.
  - Fixed with ticket 05's recipe: a copy of the policy stamped "Proving
    Run only; not an approval", registered in the disposable database.
  - Also fixed:
    - how to bound and clean up a proving run;
    - the least sample for a classification bar (`n ≥ p·z²/(1−p)`) and the
      `pending-proofs.yaml` shape;
    - a step whose verdict is another kind becomes `deferred`;
    - the `write_source` body shape;
    - list fields;
    - `allow_unknown_effective`;
    - CLI start-up times;
    - excluding earlier trials from searches.

## After merge

- Run `skills/data-onboarding/link.sh` and `skills/refining-rules/link.sh`
  from the main checkout. The old `rules` link is already gone.

## Review (three axes)

- **Standards:** no hard violations. `init` and `migrate` now have
  different help text. The tests' reliance on exact wording is kept on
  purpose: the wording is the contract with agents.
- **Spec:** four gaps fixed:
  - the CLAUDE.md pointer to the trials;
  - "deploy" wording left in Bookkeeping;
  - `rules/outputs.yaml` is named as not existing yet;
  - the link step after merge.
- **GoF:** leave it.

## Tickets found (not built here)

- `rules mapdoc` writes "the one a Company holds" in every kind's
  "Matching rules" sheet, and drops a classification step's "not". It
  should name the kind and keep the negation.
- The contract has no syntax for lookup-only identifiers (e.g. `sec_lei`).
- Rules commands crash with `KeyError: 'RULES_DATABASE_URL'` rather than
  saying the variable is missing.
- `rules check --capture <folder>`: the dry run the trials wrote by hand
  (rules-skill ticket 03).
