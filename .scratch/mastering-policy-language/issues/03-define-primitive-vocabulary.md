# Define the primitive vocabulary the policy language may call

Type: research
Status: open
Blocked by: none

## Question

Q2 fixed the boundary: **structure and parameters in data, primitives in
code**. The policy document declares steps, order, verdicts, thresholds,
token lists, field names and source ranks; code provides a fixed,
versioned vocabulary of named tests the document may call. What is that
vocabulary — the smallest set that expresses every rule this platform has
already written, with nothing speculative added?

Derive it, do not invent it. Walk the existing corpus and extract the
tests each rule actually performs:

- **Person classification, rule C-J** —
  `.scratch/person-consumer-contract/issues/03-decide-reporting-owner-classification.md`
  and its reference implementation
  `.scratch/person-consumer-contract/research/18-classify.py`
  (`ENTITY_TOKENS`/`AMBIGUOUS_TOKENS` lines 64-87, `person_name_shape`
  139-151, `_structural_empty` 492-495, `rule_combo_h`/`rule_combo_j`
  671-703).
- **Person binding, Tiers A–D** —
  `.scratch/person-consumer-contract/issues/02-decide-what-binds-a-person.md`
  (shared identifier; compound context key of issuer/firm CIK + exact
  normalized name + consistent role; fuzzy; reject).
- **Company/GLEIF** — `.scratch/gleif-company-augmentation/spec.md`
  (revalidated Adjudicated Seed Links, deterministic crosswalks, one
  active binding per side, name match never sufficient).
- **Survivorship** — `docs/specs/clean-mdm/merge-stage.md:125-160` (the
  five-step ranking, field groups, freshness limits, eligibility) and the
  implemented `edgar_warehouse/mdm/clean/survivorship.py`.
- **Legacy, as evidence of need only** — the normalization rules and
  `mdm_match_threshold` seeds in `edgar_warehouse/mdm/migrations/002_seed_data.sql`
  and `edgar_warehouse/mdm/match.py`.

For each extracted primitive give: its name, its parameters, what it
returns, which existing rule needs it, and whether the platform already
has an implementation to point at (`path:line`). Group them by family
(classification / binding & consolidation / survivorship). Then state:

1. The **minimum** vocabulary — the primitives without which some written
   rule cannot be expressed. This is the answer.
2. Primitives that appear once and could stay as a rule parameter instead
   (argue each way).
3. What the vocabulary deliberately **cannot** express, and why that is
   the right boundary (e.g. arbitrary expressions, SQL, regexes supplied
   by the document — each is a replay and determinism hazard; say what
   breaks).
4. How a primitive is **versioned**, given the whole body is pinned by one
   digest but the primitives live in code: what must happen when a
   primitive's behaviour changes (e.g. a token added to a shared list, a
   normalizer fixed) so an old batch still replays to the same result.
   Check whether Clean MDM already answers this for its own normalizers
   (`merge-stage.md:60-70`, "pin the similarity dependency").

Write to
`.scratch/mastering-policy-language/research/03-primitive-vocabulary.md`
with `path:line` citations, and a worked example: rule C-J and Person
Tier B written out in the proposed vocabulary as JSON.
