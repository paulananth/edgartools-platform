# SEC Company classification proof, frozen rule 2026-09-24.7

Ticket 12. Run 2026-09-24, 21:11–21:20 ET. Local bronze summary only; no
SEC, S3, or other network request. The input held 76,230 CIKs and has SHA-256
`395b7db4cfeb5ab0d4816ee4c0e68ca078b548fce3b8337c0ab671f0e0668600`.

## Decision

**Do not activate `sec-company-candidate`.** Each Company step must clear the
accepted 0.95 precision bar at 95% one-sided confidence. Step 4 does not.
The independent adversarial fixture also contains 33 non-Companies that the
rule calls Company. The earlier 2026-09-24.6 pooled result and digest
`b26ab87c…` were withdrawn. There is no current operator approval.

| Company step | Confirmed Company | Drawn | One-sided 95% Wilson lower bound | Bar |
| --- | ---: | ---: | ---: | ---: |
| 2: `operating` | 297 | 300 | 0.97524 | clears 0.95 |
| 4: `other` plus industry code and company word | 258 | 300 | **0.82382** | **fails 0.95** |

Step 4's 42 unconfirmed cases are seven clearly named Funds and 35 serial
Masterworks LLC issuers with 1-A/1-K investment offering filings. The summary
does not establish that those 35 are Companies rather than investment vehicles;
they are recorded as `unsure` and counted against a proof of Company precision.
Even treating all 35 as Companies would leave the 33 adversarial violations.
Step 2's three exceptions are two Funds and a liquidation trust.

## Method and hand labels

The local `12-classify.py` runs the actual rule with seed `20260924.7`, then
draws 300 separately from each Company step. It also selects four adversarial
arms without using the rule's legal-form name test: all 97 ownership-only
`other` filers with an industry code, all 187 `other` plus industry-code names
that mention another kind, 100 ownership-only filers without an industry code,
and 100 SEC `investment` filers. Overlap gives 483 distinct records.

I read the drawn names and form sets. `12-label-reviewed.py` records the
adjudications, including GOULD INVESTORS L P (Company partnership), LOWENSTEIN
SANDLER LLP (Company partnership), Telephone & Data Systems voting trust
(Trust), and HOLDING FRANK B JR (person). Every adversarial record has a
`final` label and `note`. Every fund-, trust-, and partnership-looking sampled
name has a hand-read note. Draft labels rely on forms, tickers and categories
before names; the final labels and uncertain calls are in `12-sample.jsonl`.
The labels are local judgments based on the summary, not an external registry.

The adversarial fixture has **33 violations among 483**: 33 records labeled
Fund or Trust are called Company. The named non-Company arm deliberately
includes some real Companies; those are labeled Company and do not count as
violations. This avoids assuming the arm's premise is its true label.

Across the population, version .7 calls 8,249 Company (5,980 at step 2,
2,269 at step 4) and defers 67,981. Shell and ASML still reach step 4, but
the standard policy holds their records in the Stage. Apple and Microsoft
also wait because the whole rule remains inactive. Tim Cook and Satya Nadella
remain deferred.

`12-summary.json` records exact per-step counts and SHA-256s of the sampled
labels, adversarial labels, population metadata, classifier script, and label
review script. `company_source.PROOF.cohort.files` pins those hashes. The
test re-hashes all five files. `approved_at` is absent and `automatic_rules`
is empty.

This proves neither SEC-to-GLEIF matching nor publication into a master
record. A rule revision and a fresh independent draw are needed before
requesting approval of a new exact policy digest.
