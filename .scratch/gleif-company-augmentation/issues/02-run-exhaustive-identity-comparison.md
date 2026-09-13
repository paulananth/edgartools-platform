# Run and adjudicate the exhaustive identity comparison

Type: research
Status: resolved
Claimed by: Codex
Claimed on: 2026-09-11
Blocked by: 01

## Question

For the frozen 1,000-company cohort, which MDM entities can be linked to exactly
one GLEIF LEI with retained, auditable evidence, and what are the adjudicated
coverage, precision, ambiguity, rejection, and no-candidate rates?

## Required evidence

- Generate candidates from the fixed Level 1 corpus using current names, former
  names, conservative legal-suffix normalization, jurisdiction, address, and
  reviewed registration-authority identifiers where their semantics are proven.
- Search the complete fixed candidate corpus; do not cap broad names at the
  first ten candidates and do not call a moving API for acceptance evidence.
- Retain every score component, compared raw field, normalized field, conflict,
  candidate rank, evidence tier, and reason code.
- Manually adjudicate every positive candidate as same legal entity, different
  entity, or unresolved. Exact-name-only and fuzzy-name-only candidates are not
  accepted.
- Report results overall and by predeclared cohort stratum with confidence
  intervals where a rate is inferred beyond the cohort.
- Replay independently and require identical candidates, classifications, and
  aggregates.

## Done when

All 1,000 cohort rows have an adjudicated or explicit no-candidate disposition,
all positive candidates retain review evidence, and a replay hash matches.

## Answer

Resolved by [`../research/02-identity-results.md`](../research/02-identity-results.md).

All 3,428,477 records in the fixed Level 1 publication were scanned. The scan
produced 883 candidate pairs for 498 cohort companies, and every pair received
a retained manual disposition. At company level, 308 have one accepted LEI and
no unresolved competitor, 103 have only rejected candidates, 87 remain
unresolved, and 502 have no candidate. The fixed stratified cohort does not
support population-wide inference.

Tier B's adjudicated acceptance rate was 224/249 (90.0%, Wilson 95%
85.6%-93.1%); Tier C's was 92/363 (25.3%); Tier D's was 0/271. Therefore none
of the heuristic tiers is authorized for unattended identity linking. A full
candidate replay and deterministic re-finalization reproduced the recorded
artifact hashes.
