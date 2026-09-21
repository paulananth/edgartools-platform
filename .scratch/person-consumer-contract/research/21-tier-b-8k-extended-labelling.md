# Extending the 8-K Tier B labelling to n ≥ 381 at the fixed key

Ticket: [21](../issues/21-extend-tier-b-labelling-to-97-5.md). Run 2026-09-20, 21:50 ET.
A continuation of [research 17](17-tier-b-context-key-calibration.md), not a new study: the record
table, the name parsers, the normalizers, the role classes and the Wilson arithmetic are research
17's, imported unchanged from `17-common.py`, and the labelling rules are research 17's own K/X
rules **copied verbatim and verified** (`21-label.py --verify` re-labels research 17's 281 8-K
pairs and reports 281 shared pairs, **0 draft-label mismatches**). Offline throughout: the S3
`sec_employment_event` export snapshot and research 07's Form 3/4/5 bronze union.
**Zero SEC EDGAR requests. Zero IAPD requests** (see Sources read).

## Verdict

**Yes — 8-K Item 5.02 clears ≥ 99% precision at a one-sided 97.5% Wilson lower bound on
n = 659 independently labelled pairs at ticket 20's fixed key.** Research 17 sampled this
population; ticket 21 takes the **census** — all 216 within-8-K groups and all 721 8-K rows with
a same-issuer Form 3/4/5 anchor, 938 candidate pairs, of which **661 match the fixed key** (same
issuer CIK + surname + given name + middle initial, with a generational-suffix conflict as a hard
veto). Labels: **658 `same`, 0 `different`, 1 `unknown`, 2 `ineligible`** (rows that are not
person names at all). On the eligible denominator of 659: optimistic precision 1.00000,
**LCB97.5 0.99420**; counting the one unsettled pair as an error, 0.99848, **LCB97.5 0.99146**;
settled-only, **0.99420**. All three clear.

**Which reading you get depends on this study's own settling rules, and that has to be said
first.** Under research 17's rules alone the fixed-key set is 623 `same` / 38 `unknown`, and the
conservative reading is 0.94251, **LCB97.5 0.92208 — it fails badly**. Research 21's pass-2 rules
settle 37 of those 38: **21 on a date anchor** (`L-21A`, a Form 3 initial-statement date; `L-21B`,
an 8-K event inside the anchor CIK's reporting window) and **16 on an argument** (`L-21E`, that
role disagreement is not evidence, resting on research 17 F6's measured 32-same / 0-different;
`L-21C`, that a Form 4 presupposes an earlier Form 3 and so does not date a relationship).
Accepting only the date-anchored settlements gives 0.97428, LCB97.5 0.95920. **The conservative
reading clears because of pass 2. The `settled` reading clears either way** — pass 1 alone is
623/623, LCB97.5 0.99387 — and the optimistic reading is 0.99422 either way. Ticket 20 Q2's
objection is answered, but by argument as well as by n, and the argument is `L-21E`'s.

**What n did not buy.** The 441 pairs research 17 never saw are 441 `same`, 0 `different`,
0 `unknown` — but that is not an independent confirmation, it is the same measurement with a
smaller n. **All four non-`same` labels in the entire 938-pair census fall inside research 17's
own hand-reviewed 281.** After pass 2 the only surviving route to a non-`same` label at the fixed
key is `L-X4`/`L-K3` (two owner CIKs at one issuer), and that fires on **1 of 721** rows — a 0.14%
base rate, measured. So P(non-`same` | fixed-key match) ≈ 1/661 nearly regardless of the truth,
and "0 `different` in 659" has little power against a true error rate of a few tenths of a
percent. **The discriminating stratum is exhausted**: the ticket asked for that to be said if it
happened, and it has. The binding constraint on this measurement is now the labelling method's
power, not n.

The check that does not depend on my reading runs on a source where an identifier labels every
pair. Against Form 3/4/5's 11 same-issuer homonym CIK pairs — all known `different` by
`owner_cik` — plain `mi` merges **7**, the **fixed key merges 1**, and ticket 20's
generational-suffix veto prevents **6**. The one false merge is the Zegna brothers, whose
four-token surname defeats the `LAST FIRST MIDDLE` parse; fixing that parse takes it to **0 of
11**. The veto is worth what ticket 20 says it is worth, and it is worth it on measurement rather
than argument.

**Recommendation: activate Tier B for 8-K Item 5.02 at the fixed key**, with three fixes that ship
alongside it, none of which touches the key: repair the **multi-word-surname parse** (it is the
study's only measured false merge, and 0.453% of 8-K and 0.108% of Form 3/4/5 records parse a
surname particle as the given name); close the two **eligibility-filter gaps** (`Effective Date`,
`Manufacturers Bank`); and **drop `V` from the suffix token set**, which discards the middle
initial of 241 Form 3/4/5 and 7 8-K records. Ticket 20's own token list (`JR/SR/II/III/IV`) is
already correct; research 17's normalizer is not.

## The arithmetic, shown once

For k successes in n, `p̂ = k/n`, and

&nbsp;&nbsp;`LCB = ( p̂ + z²/2n − z·√( p̂(1−p̂)/n + z²/4n² ) ) / ( 1 + z²/n )`

with z = 1.6448536 (one-sided 95%) and z = 1.9599640 (one-sided 97.5%). Worked on the headline
cell — fixed key, optimistic reading, k = n = 659: p̂ = 1, so the radical is `z·√(z²/4n²)` =
z²/2n and the expression collapses to `n/(n + z²)` = 659/(659 + 3.8416) = 659/662.8416 =
**0.994204**. On the conservative-eligible cell, k = 658, n = 659: p̂ = 0.9984825, z² = 3.8416,
centre = 0.9984825 + 3.8416/1318 = 1.0013972, radical = 1.96·√(0.9984825·0.0015175/659 +
3.8416/(4·659²)) = 1.96·√(4.5106e−6) = 0.0041627, denominator = 1 + 3.8416/659 = 1.0058294, so
LCB = (1.0013972 − 0.0041627)/1.0058294 = **0.991456**.

Zero-error sample sizes for a 0.99 bound, recomputed: **n ≥ 268** at one-sided 95%, **n ≥ 381** at
97.5%. One error needs 563 at 97.5%; two errors need 726. This study's n = 659 would still clear
99% at 97.5% with **one** error (0.99146 measured on exactly that arithmetic) but not with two.

## Sources read

Data, all offline, SHA-256 in `21-summary.json.inputs`:

| Input | Rows used | sha256 (prefix) |
|---|---|---|
| `sec_employment_event.parquet` (8-K Item 5.02, research 01's S3 export snapshot) | 7,878 rows, **4,193** person-shaped and eligible | `8e21ed8d…` |
| `r07/07-union-corpus.jsonl` (research 07's Form 3/4/5 union) | 72,981 C-J `person` owner rows | `9daf08fb…` |
| `r17/records.parquet` (research 17's record table, rebuilt by nothing here) | 207,371 rows, reused as-is | `a88ee20d…` |
| `17-pairs.jsonl` (research 17's labels, for the overlap and the deltas) | 921 pairs, 281 of them 8-K | `1f3a091a…` |

**IAPD: zero requests.** The individual endpoint is a strict lookup by CRD/`OwnerID`
(research 16 F2); 8-K Item 5.02 persons carry no CRD, so there is no key to look them up by, and
every label here was settled from SEC-sourced data already on disk. `21-iapd-requests.jsonl` is
present and empty — zero requests, zero 403s, zero 429s, nothing to report against the 300-request
cap.

Sibling files (same directory): `21-common.py` (the fixed key, the corrected sample-size helper),
`21-sample.py` (the census → `r21/pairs_draft.jsonl`, `r21/bridges.json`), `21-label.py`
(research 17's rules verbatim + this study's settling rules → `21-pairs.jsonl`),
`21-overrides.json` (2 hand readings), `21-score.py` (→ `21-summary.json`), `21-crosscheck.py`
(→ `21-crosscheck.json`).

## Method

**The key under test is fixed and was not re-opened.** Ticket 20 Q3, scored exactly as written:

1. same **MDM-resolved issuer identity** — *here, same issuer CIK*. MDM issuer ids do not exist
   yet, so this study substitutes the raw CIK. That is a real gap against ticket 20's wording and
   is carried in Limits below, not glossed: every pair in this study is two records under one
   literal `cik` string, and
2. surname + given name + **middle initial** (`mi`) — an initial matches a middle name, absent on
   both matches, absent on one side does **not** match, and
3. **no generational-suffix conflict** — `JR`/`SR`/`II`/`III`/`IV` present on one side only, or
   conflicting, is a veto. Research 17's `mi` variant is suffix-*insensitive*, so the fixed key is
   `mi` **minus** the vetoed pairs; `21-common.fixed_key_match` is the whole of it.

Role and flags are evidence, never key (ticket 20 Q3; research 17 F6). `full`, `nosuffix` and `fl`
are reported below for comparison only.

**Population: a census, not a sample.** Research 17 took the first 140 within-source groups of 216
and the first 140 cross-source rows of 721, ordered by a hash. This study takes all of both, in
the same hash order, so research 17's pairs keep their `pair_id` (the same SHA-256 of the two
record ids) and the two studies pool without double counting. There is therefore **no adversarial
sampling to correct for** — the "stratum composition" the ticket asks about is the population's
own. The only ordering effect inherited from research 17 is that it sorted the one cross-source
row carrying two owner CIKs to the front; in a census that changes nothing.

| stratum | what it is | candidate pairs | census? | labelled by research 17 |
|---|---|---|---|---|
| **K** within-source | same issuer, same `fl` key, two 8-K events on different dates; one pair per group (earliest × latest) | 216 | yes (216 of 216 groups) | 140 |
| **X** cross-source | an 8-K row against a Form 3/4/5 person owner at the same issuer sharing the `fl` key; one pair per distinct owner CIK | 722 | yes (721 of 721 rows) | 141 |
| **total** | | **938** | | 281 |

**Labels are independent of the key.** No rule asks whether `k_mi` matches. They read the Form
3/4/5 filer CIK at the issuer, the **form type** (3 vs 4), the filing periods, the 8-K event
sequence, and the middle-name / suffix *conflict* the looser variants ignore. Four labels:
`same`, `different`, `unknown` — reported, never folded into `same` — and `ineligible`, new in
this study, for a row that is not a person name and therefore never reaches any tier.
`21-pairs.jsonl` keeps research 17's fields (`pair_id`, `source`, `key_fields`, `label`,
`evidence`, `labeler_rule`) so the two files pool cleanly.

**Pass 1** is research 17's K and X rules, copied character-for-character from `17-label.py`
(L-K1…L-K8, L-X1…L-X5, L-H1) and **verified**: re-labelling research 17's own 281 8-K pairs
reproduces every draft label and rule. **Pass 2** applies this study's own rules, stated once and
applied to the whole census, only to pairs pass 1 left `unknown`:

- **L-21A — Form 3 date anchor.** Exactly one Form 3/4/5 CIK carries the name at the issuer, its
  earliest row there is a **Form 3** (the initial statement of beneficial ownership, so the
  insider relationship demonstrably began then), and an 8-K *appointment* falls within 45 days of
  it ⇒ `same`. Role is not consulted. *12 pairs.*
- **L-21B — co-presence.** Exactly one CIK; an 8-K event date falls **inside** that CIK's Form
  3/4/5 window at the issuer, so the named person was a reporting insider of that issuer on that
  date ⇒ `same`. *9 pairs.*
- **L-21C — a Form 4 does not date the relationship.** Research 17's `L-X3` treats the earliest
  Form 3/4/5 period in the corpus as the start of the relationship. That premise holds only when
  the earliest row is a Form 3. A **Form 4** is a change report that presupposes a Form 3 already
  on file, and this corpus is a recent slice, so an 8-K event long before the first Form 4 is a
  gap in the corpus, not a contradiction; the contradiction is withdrawn ⇒ `same`. *1 pair.*
- **L-21E — role disagreement is not evidence of a different person.** Research 17 F6 measured the
  role element on this exact source: of 8-K pairs with inconsistent roles, **32 are the same
  person and 0 are different**. Ticket 20 Q3 adopts that. Where `L-X5`/`L-K4` objected on role
  alone, with one anchoring CIK (X) or a coherent event sequence (K) and no name conflict ⇒
  `same`. *15 pairs.*
- **L-21F — not settled, and why.** Where the only field that would separate two candidates is the
  **middle initial itself**, settling the pair would re-apply the key and prove nothing. Such
  pairs stay `unknown`. *1 pair.*

**Pass 3** is `21-overrides.json`: two hand readings, both marking a row `ineligible`.

## Results

### F1 — The fixed key on the 8-K census

n = 659 is the **eligible** denominator: 661 candidate pairs less the 2 whose 8-K row is not a
person name (F5). `different` is 0 in every reading.

| reading | n | same | different | unknown | precision | LCB95 | **LCB97.5** | clears 99% at 97.5%? |
|---|---|---|---|---|---|---|---|---|
| **optimistic** (unsettled counted as `same`) | 659 | 658 | 0 | 1 | 1.00000 | 0.99591 | **0.99420** | **yes** |
| **conservative** (unsettled counted as an error) | 659 | 658 | 0 | 1 | 0.99848 | 0.99323 | **0.99146** | **yes** |
| **settled only** (unsettled dropped) | 658 | 658 | 0 | — | 1.00000 | 0.99591 | **0.99420** | **yes** |
| strictest (also charges the 2 non-person rows) | 661 | 658 | 0 | 1 + 2 | 0.99546 | 0.98870 | 0.98674 | no |

And the same table on the **441 pairs research 17 never labelled**, where the three readings
coincide because there is nothing unsettled in them — **read this as the same measurement at a
smaller n, not as an independent confirmation** (F9 explains why):

| | n | same | different | unknown | precision | LCB95 | **LCB97.5** |
|---|---|---|---|---|---|---|---|
| **new in research 21, all readings** | 441 | 441 | 0 | 0 | 1.00000 | 0.99390 | **0.99136** |
| research 17's own pairs, re-labelled, optimistic | 218 | 217 | 0 | 1 | 1.00000 | 0.98774 | 0.98268 |

**Sensitivity to this study's own settling rules.** Pass 2 settles 37 of the 38 pairs research
17's rules left `unknown` at the fixed key — 21 on a date anchor (`L-21A`, `L-21B`), 16 on an
argument (`L-21E` 15, `L-21C` 1). How much the conservative reading depends on that:

| settling rules in force | n | same | unknown | precision | LCB95 | **LCB97.5** | clears? |
|---|---|---|---|---|---|---|---|
| pass 1 + pass 2 (headline, conservative) | 659 | 658 | 1 | 0.99848 | 0.99323 | **0.99146** | yes |
| pass 1 + only the date-anchored settlements | 661 | 644 | 17 | 0.97428 | 0.96206 | 0.95920 | no |
| **pass 1 only** (research 17's rules alone) | 661 | 623 | 38 | 0.94251 | 0.92574 | **0.92208** | **no** |
| pass 1 only, **settled** reading (unknowns dropped) | 623 | 623 | — | 1.00000 | 0.99568 | **0.99387** | yes |

The 38 pass-1 unknowns are 34 × `L-X5` (role disagreement), 2 × `L-K4` (role classes differ),
1 × `L-X3`, 1 × `L-X4`. So the conservative reading turns entirely on whether role disagreement
and a Form-4 start date are treated as evidence of a different person. Ticket 20 Q3 says role is
not ("role and flags are evidence, never key") and research 17 F6 measured it at 32 `same` /
0 `different` on this source — but that is an adopted position, not a fresh measurement, and a
reader who rejects it should read the 0.92208 row. **The `settled` and `optimistic` readings clear
under either pass.**

Per stratum, and by what the label rests on:

| cut | n | same | different | unknown | precision (opt.) | LCB95 | LCB97.5 |
|---|---|---|---|---|---|---|---|
| **X** — cross-source, anchored to a Form 3/4/5 filer CIK | 466 | 465 | 0 | 1 | 1.00000 | 0.99423 | **0.99182** |
| **K** — within-8-K (2 `ineligible` excluded) | 193 | 193 | 0 | 0 | 1.00000 | 0.98618 | 0.98048 |
| of K, the **timeline-continuity** labels only (`L-K5`–`L-K8`) | 163 | 163 | 0 | 0 | 1.00000 | 0.98367 | 0.97698 |

**The anchored cut matters more than the pooled one.** Every X label rests on an external EDGAR
filer account at the same issuer; the `L-K5`–`L-K8` labels rest on my reading of an 8-K event
sequence, which is research 17's own stated weakness. The anchored cut alone is n = 466 ≥ 381 and
clears at 0.99182. The verdict does not need the continuity labels — it survives deleting all 163
of them.

Rule mix across the 661 fixed-key pairs: `L-X1` 238, `L-X2` 192, `L-K5` 61, `L-K6` 46, `L-K7` 36,
`L-K1` 28, `L-K8` 20, `L-21E` 15, `L-21A` 12, `L-21B` 9, `L-OVR` 2, `L-21C` 1, `L-21F` 1.

### F2 — The variants, for comparison only

The key is fixed; this table exists to show the fixed key sits where ticket 20 put it.

| variant | n (eligible) | same | different | unknown | precision (opt.) | LCB95 | LCB97.5 |
|---|---|---|---|---|---|---|---|
| `full` | 622 | 621 | 0 | 1 | 1.00000 | 0.99567 | 0.99386 |
| `nosuffix` | 632 | 631 | 0 | 1 | 1.00000 | 0.99574 | 0.99396 |
| `mi`, without the suffix veto | 669 | 668 | 0 | 1 | 1.00000 | 0.99597 | 0.99429 |
| **the fixed key (`mi` + veto)** | **659** | **658** | **0** | **1** | **1.00000** | **0.99591** | **0.99420** |
| `fl` | 936 | 934 | **1** | 1 | 0.99893 | 0.99523 | 0.99397 |

The single `different` pair in the whole census appears only at `fl`: 8-K `Kevin P. Smith` against
Form 3/4/5 `Smith Kevin Raymond Merrill` at Inogen (CIK 1294133) — two named executive officers
whom the middle name separates. The fixed key rejects it, as `full`, `nosuffix` and `mi` all do.
On this source the veto costs 10 pairs of coverage and buys no measured precision; **F6 shows
where it earns its place instead.**

### F3 — Hard case 1: homonyms at the same issuer

The 8-K side has no identifier, so the within-issuer homonym rate has to be measured from the
anchor side. Of the **721** 8-K rows with a same-issuer Form 3/4/5 anchor, exactly **1** has two
owner CIKs sharing surname + given name at that issuer (Inogen's two Kevin Smiths) — a base rate
of **0.14%**. On the 8-K side alone, **34 of 3,821** (issuer, surname + first-initial) blocks hold
two or more distinct `full` keys; 6 fixed-key pairs are drawn from those blocks and all 6 are
`same`. The key's exposure to a same-issuer homonym is small because same-issuer homonymy is rare,
not because the labeller is lenient — and F6 measures the same rate against an identifier.

**This is also the statement that the discriminating stratum is exhausted**, which the ticket
asked for if it happened. The brief's instruction was to prefer pairs that discriminate —
same-issuer homonyms, middle-initial variants, suffix cases. A census cannot prefer, but it can
count what it found: **1** two-CIK homonym row in 721, **6** fixed-key pairs from a block holding
two distinct `full` keys, **10** suffix-vetoed pairs, **37** fixed-key pairs where `full` does not
match (the middle-initial variants). There is no larger discriminating stratum left in this
population to sample — what the population can support is exactly what is reported here. F9 draws
the consequence for how much the headline n is worth.

### F4 — Hard case 2: reused identifiers

8-K carries no identifier of its own, so the analogue is the anchor side: an anchoring Form 3/4/5
CIK carrying more than one distinct name at that issuer. **0 of the 661 fixed-key pairs** are of
that shape. This is research 17 F4's result seen from the 8-K — a filer cannot set the owner name
on a Form 3/4/5 at all (EDGAR Ownership XML Technical Specification v5.1 §4.3.2), and research 17
found **0 genuinely reused identifiers** in 59 ADV + 25 Form 3/4/5 id-split pairs.

### F5 — Hard case 3: transitive bridges, and two rows that are not people

**No transitive bridge exists**, for the structural reason research 17 F5 gives: an exact-equality
key makes "shares a key with" an equivalence relation, so a bridge needs a (issuer, surname +
first initial) group holding three distinct `full` keys. Measured here twice — over 8-K alone and
over 8-K **unioned with** the Form 3/4/5 person owners at the same issuer, which is the
cross-source chain the X stratum could produce: **0 groups** in both.

What the census did surface is two rows that are not persons, both inside 8-K
`sec_employment_event.person_name`, both passing research 17's eligibility filter
(`17-common.looks_like_role_text`):

- `Effective Date` (issuer 1552000) — a parser artifact. Neither `EFFECTIVE` nor `DATE` is in the
  filter's role vocabulary. Research 17 overrode this pair to `unknown`; `ineligible` is the more
  honest disposition, because a row that is not a person never reaches a tier and does not belong
  in a precision denominator.
- `Manufacturers Bank` (issuer 1649739) — an entity, carried as `person_name` on two appointment
  events with role `Director`. `BANK` is absent from the filter's company vocabulary, which holds
  `COMPANY|CORPORATION|INC|LLC|LTD|CORP|GROUP|PARTNERS|CAPITAL|FUND|TRUST|HOLDINGS`. **Research 17
  labelled this pair `same`** — it was not among its 8 unsettled pairs, so this is a miss the
  extended census found rather than one it inherited.

Both are eligibility-filter defects, not key defects, and both are one word each to fix. They are
the entire gap between the headline reading and the strictest one.

### F6 — The fixed key measured against an identifier, not against a reading

*The check the 8-K census cannot perform on itself.* Every `different` verdict the 8-K labeller
can reach comes from a middle-name or suffix conflict (`L-H1`), and the fixed key rejects those
pairs anyway — so the one error the key could actually make, merging two genuinely different
people who share surname, given name and middle initial at one issuer, is **invisible to this
labelling method by construction**. `unknown` (`L-21F`) is the strongest thing it can say.

Form 3/4/5 can answer it, because `owner_cik` labels every pair with no interpretation
(research 17 F1: 100% of rows carry one). Research 17 F3's homonym census enumerated all **11**
same-issuer pairs of owner CIKs sharing surname and given name; every one is two different people
by the identifier. Running the **fixed key** against them:

| | count |
|---|---|
| same-issuer homonym CIK pairs, all known `different` by `owner_cik` | 11 |
| would be merged by `mi` alone | **7** |
| **prevented by the generational-suffix veto** | **6** |
| **would be merged by the fixed key** | **1** |

**A note on the denominator, because the obvious one is wrong.** It is tempting to divide 1 by the
56,307 auto-bind decisions the fixed key makes on Form 3/4/5 and quote a rate per 10,000. That
figure would be badly inflated: on Form 3/4/5 a "decision" is overwhelmingly one owner CIK filing
repeatedly at one issuer (Michael G. Combs above is 16 rows, 15 "decisions", all trivially
correct), so ~65,000 records collapse into ~9,300 groups and almost none of those collapses is
cross-identity. Research 17 deliberately avoided that denominator, reporting Form 3/4/5 two ways
instead (F2 population framing, unit = group; residual framing, unit = labelled id-pair), and its
`mi` figures stand unchanged: **population 0.99925, LCB95 0.99862; residual 0 `same` of 7,
precision 0.000**. The new fact here is not a rate, it is the count: of the 11 pairs, the fixed
key merges **1** where `mi` alone merges 7.

The 6 the veto prevents are `FLORSHEIM THOMAS W JR`/`THOMAS W` (Weyco), `ABERNETHY ROBERT C`/
`Robert C. JR` (Peoples Bancorp NC), `White Blaine Scott`/`Scott II` (New Peoples Bankshares),
`Stetz Gary S.`/`Gary S. II` (Hepion), `Romney Edgar`/`Edgar Jr` (Amalgamated Financial), and
`DILLARD WILLIAM T II`/`William T. III` (Dillard's) — five fathers and sons and one II/III pair,
exactly ticket 20 Q3 point 3's case. **The one false merge is not a key failure**: `Zegna di Monte
Rubello Edoardo` and `Zegna di Monte Rubello Angelo`, two brothers at Ermenegildo Zegna N.V. whose
four-token surname defeats the EDGAR `LAST FIRST MIDDLE` parse — both parse to
last `ZEGNA`, first `DI`, middle initial `M`. Research 17 F3 already named it as a parse artifact.
**Repair the parse and the fixed key merges 0 of 11** (F7b).

What this check is worth: nothing in it is my reading — an identifier does the labelling and the
11-pair census is complete — so it is the one place where the key's precision is measured rather
than argued. What it is not: a different-sized sample of the same thing. It is 11 pairs on a
different source, and it says two specific things. Ticket 20's suffix veto is **load-bearing**
(6 of 7), and the key's remaining exposure on an id-bearing source is a **name-parsing** defect,
not a key defect.

### F7 — The `V` token: a normalizer defect the fixed key inherits

Research 17's suffix token set carries `V` (fifth). `V` is also a common middle initial, and both
name parsers strip suffix tokens out of the name core *before* building the key — so a middle
initial `V` is silently discarded and `mi` collapses to `fl` for that record.

| | 8-K | Form 3/4/5 |
|---|---|---|
| records whose parsed suffix holds `V` | 7 | 257 |
| …of those, with an otherwise empty middle (so the middle initial was lost) | **7** | **241** |

Examples: `Mark V. Anquillare`, `Robert V. Vitale`, `Cydonii V. Fairfax`, `Paul V. Stahlin` on the
8-K side; `Bergh Charles V`, `CRAWFORD MATTHEW V`, `Caldwell Nick V.`, `Date Rajeev V` on the
Form 3/4/5 side. For those 248 records the key runs one variant looser than ticket 20 specifies.
**Ticket 20 Q3's own token list — `JR`/`SR`/`II`/`III`/`IV`, no `V` — is the correct one**, and
this study scored the veto with exactly that list. Scoring it with research 17's list instead
would veto 12 rather than 10 `mi`-matching 8-K pairs, the 2 extra being `Stuart V Flavin` against
`Stuart V. Flavin III`, where the `V` is a middle initial on one side and part of a
suffix-plus-initial collision on the other. The fix is to remove `V` from the token set, not to
change the key.

### F7b — The multi-word surname: the study's one measured false merge

F6's single false merge is a parse defect, so it is worth sizing. Both name parsers assume the
surname is one token (`parse_edgar`: `LAST FIRST MIDDLE`; `parse_western`: `First Middle Last`),
so a surname carrying a particle — `di`, `de`, `van`, `von`, `da`, `la`, `le`, `dos` — is split,
and the particle becomes the **given name**.

| | 8-K | Form 3/4/5 |
|---|---|---|
| records whose parsed **given name** is a surname particle | 19 of 4,193 (**0.453%**) | 79 of 72,980 (**0.108%**) |
| …of those, in a multi-record fixed-key group at one issuer holding more than one distinct raw name | **0** | **1** |

8-K examples: `Del Pozzo`, `Di Salvo`, `Mr. Le Merle`, `Mr. Van Hauwermeiren`, `Mr. Van Vleet`,
`La Vonda Williams` (a genuine given name the same rule mis-splits). Form 3/4/5 examples:
`Bodin de Moraes Pedro Luiz`, `Foufopoulos - De Ridder Lucrece`, `Gomide de Faria Mariano`.

The realised exposure across both corpora is **exactly one group** — the Zegna brothers. That is
reassuring about today's data and not about tomorrow's: the defect turns a four-token surname into
a shared `(last, first, mi)` of `ZEGNA|DI|M`, which merges *every* member of such a family at one
issuer, and this corpus happens to hold one such family. Repairing the parse takes F6's count from
1 of 11 to **0 of 11**, which is why it leads the ship-with list rather than trailing it.

### F8 — Candidate recall and review volume

`recall` here is measured on the labelled set, since 8-K carries no identifier to define an
id-group recall: of the pairs a Tier C comparator (surname + first initial) raises that are
labelled `same`, the fraction the fixed key also matches.

| | count |
|---|---|
| labelled `same` pairs raised by the Tier C comparator | 934 |
| …matched by the fixed key | 658 |
| **recall** | **0.7045** |
| lost because one side has a middle name and the other has none | **266** |
| lost to the generational-suffix veto | 10 |

Review volume, over the 4,193 eligible 8-K records (7,878 raw):

| | value |
|---|---|
| records with a Tier C candidate | 697 |
| records with a fixed-key candidate | 633 |
| records raised by Tier C but **not** matched by the fixed key → Steward review | 64 |
| **review per 1,000 eligible 8-K records** | **15.26** |
| review per 1,000 raw 8-K records | 8.12 |
| the same at `mi` without the veto | 15.03 |
| fixed-key auto-bind decisions on 8-K | 338 |

**Recall is the real cost of this key, and it is large.** 266 of 934 known-same candidate pairs —
28.5% — are lost to one asymmetry: 8-K writes a person's name as prose ("Chris Bruzzo") while
EDGAR writes it conformed with the middle name ("Bruzzo Chris" or `SKINNER DEBORAH E`), and
ticket 20's "absent on both matches" means absent on **one** side does not. Those 266 pairs are
not errors; they fall to Steward review, which is the correct fail-closed behaviour and is what
the 15.26-per-1,000 figure counts. It is worth saying plainly because research 17 never measured
recall on a name-only source, and nothing in ticket 20 anticipates that the key's dominant effect
on 8-K is a 30% coverage loss rather than a precision risk.

### F9 — What n bought, and what it did not

The jump from research 17's n = 223 to this study's n = 659 looks like a large gain in evidence.
It is a real gain in *coverage* — every pair the population can offer is now labelled — and a
much smaller gain in *power*, for a reason that has to be on the record next to the headline.

**All four non-`same` labels in the whole 938-pair census fall inside research 17's own
hand-reviewed 281**: the two `ineligible` rows, the one `different` (which only matches at `fl`),
and the one `unknown`. Every one of the 657 pairs added by this study is `same`. That is not
robustness; it is close to what the rule set produces by construction. After pass 2, the only
surviving route to a non-`same` label at the fixed key is `L-X4`/`L-K3` — two owner CIKs sharing
surname and given name at one issuer — and F3 measures that at **1 of 721 rows, 0.14%**. Every
other `different`-producing rule (`L-H1`, a middle-name or suffix conflict) labels exactly the
pairs the fixed key already rejects, so it can never fire *inside* the denominator.

The consequence, stated plainly: **P(non-`same` | fixed-key match) ≈ 1/661 almost regardless of
the truth.** A true error rate of a few tenths of a percent would be expected to produce one or
two contradictions in 659, and this method would see none of them unless they happened to land on
the one detecting rule. "0 `different` in 659" therefore has little power against exactly the
error rate the 99% bar is drawn at. The 441-new and 466-anchored cells are the same measurement at
a smaller n, not independent confirmations of it — they share the blind spot exactly.

What this does **not** undermine: the bar is a *lower confidence bound on precision*, and n = 659
with no detected contradiction is a legitimate measurement of it under the stated method, which is
what ticket 20 asked for. What it means for the next decision: **the binding constraint is now the
labelling method's power, not n.** Labelling 600 more 8-K pairs would move LCB97.5 and would not
move what can be detected. Two things would: an MDM-resolved Person id on the 8-K side (which
would turn every label into an identifier comparison, as F6 already is on Form 3/4/5), or a
deliberate adversarial fixture set — Q11's "zero hard-veto violations in adversarial fixtures",
which this study reports on found data and does not construct.

## Settling research 17's eight unsettled pairs

Research 17 left 8 pairs unsettled at the `mi` variant: **6 on 8-K** and 2 on DEF 14A. Ticket 20
Q4 puts DEF 14A outside the activating measurement, so only the 6 bear on this verdict. Five are
settled; one is not, for a reason that is itself a finding.

| pair | research 17 | research 21 | why |
|---|---|---|---|
| `K-8k-4f410feca401` `Effective Date` (issuer 1552000) | `unknown` (override) | **`ineligible`** | Not a person name; a parser artifact research 17's eligibility filter missed. Excluded from the eligible denominator, counted as an error in the strictest reading. |
| `K-8k-cb137645e75d` David Lazar (1857044) | `unknown` (`L-K4` role classes differ) | **`same`** | The same 8-K that appoints `David Lazar` Co-CEO on 2025-12-23 also appoints `Mr. Lazar` **Chairman** that day; a chairman is a director, so the 2026-03-18 departure recorded against `Director` is the same seat. No other Lazar at the issuer. (`L-21E`.) |
| `X-8k-9b97291ae393` Chris Bruzzo (1639825, Peloton) | `unknown` (`L-X3` timeline contradiction) | **`same`** | The contradiction was "the Form 3/4/5 window begins 2026-09-09, 677 days after the 8-K departure". That row is a **Form 4** (accession `0001525336-26-000009`), a change report that presupposes a Form 3 already on file, so it does not date the relationship. The gap is this corpus's recent slice. (`L-21C`.) |
| `X-8k-0adec994d495` Jerry Kyriazis (1528985) | `unknown` (`L-X5` role disagreement) | **`same`** | The anchoring CIK 1357355's earliest row at the issuer is a **Form 3** dated **2025-05-02** — the same day as the 8-K appointment. An exact initial-statement date anchor; the role text ("Director" vs "Chief Financial Officer") is evidence, not key. (`L-21A`.) |
| `X-8k-28c1da02a690` Michael G. Combs (874866) | `unknown` (`L-X5` role disagreement) | **`same`** | The 8-K appointment 2024-11-26 falls inside CIK 1641248's Form 3/4/5 window at that issuer (2024-08-12 … 2026-06-12, 16 filings), so that person was a reporting insider there on the day. The CEO also seated on the board is research 17 F6's named case. (`L-21B`.) |
| `X-8k-8b31228b46fe` Kevin P. Smith (1294133, Inogen) | `unknown` (`L-X4` two CIKs) | **`unknown`** | **Cannot be settled without circularity.** Inogen has two Form 3/4/5 filer accounts sharing surname + given name — `Smith Kevin P.` (2031211) and `Smith Kevin Raymond Merrill` (1802639) — and the only field that separates them is the **middle initial**, which is the key. A label that used it would be the key marking its own homework. DEF 14A corroborates that these are two distinct named executive officers but corroborates it with the same field. (`L-21F`.) |

The two DEF 14A pairs (`X-proxy-4481dd7d0918`, `X-proxy-7b3430c8ac9c`) are the *same* Inogen pair
of people seen from the proxy and stay `unknown` for the same reason. They do not affect this
verdict; ticket 20 Q4 excludes DEF 14A until [ticket 10](../issues/10-fix-proxy-executive-name-parser-leak.md).

Two further relabellings are not settlements of research 17's list but corrections found by the
census: `K-8k-6a1211ea79c9` `Manufacturers Bank` moves from research 17's `same` to `ineligible`
(F5), and four pairs research 17 left `unknown` at `fl` — `Scott Sutton`/`Scott M. Sutton`,
`Deborah Skinner`/`SKINNER DEBORAH E`, `Thomas Stewart`/`Stewart Thomas Carlton`,
`Dale S. Rosenthal`/`Rosenthal Dale` — settle to `same` under `L-21C`/`L-21E` but do **not** match
the fixed key (each is a middle-name-absent-on-one-side pair), so they enter the recall column,
not the precision one. All 10 deltas are listed in `21-summary.json.pooled_with_research_17`.

## Pooling with research 17

Research 17's 281 8-K pairs are a **subset** of this census and carry the same `pair_id`s, so
"pooling" is a re-label, not an addition — verified: `all_r17_8k_pairs_are_in_this_census: true`.
The census figure **is** the pooled figure; nothing is counted twice. Research 17's own contribution
at the fixed key is the 220-pair cell (218 eligible, LCB97.5 0.98268 optimistic) and the study's
new contribution is the 441-pair cell (LCB97.5 0.99136 under all readings). Research 17's headline
was 8-K pooled at `mi`, n = 223, 217 `same` / 0 `different` / 6 `unknown`, LCB95 0.98801,
LCB97.5 0.98307; those 223 pairs are 220 of the 661 here, with 6 of their unknowns resolved to
4 `same`, 1 `ineligible` and 1 still `unknown`.

## What this settles for ticket 21

1. **8-K's precision at the fixed key, on n ≥ 381**: n = 659 eligible labelled pairs, 658 `same`,
   **0 `different`**, 1 `unknown`. LCB97.5 = **0.99420** optimistic, **0.99146** counting the
   unsettled pair as an error, **0.99420** on settled pairs only. All three clear 99%. n = 381 was
   the requirement; the census supplied 659.
2. **The verdict is activate.** It holds under the optimistic and settled readings whichever
   settling rules are in force, and under the conservative reading **only with this study's pass-2
   rules** — research 17's rules alone leave 38 unknowns and a conservative LCB97.5 of 0.92208
   (F1). 21 of the 37 settlements rest on a date anchor, 16 on the argument (ticket 20 Q3's own)
   that role disagreement is not evidence of a different person.
3. **Ticket 20's suffix veto is confirmed by measurement, not just by argument** — on the one
   source where identity is known it removes 6 of the 7 false merges plain `mi` would make (F6).
   Its cost on 8-K is 10 pairs of coverage, all of them the 8-K prose name omitting a suffix the
   EDGAR conformed name carries.
4. **Three fixes ship with activation, none touching the key.** Repair the multi-word-surname
   parse — it is the study's only measured false merge, and fixing it takes F6 from 1 of 11 to
   0 of 11 (F7b); add `DATE` and `BANK` to `looks_like_role_text`'s vocabulary (F5); remove `V`
   from the suffix token set, which keys 241 Form 3/4/5 and 7 8-K records one variant looser than
   ticket 20 specifies (F7).
5. **Nothing here contradicts ticket 20.** Four things qualify it: the issuer component is a raw
   CIK, not an MDM-resolved identity, because MDM issuer ids do not exist yet (Limits); the key's
   dominant effect on 8-K is a **29.6% recall loss** to middle-name asymmetry rather than any
   precision risk (F8), which ticket 20 does not anticipate; the conservative reading depends on
   pass 2 (point 2); and the 8-K labelling method cannot detect the one error the key could make,
   which is why F6 and F9 exist.
6. **What ticket 22 or its successor should chart is not more labelling.** The discriminating
   stratum is exhausted (F3) and the method's power, not n, is now binding (F9). More 8-K pairs
   would move the bound and not what can be detected; an MDM-resolved Person id on the 8-K side,
   or a constructed adversarial fixture set per Q11, would.

## Limits

- **The issuer component is a raw CIK, not an MDM-resolved identity.** Ticket 20 Q3 point 1 and
  the operator's standing principle both require the context to be an MDM-resolved issuer
  identity. No MDM issuer ids exist yet, so every pair here is two records under one literal
  `cik` string. That is strictly *weaker* than the specified key in one direction (two CIKs for
  one issuer would split a group that MDM would join, costing recall) and identical in the other
  (one CIK never spans two issuers), so it does not inflate precision. It does mean the key as
  ticket 20 writes it has not been measured end to end.
- **The 8-K labelling method cannot produce the error it is looking for.** Every `different` the
  labeller can reach is a name conflict the key already rejects, so 0 `different` at the fixed key
  is substantially a property of the method, and "0 in 659" has little power against an error rate
  of a few tenths of a percent (F9). F6 is the one check that escapes this, and it escapes it by
  changing source, not by changing n.
- **The conservative reading is bought by this study's own settling rules.** Research 17's rules
  alone give LCB97.5 0.92208 on the same 661 pairs (F1). The settled and optimistic readings clear
  either way, but a reader who rejects `L-21E`'s premise — ticket 20 Q3's own, that role is
  evidence and not key — should read the pass-1 row and not the headline.
- **370 of 661 fixed-key labels rest on role or timeline compatibility, not on a date anchor**
  (`L-X2` 192, `L-K5`–`L-K8` 163, `L-21E` 15). Research 17 said the same
  of its own set. The anchored-only cut (n = 466, LCB97.5 0.99182) is the reading that does not
  depend on it, and it still clears.
- **The Wilson bound assumes independent trials.** The 661 pairs cover 441 distinct issuers and
  640 distinct (issuer, 8-K name) combinations, at most 6 pairs from any one issuer, so a pair is
  close to one distinct person — but not exactly, and the bound cannot account for what remains.
- **A point-in-time slice, and a recent one.** The 8-K input is research 01's S3 export snapshot
  and the Form 3/4/5 input is research 07's bronze union, not silver; Snowflake was unreachable
  throughout. `L-21C` exists precisely because the slice truncates filing histories. A person who
  appears at an issuer only outside the window is invisible, which affects recall, not precision.
- **47% of 8-K rows never reach the key at all** (4,193 eligible of 7,878), and F5 shows the
  eligibility filter is not tight: two non-person rows reached the census. The eligible denominator
  is therefore slightly optimistic, and the strictest reading in F1 is the price of that.
- **Zero IAPD evidence.** Nothing here is corroborated by a registration record, because IAPD
  cannot be keyed by anything an 8-K carries. Every label is SEC-sourced.

## Could not be determined

- **Whether Inogen's 8-K `Kevin P. Smith` is the EVP/General Counsel or a third person** — the one
  `unknown` in the census. Every available field that separates Inogen's two Kevin Smiths is the
  middle initial, which is the key. Settling it needs an identifier on the 8-K row, which the
  source does not carry, or an MDM-resolved Person id, which does not exist yet.
- **The key's behaviour across issuers.** Every pair here is within one issuer CIK, per ticket 02
  Tier C. Research 01 F3 (398 of 10,042 names appear under more than one issuer) remains the only
  measurement of that direction.
- **Whether the 29.6% recall loss is acceptable.** This study measures it; whether 266 known-same
  pairs per 934 candidates falling to Steward review is the right trade is an operator decision,
  not a measurement. The alternative — matching an absent middle name to a present one — is `fl`
  in all but name, and `fl` is where this census's only `different` pair appears.
- **DEF 14A's own figure at the fixed key.** Out of scope by ticket 20 Q4 and still blocked by
  ticket 10; its two unsettled pairs are unchanged here.
