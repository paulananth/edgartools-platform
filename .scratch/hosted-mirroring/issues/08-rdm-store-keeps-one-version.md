# 08: The RDM store keeps one version of each code set

Status: resolved

The operator, 2026-11-20: "there should not be more than one version now", then, asked whether to open this ticket:
"Yes". Ticket 07 made the repository hold one version per code set and made each Gold view select that version by
name. The store still keeps every published version, by design.

## What the store does today (docs/specs/rdm/spec.md)

- A published version's rows are immutable: a trigger refuses any update or delete (spec section 2, "Integrity").
- `retire` sets `retired` and closes `valid_to`; "nothing deletes a published version" (section 3).
- A new version must name in `supersedes` the newest version ever published, current or retired (section 3).
- `rdm.published_code` is written once at publish, and a retired version keeps its rows (`001-published-code.sql`).
- The context read can answer "as it stood then" over past versions (`edgar_warehouse/rdm/context.py`).

On the hosted data database, besides `mdm-relationship-types` version 5, this leaves versions 1-4 of that code set and
the history set `mdm-relationship-types-before-real-names` version 1: 111 rows in `rdm.published_code`, with their rows
in `code`, `code_label`, `code_path`, `level` and `crosswalk_row`.

## The change

Publishing a version replaces the code set's previous version: its rows leave every RDM table in the same transaction.
Retiring a code set removes it. A version's rows stay immutable while it is the one version. History is git
(`rules/reference/published/`, one folder per code set).

## Checklist

- [x] Spec first: docs/specs/rdm/spec.md and docs/specs/agent-context/spec.md say a code set holds one version; `supersedes` names the version it replaces and is a recorded name, not a key; the "every published version is kept" rule and the "as it stood then" read are removed 2026-11-20 15:28 ET
- [x] Skill: data-modeling GOLD.md points to the store rule; data-operations names the publish that replaces and `rdm prune`; data-profiling CODE-SETS.md says a new version replaces the current one 2026-11-20 15:28 ET
- [x] Consult `/gof-refactor-reviewer` (haiku) on store.py, the triggers and context.py before code. Findings taken: one shared delete (`_drop_closed`, children first), one predicate (a version whose `valid_to` is set may be deleted, nothing else), `guard_published` and `code_path` need the same predicate, the supersedes foreign key goes on both engines, `retire` and `publish` share the delete. Declined: dropping the `retired` status and the supersedes checks (`retired` is the step that sets `valid_to`; the checks still hold with one version) 2026-11-20 15:28 ET
- [x] Publish removes the previous version's rows in one transaction; the triggers allow only that delete. PostgreSQL: `migrations/002-one-version.sql` (a numbered file, because an installed store refuses a changed `schema.sql`, so the hosted store takes it with `rdm init` and no reset), `rdm.delete_published_codes`; MySQL: `mysql-one-version-v5.sql` and `schema.py`. Both engines: `tests/reference_storage` 66 passed each 2026-11-20 15:28 ET
- [x] Retire removes the code set's version (the code set's own row stays: its words are immutable); `context.py` drops the past-version read, `--as-at` is refused for a code set; `rdm prune` deletes what an earlier build kept 2026-11-20 15:28 ET
- [x] Tests. Failed before the change: `test_only_the_published_version_appears` (`{'gone 1': 2, 'one 1': 2, 'one 2': 2} != {'one 2': 2}`) and `test_a_publish_leaves_only_its_version_in_every_table_and_a_retire_leaves_none` (version 1 held in every table). Still refused (new test): a delete of the kept version's rows or version row, and any update. `tests/integration/test_rdm_published_postgres.py`, `test_rdm_postgres.py`, `test_rdm_context_postgres.py` rewritten to state the new answers: 30 passed on PostgreSQL 16 2026-11-20 15:28 ET
- [x] Hosted: `rdm init` applied `002-one-version.sql` (checksums read back for 001, 002 and schema.sql); `rdm prune` removed `mdm-relationship-types` versions 1-5, and `rdm retire` removed the history code set `mdm-relationship-types-before-real-names` (still current on hosted). Before: 17 versions, 7,408 published codes; after: 11 versions (one per code set, equal to the 11 folders of `rules/reference/published/`), 7,272 codes in `rdm.code` and `rdm.published_code`. The mirror read back as the mirror operator: `EDGARTOOLS_MIRROR.RDM.PUBLISHED_CODE` 7,272 rows, 11 versions, no code set with two 2026-11-20 15:52 ET
- [x] Learning → skill: data-operations SKILL.md ("RDM, per domain": publish replaces, `rdm prune`), data-modeling GOLD.md (the store holds the same rule), data-profiling CODE-SETS.md 2026-11-20 15:28 ET

## Answer

Resolved 2026-11-20 15:52 ET. A code set keeps one version in the RDM store on both engines (PR 1959). On the hosted store 136 rows of six replaced or retired
versions were removed through the new path: 17 versions and 7,408 codes became 11 versions and 7,272 codes, and the mirror's
`rdm.published_code` equals PostgreSQL's (7,272 rows, 11 versions). The `ref_` views select each folder's one version by name and read the same 11.
