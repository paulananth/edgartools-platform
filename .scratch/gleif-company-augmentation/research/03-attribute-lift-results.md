# Ticket 03 GLEIF attribute lift and conflicts

Date: 2026-09-12
Inputs: 308 accepted Company-to-LEI links and the fixed GLEIF 2026-09-11
16:00 UTC Level 1 Golden Copy.

## Result

GLEIF provides material legal-entity enrichment for accepted links, but the
fields must remain source-grained. The denominator below is always 308 accepted
links; dividing by the full frozen cohort gives the corresponding all-cohort
coverage. The fixed stratified cohort does not support population-wide
inference.

| GLEIF attribute | Accepted-link coverage | All-cohort coverage | Finding |
| --- | ---: | ---: | --- |
| Legal form | 308/308 (100%) | 30.8% | Entirely new to current Company MDM; retain ISO 20275 code and exceptional text |
| LEI registration/status/dates/LOU/validation | 308/308 (100%) | 30.8% | Entirely new operational provenance; 197 issued, 107 lapsed, two duplicate, two retired |
| Legal/headquarters addresses | 308/308 present | 30.8% | 237 have address support against SEC; 71 are not directly comparable; legal and HQ addresses stay distinct |
| Legal jurisdiction | 308/308 present | 30.8% | 232 equal to SEC subdivision, seven compatible country-vs-subdivision, five different, 64 not comparable |
| Registration-authority entity ID | 286/308 (92.9%) | 28.6% | High-value corroborating identifier, but authority-local and never assumed to be CIK |
| Entity creation date | 253/308 (82.1%) | 25.3% | New lifecycle evidence |
| Legal-entity events | 62/308 (20.1%) | 6.2% | 98 retained events across address, name, form, merger/acquisition, dissolution, and other-name changes |
| Other/previous/trading/transliterated names | 50/308 (16.2%) | 5.0% | 41 companies have at least one name not present in current SEC former-name evidence |
| Successor LEI | 3/308 (1.0%) | 0.3% | Low coverage but critical for duplicate/retired identity transitions |
| Explicit entity-expiration fields | 0/308 | 0% | No lift in this cohort; preserve if later publications provide them |

All 308 accepted records are GLEIF category `GENERAL`. Entity status is 304
`ACTIVE`, two `INACTIVE`, and two literal `NULL`; it is not comparable to MDM
tracking status. LEI registration status is a separate concept and is notably
stale for 107 `LAPSED` records. Validation sources are 280 fully corroborated,
six partially corroborated, and 22 entity-supplied only.

The latest GLEIF update date is present for all accepted links. At publication,
its age ranges from one to 1,886 days with a median of 224 days. This makes the
daily delta useful for change detection but does not imply that every accepted
Company changes daily.

## Comparison classes and conflicts

Legal-name comparison produced 210 exact, 79 suffix-compatible, and 19
different-but-independently-supported accepted identities. Conservative legal
suffix handling is therefore material to recall (79/308), while SEC former
names supplied the chosen match for four accepted links. Neither mechanism is
identity authority by itself.

Five accepted links disagree on legal jurisdiction after comparable
country/subdivision normalization. These are field conflicts, not automatic
identity rejection, because their accepted identity evidence includes
independent address/name context; each must remain visible for stewardship.
The seven GLEIF `US` values against an SEC U.S. state are compatible broader
evidence, not conflicts.

Other-name comparison found nine entirely equal, five compatible mixtures of
shared and new names, 27 names where current MDM has no former-name value, nine
different sets, and 258 accepted links with no GLEIF other name. Raw name type,
language, and source must be retained.

Address support is not an equality claim. SEC business/mailing addresses and
GLEIF legal/headquarters addresses have different meanings; 71 without shared
city/postal/street context remain parallel, not conflicting, evidence.

## Ranking for the first slice

1. Legal form and LEI registration/lifecycle status: universal lift and clear
   GLEIF authority.
2. Registration authority and authority-local entity ID: 92.9% coverage and
   useful future deterministic matching, with an explicit no-CIK rule.
3. Legal jurisdiction and distinct legal/headquarters addresses: high coverage
   with five jurisdiction conflicts requiring review.
4. Creation dates and typed legal events: useful temporal evidence that must not
   be flattened into current SEC fields.
5. Other names and successor LEIs: lower coverage but important for candidate
   recall and retirement/merge handling.
6. Mapping identifiers: not present in the canonical Level 1 source grain used
   here; ingest only through the separately governed mapping feeds in Ticket 11.

## Reproducibility

The extractor scanned all 3,428,477 fixed Level 1 records and retained 316
records touching an accepted LEI; this includes 308 records whose own LEI is
accepted plus eight records that reference an accepted LEI elsewhere. The
retained artifact SHA-256 is
`a8372f23f6cd4be322839327145357f501c998637ae72b96c3dc34275fa51cf2`.

[`03-analyze-attribute-lift.py`](03-analyze-attribute-lift.py) joins only the
308 own-LEI records to the accepted entity/LEI pairs and writes one comparison
row per accepted link. The comparison SHA-256 is
`06ba42f1c65a416047d0831f996e217c2cb6f2ae4ad8f62c1833355e9dad2e8a`;
the machine-readable aggregate is
[`03-attribute-lift-summary.json`](03-attribute-lift-summary.json).

## Specification consequence

Proceeding is justified only as a bounded, review-gated tracer bullet. Preserve
the complete Level 1 source record. Project selected attributes only after an
accepted identity link, with observed/effective validity and explicit conflict
states. Never let a GLEIF legal-entity field overwrite SEC filings, reported
financial facts, CIK, or SEC source evidence.
