# Extend the 8-K Tier B labelling to the 97.5% sample size

Type: research
Status: open
Blocked by: none (17 resolved, 20 decided the bar 2026-09-20)

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
