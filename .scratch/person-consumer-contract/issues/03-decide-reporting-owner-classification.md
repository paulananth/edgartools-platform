# Decide how Form 3/4/5 reporting owners are classified as Person vs entity

Type: grilling
Status: resolved
Blocked by: 18

## Question

`sec_ownership_reporting_owner` mixes natural persons (directors, officers)
with entities (10% owners that are funds, holding companies, trusts). A
reporting-owner row with `is_ten_percent_owner` and no officer/director
flag is usually not a person. What rule classifies each row's kind —
`person`, `company`, `fund_structure`, or deferred — before any binding is
attempted, and what happens to a row whose kind cannot be decided from
flags and name (deferred with a blocking review, per Clean MDM's
`deferred_record`, never coerced)?

## Resolution

Resolved 2026-09-20 (operator: "agreed"). Rule **C-J** from
[research/18](../research/18-reporting-owner-classification-precision.md),
chosen because it is the only measured rule whose automatic decisions clear
the operator's 99% bar (ticket 02) on both arms: person 841/841 (Wilson 95%
lower bound 0.9955), entity 507/507 pooled (lower bound 0.9925) with ~1% of
owners deferred. The order ticket 03 first proposed (SEC `entityType` first,
then flags, then name) is rejected by the numbers: `entityType='other'` is
71% person, and `10%-only` is 72% entity (50 of 60 labeled no-token 10%-only
owners are natural persons).

### The rule, for the implementer

Evaluate per **owner CIK** (one verdict per CIK, applied to every row that
carries it), in this order. Definitions follow
[`18-classify.py`](../research/18-classify.py) exactly:
`ENTITY_TOKENS` / `AMBIGUOUS_TOKENS` (lines 64-87), `person_name_shape`
(2-5 alphabetic words, suffixes allowed, no digits, no `&`; lines 139-151),
`_structural_empty` (`sic`, `stateOfIncorporation`, `ein`, `tickers`,
`ownerOrg`, `fiscalYearEnd` all empty in the owner's `submissions.json`;
lines 492-495), `rule_combo_h` / `rule_combo_j` (lines 671-703).

| Step | Condition | Verdict |
| --- | --- | --- |
| 0 | No captured `submissions.json` for the owner CIK | **deferred** — never decide from the row alone; capture first (a task, not a Steward item) |
| 1 | SEC `entityType` ∈ {`operating`, `investment`} | **company** — bind to the Company Identity by CIK (Tier A, ticket 02); never a Person |
| 2 | Name carries an **unambiguous** legal-form token (a token not in `AMBIGUOUS_TOKENS`), **unless** the surname guard fires: name is person-shaped **and** structurally empty **and** carries exactly one token | **entity, kind undetermined** — see below; guard hit → **deferred** |
| 3 | No legal-form token at all **and** structurally empty **and** person-shaped | **person** — automatic; proceed to binding under ticket 02 |
| 4 | Anything else (ambiguous-token names, populated structural field with no token, non-person-shaped token-free names) | **deferred** — Steward |

- **Flags are evidence, never deciders.** `is_officer`, `is_director`,
  `is_ten_percent_owner`, `is_other`, `officer_title` are recorded on the
  assertion and used for role/relationship facts (ticket 05). Requiring
  officer/director for `person` adds no precision and defers ~2.6% of
  owners. **A 10%-only or other-only row is never coerced to entity.**
- **`entityType='other'` is evidence, never a decider** (71% person).
- **Deputization** (`otherText`/footnote text matching `deputi[sz]`) is
  recorded as evidence; it does not change the verdict (0.9% of rows; 29 of
  34 affected owners are entities by name already). The parser must start
  keeping `otherText` and footnotes so the evidence exists (ticket 10-class
  parser work; noted for ticket 04).
- **"Entity, kind undetermined" is terminal for the Person consumer**, not a
  Steward item. Only Company and Person are enabled kinds
  (`docs/specs/clean-mdm/domain-model.md:25`); a trust/LLC/fund owner has no
  consumer to publish it, so it is retained as a Clean MDM deferred record
  *outside* the Person publishing scope (`company-completion.md:63-67`): it
  does not block Person completeness and generates no review. When a Fund
  Structure (or other) consumer is enabled, these records are its input.
- **The Steward queue is step 0/2-guard/4 only**: measured ~1.1% of owners,
  dominated by natural persons SEC tagged with a state or fiscal year end
  (the Malone/Ault class, 37 of 52 in the primary corpus), then token-free
  boards (union locals, `FDB I`), ambiguous-token names
  (`BANK OF AMERICA NA`), and single-token surnames (`Trust Jane`).

### What is recorded (no new tables)

Per `domain-model.md:41-44` the source category, the asserted legal form,
and the inferred kind are stored **separately**, each with its rule and
evidence, in the `mdm_v2.assertion.body` the Person adapter writes
(migration 023, `44374b8b…942a1`):

- source category: SEC `entityType` verbatim, and the six structural fields
  with the `submissions.json` bronze object key they were read from;
- asserted legal form: the token(s) found, the ambiguity class, the
  person-shape result, deputization text if any;
- inferred kind: `person` / `company` / `entity_undetermined` / `deferred`,
  with `rule_id = C-J`, the rule version (the script's git blob hash), and
  the step (0-4) that fired.

A kind correction (a `person` that turns out to be an entity, or vice
versa) is **review + bounded rebuild**, never an entity merge
(`domain-model.md:43-44`) — the incompatible-kind veto stands.

### Release gates carried to the spec (ticket 08)

1. Automatic `person` may go live on research 18's result (841/841).
2. Automatic `entity` decisions require the two **post-hoc** guards (steps
   2-guard) re-measured on the first production cohort — the 507/507 is
   "no error observed under a guard written after both errors were seen".
3. The classifier reads the **bronze** `submissions.json`, never a live SEC
   fetch. edgartools' `Ownership.from_xml` already fetches every owner's
   submissions at parse time (`edgar/ownership/ownershipforms.py:1017-1020`
   in the locked 5.30.0) and computes an `is_company` the repo discards
   (`parsers/ownership.py`); its verdict is **not** to be reused (it calls
   `PX14A6G` filers companies and lacks `PLAN`/`fiscalYearEnd`).
4. The 4 uncertain labels and 16 overrides in `18-sample.jsonl` are the
   regression fixture for the rule.

### Unblocks

- Ticket 17 (Tier B calibration): the context key is built over `person`
  verdicts only.
- Ticket 05 (relationships): `IS_INSIDER`/`HOLDS` publish only from
  `person` and `company` verdicts; `entity_undetermined` rows publish
  nothing until their kind has a consumer.
