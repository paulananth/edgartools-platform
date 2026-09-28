# An init mode: the mapping document first, then the rules

Type: build
Status: open
Blocked by: company mastering ticket 22 (data quality), which adds the
critical data elements and the quality file this document describes.

## Outcome

Operator, 2026-09-28:
- "We might need a data catalog and a mapping document".
- "The skill must have a init mode that creates mapping document and
  document which is critical and merge priorities then they are converted
  into rules".

The Rules skill gets an **init** mode. For a new source it first writes a
**mapping document** that people read and approve, then converts it into
the rules files (`source.yaml`, `quality.yaml`, the kind's merge rules).
The document states, per source:
- each source field, the MDM field it maps to, and its identifiers;
- which fields are **critical data elements** (missing: the record becomes
  an exception, never merges, never stops the run; ticket 22);
- the **merge priorities**: which source wins each MDM field, and the
  matching rules in their order.

A **data catalog** lists every source, dataset and MDM field in one place.

## Decided

- 08:18 ET, asked which one people edit after conversion: "Two separate
  things" (a document kept by hand beside the rules).
- 09:57 ET, superseding it, shown that `CONTEXT.md` and the Source Contract
  spec define the Mapping Document as generated, never hand-edited:
  "Initially, machine-generated must be able to edit and update by stewards
  in an easily understandable way for humans research and provide a
  sustainable format". So the init mode generates the document; stewards
  then edit and update it in a format people read easily, and the rules
  follow from it. The format is researched first
  ([research 11](../research/11-mapping-document-format.md)).
  `CONTEXT.md`'s "Do not edit by hand" changes with the chosen format.

- 10:21 ET, after [research 11](../research/11-mapping-document-format.md)
  and a plain list of options: "1 B, + E / 2 option 1 / 3. Option 1, auto
  approve / 4 option 1". So:
  1. **Format:** the Mapping Document is a **spreadsheet** (Excel), and the
     data catalog is kept in a **catalog server** (OpenMetadata or DataHub).
     The research recommended Markdown; the operator chose otherwise.
  2. **Stewards may change everything** in the Mapping Document; Claude
     turns each change into the rules.
  3. **Stewards may change merge priorities**, "auto approve": asked what
     approves, the operator chose "Steward's approval counts": the steward
     who makes the change runs `rules approve` on its digest under their own
     login, after Claude shows the proof (which winners move). The Rules
     Database still records a named approver. Claude never approves.
  4. **Catalog scope:** sources, datasets and MDM fields.

- 10:23 ET: the catalog server is **OpenMetadata**, published one way from
  the rules; nobody edits rules in it.

## Design (Claude, from the rulings; defaults, not new questions)

- **One workbook per source** (`rules/sources/<source>/MAPPING.xlsx`) and
  **one per kind** (`rules/merge/kinds/<kind>.xlsx`), generated from the
  rules. Source sheets: Source, Fields, Identifiers, Critical data elements,
  Data quality, Who wins, Notes. Kind sheets: Preferred sources, Matching
  rules, Notes. Plain words in every header; one row per rule fact, naming
  the rules path it comes from.
- **Notes** (a sheet per workbook) are the stewards' own: kept as written
  when the workbook is regenerated. The reasons now in YAML comments move
  there.
- **An edit becomes rules:** the steward commits the edited workbook in a
  pull request. `rules mapdoc diff` prints what changed, cell by cell, in
  plain text (a spreadsheet does not diff in a pull request, so this report
  is what reviewers read). Claude turns each change into the YAML, runs the
  dry run with counts and examples, and regenerates the workbook. Then
  `rules save` and `record-proof`; the steward approves the digest under
  their own login (a merge priority change included). Claude never approves.
- **Drift:** a test regenerates every workbook from the rules and fails when
  any cell outside Notes differs.
- **Init mode:** Claude profiles the captured files, writes a working draft
  of the rules (unsaved), generates the workbook from it, and iterates with
  the stewards; only an agreed workbook's rules are saved.
- **Catalog:** OpenMetadata, published from the rules: each source and
  dataset, each MDM field with the sources that fill it, in priority order.
  It runs first on a laptop (Colima); hosting in AWS is a later decision.

## Checklist (times ET)

- [x] Research the format (09:57 to 10:10 ET).
- [x] The operator's rulings (10:21, 10:23 ET).
- [ ] `/gof-refactor-reviewer` on `edgar_warehouse/rules/`.
- [ ] Workbook generator and `rules mapdoc` (write, diff, check), with the
  drift test; `openpyxl` added.
- [ ] Notes sheet kept on regenerate; today's YAML comments moved into it.
- [ ] Rules skill: the init mode and the steward edit loop; REFERENCE.md.
- [ ] `CONTEXT.md` (Mapping Document, Data Catalog) and spec §5, §20.
- [ ] OpenMetadata on Colima; publish the catalog; a separate PR.
- [ ] Three-axis review, PR, CI; merge on the operator's word.
