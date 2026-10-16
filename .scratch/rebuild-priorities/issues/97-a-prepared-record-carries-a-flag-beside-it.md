# A prepared record carries a flag read beside it

Priority: 97, tier 1, blocks ticket 22's resolution. Map: [Rebuild priorities](../map.md).

Type: task (engine code, small). Status: merged (#1013, 2026-10-16 13:43 ET); Ticket 22's Proving Run 2 is its last proof. Blocked by: none. Blocks: 22 (ISSUED_BY by issuer LEI).

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

- [x] Operator's word to code it: "Yes, code ticket 97 (Recommended)" 2026-10-16 13:13 ET
- [x] GoF consult (add as planned; one column-list parser shared with `distinct_on`); `mdm.prepare` `record_extras`: absent or null adds nothing, a clash is refused, without `record_column` refused; 4 unit tests, the verifier rebuilds and compares 2026-10-16 13:13 ET
- [x] (the reading side; the run's wiring is below) `level1-json.yaml`: a reference `nport_issuers` (empty by default, like `approved_scope`; a lookup set would need every caller to supply one) and column `nport_issuer`; the Level 1 contract's matching is its old object as `base` plus `nport_issuer` with `omit_nulls`, so a record without the flag reads exactly as before (assertion ids unchanged, `test_gleif_configured_fields.py`); contract digest layer `WITH_ISSUER_FLAG` and policy layer `without_issuer_lei`, each peeling back to the digest pinned before; `tests/mdm` and affected tests: 952 passed, installed GLEIF mapping test passed 2026-10-16 13:13 ET
- [x] Rule `gleif-issuer-lei` (declared, not switched on): `evidence_present@1` on `provenance.matching.nport_issuer`, then join the one Company holding the LEI, else create; GLEIF added to the LEI contract's sources (it issues LEIs; a creating rule must name an issuing source). Binding rules may now carry record tests (`activation.check_binding_rule`, `binding._record_tests_hold`). Identifier rules run before the name rules in every batch (`merge.py`), so an issuer that is also an SEC filer can become two Companies (the ruling took this risk). On PG16: a flagged record creates its Company, another waits, a second flagged record joins; with the record test removed the test fails 2026-10-16 13:13 ET
- [x] Review (Standards, Spec, GoF): binding rules use classification's own evaluator (one place applies `negate`). Spec found, and this ticket now says plainly 2026-10-16 13:16 ET:
  - The flag reaches a record only where a GLEIF run's records step passes `record_extras: [nport_issuer]` and fills the `nport_issuers` reference. No platform command builds GLEIF Level 1's prepare step yet (only the proof scripts do); that wiring belongs to GLEIF's source activation (tickets 02 and 71), which must pass both. Until then the rule cannot fire outside a Proving Run.
  - A record without the flag is unchanged; the Level 1 reading's rows now carry an `nport_issuer` column (null when not listed), which `mdm.prepare` leaves out of the record.
  - With GLEIF an LEI source, a Company bound to a GLEIF record through the name rules now holds that LEI. The ADV custodian LEI rule (ticket 76, not switched on) then joins such a Company instead of creating one, and an LEI held by two Companies goes to review (`ambiguous_identifier`). Ticket 76's proof predates this and is re-run before its switch-on.
  - `check_binding_rule` admits any record test (classification family) in a binding rule, not only `evidence_present@1`; each reads the record alone.
- [x] Ticket 22's Proving Run 2 through the real Level 1 reading and `mdm.prepare` with `record_extras` and the issuer lookup set: 24,124 flagged records each created or joined a Company by LEI, 0 LEIs on two entities, second pass unchanged. It found `mdm.prepare` refusing lookup receipts, fixed in #1013 before merge. 2026-10-16 14:12 ET
- [x] Review (Standards, Spec, GoF), PR #1013, CI green (6 checks), merged on the operator's words "merge one by one" 2026-10-16 13:43 ET
- [x] Learning → skill: data-onboarding REFERENCE "Merge rules" (record tests narrow a matching rule; a creating rule names an issuing source) and data-platform SKILL (`record_extras`) 2026-10-16 13:13 ET
