# Define the primitive vocabulary the policy language may call

Type: research
Status: resolved
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

## Answer

Resolved 2026-09-20 — [findings](../research/03-primitive-vocabulary.md).
**Twelve primitives**: 2 shared normalizers (`normalize_text`,
`normalize_identifier`), 5 classification (`evidence_present`, `field_in_set`,
`token_match`, `name_shape`, `fields_all_empty`), 4 binding
(`identifier_match`, `identifier_cardinality`, `compound_key_equal`,
`name_similarity`), 1 survivorship (`select_by_source_rank` — small because
`merge-stage.md:123-130` fixes the total order, so the document supplies only
the rank list and eligibility parameters). Everything large is a **parameter**:
the 90+ `ENTITY_TOKENS`, the ambiguous/suffix lists, the six structural field
paths, the ordered `sources` list, the 0.99/0.999 bars. Decisive evidence for
that line — the same words (`TRUST`, `FUND`, `CO`, `HOLDINGS`) are entity
*evidence* in `18-classify.py:64-80` and *deleted* by the legacy normalizer at
`002_seed_data.sql:73-98`: one primitive, two declared lists, opposite uses.
Excluded after arguing both ways: `kind_compatible` (already unconditional,
`identity.py:94-95`), `digest_tuple` (Person `#3`, `02:67-68`, requires an exhaustive
attempt), `field_group_together` (accepted policy, **no implementation and no
consumer** — a gap found here, flagged to Codex), publication-time tiebreak (a
parameter, also unimplemented in `survivorship.py:239-249`). The vocabulary
cannot express document-supplied regexes/SQL, clock or network reads, loops, or
`OR` inside a step; two exclusions are repo-specific and statically checkable —
a binding rule may not reach a survivorship primitive (`CONTEXT.md:23,51`), and
may not decide on `name_similarity` alone (`spec.md:95`). Versioning: primitives
are referenced `name@version`, an unknown pair is refused fail-closed like
research 02's `qualified()`; list edits need no version bump (they re-digest the
body); the honest limit is that exact replay needs the old implementation still
in the build — recommend retaining superseded versions, which is the same
bargain `merge-stage.md:100-104` already struck for decisions.
[research/03](../research/03-primitive-vocabulary.md).
