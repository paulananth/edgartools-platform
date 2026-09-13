# Measure GLEIF attribute lift and conflicts

Type: research
Status: resolved
Blocked by: 02

## Question

Across adjudicated same-entity links, which GLEIF Level 1 attributes add useful
company evidence beyond current MDM/SEC data, which merely duplicate it, and
which conflict with it?

## Required evidence

- Keep separate denominators for accepted links, all 1,000 companies, and each
  cohort stratum.
- Measure legal form, jurisdiction, legal and headquarters addresses, other and
  transliterated names, entity lifecycle/events, registration status and
  freshness, and mapped identifiers.
- Classify every field comparison as equal, compatible, different, missing in
  MDM, missing in GLEIF, or not comparable.
- Distinguish source disagreement from temporal change and from unlike field
  semantics; do not overwrite SEC evidence in the analysis.
- Rank additions by coverage, decision usefulness, conflict risk, and source
  freshness.

## Done when

The comparison identifies concrete useful additions and conflicts without
letting unmatched companies or rejected candidates inflate coverage.

## Answer

Resolved by [`../research/03-attribute-lift-results.md`](../research/03-attribute-lift-results.md).

Among 308 accepted links, GLEIF supplies legal form and LEI registration
evidence for all 308, registration-authority entity IDs for 286, entity creation
dates for 253, typed legal events for 62, names new to current MDM for 41, and
successor LEIs for three. Five comparable legal-jurisdiction values disagree
with SEC and require review. Counts use only accepted links and are also stated
against the full 1,000-company cohort; unmatched and rejected companies do not
inflate lift.
