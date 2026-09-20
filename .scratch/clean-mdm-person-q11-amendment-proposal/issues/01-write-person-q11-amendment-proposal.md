# Write and evidence the Person Q11 amendment proposal

Type: task
Status: resolved
Blocked by: none

## Question

Write the proposal for Codex/Grok.

## Answer

### What is accepted today

`docs/specs/clean-mdm/merge-stage.md` (your branch, read-only), lines 53–60:

> No universal automatic or review score is specified. Accepted Q11 requires
> at least 99.9% precision, demonstrated by a one-sided 95% lower confidence
> bound on representative, independently labeled held-out automatic-binding
> decisions for each enabled entity kind and rule family. Insufficient
> evidence keeps a rule review-only.

And line 13–15: Q16 "permits the local build with every unqualified
exact/scored automatic rule disabled. Measured calibration and versioned
policies gate each rule's activation."

Nothing here disputes the method. The proposal changes one number, for one
kind, and supplies the rule family it applies to.

### What the operator decided for Person (2026-09-20)

From the [Person Consumer Contract, ticket 02](../../person-consumer-contract/issues/02-decide-what-binds-a-person.md):

1. **One Person, one `entity_id`.** Every source identifier is a
   cross-reference bound to it — `owner_cik` (Form 3/4/5 `rptOwnerCik`)
   and ADV Schedule A/B `OwnerID` (a CRD-system individual record id,
   [research 16](../../person-consumer-contract/research/16-schedule-ab-ownerid-meaning.md)).
   A cross-reference id points at exactly one Person; a second Person
   claiming a bound id is a hard veto. Duplicate CRD records (which IARD's
   own FAQ concedes exist) collapse onto one Person as two cross-refs.
2. **No Person is created without a match attempt.**
3. **Rule families for the no-shared-key case:**

   | Tier | Evidence | Action |
   | --- | --- | --- |
   | A | shared cross-reference id | automatic, deterministic — unchanged from your exact-identifier rule |
   | B | compound context key: same issuer/firm CIK + exact normalized name + consistent role/flag | **automatic at ≥ 99% measured precision** (this proposal); review-only until measured |
   | C | fuzzy name; or name across different issuers | review |
   | D | below the review floor | reject with disposition |

### The ask

Amend Q11 **for `kind = 'person'` and the Tier B rule family only**:
activation threshold **≥ 99% precision**, one-sided 95% lower confidence
bound, on independently labeled held-out decisions — your method, your
adversarial cases (homonyms, reused identifiers, mixed kinds, transitive
bridges), your "zero hard-veto violations" requirement. Everything else in
Q11/Q16 unchanged; Company stays at 99.9%.

### Why the operator wants it

Person volume is where manual review would concentrate: the platform has
8,944 distinct reporting-owner keys (research 01), 11,126 identified ADV
individuals (research 16), 7,700 clean 8-K names (research 01). Tier A
covers most rows; Tier B is the population arriving from a *second*
issuer (a Form 4 filer who is also an adviser owner) with no shared id.
At 99.9% that population sits in a Steward queue indefinitely — no
Person corpus today could clear the bar. At 99%, roughly one wrong
auto-bind per hundred cross-issuer persons is accepted as the cost of a
near-empty queue. The operator's words: "don't want to create manual
work."

### What it is not

- Not a similarity cutoff. Tier B is a compound key, not a name score;
  its precision is measured, not assumed.
- Not a change to Company, Security, Fund, or any other kind.
- Not a change to Q16: Tier B stays review-only until the calibration
  study ([Person ticket 17](../../person-consumer-contract/issues/17-calibrate-person-tier-b-context-key.md))
  reports its lower bound.
- Not an edit to any of your files.

### Open questions — yours

1. Whether 99% should apply per rule family (Tier B only) or per kind.
2. Whether a Tier B auto-bind should carry a distinguishable
   `decision.body` marker so a later reversal can target the tier.
3. Whether the calibration study's labels need a reviewer independent of
   the operator, as the GLEIF cohort labels were flagged for.
