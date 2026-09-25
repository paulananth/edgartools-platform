# Write the versioned MDM Company table

Type: task
Status: claimed
Blocked by: 04

The full Company milestone still needs ticket 04's approved binding.

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
- [x] Decide what happens to the Company rows in `mdm_v2.projection` and the
  `company_master` view — operator (2026-09-24 08:31 ET): the `company_master` view is
  removed; Company rows in `projection` are the engine's working state only,
  read by no reader or export; the Snowflake export and the API read
  Companies from `mdm_v2.company` alone
- [x] Name Company identifying columns — operator reply and migration 037 inspected (2026-09-25 16:23 ET).
  `cik`, `lei`, `name`, structured `address`, SEC and GLEIF identifying fields
  are columns; future selected fields and cross-references remain in JSONB.
- [x] Set `valid_from` to MDM decision time — operator reply and PG16 test passed (2026-09-25 16:23 ET).
  Source effective time stays in evidence. A repeated `as_of` cutoff does not collapse two
  separately committed decisions.
- [x] Source priority for Company values: **SEC first, GLEIF next**,
  configurable per entity kind in the Mastering Policy — operator (2026-09-24 09:45 ET)
- [x] Fill rule: the master takes every field from every source; priority
  applies only when a field exists in more than one — operator (2026-09-24 09:59 ET)
- [x] Decide which SEC and GLEIF fields count as **the same field** —
  operator (2026-09-24 10:00 ET): **name**, **jurisdiction** and **address** are one field
  each; SEC wins when both have a value; GLEIF's value stays in the Stage as
  evidence; jurisdiction is normalized to one code format before comparing
  (`CA` and `US-CA` are the same). Every other field comes from whichever
  source has it. Supersedes the accepted GLEIF field semantics that kept these
  separate.
- [x] Write it as the Company rule, per kind: `edgar_warehouse/mdm/policies/company.json`
  (one file per kind, loaded not restated), a kind-level `defaults` rule every
  field inherits (SEC first, GLEIF next), SEC and GLEIF both mapping `name`
  and `jurisdiction`, and a `field_formats` entry converting SEC state codes
  to ISO 3166-2 — unit + PG16 on AAPL, MSFT, Shell, ASML (2026-09-24 10:17 ET)
- [x] Build the kind-level default priority list — `defaults`, an authority
  section, so changing it moves every value's recorded digest (2026-09-24 10:17 ET)
- [x] Select one whole structured address — PG16 154 tests passed (2026-09-25 18:31 ET).
  SEC business address and GLEIF legal
  address map to the same field; the winner supplies all components, and a
  different whole address remains conflicting evidence. The SEC country-code
  gap remains ticket 14. GLEIF additional legal-address lines are retained.
- [ ] ~~Foreign EDGAR location codes to ISO 3166~~ no longer needed: SEC's
  code is not compared with anything (2026-09-24 11:10 ET)
- [x] Three-axis `/code-review` — Standards: 1 hard (defaults read outside the
  kind resolver); Spec: raw foreign code lost, Stage claim untested; GoF:
  load kind files in their own loader. All fixed: `_defaults_for` beside
  `_rules_for`, raw SEC code kept, `policies.load_kinds()`, error messages
  name formats generally, Stage assertion added, `defaults` documented in
  policy-language §8 (2026-09-24 10:19 ET)
- [x] Refuse an unlisted Company source — PG16 test passed (2026-09-25 16:23 ET).
  The Merge Stage refuses an arriving Company source missing from the
  kind's default priority list, so a typo cannot silently drop its fields.
  It permits a declared future source before that dataset is registered —
  `test_company_fill_rule_refuses_an_unlisted_arriving_source` passed.
- [x] Correct the GLEIF Level 1 source default — source unit tests passed (2026-09-25 16:23 ET).
  `gleif_source.dataset_contract` defaults `level1_source` to `gleif.level1.v1`,
  matching the policy and native spec.
- [ ] Priority changes are data, but the file ships in the package, so a
  change still needs an image rebuild; the Rules Database is where a live
  change belongs (Codex's Source Contract area)
- [ ] A store holding readings under the old field names
  (`incorporation_jurisdiction`, `gleif_legal_jurisdiction`) would show them
  beside `jurisdiction` until re-read; no live store holds Clean MDM Company
  evidence yet (migrations 027+ unapplied), so this is noted, not built
- [x] Blank text is unknown, never a value — operator (2026-09-24 13:40 ET); applies to
  every source's fields in `adapters.normalize`. ASML now has no SEC state of
  incorporation instead of an empty one, and no Company shows SEC's blank
  description — unit + PG16 (2026-09-24 13:40 ET)
- [x] Decide Shell's jurisdiction — operator (2026-09-24 11:10 ET): **two fields, not one**.
  SEC gives `state_of_incorporation`, as SEC writes it (`CA`, `DC`); GLEIF
  gives `jurisdiction` (`US-CA`, `GB`). They never compete, so the
  SEC-to-ISO conversion is removed. Supersedes "jurisdiction is one field"
  above. Shell now reads `DC` from SEC and `GB` from GLEIF. **Name** is the
  only field both sources supply today — PG16, four Companies (2026-09-24 11:10 ET)
- [x] Install migration 037 and date Company rows — PG16 154 tests passed (2026-09-25 18:31 ET).
  Migration 037 creates and backfills the dated table, routes aliases in
  a separate metadata table, writes new versions through the Merge Stage's
  projection trigger in the same transaction, removes `company_master`, and
  moves `company_master_field` onto the dated table. PostgreSQL 16 tests cover
  a populated upgrade, later writes, historical reads, alias reversal and
  restricted writes. The populated-store test delivers pending pre-migration
  exports from the dated authority.
