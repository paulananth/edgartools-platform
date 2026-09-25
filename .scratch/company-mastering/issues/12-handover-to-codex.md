# Ticket 12 handover: Claude → Codex (2026-09-24, about 21:30 ET)

The operator asked to hand ticket 12 to Codex. Read
`12-prove-and-switch-on-the-sec-company-classification-rule.md` (decisions and
checklist) and `../research/12-sec-company-classification-proof.md` (the
first measurement) first.

## Goal

Shell and ASML become Companies automatically on the standard SEC setup.
SEC types them `other`, as it does individuals such as Tim Cook. The
classification rule `sec-company-candidate` (in
`edgar_warehouse/mdm/policies/company.json`) tells them apart, but it may act
alone only on a measured proof that clears the operator's bar **and** the
operator's approval of the exact policy digest.

## State of the branch

- Merged on `main` earlier today: tickets 03, 04, 09, 11 (PRs 704–709).
- Commit `71c9d179` on this branch: accepted bars keyed by (kind, family),
  Company classification at 0.95; rule frozen at `2026-09-24.6`; first
  measurement (research/12-*).
- The WIP commit after it:
  - rule is now **`2026-09-24.7`**: the legal-form word list is
    `company_legal_form`, i.e. the Person list minus words for non-companies
    (FOUNDATION, UNIVERSITY, CHURCH, PENSION, PLAN, FAMILY, TRUST, FUND, and
    others);
  - the SEC contract names the rule (`sec-company-landing-v2`) instead of
    the `kind_values` lookup;
  - **no activation**: `POLICY["automatic_rules"]` is `[]`. So, on this
    branch, every SEC record waits, Apple included, until the new proof and
    approval land. Do not merge in this state.

## Why the first approval was withdrawn

The operator approved digest `b26ab87c…` at 21:05 ET. The three-axis review
then found:

1. **The bar is per rule step, not per verdict.** `company-policy.md`,
   Confidence bands: "Probability here is how often the **rule step** that
   made the decision is right". Step 4 (`other`, industry code, legal-form
   word) measured 70/71, a lower bound of 0.939, below 0.95. Shell and ASML
   come through step 4.
2. The legal-form list caught non-companies (fixed in `.7`).
3. The adversarial arm "individuals with an industry code" was chosen by a
   name test that overlaps the rule's own, so it was partly true by
   construction.

## What is left (in order)

1. **Rework `research/12-classify.py`**. My last edit did not apply; the file
   is as committed in `71c9d179`. Change it to:
   - use a fresh seed `20260924.7`;
   - sample **each Company step separately**, 300 each (steps 2 and 4);
   - build a **name-blind adversarial fixture**, every record with its true
     label:
     - every ownership-only `other` filer with an industry code, whatever
       its name (hand-read entities: GOULD INVESTORS L P, LOWENSTEIN SANDLER
       LLP, TDS voting trust);
     - every `other` + industry-code filer whose name names a non-company
       kind;
     - 100 individuals with no industry code;
     - 100 `investment` funds.

     A violation is any record whose true label is not Company and which the
     rule calls Company.
   - Record a hand-read `note` for **every** fund-, trust- or
     partnership-looking name in the sample, not only the non-company drafts.
2. Score it. **Each step must clear 0.95 on its own**. If step 4 does not,
   report it to the operator; do not ship an activation. In that case Shell
   and ASML stay waiting.
3. Put the proof in `company_source.py` (`automatic_rules`, as in
   `71c9d179`), with the file SHA-256s from `12-summary.json` and the per-step
   results inside `cohort`.
4. **Ask the operator to approve the new digest, explained in plain English
   first**: what a digest is (a fingerprint of the exact rule document, so an
   approval cannot be carried over to an edited rule), what it switches on,
   the per-step numbers, and how to reverse it. The operator rejected a bare
   "do you approve digest X?" today. Record the true approval time in the
   ticket.
5. Fix the tests that still expect the lookup table:
   - 6 in `tests/mdm/test_clean_classification.py` (lines ~297, ~367 do
     `del contract["adapter"]["kind_field"]`);
   - 5 in `tests/mdm/test_clean_company_source.py` (policy digest now
     required; line ~88 expects `unsupported_identity_kind`);
   - `tests/integration/test_clean_mdm_postgres.py:~1698`.

   Also update the digest pins:
   - `APPROVED_POLICY` in `tests/integration/test_clean_four_companies.py`;
   - `test_the_policy_is_the_approved_digest` in
     `tests/mdm/test_clean_activation.py`.

   Add a test that re-hashes the research files against
   `PROOF.cohort.files`.
6. Full suite, three-axis `/code-review`, PR, CI green, then merge on the
   operator's word.

## Rules (CLAUDE.md, operator)

- **Own branch:** work on your own `codex/` branch, never on
  `claude/company-mastering-12-prove-sec-classification`.
- **Data:** zero SEC requests; bronze and fixtures only. The population file
  is the bronze scan summary (sha256 `395b7db4…`, 76,230 CIKs), produced by
  `.scratch/individual-filer-company-misclassification/research/05-scan-bronze-entity-types.py`.
- **Talking to the operator:**
  - use business terms: say "matching rule", "Stage" and "master record",
    not engine words;
  - ask one question at a time, in plain English, with a recommendation;
  - report times in ET.
- **Checklist:** keep the ticket checklist live, with ET times and how each
  part was verified.
- **Tests:** PG16 tests use
  `DOCKER_HOST=unix://$HOME/.colima/default/docker.sock`. The `fastapi`
  import failures in `tests/mdm/test_runtime_ops.py`, `test_api.py` and
  `test_temporal_graph_queries.py` are the known baseline.

## Operator decisions already made (do not re-ask)

- SEC `investment` filers are Funds.
- BDCs are Companies.
- Asset-backed loan trusts (SIC 6189) are not Companies.
- Exchange-traded commodity and crypto trusts and futures pools (SIC 6221)
  are Funds.
- Foreign governments (SIC 8888) are Government Bodies.
- The Company classification bar is 95% at 95% one-sided confidence.
- Merging two published Company IDs keeps 99.9%.
