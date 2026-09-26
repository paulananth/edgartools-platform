# The `rules` skill

Label: `wayfinder:map` (execution carried in the map: the operator approved
the plan on 2026-09-26, so each ticket builds rather than decides)

## Destination

One skill, `rules`, that an operator or agent uses to initialize the Rules
Database, migrate rules between files and the database, and add any new source
end to end: identify and confirm the source, profile and research its captured
files, infer the MDM entities, identifiers, fields and relationships, ask
plain-language questions, then build its parse configuration and merge rules,
and run its pipeline to MDM and to silver. Proven by a cold trial on an unseen
non-SEC source. The approved plan is [plan.md](plan.md).

## Notes

- **Owner:** Claude (operator, 2026-09-26: "you own the work of building the
  skill and simplifying the design and make it easy"). Supersedes the Codex
  engine hand-off of 2026-09-21/22.
- **Standing direction:** lean, clean, KISS; sources fully decoupled; new MDM
  fields easy to add; remove a layer rather than tune it; no extra work.
- **Decisions (operator, 2026-09-26):** see the table in [plan.md](plan.md).
  In short:
  - files in git are edited, and one table (`rules.rule_version`) records
    versions and status;
  - migration runs both ways;
  - a source starts from captured bronze;
  - MDM and silver run separately, each from the same `read` section, and
    parse each run;
  - silver goes to Delta (lakehouse) and/or Postgres (Lakebase);
  - anything that feeds MDM needs the operator's approval;
  - preview runs on a copy of the local MDM;
  - the skill lives in the repo and is linked into `~/.agents/skills/`.
- **Standing rules:**
  - branch per ticket off `origin/main`, in its own worktree;
  - `/gof-refactor-reviewer` before production code;
  - a checklist in each ticket, with ET times;
  - three-axis `/code-review`;
  - test every migration on a populated store;
  - zero SEC requests;
  - `uv` only;
  - CI green;
  - merge only on the operator's word.
- **Questions to the operator:** plain language, one at a time, each with a
  recommendation.

## Decisions so far

- [Approved plan](plan.md): seven phases, P1–P7 (approved 2026-09-26, before 15:49 ET).
- **Skill first** (operator, 2026-09-26, answered between 16:15 and 16:21 ET): "skill first, however must test skill on company entity for each source from scratch and fine tune and fix the skill, the incorporate all company data pipelines and test". The skill is written now
  (ticket 07). Each source that feeds Company is onboarded with it from
  scratch, and the result is compared with the rules already proven in
  `rules/`; every difference is a skill fix. Then all Company data
  pipelines move onto it and are tested. Tickets 02–06 build only what a
  trial round shows the skill needs.

## Tickets

| # | Ticket | Blocked by |
|---|---|---|
| 01 | [Rules files; production loads them](issues/01-rules-files-production-loads-them.md) | — |
| 02 | [The Rules Database](issues/02-the-rules-database.md) | 01; built when a trial needs it |
| 03 | [The production engine](issues/03-the-production-engine.md) | 01; built when a trial needs it |
| 04 | [Run a source into MDM](issues/04-run-a-source-into-mdm.md) | built when a trial needs it |
| 05 | [Silver outputs](issues/05-silver-outputs.md) | built when a trial needs it |
| 06 | [Profile any source](issues/06-profile-any-source.md) | built when a trial needs it |
| 07 | [The skill, then Company trials](issues/07-the-skill-and-a-cold-trial.md) | 01 (merged) |

## Not yet specified

- A stored parsed-record table (ADR 0016), if a measurement shows re-parsing
  costs too much.
- Moving the SEC Company and GLEIF parsers into `read` sections (ADR 0016's
  proven trial).
- Scheduling a source in AWS/Databricks, and Unity Catalog registration.

## Out of scope

- Getting data into bronze (fetch, schedule, source access).
- The old MDM's rule tables (`mdm_source_priority` and the rest): that MDM is
  being replaced.
