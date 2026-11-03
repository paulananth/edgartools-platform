# 179: Investigate the use of "accession" in the project

Priority: 179. Map: [Rebuild priorities](../map.md). Opened 2026-11-03 06:02 ET (operator, 2026-11-03: "create a ticket to investigate use of \"accession\" in the project").

Type: task (investigation; no code change until the findings are read). Status: open. Blocked by: none. Related: [178](178-the-name-count-replaces-name-frequency-and-census.md) (the same question asked of "census"), [158](158-glossary-holds-only-real-terms.md) (the glossary holds only terms that real data backs).

## Question

"Accession" is an SEC word (the number EDGAR gives each filing). The project uses it widely, and the operator asks where and how, as ticket 178 asked of "census": is it a word the operator would use, is it spelled one way, and does the glossary define it?

## What a first count showed (read 2026-11-03 06:02 ET on `origin/main`, outside `.scratch/`, `.planning/` and `docs/research/`)

- 172 files and about 1,775 lines say "accession".
- By kind: about 395 lines in Python, 328 in rules `.yaml`, 38 in Rust, 648 in tests; the rest in docs, skills and `CONTEXT.md`.
- Spellings: `accession` (529), `accession_number` (144), `accessionNumber` (119, SEC's own JSON key), `ACCESSION`, `ACCESSION_NUMBER`, and compounds (`source_accession`, `superseded_by_accession`, `accession_seen`, `cik_and_accession`).
- `CONTEXT.md` uses it inside other terms (daily-artifact run selection, candidate attempts, relationship source candidates, a normalized-text projection "identified by filing accession") but holds no entry of its own for the word.

## Parts

- [ ] Read the uses and sort them: (a) SEC's own field name kept as source data, (b) our field or column name, (c) prose in docs, skills and tickets, (d) a stored name in MDM, silver or the Change Journal
- [ ] Say what the word means in each kind (a filing's identifier, a filing itself, a filing's folder in the capture) and where one word covers two meanings
- [ ] Compare with the business words of `CONTEXT.md` ("filing", "Filing Identifier"?) and with the operator's rule to use business words and translate engine terms; list where a plain word would serve
- [ ] Check the spellings: one name per meaning (`accession`, `accession_number`, `accessionNumber`), and which are fixed by SEC's data
- [ ] Check which uses are stored identities that cannot be renamed (registered rule versions, Dataset Contract wording, migrations, MDM and silver column names), as ticket 178 found for "census"
- [ ] Findings to the operator with numbers, one recommendation (keep, define in `CONTEXT.md`, or rename in slices), and a ticket for any rename the operator chooses
- [ ] Learning → skill: name the skill line the findings change (for example the glossary rule in `skills/data-platform`), or "none"
