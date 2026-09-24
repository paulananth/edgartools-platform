# Write the versioned MDM Company table

Type: task
Status: open
Blocked by: 04 (a Company master exists only once binding works)

## Question

Operator, 2026-09-24: the final authority for a Company is **one table**,
`mdm_v2.company`, holding **one company per row version** with **both CIK and
LEI**, its other cross-references, its **name and every other identifying
field**, and **start and end dates**. A reader never goes to two places for
Company information.

Today the master record is one JSON document per entity in the shared
`mdm_v2.projection` table, for every kind, overwritten on change; its
cross-references are there (`identifiers`), but no row says "this was true from
X to Y", and `company_master` is only a view over it. Downstream readers
(legacy `mdm_company`, gold `mdm_company`) already expect `valid_from` /
`valid_to`.

## Decided (operator, 2026-09-24 08:28 ET)

- `mdm_v2.company` is a real table, written **only** by the Merge Stage, in the
  **same transaction** as the master record, never edited another way.
- One row per company version: a change closes the current row (`valid_to`)
  and opens a new one (`valid_from`).
- Columns: `entity_id`; cross-references (`cik`, `lei`, and any others the
  kind declares); `name` and the other identifying fields as named columns;
  `valid_from` / `valid_to`.
- It is the one place to read a Company. Evidence and decisions underneath are
  kept as they are.

## Checklist

- [x] Decide a real, dated Company table with CIK, LEI, name and identifying
  fields as the single read surface — operator (2026-09-24 08:28 ET)
- [ ] Decide what happens to the Company rows in `mdm_v2.projection` and the
  `company_master` view, so there is only one place to read
- [ ] Decide the exact identifying-field columns (SEC and GLEIF fields named in
  the Company policy's field semantics)
- [ ] Decide what `valid_from` means: when the source changed, or when MDM
  recorded it
- [ ] Migration, Merge Stage write, tests on a populated store (PG16)
