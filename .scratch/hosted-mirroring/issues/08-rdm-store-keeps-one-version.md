# 08: The RDM store keeps one version of each code set

Status: open

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

- [ ] Spec first: docs/specs/rdm/spec.md says a code set holds one version; `supersedes` names the version it replaces; the "every published version is kept" rule and the "as it stood then" read are removed
- [ ] Skill: the RDM rule in data-modeling GOLD.md ("A code set keeps exactly one version") points to the store rule; data-operations names the publish that replaces
- [ ] Consult `/gof-refactor-reviewer` on `edgar_warehouse/rdm/store.py` (publish, retire) before code
- [ ] Publish removes the previous version's rows, in one transaction; the immutability trigger allows only that delete (init SQL; no migration)
- [ ] Retire removes the code set; `context.py` drops the past-version read
- [ ] Tests: a publish of version 2 leaves only version 2 in every RDM table (fails on today's code: version 1 kept); the trigger still refuses any other update or delete; `tests/integration/test_rdm_published_postgres.py` updated (it asserts a retired version keeps its rows)
- [ ] Hosted: remove the six old versions through the new path, with counts before and after; Gold's `ref_` views and `rdm.published_code` read back with one version per code set
- [ ] Learning → skill
