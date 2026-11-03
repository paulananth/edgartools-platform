# 179: Investigate the use of "accession" in the project

Priority: 179. Map: [Rebuild priorities](../map.md). Opened 2026-11-03 06:02 ET (operator, 2026-11-03: "create a ticket to investigate use of \"accession\" in the project").

Type: task (investigation; no code change until the findings are read). Status: resolved (2026-11-03 06:28 ET: findings below; a rename waits for the operator). Blocked by: none. Related: [178](178-the-name-count-replaces-name-frequency-and-census.md) (the same question asked of "census"), [158](158-glossary-holds-only-real-terms.md) (the glossary holds only terms that real data backs).

## Question

"Accession" is an SEC word (the number EDGAR gives each filing). The project uses it widely, and the operator asks where and how, as ticket 178 asked of "census": is it a word the operator would use, is it spelled one way, and does the glossary define it?

## What a first count showed (read 2026-11-03 06:02 ET on `origin/main`, outside `.scratch/`, `.planning/` and `docs/research/`)

- 172 files and about 1,775 lines say "accession".
- By kind: about 395 lines in Python, 328 in rules `.yaml`, 38 in Rust, 648 in tests; the rest in docs, skills and `CONTEXT.md`.
- Spellings: `accession` (529), `accession_number` (144), `accessionNumber` (119, SEC's own JSON key), `ACCESSION`, `ACCESSION_NUMBER`, and compounds (`source_accession`, `superseded_by_accession`, `accession_seen`, `cik_and_accession`).
- `CONTEXT.md` uses it inside other terms (daily-artifact run selection, candidate attempts, relationship source candidates, a normalized-text projection "identified by filing accession") but holds no entry of its own for the word.

## Findings (read 2026-11-03 06:28 ET on `origin/main`, outside `.scratch/`, `.planning/`, `docs/research/` and workbooks)

**What the word is.** An accession number is the number EDGAR gives one filing. Every use in the project means that, except the daily-run terms in `CONTEXT.md` ("accession selection", "accession-scoped", "accession-level", "an accession or metadata record"), where "accession" stands for the filing itself.

**Where it is** (lines): `edgar_warehouse` 108, rules `.yaml` 114, tests 648 (450 of them in one fixture), Rust 38, Snowflake SQL and dbt 683, skills 7, `CONTEXT.md` 5. `docs/` shows 18,404 lines, but 18,280 of them are in `docs/research/` (two data files hold 18,268); the other docs hold 124.

**One thing, two column names.**
- The Silver column lists of `silver_schema.py` (49 of them) and the Snowflake DDL and dbt models say `accession_number` (548 uses).
- The five newer rules-defined Silver tables say `accession`: `company_fact`, `company_line_item`, `holding`, `insider_ownership`, `insider_position`. Their own definition reads "The filing's accession number."
- Compounds: `source_accession`, `superseded_by_accession`, `sec_fundamentals_processed_accession`, `owner_accession_number`, `reference_accession_number`, `accession_year`.
- Rules files use bare `accession` 267 times, `accession_number` 26.

**SEC's own spellings (source data, not ours to rename):** `accessionNumber` (29, the JSON key), `ACCESSION NUMBER` (9, the SGML header), `ACCESSION_NUMBER` (18, the N-PORT tables), `accn` (2, company facts).

**Glossary.** `CONTEXT.md` has no entry for the word (13 terms contain "Filing"). Its only uses sit inside other terms.

**Stored names that would resist a rename.** The five rules-defined Silver tables are registered in Silver; a column rename there is a Silver migration and a new rules version for each of four sources. The legacy column lists and the Snowflake DDL are far larger. SEC's own keys never change.

**Recommendation.** Keep the word: it is EDGAR's own, and the operator sees it in every filing address. Define it once in `CONTEXT.md` as **Accession Number** (the number EDGAR gives one filing), saying that prose may say "filing" where the number is not the point. Make one column name, `accession_number`, the legacy column lists, the Snowflake models and SEC's own key already use it; the change is the five newer Silver tables and their rules (small, and those tables are new). Leave SEC's spellings, and fix the four daily-run terms in `CONTEXT.md` to say "filing" where they mean the filing. A rename is its own ticket, on your word.

## Parts

- [x] Read the uses and sort them: (a) SEC's own field name kept as source data, (b) our field or column name, (c) prose in docs, skills and tickets, (d) a stored name in MDM, silver or the Change Journal (2026-11-03 06:28 ET)
- [x] Say what the word means in each kind (a filing's identifier, a filing itself, a filing's folder in the capture) and where one word covers two meanings
- [x] Compare with the business words of `CONTEXT.md` ("filing", "Filing Identifier"?) and with the operator's rule to use business words and translate engine terms; list where a plain word would serve
- [x] Check the spellings: one name per meaning (`accession`, `accession_number`, `accessionNumber`), and which are fixed by SEC's data
- [x] Check which uses are stored identities that cannot be renamed (registered rule versions, Dataset Contract wording, migrations, MDM and silver column names), as ticket 178 found for "census"
- [x] Findings to the operator with numbers, one recommendation (keep, define in `CONTEXT.md`, or rename in slices), and a ticket for any rename the operator chooses: findings above; the rename ticket waits for the operator's choice
- [x] Learning → skill: name the skill line the findings change (for example the glossary rule in `skills/data-platform`), or "none": none yet; a rename ticket will name it
