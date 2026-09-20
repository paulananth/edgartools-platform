# Calibrate the Person Tier B compound context key on a held-out sample

Type: research
Status: resolved 2026-09-20
Blocked by: none (03 resolved 2026-09-20)

## Question

Ticket 02 lets Tier B — same issuer/firm CIK + exact normalized name +
consistent role/flag — auto-merge once a held-out calibration proves
≥ 99% precision (one-sided 95% lower confidence bound, Clean MDM's own
method). No Snowflake: build the study from data the platform can reach
offline — the ADV `IA_Schedule_A_B` archive (research 16's
IAPD-corroborated `OwnerID` persons are a truth source for "same person
at the same firm") and the S3 export snapshots of 8-K events, plus a
frozen sample of Form 4 XML from bronze if reporting owners are needed.
Independently label at least 400 candidate pairs, including homonyms at
the same firm, reused ids, and transitive bridges (Clean MDM's stated
validation cases). Report precision with its lower bound, candidate
recall, and expected review volume. Blocked on ticket 03 because the
person-vs-entity classification decides which reporting-owner rows are
even eligible.

## Answer

**The key clears 99% only where it has nothing to do, and fails where Tier B
actually fires.** 921 independently labelled pairs (696 same / 160 different /
65 unknown), 207 IAPD requests, all 200.

- **ADV Schedule A/B** — 99.7% of rows carry an `OwnerID`, so Tier A binds
  first and Tier B only sees the residual: two records, one firm, same
  normalized name, different ids. Census of 155 such pairs; at the strictest
  normalizer 55 match, of which **1 same / 27 different / 27 unsettled**
  (0.018, LCB95 0.004; optimistic 0.509, LCB95 0.400). Same-firm namesakes are
  fathers, sons and duplicate CRD records, not one person filed twice.
  27 hard-veto violations, not the zero Q11 requires.
- **Form 3/4/5** — population 9,332/9,332 (LCB95 0.99971), but vacuous: the
  residual at the strict key is **empty** (no two owner CIKs at one issuer
  share a full name); the 11 loosest-variant pairs are 10 `different`.
- **8-K Item 5.02** — the real home. Pooled 277 pairs at the `mi` variant,
  **zero contradictions**, LCB95 **0.99033** (clears) / LCB97.5 0.98632
  (fails, needs n >= 381). Conservative reading 0.9711, LCB95 0.9495.
- **DEF 14A** — 58.7% of rows are not person names; not eligible until ticket 10.
- Recall 99.6-99.8%; review 0.2-15.3 records per 1,000 to Tier C.
- Hard cases: homonyms are the failure mode (above); **zero reused ids** in
  either corpus (84 id-split pairs, all one person); **no transitive bridge can
  exist** under an exact-equality key (no group holds 3 distinct keys) - 42 of
  48 chains at the Tier C comparator are false.
- Variant: **`mi`** (surname + given + middle initial), suffix as a **hard
  veto**, role dropped from the key (buys nothing, costs 33 true pairs).

Contradicts ticket 02 §4: Tier B's stated scope (ids unbound) almost never
occurs on the id-bearing sources, and its "consistent role/flag" element is
inert. Findings: [research/17](../research/17-tier-b-context-key-calibration.md).
