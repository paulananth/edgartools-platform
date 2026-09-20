# Handover — 2026-09-20, Claude → Codex (Clean MDM): reporting-owner classification rule

## TL;DR

The Person Consumer Contract has decided **how a Form 3/4/5 reporting owner
is classified as person / company / entity / deferred before any binding**.
The rule (C-J) was chosen by measurement, not by argument: it is the only
candidate whose automatic decisions clear the operator's 99% precision bar
on both arms, with ~1% of owners left for a Steward. Two things you may
have assumed are false: SEC's `entityType='other'` is only 71% person, and
a 10%-owner-only row is only 72% entity — neither may decide.

Read, in order:

1. [`.scratch/person-consumer-contract/issues/03-decide-reporting-owner-classification.md`](../person-consumer-contract/issues/03-decide-reporting-owner-classification.md)
   — **the rule for the implementer**: the five-step table, what is
   evidence versus decider, what is recorded where, release gates.
2. [`.scratch/person-consumer-contract/research/18-reporting-owner-classification-precision.md`](../person-consumer-contract/research/18-reporting-owner-classification-precision.md)
   — the measurement: population, labeled sample, every rule scored,
   uncertain cases, what could not be determined.
3. [`18-classify.py`](../person-consumer-contract/research/18-classify.py)
   — the exact definitions (`ENTITY_TOKENS`, `AMBIGUOUS_TOKENS`,
   `person_name_shape`, `_structural_empty`, `rule_combo_j`). Port these,
   do not re-derive them; `18-sample.jsonl` is the regression fixture.

## The rule in one table

Per owner CIK, one verdict for every row carrying it:

| Step | Condition | Verdict |
| --- | --- | --- |
| 0 | no captured `submissions.json` for the owner CIK | deferred (capture task) |
| 1 | SEC `entityType` ∈ {`operating`, `investment`} | **company** — Tier A bind by CIK |
| 2 | unambiguous legal-form token in the name — unless person-shaped, structurally empty, exactly one token (surname guard) | **entity, kind undetermined** (guard → deferred) |
| 3 | no token, structurally empty SEC profile, person-shaped name | **person** — automatic |
| 4 | else | deferred — Steward |

Measured: person 841/841 (Wilson LCB 0.9955); entity 507/507 pooled (LCB
0.9925, under two post-hoc guards); deferred ≈ 1.1% of owners.

## What this means for your Person integration

- **Flags are not classifiers.** `is_officer`/`is_director`/
  `is_ten_percent_owner`/`is_other` go on the assertion for role facts;
  requiring officer/director for `person` buys no precision and defers 2.6%
  of owners.
- **"Entity, kind undetermined" is terminal for Person, not a review.** Only
  Company and Person are enabled kinds (`domain-model.md:25`). A trust/LLC/
  fund 10% holder is retained as a `deferred_record` outside the Person
  publishing scope (`company-completion.md:63-67`), blocks nothing, and is
  the input for whichever consumer later claims those kinds.
- **Recording** follows your `domain-model.md:41-44`: source category (SEC
  `entityType` + the six structural fields + bronze object key), asserted
  legal form (tokens, ambiguity class, person-shape, deputization text), and
  inferred kind (`rule_id = C-J`, rule version, step fired) stored
  separately in `assertion.body`. Kind correction = review + bounded
  rebuild, never merge. No new tables.
- **Read bronze, never SEC, at classification time.** edgartools'
  `Ownership.from_xml` fetches every reporting owner's `submissions.json`
  from SEC during parse (`edgar/ownership/ownershipforms.py:1017-1020`,
  locked 5.30.0) to compute an `is_company` that `parsers/ownership.py`
  discards. Do not reuse its verdict: it lists `PX14A6G` under
  `COMPANY_FORMS` (activist individuals become companies) and has no
  `PLAN` token and no `fiscalYearEnd` check (a UAW benefits plan becomes a
  person). Every owner CIK in bronze already has its payload captured
  (4,831/4,831).
- **Deputization** lives in `otherText`/footnotes the silver parser drops
  (0.9% of rows; 3.1% in the older corpus). It is evidence only; it changes
  no verdict. The parser will be asked to keep the text (Person map,
  parser-owner task, alongside ticket 10).

## Release gates you will be held to

1. Automatic `person` can go live on the 841/841 result.
2. Automatic `entity` needs the surname guard re-measured on the first
   production cohort before it is enabled — the 507/507 is "no error seen
   under a guard written after both errors were seen".
3. Classification reads the bronze `submissions.json` object, never a live
   fetch.
4. `18-sample.jsonl` (1,220 labels, 4 uncertain, 16 overrides listed) is
   the fixture; a port that disagrees with any label is a finding to
   raise, not a label to change.

## Where disagreement goes

Reply by a note under `.scratch/handover/`; do not edit the Person map or
its tickets. The Q11 amendment note
([2026-09-20-claude-to-codex-person-q11-amendment.md](2026-09-20-claude-to-codex-person-q11-amendment.md))
still stands and is the bar this rule was measured against.
