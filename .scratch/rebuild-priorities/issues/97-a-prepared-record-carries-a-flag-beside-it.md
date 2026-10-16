# A prepared record carries a flag read beside it

Priority: 97, tier 1, blocks ticket 22's resolution. Map: [Rebuild priorities](../map.md).

Type: task (engine code, small). Status: open; coding waits for the operator's word (configuration-only rule). Blocked by: none. Blocks: 22 (ISSUED_BY by issuer LEI).

## Why

Ticket 22's ruling (operator, 2026-10-16: "Issuers only, by LEI (Recommended)"):
a GLEIF record of an N-PORT issuer creates its Company, or joins the one
Company holding its LEI, when no Company holds that LEI; the rest of GLEIF
stays as today.

The rule must know which GLEIF records are issuers. The issuer set is a lookup
set (the LEIs the N-PORT issuer reduction gives, as ticket 91's pair sets),
read beside the record in the Level 1 source extract
(`rules/sources/gleif/level1-json.yaml`). That reading passes each record whole
(`record: {value: {path: '.'}}`), and `mdm.prepare` takes only that column
(`record_column`, `edgar_warehouse/workers/mdm_prepare.py:95-113`). A column
beside it is dropped, so the Dataset Contract cannot map the flag into its
matching values, and no configuration can carry it.

Ruled out:
- **A second GLEIF Dataset Contract for issuers** (a 341-line copy): a link
  resolves to a subject (source code and record key), so the same LEI would
  arrive as two subjects, and the main GLEIF record could bind the same LEI to
  an SEC Company: one LEI on two Companies.
- **A flag hand-added to the extracted test records**: the Proving Run would
  prove a reading that never runs.

## Proposed change

`mdm.prepare` gains an optional key `record_extras: [<column>, ...]`: with
`record_column`, each named column of the row is added to the record under its
own name (refused if the record already holds that name). The GLEIF Level 1
Dataset Contract then maps `matching.nport_issuer` from it, omitted when absent,
so a record without the flag reads exactly as today.

## Checklist

- [ ] Operator's word to code it
- [ ] GoF consult; `mdm.prepare` `record_extras` with its verifier, tests (present, absent, name clash)
- [ ] `level1-json.yaml`: lookup set `nport_issuers` and column `nport_issuer` (`member_value`); GLEIF Level 1 contract maps `matching.nport_issuer`; whole `tests/mdm` for pinned digests
- [ ] Rule `gleif-issuer-lei` in `rules/merge/kinds/company.yaml`, after the SEC–GLEIF name and cascade rules: `evidence_present@1` on `matching.nport_issuer`, then join the one Company holding the LEI, else create
- [ ] Ticket 22's Proving Run 2, with the cm27 SEC Companies loaded too (see ticket 22)
- [ ] Review, PR, CI green, merge on the operator's word
- [ ] Learning → skill
