# 180: One name for the filing's accession number

Priority: 180. Map: [Rebuild priorities](../map.md). Opened 2026-11-03 06:32 ET (operator, 2026-11-03: "add the line and write the rename ticket is filing_id is a better name or keeping it closer to sec naming better").

Type: task. Status: open. Blocked by: none (ticket 179's findings are merged or in PR 1333). Related: [179](179-investigate-the-use-of-accession-in-the-project.md) (the findings), [178](178-the-name-count-replaces-name-frequency-and-census.md) (a rename that hit stored names).

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

- [ ] Operator's choice of the one name (`accession_number` recommended, or `filing_id`)
- [ ] Check the stored form: dashes or none in each Silver table and the Snowflake DDL; one form, written in the entry
- [ ] Add the **Accession Number** entry to `CONTEXT.md` (with the line above), and change the four daily-run terms that use "accession" for the filing to "filing"
- [ ] If `accession_number`: rename the `accession` column of the five newer Silver tables and the references in their four sources' rules (`sec.company-facts`, `sec.nport.security`, `sec.ownership`, and the readings that feed them), as slices: tests first, one source per slice, new rule versions with carried-forward proofs, a Silver migration, Mapping Documents regenerated
- [ ] Final check: `git grep -w accession` outside SEC's own spellings, history and the glossary finds only prose that means something else
- [ ] Learning → skill: name the skill line this changes (the glossary rule in `skills/data-platform` or `skills/data-onboarding`: a column named for a source's number keeps the source's word), or "none"
