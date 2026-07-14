# 06-06 Task 1 Disposition: EDGE-05 (IS_ENTITY_OF) and EDGE-06 (IS_PERSON_OF)

**Plan:** 06-06 Task 1 (Wave 4, fix-pipelines)
**Status:** COMPLETE. Both types closed via the D-04 SQL-confirmed zero-overlap check, run live
against the current dev MDM Postgres (`edgartools-dev/mdm/postgres_dsn`, `AWS_PROFILE=edgartools-690`).
Both are **source-coverage exclusions scoped to the current tracking-list universe**.

## Method

Independently mirrored the actual production join logic (not merely read back the
already-resolved `linked_company_entity_id` FK, which would be circular verification):

- **EDGE-05**: `AdviserResolver._link_to_company` (`edgar_warehouse/mdm/resolvers/adviser.py:167-178`)
  sets `MdmAdviser.linked_company_entity_id = MdmCompany.entity_id` WHERE
  `MdmCompany.cik == <the adviser's own cik>`. The independent SQL check reproduces exactly this
  join condition directly against `mdm_adviser`/`mdm_company`, not `pipeline.py`'s
  `_adviser_company_pairs` (which only reads back the already-set FK — not an independent check).
- **EDGE-06**: `pipeline.py:_adviser_person_pairs` (`edgar_warehouse/mdm/pipeline.py:1483-1491`)
  joins `MdmPerson.owner_cik == MdmAdviser.cik` for advisers where `linked_company_entity_id IS
  NULL`. The independent check reproduces this join directly.

## Live query results (dev MDM Postgres, 2026-07-13)

```sql
-- EDGE-05: adviser.cik == company.cik
SELECT count(*) FROM mdm_adviser JOIN mdm_company ON mdm_company.cik = mdm_adviser.cik
WHERE mdm_adviser.cik IS NOT NULL;
-- => 0

-- Cross-check: advisers with linked_company_entity_id already set (should agree, and does)
SELECT count(*) FROM mdm_adviser WHERE linked_company_entity_id IS NOT NULL;
-- => 0

-- EDGE-06: person.owner_cik == adviser.cik (unlinked advisers)
SELECT count(*) FROM mdm_adviser JOIN mdm_person ON mdm_person.owner_cik = mdm_adviser.cik
WHERE mdm_adviser.cik IS NOT NULL AND mdm_adviser.linked_company_entity_id IS NULL;
-- => 0
```

| Type | CIK-overlap count | Universe sizes |
|---|---|---|
| EDGE-05 (adviser.cik ∩ company.cik) | **0** | 1 adviser, 20,093 companies |
| EDGE-06 (person.owner_cik ∩ adviser.cik) | **0** | 1 adviser, 45 persons |

**Direct row-level confirmation (not just aggregate counts):** the current tracking-list universe
has exactly **one** `mdm_adviser` row (`entity_id=f027a405-7fb0-4f5b-af5f-9fd37785aa5f`,
`cik=105958`). Confirmed directly that no `mdm_company` row has `cik=105958`
(`SELECT * FROM mdm_company WHERE cik=105958` — zero rows), and none of the 45 `mdm_person` rows'
`owner_cik` values equal `105958`. This rules out a query-logic bug (e.g. type mismatch, wrong
join column) — the zero-overlap result is a direct, small-N fact about the actual data, not an
artifact of an incorrect aggregate query.

## Small-N caveat (explicit, per D-04's "scoped to current tracking-list universe" requirement)

**The MDM adviser universe currently contains exactly 1 adviser entity.** This is consistent with
the standing Active Decision in `fix-pipelines/STATE.md` that ADV filings are largely a confirmed
dead end (MANAGES_FUND/EDGE-07: "all 30 ADV filings in the active universe are paper filings with
no electronic document" — see `.planning/workstreams/claude-mdm-source-recovery/FINDINGS.md`).
With only one adviser entity resolved at all, EDGE-05/06's zero-overlap findings carry
correspondingly low statistical weight — this is not "checked many candidate adviser/company or
adviser/person pairs and found none," it is "there is currently almost no adviser data in MDM to
even test the overlap against." The finding is genuine and SQL-confirmed for the *current* state,
but should be re-run if/when the adviser universe grows (e.g. via new ADV electronic filings, or a
broader tracking-list expansion that resolves more advisers).

## Disposition

**EDGE-05 (IS_ENTITY_OF): EXCLUDED — source-coverage exclusion scoped to the current tracking-list
universe.** No adviser CIK matches any company CIK in the current MDM universe (0 of 1 advisers).
Per D-04, this independently confirms what `_link_to_company`'s always-on resolver already
computes (it has never found a match either — 0 advisers have `linked_company_entity_id` set).
Not added to `POPULATED_RELATIONSHIP_TYPES` (no rows exist to graph-sync or verify).

**EDGE-06 (IS_PERSON_OF): EXCLUDED — source-coverage exclusion scoped to the current tracking-list
universe.** No person's `owner_cik` matches the one adviser's `cik` in the current MDM universe.
Not added to `POPULATED_RELATIONSHIP_TYPES`.

**Re-check trigger (per D-04):** both exclusions must be re-verified if the tracking-list universe
expands to include more advisers (e.g. a future ADV-coverage improvement, or a larger CIK universe
load) — this is a snapshot-in-time finding against the current MDM state, not a permanent
structural conclusion like EDGE-10's (SEC API limitation) or EDGE-07's (paper-filing dead end).

## No code changes

Per the plan's constraint, no new deriver code was written and no fix was applied —
`_derive_is_entity_of`/`_derive_is_person_of`/`_adviser_company_pairs`/`_adviser_person_pairs` are
all confirmed correct as-is; the zero result is a genuine data-coverage fact, not a bug.
