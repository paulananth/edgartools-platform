# Ticket 02 exhaustive identity comparison

Date: 2026-09-12 America/New_York
Mode: fixed local GLEIF corpus and frozen MDM cohort; no network or production
write operations.

## Result

The exhaustive scan found at least one GLEIF candidate for 498 of the 1,000
frozen companies. Review of all 883 candidate pairs produced 308 companies
with exactly one accepted LEI and no unresolved competing candidate. Another
103 companies had candidates that were all rejected, 87 remain unresolved,
and 502 had no candidate under the declared rules.

These are cohort results, not population estimates. The 1,000 rows were a
fixed, deliberately stratified sample rather than a simple random sample.
Wilson 95% intervals in `02-identity-summary.json` describe the selected
strata only.

| Company disposition | Count | Cohort rate |
| --- | ---: | ---: |
| Accepted same legal entity | 308 | 30.8% |
| Rejected different legal entity | 103 | 10.3% |
| Unresolved | 87 | 8.7% |
| No candidate | 502 | 50.2% |

The 883 manually reviewed candidate pairs were classified as 316 same legal
entity, 480 different legal entity, and 87 unresolved. Eight accepted
candidate pairs do not become accepted company links because another candidate
for the same company remains unresolved. No LEI is accepted for more than one
company and no duplicate company/LEI pair exists.

## Evidence-tier result

| Candidate tier | Reviewed | Accepted | Adjudicated acceptance rate | Wilson 95% interval |
| --- | ---: | ---: | ---: | ---: |
| B: strong multi-attribute review | 249 | 224 | 90.0% | 85.6%-93.1% |
| C: contextual manual review | 363 | 92 | 25.3% | 21.1%-30.1% |
| D: conflict or insufficient context | 271 | 0 | 0.0% | 0.0%-1.4% |

Tier B is useful candidate-generation evidence but is not sufficiently precise
to become unattended identity authority. Tier C requires review. Tier D must
not link identities. In particular, exact or fuzzy normalized name alone never
supports acceptance. A root audit changed three initially accepted Tier D
name-only candidates to unresolved before finalization.

## Method and retained evidence

The generator streamed all 3,428,477 records from the pinned GLEIF 2026-09-11
16:00 UTC Level 1 Golden Copy without extraction. Candidate generation used
current and former names, conservative legal-suffix normalization, and
address/jurisdiction context. It did not compare CIK with a GLEIF registration
authority value because no semantically proven shared identifier was present
in the frozen inputs.

Every candidate retains the raw and normalized compared fields, score
components, evidence tier, reason code, rank, manual disposition, and reviewer
reason. The complete candidate scan generated 883 ordered rows with SHA-256
`d9ed01dd3aeaf069bdf4bb60ce293798aa81ffb4873c778a9cc7ea4feb98e5c4`.
The comparison run ID is `a4dcce925d1e0fbc19abad03f6014f8f`.

Final artifact hashes are:

| Artifact | Rows | SHA-256 |
| --- | ---: | --- |
| `02-decisions.jsonl` | 883 | `c4df91d48d1b385af3fa9f103b6a43e166743f560ba5a6fab9784450f3292230` |
| `02-reviewed-candidates.jsonl` | 883 | `fad4f9359c775dc656fdb6f6bcd653187f8ddf3548f68e3001ebc9a233d4455b` |
| `02-cohort-dispositions.jsonl` | 1,000 | `d6684d9e0c9a4485d70ad047ced01c0b0dc8e814bc8ea398ea256fc9a2a50a53` |
| `02-identity-summary.json` | derived | `f72310658adc78c7dabe1c1bc6390c538a857c0897e9c480dc094cc6c84c4b5a` |

The parser includes a regression test for the Golden Copy's final `}]}` footer.
`uv run --with ruff ruff check 02-compare-gleif-identities.py` and
`uv run --with orjson --with rapidfuzz python
02-compare-gleif-identities.py --self-test` pass. A complete second Level 1
scan reproduced the ordered candidate hash; finalization from the fixed,
complete decision ledger reproduced the reviewed rows, company dispositions,
and aggregate summary hashes.

## Consequence for the specification

The first implementation must not auto-link a new LEI from these heuristic
tiers. It may load explicitly approved links as source-grained evidence and
produce review candidates, but automatic acceptance needs a stronger,
independently verified identifier or a substantially stricter rule whose
measured lower confidence bound meets an explicit release threshold. A
no-candidate result is not a claim that the company has no LEI.
