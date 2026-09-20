# Calibrating the Tier B compound context key (firm/issuer + normalized name + role)

Ticket: [17](../issues/17-calibrate-person-tier-b-context-key.md). Run 2026-09-20 (ET).
Offline: two ADV FOIA archives, the Form 3/4/5 bronze corpora of research 07/18, and the two
S3 source-layer export snapshots of research 01. **Zero SEC EDGAR requests.** 207 IAPD requests,
all HTTP 200, logged line-by-line in `17-iapd-requests.jsonl`. Labels are **my own reading** of
identifiers, IAPD registration records, `Status Acquired`, flags/titles and event timelines; every
pair I could not settle is labelled `unknown` and reported separately, never folded into `same`.

## Verdict

**The compound key as ticket 02 defines it does not clear 99% at a one-sided 95% Wilson lower
bound for the source it was written for, and clears it for the sources it was not.** Split by what
Tier B actually decides: on **ADV Schedule A/B** and **Form 3/4/5**, every record carries a
cross-reference id (`OwnerID` 99.7%, `owner_cik` 100%), so Tier A binds first and Tier B only ever
sees the *residual* — two records at one firm/issuer with the same normalized name and **different
ids**. That residual is not a near-miss, it is inverted: 55 such ADV id-pairs at the strictest
normalizer, of which **1 same / 27 different / 27 unsettled** (precision 0.018, LCB95 0.004; even
counting every unsettled pair as `same` the upper reading is 0.509, LCB95 0.400). Same-firm
identical names are overwhelmingly *fathers and sons and duplicate CRD records that IAPD shows as
two registration histories*, not one person filed twice. On Form 3/4/5 the residual at the
strictest variant is **empty** (0 pairs: no two CIKs at one issuer share a full normalized name),
and at the loosest it is 11 pairs, 10 of them `different`. So for both id-bearing sources the
honest answer is that Tier B has no population to serve: what it would auto-merge is precisely the
set Tier A already covers, and what is left over belongs in Tier C. Where the key *does* work is
the **name-only** sources it was written as a fallback for: pooled over 8-K Item 5.02 and DEF 14A,
**277 independently labelled pairs at the `mi` variant (surname + given name + middle *initial*,
suffix-insensitive) show zero contradictions** — precision 1.000 if the 8 unsettled pairs are
same, **LCB95 0.9903, which clears 99%**; the same figure at one-sided 97.5% is 0.9863, which does
**not** (n ≥ 381 error-free decisions are needed at that coverage, 268 at 95%). On the
conservative reading that counts all 8 unsettled pairs as errors, it is 0.9711, LCB95 0.9495 —
fails. Review volume is small either way (5.4–15.3 records per 1,000 fall to Tier C on 8-K/DEF
14A, 0.2–7.6 per 1,000 on the id-bearing sources) and candidate recall of the id-labelled pairs is
99.6–99.8%. **The one extra field that would settle it is not a field but a count**: the key's own
arithmetic needs 104 more labelled name-only pairs to reach 381 and clear 99% at the coverage
research 18 used. DEF 14A cannot supply them until ticket 10's parser fix lands (58.7% of its rows
are not person names at all).

## Sources read

Data (all offline; SHA-256 of every input in `17-summary.json.inputs`):

| Input | Rows used | sha256 (prefix) |
|---|---|---|
| `IA_Schedule_A_B_20260301_20260331.csv` (March 2026) | 68,642 `I` rows | `36375323…` |
| `IA_Schedule_A_B_20260801_20260831.csv` (August 2026) | 11,126 `I` rows | `fe4fc0cb…` |
| `IA_ADV_Base_A_*` (both months) | 15,027 + 2,386 filings, joined for `1E1` firm CRD | `34b9a7ba…` / `ed098484…` |
| `r07/07-union-corpus.jsonl` (research 07's Form 3/4/5 union) | 104,970 owner rows, 72,981 C-J `person` | `9daf08fb…` |
| `sec_employment_event.parquet` (8-K Item 5.02, research 01) | 7,878 | `8e21ed8d…` |
| `executive_record.parquet` (DEF 14A, research 01) | 14,755 | `b6b1c419…` |
| `IA_1D3_CIK_*` | 4,697 filing→CIK rows | in `17-census.json` |

IAPD (`https://api.adviserinfo.sec.gov/search/individual/<OwnerID>`, the endpoint research 16 F2
established as a strict id lookup): **207 requests, 207 × HTTP 200, zero 403, zero 429**, User-Agent
from `EDGAR_IDENTITY`, `time.sleep(1.0)` before each, hard cap 300 not reached; first
2026-09-20 18:38:07 ET, last 18:53:59 ET. 216 ids were resolved in total — 10 of them reused from
research 16's own `16-results.jsonl` rather than re-requested. 155 of 216 resolve.

Prior work this builds on and does not re-derive: research
[16](16-schedule-ab-ownerid-meaning.md) F1/F2/F5 (what `OwnerID` is, its duplicates, IAPD response
shape), [18](18-reporting-owner-classification-precision.md) (`norm_name`, `person_name_shape`,
rule C-J, the Wilson arithmetic), [07](../../mastering-policy-language/research/07-owner-cik-cardinality-and-deterministic-binding.md)
(`owner_cik` cardinality, the 42 multi-name CIKs, EDGAR Ownership XML spec §4.3.2), and
[01](01-name-only-source-overlap.md) F1/F2 (the proxy role-text defect, 8-K name cleanliness).

Method definition read at the source: Clean MDM's accepted Q11 — "at least 99.9% precision,
demonstrated by a one-sided 95% lower confidence bound on representative, independently labeled
held-out automatic-binding decisions for each enabled entity kind and rule family … Also require
zero hard-veto violations in adversarial fixtures; measure candidate recall and review volume"
(`docs/specs/clean-mdm/merge-stage.md:53-58`, proposed at
`.scratch/clean-mdm/issues/01-set-merge-stage-policy.md:135-142`); its named validation cases are
"homonyms, reused identifiers" and transitive bridges (`merge-stage.md:74`). The Person-kind bar is
**99%**, an operator amendment ([ticket 02 Answer](../issues/02-decide-what-binds-a-person.md) §4,
map "Operator directives" 2026-09-20). The 95%-vs-97.5% mismatch is the one flagged at
`docs/specs/mdm/policy-language.md:463` and
`.scratch/mastering-policy-language/research/02-rule-activation-and-proof.md:284-294`; both bounds
are reported below.

Sibling files (same directory):
`17-common.py` (normalizers, name parsers, role classes, Wilson), `17-build.py` (one record table
across four sources + the population census → `17-census.json`), `17-sample.py` (stratum
enumeration → pair drafts), `17-label.py` (the labelling rules → `17-pairs.jsonl`),
`17-score.py` (→ `17-summary.json`), `17-overrides.json` (my 8 hand overrides),
`17-iapd.py` / `17-iapd-requests.jsonl` / `17-iapd-results.jsonl`.

## Method

**The key under test.** `(context, normalized name, role)` where context = firm CRD (ADV
`IA_ADV_Base_A.1E1`) or issuer CIK (Form 3/4/5, 8-K, DEF 14A). Role is carried as a *consistency*
check, never as a key component, because it is absent or free text on most rows — its effect is
reported separately (F5). Four **normalizer variants**, all exact-equality keys built on research
18's `norm_name` (`18-classify.py:118-123`, unchanged), differing only in how much of the name they
require to match:

| variant | key | rationale |
|---|---|---|
| `full` | last ∥ first ∥ all middle names ∥ suffix | strictest; the literal reading of "exact normalized name" |
| `nosuffix` | last ∥ first ∥ all middle names | drops `JR`/`III`; the suffix-insensitive reading |
| `mi` | last ∥ first ∥ **first letter** of middle | the middle-initial case that killed deactivate-on-first in policy research 07 (`Kissner Matthew` vs `KISSNER MATTHEW S`, decision 3,107 of 72,981) |
| `fl` | last ∥ first | loosest; middle name ignored entirely |

Name parsing is per source format, since the three sources write names three different ways: ADV
`LAST, FIRST, MIDDLE` (also one-comma and suffix-as-segment forms, `parse_adv`), EDGAR conformed
`LAST FIRST MIDDLE` (`parse_edgar`), free-text `First Middle Last` with honorifics stripped
(`parse_western`). `NMN` ("no middle name", 1,079 ADV rows) is dropped in every variant. Eligibility
= research 18's `person_name_shape` plus, for the two free-text sources, research 01's
"no role vocabulary inside the name field" test.

**Labels are independent of the key.** No labelling rule reads whether the key matches; they read
cross-reference ids, IAPD registration histories, `Status Acquired`, flags/titles, event timelines,
and the middle-name/suffix *conflict* that the looser variants ignore. Each label carries its rule
id and its evidence string in `17-pairs.jsonl` (`pair_id, stratum, source, key_fields, match,
label, evidence, labeler_rule, draft_label, draft_rule`). Three labels: `same`, `different`,
`unknown` — and `unknown` is reported, never silently counted as either.

**Strata** (a pair is two records from different filings at the same firm/issuer). H, R and B are
**censuses**, not samples: every qualifying pair in the corpus is labelled.

| stratum | what it is | n | census? |
|---|---|---|---|
| **H** homonyms | same context, same `fl` key, **different** cross-ref id | 155 ADV + 11 F4 | yes |
| **R** reused ids | same context, same cross-ref id, **different** `full` key | 59 ADV + 25 F4 | yes |
| **B** bridges | every pair of distinct `full` keys inside a (context, surname+first-initial) group holding ≥ 3 of them | 42 ADV + 3 F4 + 3 proxy | yes |
| **P** positives | random same-context same-`full`-key pairs with an id on both sides | 160 ADV + 110 F4 | seed `20260920` |
| **K** 8-K within-source | same issuer, same `fl` key, two 8-K events on different dates | 140 | first 140 by hash |
| **X** cross-source | 8-K or DEF 14A row vs a Form 3/4/5 person owner at the same issuer, same `fl` key | 141 + 72 | 2+-CIK cases first, then by hash |

**921 labelled pairs** total (696 same / 160 different / 65 unknown), against the brief's ≥ 400.

**Labelling rules**, by stratum (full list with counts in `17-summary.json.strata.rules`):

- **P** — `L-P1`: shared cross-ref id ⇒ same (ticket 02 §2). Corroboration by an id-independent
  field is recorded where present (`Status Acquired` equal, flags equal, title class equal,
  `submissions.json` name equal) but is not required.
- **R** — same id, names differ: `L-R1` middle/initial/suffix/typo variant, `L-R2` nickname or
  ≤ 1-edit typo of the given name, `L-R3` surname change with the given name kept, `L-R4` token
  reorder ⇒ same; `L-R5` unexplained ⇒ unknown (this is the "reused id" alarm).
- **H/B** — different ids: `L-H1` conflicting middle names, `L-H2`/`L-H2b` conflicting generational
  suffix or a suffix on one side only, `L-H3` IAPD middle names conflict, `L-H7` both ids resolve on
  IAPD with a generational-suffix conflict in their own names/`otherNames` or with registration at
  the filing firm beginning > 365 days apart ⇒ different; `L-H8` both resolve with an identical firm
  set and a start within 31 days ⇒ same; `L-B1` given names differ ⇒ different; `L-H5`/`L-H6`
  otherwise ⇒ unknown.
- **K** (8-K vs 8-K) — `L-K1` exactly one Form 3/4/5 CIK carries that name at that issuer ⇒ same
  (an external anchor); `L-K3` two CIKs do ⇒ unknown; without an anchor, timeline coherence:
  `L-K5` appointment-then-departure, `L-K6` repeated appointments of one role, `L-K7` officer↔board
  role change across two appointments, `L-K8` repeated departures / departure-then-reappointment ⇒
  same; anything else ⇒ unknown.
- **X** (8-K or DEF 14A vs Form 3/4/5) — `L-X1` role agrees **and** the 8-K appointment date is
  within 45 days of the first Form 3/4/5 period ⇒ same; `L-X2` role agrees and the Form 3/4/5
  filing window does not contradict the event timeline ⇒ same; `L-X3` timeline contradiction
  (> 400 days), `L-X4` two CIKs carry the name at the issuer, `L-X5` role disagreement ⇒ unknown.

I overrode 8 draft labels by hand (`17-overrides.json`), each with its reason: the
MARINICH duplicate-vs-II pair research 16 left open (→ unknown), the two `L-R5` alarms settled by a
fresh IAPD lookup and by research 07's name-variant class, the `Zegna di Monte Rubello`
multi-word-surname parse artifact, the `Matthew (Matt) Furlong` nickname triple, and
`Effective Date` (a parser artifact the role-text filter missed).

**Two precision framings**, because they answer different questions:

- **population** — P(same person | two records share context + key). Unit: the multi-record
  (context, key) group in the whole corpus. A group is impure if any labelled id-pair inside it is
  `different`. This is what Tier B faces on a source with no cross-reference id, and what the key
  delivers *before* Tier A.
- **residual** — P(same person | key matches **and** the cross-ref ids differ). Unit: the labelled
  id-pair (stratum H). **This is the population Tier B actually decides on** for ADV and Form 3/4/5,
  because Tier A has already bound every shared id (ticket 02 §2, §4).

**Wilson arithmetic, shown once.** For k successes in n, `p̂ = k/n`, and

  LCB = ( p̂ + z²/2n − z·√( p̂(1−p̂)/n + z²/4n² ) ) / ( 1 + z²/n )

with z = 1.6448536 (one-sided 95%, Clean MDM's accepted coverage) and z = 1.9599640 (one-sided
97.5%, research 18's constant). Worked on the headline cell — name-only pooled at `mi`, k = 277,
n = 277: p̂ = 1, z² = 2.70554, LCB = (1 + 2.70554/554 − 1.6449·√(0 + 2.70554/306916)) /
(1 + 2.70554/277) = (1.004884 − 0.004884)/1.009767 = **0.99033**. At z = 1.96 the same cell is
277/(277 + 3.8416) = **0.98632**. Zero-error sample sizes for a 0.99 bound: **n ≥ 268** at 95%,
**n ≥ 381** at 97.5% (one error needs 446 / 563).

## Results

### F1 — Eligible population, per source

| source | records | person-shaped & eligible | not eligible /1,000 | contexts | records with a cross-ref id | distinct ids |
|---|---|---|---|---|---|---|
| ADV Schedule A/B `I` rows (2 months) | 79,768 | 79,766 | 0.03 | 13,856 firm CRDs | 79,543 (99.72%) | 47,394 |
| Form 3/4/5 reporting owners, C-J `person` | 72,981 | 72,980 | 0.01 | 4,010 issuer CIKs | 72,981 (100%) | 14,566 |
| 8-K Item 5.02 | 7,878 | **4,193** | **467.8** | 1,742 issuer CIKs | 0 | 0 |
| DEF 14A executive records | 14,755 | **6,091** | **587.2** | 903 issuer CIKs | 0 | 0 |

The two id-bearing sources are essentially fully eligible. The two name-only sources lose 47% and
59% of rows before any key is applied — 8-K to role phrases and non-names the parser writes into
`person_name` (`Compensatory Arrangement`, `Corporate Governance Committees`, `Effective Date`),
DEF 14A to ticket 10's documented 47% role-text leak plus single-token and honorific-only rows.
**DEF 14A is reported throughout but is not eligible for any tier until ticket 10 lands.**

### F2 — The key, per source and variant

`decisions` = records that would be auto-bound to an existing record by this key (records in
multi-record groups minus one survivor per group) — the denominator a runtime tolerance counts.
`review/1k` = records per 1,000 eligible that a Tier C comparator (surname + first initial) raises
as a candidate but the Tier B key does **not** match, i.e. that fall to Steward review.
`recall` = of (context, id) groups whose records are known-same by the id, the fraction the key
keeps in one group.

**Population framing** (P(same | context + key), unit = group):

| source | variant | groups | decisions | precision (pess.) | LCB95 | LCB97.5 | precision (opt.) | LCB95 (opt.) | recall | review /1k |
|---|---|---|---|---|---|---|---|---|---|---|
| ADV | full | 16,641 | 25,324 | 0.99676 | 0.99594 | 0.99577 | 0.99838 | 0.99750 | 0.99645 | 7.60 |
| ADV | nosuffix | 16,646 | 25,336 | 0.99610 | 0.99522 | 0.99503 | 0.99772 | 0.99675 | 0.99651 | 7.38 |
| ADV | mi | 16,666 | 25,376 | 0.99460 | 0.99358 | 0.99337 | 0.99694 | 0.99615 | 0.99735 | 6.63 |
| ADV | fl | 16,705 | 25,476 | 0.99078 | 0.98948 | 0.98921 | 0.99377 | 0.99269 | 0.99952 | 4.89 |
| Form 3/4/5 | full | 9,332 | 56,304 | **1.00000** | **0.99971** | **0.99959** | 1.00000 | 0.99971 | 0.99732 | 0.41 |
| Form 3/4/5 | nosuffix | 9,329 | 56,311 | 0.99936 | 0.99876 | 0.99860 | 0.99936 | 0.99876 | 0.99743 | 0.36 |
| Form 3/4/5 | mi | 9,326 | 56,314 | 0.99925 | 0.99862 | 0.99845 | 0.99936 | 0.99876 | 0.99764 | 0.36 |
| Form 3/4/5 | fl | 9,324 | 56,325 | 0.99882 | 0.99807 | 0.99789 | 0.99903 | 0.99834 | 0.99839 | 0.23 |

Read this table with F3 and the Limits: a group holding one id is pure *by that id*, which is a
strong label (research 07: 0 of 72,981 `owner_cik` binding decisions were a true violation; research
16: `OwnerID` stable 5,322/5,322 month to month) but not an independent one. The honest number for
the decision Tier B makes is F3.

**Residual framing** (P(same | key matches **and** ids differ), unit = labelled id-pair — Tier B's
real population on these two sources):

| source | variant | n | same | different | unknown | precision (pess.) | LCB95 | LCB97.5 | precision (opt.) | LCB95 (opt.) |
|---|---|---|---|---|---|---|---|---|---|---|
| ADV | full | 55 | 1 | 27 | 27 | 0.01818 | 0.00407 | 0.00322 | 0.50909 | 0.40042 |
| ADV | nosuffix | 66 | 1 | 38 | 27 | 0.01515 | 0.00339 | 0.00268 | 0.42424 | 0.32911 |
| ADV | mi | 91 | 1 | 51 | 39 | 0.01099 | 0.00246 | 0.00194 | 0.43956 | 0.35695 |
| ADV | fl | 155 | 1 | 104 | 50 | 0.00645 | 0.00144 | 0.00114 | 0.32903 | 0.27035 |
| Form 3/4/5 | full | **0** | — | — | — | — | — | — | — | — |
| Form 3/4/5 | nosuffix | 6 | 0 | 6 | 0 | 0.00000 | 0.0 | 0.0 | 0.00000 | 0.0 |
| Form 3/4/5 | mi | 7 | 0 | 6 | 1 | 0.00000 | 0.0 | 0.0 | 0.14286 | 0.03254 |
| Form 3/4/5 | fl | 11 | 0 | 9 | 2 | 0.00000 | 0.0 | 0.0 | 0.18182 | 0.06212 |

**Name-only sources** (no id at all, so population and residual coincide; `within` = two 8-K events,
`cross` = the source row against a Form 3/4/5 person owner at the same issuer):

| source | variant | n | same | different | unknown | precision (pess.) | LCB95 | LCB97.5 | precision (opt.) | LCB95 (opt.) | review /1k |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 8-K, within | full | 123 | 121 | 0 | 2 | 0.98374 | 0.95205 | 0.94265 | 1.00000 | 0.97848 | 15.26 |
| 8-K, cross vs F4 | full | 85 | 81 | 0 | 4 | 0.95294 | 0.89924 | 0.88516 | 1.00000 | 0.96915 | — |
| 8-K, pooled | full | 208 | 202 | 0 | 6 | 0.97115 | 0.94520 | 0.93851 | 1.00000 | 0.98716 | 15.26 |
| 8-K, pooled | mi | 223 | 217 | 0 | 6 | 0.97309 | 0.94882 | 0.94255 | 1.00000 | 0.98801 | 15.03 |
| 8-K, pooled | fl | 281 | 270 | **1** | 10 | 0.96085 | 0.93702 | 0.93127 | 0.99644 | 0.98421 | 5.01 |
| DEF 14A, cross vs F4 | full | 51 | 50 | 0 | 1 | 0.98039 | 0.91677 | 0.89695 | 1.00000 | 0.94962 | 6.40 |
| DEF 14A, cross vs F4 | mi | 54 | 52 | 0 | 2 | 0.96296 | 0.89408 | 0.87465 | 1.00000 | 0.95229 | 5.42 |
| DEF 14A, cross vs F4 | fl | 72 | 67 | **3** | 2 | 0.93056 | 0.86413 | 0.84752 | 0.95833 | 0.90024 | 3.12 |
| **name-only pooled** | full | 259 | 252 | **0** | 7 | 0.97297 | 0.95089 | — | 1.00000 | **0.98966** | — |
| **name-only pooled** | **mi** | **277** | **269** | **0** | 8 | 0.97112 | 0.94947 | — | 1.00000 | **0.99033** | — |
| name-only pooled | fl | 353 | 337 | 4 | 12 | 0.95467 | 0.93275 | — | 0.98867 | 0.97500 | — |

**`mi` pooled is the only cell in this study that clears the 99% bar at one-sided 95% (0.99033)**,
and it does so on the optimistic reading (the 8 unsettled pairs counted as same). Its 97.5% figure
is 0.98632 — short, purely for want of 104 more labelled pairs. The first *contradiction* appears
only at `fl`: 4 `different` pairs, three of them at one issuer (F4 below).

### F3 — Hard case 1: homonyms at the same firm/issuer

This is the stratum the whole question turns on, and it is a **census**: all 155 ADV and all 11
Form 3/4/5 same-context same-surname-and-given-name pairs carrying two different ids.

| | ADV (155 pairs) | Form 3/4/5 (11 pairs) |
|---|---|---|
| also match under `full` | 55 | **0** |
| also match under `nosuffix` | 66 | 6 |
| also match under `mi` | 91 | 7 |
| labelled `different` | 104 | 10 |
| labelled `same` | 1 | 0 |
| labelled `unknown` | 50 | 1 |
| settled by IAPD evidence | 36 | — (no IAPD for CIKs) |

The ADV rule breakdown: 58 pairs have conflicting middle names, 11 a conflicting or one-sided
generational suffix, **35 resolve on IAPD as two separately-registered individuals** (a suffix
conflict inside their own IAPD names/`otherNames`, or registration at the filing firm beginning more
than a year apart), 1 is a duplicate CRD record with one registration history, and 49 cannot be
settled from any public source. Worked examples from `17-pairs.jsonl`:

- `CRAWFORD, JOHN, HANNON` × 2 at CRD 110271 — **identical** name, identical `Status Acquired`
  month, identical two-firm history, identical registration start. IAPD `otherNames` separate them:
  `JOHN H CRAWFORD III` and `JOHN H CRAWFORD IV`. Father and son.
- `HOISINGTON, VAN, ROBERT` × 2 at 107710 — identical names and titles both naming trusts;
  `otherNames` on one side carries `VAN ROBERT HOISINGTON JR.`, registrations 2,044 days apart.
- `RICE, WILLIAM, PHIPPS` × 2 at 105540 — identical IAPD names, but one holds a 1992 registration
  at a predecessor firm the other never had, and their filing-firm registrations begin 8,402 days
  apart.
- `FRUGE, DON, L.` × 2 at 141024/149447 — identical IAPD names, identical two-firm set, identical
  registration start date: the single `L-H8` duplicate-CRD-record pair in the corpus.
- `MARINICH, DENNIS, PAUL` × 2 — research 16 F5.4's flagship "probable duplicate". Both resolve,
  four shared firms; but 2940858 carries `DENNY MARINICH II` in `otherNames` and two extra firms.
  I left it `unknown`: the same evidence reads as duplicate *or* as son.

The Form 3/4/5 side is cleaner and more decisive: **no two owner CIKs at one issuer share a full
normalized name at all.** The 11 pairs that share surname+given name are 5 father/son suffix pairs
(`FLORSHEIM THOMAS W JR` / `THOMAS W`; `DILLARD WILLIAM T II` / `III`; Abernethy, White, Stetz,
Romney), 3 middle-name conflicts (`Smith Kevin Raymond Merrill` / `Smith Kevin P.` — both officers
of Inogen; `KWOK YIU WAH` / `Kwok Yiu Keung`; `Gebbia John M.` / `John J`), 1 `Baqar Hassan` /
`Baqar Hassan Sajjad` CEO-vs-CFO pair left unknown, and 1 parse artifact
(`Zegna di Monte Rubello Edoardo` / `Angelo`, two brothers whose multi-word surname defeats the
EDGAR `LAST FIRST` parse). **Zero of 11 are one person.**

Adversarial-fixture reading, per Q11's "zero hard-veto violations": at `full`, the ADV key would
auto-merge 55 id-pairs of which 27 are demonstrably two people and only 1 is demonstrably one —
**27 hard-veto violations**, not zero. At `mi` it is 51. Form 3/4/5 at `full` has zero violations
because it has zero decisions.

### F4 — Hard case 2: reused identifiers

Also a census: every (context, id) group whose records carry more than one `full` key — 59 ADV and
25 Form 3/4/5, i.e. the places where one id is attached to two spellings.

| | ADV | Form 3/4/5 |
|---|---|---|
| id-split pairs | 59 | 25 |
| labelled `same` | 59 | 25 |
| labelled `different` (a genuinely reused id) | **0** | **0** |
| captured by `full` / `nosuffix` / `mi` / `fl` | 0 / 1 / 15 / 51 | 0 / 1 / 3 / 10 |

Rule mix: 48 + 10 middle/initial/suffix variants, 5 + 6 surname changes with the given name kept
(`BRENNER, MEGAN, MARIE` → `JEWETT, MEGAN, MARIE`; `Gottung Lizanne C` → `Bruce Lizanne M`), 4 + 4
nicknames or ≤ 1-edit typos (`Corrreia` → `Correia`; `Karlin Dan` → `Daniel`), 1 + 4 token
reorders (`GIBSON C SCOTT` / `GIBSON SCOTT C`). Two cases initially resisted and were resolved by
hand: ADV `8234676` carries both `BINDERT, LAURA, KAY` (March) and `BINDERT, PAULA, KAY` (August) —
a fresh IAPD lookup resolves that id to a single `PAULA KAY BINDERT` registered at the filing firm
from 2026-04-16, so March is a typo on one record, not two people; and F4 CIK `1816838`
(`Owen Adams Catherine` / `Owen Catherine E.`) is research 07's "name variant" class. **No reused
identifier exists in either corpus** — consistent with research 07's finding that a filer cannot set
the owner name on a Form 3/4/5 at all (EDGAR Ownership XML Technical Specification v5.1 §4.3.2) and
with research 16's 5,322/5,322 month-to-month `OwnerID` stability.

The consequence for the key runs the opposite way to the homonym case: these 84 pairs are the
recall cost of strictness. The `full` variant captures **0 of 84**; `mi` captures 18; `fl` captures
61. That is the whole of the recall column in F2 — and it is the middle-initial case policy research
07 named: `full` splits `Kissner Matthew` from `KISSNER MATTHEW S` and sends a known-same pair to
Tier C.

### F5 — Hard case 3: transitive bridges

**No transitive bridge exists under any variant of this key, and the reason is structural, not
lucky.** Every variant is an exact-equality key, so "shares a key with" is an equivalence relation
by construction — A~B and B~C forces A~C. A bridge can only arise if a *third* key value sits
between two others, which requires a (context, surname, given name) group holding three distinct
`full` keys. Measured across all four sources: **zero such groups.** The largest is two
(162 ADV, 21 F4, 25 8-K, 30 proxy).

Bridges were therefore constructed one comparator looser, at the Tier C candidate generator
(surname + first initial), where 42 ADV, 3 F4 and 3 proxy groups do hold ≥ 3 distinct `full` keys —
48 pairs in total. Of these, **39 ADV + 3 F4 are `different`, 2 ADV unknown, 1 ADV + 3 proxy
`same`.** They are family clusters at family firms, exactly the shape a fuzzy matcher would chain:
`Sit, Raymond Eugene` / `Robert W` / `Roger J` / `Ronald D.` at one adviser (4 ids);
`HUNT, JAMES CHRISTOPHER` / `JASON MICHAEL` / `JOSHUA WILLIAM`;
`PETREDIS, CHARLES JOHN` / `CHARLES WILLIAM` / `CHRISTIAN SAVA`;
`DeSantis Damon` / `Dean` / `Deborah` at one issuer. The three `same` pairs are all one DEF 14A
issuer rendering one CEO three ways (`Matthew (Matt) Furlong` / `Matthew Furlong` / `Matt Furlong`).
**Reading: the exact key is immune to bridging by construction; the risk lives entirely in the Tier
C comparator that would replace it, and at that comparator 42 of 48 chains are false.**

### F6 — The role element contributes nothing measurable

Role consistency (EXEC / GOVERNANCE / OWNER_ONLY, intersecting where both sides are known) across
all key-matching labelled pairs, at `full`:

| source | consistent, same | consistent, different | inconsistent, same | inconsistent, different |
|---|---|---|---|---|
| ADV | 160 | 17 | 1 | 10 |
| Form 3/4/5 | 109 | 0 | 1 | 0 |
| 8-K | 170 | 0 | 32 | 0 |
| DEF 14A | 50 | 0 | 0 | 0 |

Requiring role consistency would reject 33 pairs that are the same person (the CEO who is also a
director, the officer later seated on the board) and catch 10 ADV pairs that are two people — all
10 of which `L-H1`/`L-H2` already catch on the name. This is research 18 F7's finding repeated in a
new setting: the relationship/role element buys no precision and costs recall. **Role belongs in
the evidence record, not in the key.**

### F7 — What Tier B would actually decide, per source

| source | records | Tier A covers | Tier B residual (full) | Tier B verdict |
|---|---|---|---|---|
| ADV Schedule A/B | 79,768 | 99.72% (has `OwnerID`) | 55 id-pairs | **fails** — 27 different, 1 same |
| Form 3/4/5 | 72,981 | 100% (has `owner_cik`) | 0 pairs | **nothing to decide** at `full` |
| 8-K Item 5.02 | 4,193 eligible | 0% | all of it (338 decisions) | **clears at 95% under `mi`, on the optimistic reading**; 0.9863 at 97.5% |
| DEF 14A | 6,091 eligible | 0% | all of it (3,069 decisions) | **not eligible** (ticket 10) |

A bridge between an ADV firm and an SEC issuer, which would let an ADV person meet a Form 3/4/5
person under one context, is essentially absent from this corpus: `IA_1D3_CIK` maps 4,697 filings to
3,981 distinct CIKs, of which **3** are issuer CIKs in the Form 3/4/5 corpus. The two id-bearing
sources do not meet.

## What this settles for ticket 17

1. **Per the brief's question — does the compound key clear 99% at a one-sided 95% Wilson LCB, per
   source, and under which variant?** Form 3/4/5: yes at `full` in the population framing
   (9,332/9,332, LCB95 0.99971) but the result is vacuous, since the residual Tier B decides is
   empty. ADV: no, and not marginally — 1 of 55 at `full`, LCB95 0.004. 8-K: yes at `mi`
   (277 pairs, 0 contradictions, LCB95 0.99033) on the reading that treats the 8 unsettled pairs as
   same; no at one-sided 97.5% (0.98632, needs n ≥ 381). DEF 14A: not eligible until ticket 10.
2. **The variant that wins is `mi`, not `full`** — surname + given name + middle *initial*,
   suffix-insensitive. `full` costs recall on all 84 known-same name-variant pairs (F4) and buys
   nothing on the name-only sources; `fl` is where the first contradictions appear (4 pairs, F2)
   and where the father/son clusters collapse (F3, F5). The middle *initial* is the line: it
   captures `MARTELLARO, DOMINIC CARL` / `DOMINIC C` and still separates `DAMASCO, GEORGE THOMAS`
   from `GEORGE T` only via IAPD, not via the key.
3. **Generational suffix must be a hard veto, not a normalization step.** 11 of the 166 homonym
   pairs are a father/son distinguished *only* by `JR`/`III`, and `nosuffix` — the reading of
   "exact normalized name" that drops suffixes — merges every one of them. Suffix present on one
   side and absent on the other is as strong a signal as a conflicting suffix (9 of those 11).
4. **The role/flag element should be dropped from the key** (F6) and kept as recorded evidence.
5. **The one extra field that would get 8-K over the 97.5% bar is more labelled pairs, not a new
   field**: 104 more, and they exist — 721 8-K rows and 626 DEF 14A rows have a same-issuer
   Form 3/4/5 anchor available, of which only 213 were labelled here.
6. **What contradicts ticket 02's Tier B definition.** Three things, in order of weight:
   - Tier B is defined as the fallback "for a record whose cross-ref ids are all unbound"
     (ticket 02 §4). On ADV and Form 3/4/5 that condition is almost never met — 99.7% and 100% of
     records carry an id — so the tier as scoped applies mostly to the two sources ticket 02 §6
     restricts hardest (8-K "Tier B/C only", proxy excluded). Its measured home is the opposite of
     its stated one.
   - Where Tier B *does* fire on an id-bearing source, it fires on the residual, and there it is
     wrong 27 times for each time it is right. Ticket 02 §2's "a second Person claiming a bound id
     is a hard veto" protects the id direction; nothing protects the *name* direction, which is
     where same-firm fathers, sons and duplicate CRD records live.
   - "Consistent role/flag" is in the key definition and earns nothing (F6); and "exact normalized
     name" is under-specified in exactly the place that decides the answer — whether `JR` is part
     of the name (it must be) and whether a middle initial matches a middle name (it should).

## Limits

- **The population framing's labels are only partly independent.** A (context, key) group holding a
  single cross-reference id is counted pure *by that id*. That id label is strong (research 07:
  0 true violations in 72,981 decisions, 95% upper bound 0.53 per 10,000; research 16: 5,322/5,322
  stable) but it is not an independent second reading, so the ADV/Form 3/4/5 population rows in F2
  should be read as "the key agrees with the identifier this often", not as a blind precision.
  The residual rows and every name-only row are independently labelled.
- **65 of 921 pairs are `unknown`**, 50 of them ADV homonym candidates where two CRD records carry
  one name and neither IAPD nor the archive separates them — research 16's "could not be
  determined" item, unchanged. Every headline figure is given twice, counting these as errors and
  as successes; where the two readings straddle the bar I have said so.
- **The 8-K/DEF 14A labels lean on Form 3/4/5 as the anchor.** 74 of 208 pooled `full` pairs rest on
  an external CIK or a middle-name conflict (`anchored_only`: 73/74, LCB95 0.9417); the other 134
  rest on timeline and role continuity at one issuer, which is my reading of the event sequence, not
  an identifier. A stricter study would label only the anchored subset — and that subset is n = 74,
  far short of 268.
- **DEF 14A is measured but not eligible.** Its 58.7% ineligible share is ticket 10's parser defect;
  the 51 labelled `full` pairs come from the clean 41%, so its numbers describe a post-fix parser,
  not today's data.
- **Two ADV months, not a year.** March is the annual-amendment month and August an ordinary one;
  the homonym census is therefore of firms that amended in those two windows. A firm whose two
  same-named owners appear only in, say, June is invisible.
- **IAPD resolves only 155 of 216 probed ids** (research 16 F5.5: registered individuals only), so
  the `L-H7`/`L-H8` evidence is available for roughly two-thirds of the ADV homonym census and
  systematically missing for recently-created CRD records.
- **No Snowflake.** Silver and gold were unreachable throughout (map, 2026-09-19); the 8-K and
  DEF 14A inputs are the S3 export snapshots research 01 used, which are a point-in-time slice, and
  the Form 3/4/5 input is research 07's bronze union, not the silver table.
- **`Status Acquired` was used as corroboration, never as a key component.** It equals across 14 of
  the 55 ADV `full` homonym pairs, 6 of which are two people — so it is not the extra field that
  rescues the ADV residual either.

## Could not be determined

- Whether the 49 unsettled ADV homonym pairs are duplicate CRD records or relatives: IAPD publishes
  no date of birth and the FOIA export suppresses the SSN/DOB fallback (research 16 F5.4). This is
  the same wall research 16 hit, and it caps the ADV residual's `different` count at 27 measured out
  of a possible 76.
- The true precision of the 8-K key at one-sided 97.5%: n = 277 where 381 error-free decisions are
  needed. Nothing in the data says the extra 104 would be error-free — only that the first 277 were.
- Whether the name-only key holds across issuers: this study only ever compares within one issuer
  CIK, per ticket 02 Tier C's "name across different issuers → Steward". Research 01 F3 (398 of
  10,042 names appear under more than one issuer) remains the only measurement of that direction.
- Whether an ADV Schedule A/B person and a Form 3/4/5 reporting owner can be the same Person under
  one context: only 3 of 3,981 ADV firm CIKs are issuer CIKs in this corpus, so the question has
  essentially no population here.
- The bridge behaviour of a real Tier C comparator: I used surname + first initial as a stand-in.
  A Jaro-Winkler or Splink comparator would generate a different, probably larger, candidate set,
  and the 42-of-48-false result is a property of my stand-in, not of any implemented matcher.
