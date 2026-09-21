# Extend the 8-K Tier B labelling to the 97.5% sample size

Type: research
Status: resolved 2026-09-20

## Answer

**Activate Tier B for 8-K Item 5.02 at ticket 20's fixed key.**
[Research 21](../research/21-tier-b-8k-extended-labelling.md) took the **census** research 17
sampled — all 216 within-8-K groups, all 721 8-K rows with a Form 3/4/5 anchor, 938 candidate
pairs, **661 matching the fixed key**; **658 `same`, 0 `different`, 1 `unknown`, 2 `ineligible`**
(not person names). Eligible **n = 659**, `n/(n+z²)` at z = 1.96:

| reading | precision | LCB95 | **LCB97.5** | clears? |
|---|---|---|---|---|
| optimistic (unsettled = same) | 1.00000 | 0.99591 | **0.99420** | yes |
| conservative (unsettled = error) | 0.99848 | 0.99323 | **0.99146** | yes |
| settled only, n = 658 | 1.00000 | 0.99591 | **0.99420** | yes |
| *research 17's rules alone, conservative* | *0.94251* | *0.92574* | *0.92208* | *no* |

**Two caveats.** (1) The conservative row holds only with research 21's settling rules — they
settle 37 of 38 unknowns, 21 on a date anchor, 16 on ticket 20 Q3's own position that role is
evidence never key; settled and optimistic clear either way. (2) **All four non-`same` labels in
the census sit inside research 17's original 281**, and the only surviving route to a non-`same`
label fires on 1 of 721 rows (0.14%): the discriminating stratum is exhausted and the binding
constraint is now the method's power, not n — more labelling will not move it.

5 of research 17's 6 unsettled 8-K pairs are settled (4 `same`, 1 `ineligible`); Inogen's
`Kevin P. Smith` stays `unknown`, separable only by the middle initial, i.e. the key. On Form
3/4/5's 11 same-issuer homonym CIK pairs, which `owner_cik` labels outright, plain `mi` merges
**7**, the fixed key **1**, and **the suffix veto prevents 6** — ticket 20 Q3 confirmed by
measurement, its one false merge the Zegna brothers' four-token surname defeating the parse.
Ships alongside, none touching the key: repair that parse (0 of 11), add `DATE`/`BANK` to the
eligibility vocabulary, drop `V` from the suffix tokens. Recall **0.7045**, review **15.26/1,000**
eligible records — the dominant 8-K effect is ~30% coverage loss, not precision risk. Nothing
contradicts ticket 20; the issuer component is a raw CIK only because MDM ids do not exist yet.

## Question

[Ticket 20](20-redecide-tier-b-after-calibration.md) set Tier B's bar at
≥ 99% precision on a **one-sided 97.5%** Wilson lower bound, measured on
**8-K Item 5.02 only** (DEF 14A is excluded until ticket 10 lands).
[Research 17](../research/17-tier-b-context-key-calibration.md) labelled
223 8-K pairs at the `mi` variant with zero contradictions — LCB95
0.98801, LCB97.5 0.98307. Clearing 99% at 97.5% needs **n ≥ 381**.

The pairs exist offline: 721 8-K rows have a same-issuer Form 3/4/5
anchor; only 213 were labelled. Extend the labelled set to at least 381
8-K pairs under research 17's own method and re-score.

Specifics, all fixed by ticket 20 so this study does not re-open them:

- **The key is fixed**: same MDM-resolved issuer identity + surname,
  given name and middle initial (`mi`; an initial matches a middle name,
  absent-on-both matches) + **no generational-suffix conflict**
  (suffix on one side only is a conflict). Role and flags are evidence,
  never key. Score this key; report the other variants only as context.
- **Settle the 8 unsettled pairs** research 17 could not, or state per
  pair why not. The optimistic reading currently carries the result; a
  conservative reading falls to LCB95 0.9495.
- Label independently of the key, as research 17 did, and keep its JSONL
  fields (`pair_id`, `source`, `key_fields`, `label`, `evidence`,
  `labeler_rule`).
- Report precision with LCB95 **and** LCB97.5, candidate recall, review
  volume per 1,000 8-K records, and the homonym/reused-id/bridge strata
  separately.
- Offline only: the S3 export snapshots and bronze research 17 used; IAPD
  under the same fair-access cap (UA from `EDGAR_IDENTITY`, ≤ 1 req/s,
  stop on 403/429, cap 300, every request logged); **zero SEC EDGAR
  requests**.

Resolved when 8-K's LCB97.5 is measured on n ≥ 381 and the verdict —
activate Tier B for 8-K, or not — is stated with its arithmetic.
