# 180: One name for the filing's accession number

Priority: 180. Map: [Rebuild priorities](../map.md). Opened 2026-11-03 06:32 ET (operator, 2026-11-03: "add the line and write the rename ticket is filing_id is a better name or keeping it closer to sec naming better").

Type: task. Status: resolved. Blocked by: none (ticket 179's findings are merged or in PR 1333). Related: [179](179-investigate-the-use-of-accession-in-the-project.md) (the findings), [178](178-the-name-count-replaces-name-frequency-and-census.md) (a rename that hit stored names).

## Question

The project has two column names for the number EDGAR gives each filing: `accession_number` (the 49 legacy Silver column lists, the Snowflake DDL and dbt models, 548 uses) and `accession` (the five newer Silver tables: `company_fact`, `company_line_item`, `holding`, `insider_ownership`, `insider_position`). Which one name should it be: `accession_number` (SEC's own word) or `filing_id` (a plain word)?

## The two names compared (read 2026-11-03 06:32 ET on `origin/main`)

| | `accession_number` (recommended) | `filing_id` |
|---|---|---|
| Matches the source | Yes: SEC says "accession number"; its JSON key is `accessionNumber`, the SGML header says `ACCESSION NUMBER`, the N-PORT tables say `ACCESSION_NUMBER` | No: the SEC never says "filing ID" for it |
| Already in use | 548 uses, in the legacy Silver, Snowflake and dbt | 17 uses, and **for a different thing** |
| Collision | none | `filing_id` is already IAPD's own filing identifier (Form ADV) and Form AP has `form_ap_filing_id`; the Silver table `sec_adv_private_fund` holds **both** `accession_number` and `filing_id` for two different numbers |
| Plain to a reader | Needs one glossary line (below) | Reads plainly, but a reader would not know which agency's number it is, and the SEC's number is not the only filing number in the data |
| Cost of the rename | The five newer Silver tables and their four sources' rules (a Silver migration and new rule versions) | Every legacy list, the Snowflake DDL and dbt, and a clash to untangle in the ADV tables |

**Recommendation: `accession_number`.** It is the source's own name, it is what most of the project already says, and `filing_id` is taken by IAPD's different number. The cost is the five newer Silver tables, which are new.

## The glossary line (operator: "add the line")

Proposed `CONTEXT.md` entry:

> **Accession Number**: The number EDGAR gives one submission (one 10-K, one Form 4, one N-PORT report); an amendment gets its own. It has 18 digits in three parts, shown as `0001234567-23-000123`: the submitter's ID (10 digits), the year (2) and a running count (6). The first part is the CIK of whoever sent the submission, often a filing agent, so it does not name the company the filing is about. Prose says "filing" where the number is not the point.
> _Avoid_: filing ID (IAPD's `filing_id` is a different number)

Format seen in the project (read 2026-11-03 06:32 ET): the SGML header and the Rust tests hold it with dashes; `dashboard_workflows.py` strips the dashes to build a folder address. Whether every Silver table stores one form is not checked yet (part below).

## Parts

- [x] Operator's choice of the one name: `accession_number` (2026-11-03 06:49 ET; operator: "accession_number")
- [x] Check the stored form (2026-11-03 06:49 ET): the five newer Silver tables' tests, the SGML header, company facts' `accn` and the Rust tests all hold the number with dashes (`0000000001-26-000001`); one dashboard helper strips them only to build a folder address; the entry says "stored with dashes". Not checked: the live legacy Silver rows (no data read)
- [x] Add the **Accession Number** entry to `CONTEXT.md` (with the line above), and change the four daily-run terms that use "accession" for the filing to "filing" (2026-11-03 06:49 ET; `git grep -i accession CONTEXT.md` now finds only the entry and Derived Filing Text's "Accession Number"; the genericity lint passes)
- [x] Slice `sec.ownership` (2026-11-03 07:12 ET): the two readings, the source's record key list, the two Silver specs (`insider_ownership`, `insider_position`) and their tests say `accession_number`; prose says "accession number"; the dataset contract's key words changed too (the source is registered nowhere yet, so nothing refuses it). The capture's folder name `accession=` is SEC's stored layout and stays. tests/mdm, tests/unit, tests/architecture and all of tests/engine pass locally; the store holds no Silver, so no Silver migration ran. `sec.ownership` is not switched on in `source-by-source`, so no rule version
- [x] Slice `sec.nport.security` (`holding`) (2026-11-03 07:36 ET): the three readings, the lookup joins in source.yaml, the Silver spec (`holding`) and the two integration tests say `accession_number`; prose says "accession number"; MAPPING.xlsx regenerated. tests/mdm, tests/unit, tests/architecture pass (2318) and the nport integration tests (34) pass. The store holds no Silver and the source is not switched on, so no Silver migration or rule version ran.
- [x] Slice `sec.company-facts` (2026-11-03 07:58 ET): the facts reading, the three Silver specs, `line_items.py` and `measures.py` (SQL columns and the stored `inputs` key), the three tests and the company-financials skill say `accession_number`; MAPPING.xlsx regenerated. tests/mdm, tests/unit, tests/architecture (2411) and the company/silver integration tests (49) pass. The store holds no Silver and the source is not switched on: no Silver migration or rule version ran.
- [x] Slice the remaining rules (2026-11-03 08:21 ET): `sec.nport.fund`, `sec.nport.registrant` and `sec.registration` (reading fields, lookup joins, order-by lists, scope key, prose) say `accession_number`; their MAPPING.xlsx regenerated. `sec.submissions.person` names no accession. tests/mdm, tests/unit, tests/architecture (2411), engine nport/registration tests (14) and nport/registration integration tests (21) pass. No Silver, none of the three sources active: no migration or rule version.
- [x] The rest of the rename (2026-11-03 08:39 ET): done by the slices above (`sec.ownership` #1337, `sec.nport.security` #1338, `sec.company-facts` #1339, the other rules #1341); no Silver exists in the store, so no Silver migration ran
- [x] Final check (2026-11-03 08:39 ET): `git grep -w accession` on main finds no rule, Silver spec, reading or code column. What is left is meant: SEC's capture folder name `accession=`; the old Snowflake DDL, dbt and Terraform comments and the legacy docs and TODOS (their tables keep `accession_number`); engine and Rust test fixtures that invent a column named `accession` (`crates/source-contract/tests`, `tests/engine/test_sgml_container.py`, `tests/engine/fixtures/parallel-filings.yaml`, `skills/data-platform/READING.md` example); local variable and parameter names in tests and `dashboard_workflows.py`; and prose that already says "accession number"
- [x] Learning → skill (2026-11-03 08:39 ET): none for the skills (the genericity lint keeps skills free of source names). The rule lives in `CONTEXT.md`, **Accession Number** (merged in #1336): the source's own word, stored with dashes, avoid bare `accession` as a column name
