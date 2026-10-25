---
name: security-master
description: The operator's rules for the Security master in MDM - which sources feed a Security, its record keys, identifiers and cross-references, every OpenFIGI field and the primary listing, the listings detail table, matching, survivorship, held-back records and the run order. Use before changing any Security source, contract, merge rule or run, or when answering what a Security holds.
---

# Security Master

> Part of the **data-platform** skill set. data-onboarding and refining-rules
> say *how* to change rules; this skill says *what* a Security must be. Every
> rule here is an operator ruling, dated; change one only on the operator's
> words, and record them here.

It answers: **what is one Security in MDM, where does each part come from,
and what must never happen to it?**

## Status of each rule

Rules marked **live** are in `rules/` and proved. Rules marked **switched on
in the files** are in `policy.yaml`; a new run uses them. The OpenFIGI-first
rules (ticket 120) are switched on in the files (2026-10-24 19:27 ET, "switch
on ticket 120"). They are not activated in the company-on Rules database.

## Hard stops

| Never | Instead |
|---|---|
| Join two Securities on a FIGI or a ticker | They are cross-references: lookup only (operator, 2026-10-20: "Lookup only for now") |
| Let one identifier sit on two Securities | Every proof counts `identifiers_on_two_masters`; it must be 0 |
| Let an OpenFIGI ISIN answer create a second Security for an issue its CUSIP answer already made | It joins that CUSIP's Security by their shared listing FIGI; two or more such CUSIPs set it aside for review (switched on in the files, ticket 120) |
| Attach an ISIN to a CUSIP on a filing alone | Only when OpenFIGI agrees, one to one (live) |
| Fill a security-level field by guessing between disagreeing listings | Take the primary listing's value, else leave it blank (decided) |
| Fold OpenFIGI's values into N-PORT's record | OpenFIGI keeps its own record on the same Security (decided) |
| Send a request to OpenFIGI or the SEC | Captured files only; a new request needs the operator's permission for that request |
| Load ISIN-only Securities in a second run over the same quarter | One run reads the quarter once (decided) |

## One Security, several sources

One Security is one issue (one CUSIP, or one ISIN when there is no usable
CUSIP). Each source keeps its own record on it; MDM merges them.

| Source | Dataset | Creates a Security? | Gives |
|---|---|---|---|
| SEC N-PORT | `sec.nport.security.v2` | Yes (decided) | CUSIP, ISIN (FIGI-agreed), issuer name as filed, title of class, issuer LEI, "issued by" link |
| SEC 13F | `sec.thirteenf.information_table.security.v1` | Yes (live) | CUSIP, name and title as filed, a filed FIGI |
| OpenFIGI | `openfigi.security.v1` (CUSIP), `openfigi.security_isin.v1` (ISIN) | Yes, and first (switched on in the files 2026-10-24 19:27 ET, "switch on ticket 120") | All ten OpenFIGI fields and every listing; an ISIN answer also carries the one CUSIP sharing a listing FIGI with it |

The ranking that fills a field: OpenFIGI first, then N-PORT, then 13F
(operator, 2026-10-18: "make openfigi priority 1 and 13f last"; ticket 84).
`rules/merge/kinds/security.yaml`, `defaults.sources`.

## Keys and identifiers

- **Record key (decided):** N-PORT gives one record per Security keyed by its
  CUSIP, else its ISIN (operator, 2026-10-20: "One master record ... why
  can't one run captures all attributes and builds the cross reference").
  The key has no fixed format; CUSIP and ISIN are each checked as
  identifiers, so a bad check digit is held back under its own identifier's
  reason. One dataset, `sec.nport.security.v2`, replaces the two v1 datasets
  (a new record key is a new dataset); one target, `mastering`.
- **Identifiers (match):** `cusip` and `isin`, each verified by its check
  digit (`rules/identifiers/`).
- **Cross-references (lookup only):** the only listing's FIGI, the composite
  FIGI and ticker (the US composite's, else the ISIN country's composite's),
  the share-class FIGI. `mdm.cross_reference_lookup` finds a Security by them.
  Every listing's FIGI is also found through `mdm.detail_version` (its key,
  indexed). No rule matches on any of them.

## How a Security is merged (live)

The rules are `rules/merge/kinds/security.yaml` (version
`security-2026-10-23.openfigi-first`), one file of the Mastering Policy
(`rules/merge/policy.yaml`). A record passes three stages in the Merge Stage.

### 1. Matching: which Security a record joins

Each source has its own matching rules. All are identifier rules: the record's
identifier is held by exactly one Security (`identifier_match@1`,
`identifier_cardinality@1`), so they are deterministic and switch on when
their Identifier Contract is verified (`policy.yaml`, `automatic_rules`,
`activation: deterministic`).

| Rule | Source | Joins by | No Security holds it | Switched on |
|---|---|---|---|---|
| `security-cusip` | 13F | CUSIP | creates one | 2026-10-15 ("merge 985 when green agreed for the rest") |
| `nport-security-cusip` | N-PORT | CUSIP | creates one | 2026-10-17 21:03 ET ("Switch on all six (Recommended)"); v2 version 2026-10-20.1 decided |
| `nport-security-isin` | N-PORT | its ISIN (FIGI-agreed on a CUSIP's record; the key of an ISIN-only one) | creates one | same; it replaces `nport-isin-security-isin` (retired with `sec.nport.security_isin.v1`) |
| `openfigi-security-cusip` | OpenFIGI (CUSIP asked) | CUSIP | creates one (version 2026-10-23.1) | switched on 2026-10-24 19:27 ET ("switch on ticket 120"); version 2026-10-17.1 (waits) was on from 2026-10-17 13:12 ET |
| `openfigi-isin-security-cusip` | OpenFIGI (ISIN asked) | the CUSIP sharing a listing FIGI with it | joins that Security (2026-10-23.1) | switched on 2026-10-24 19:27 ET ("switch on ticket 120") |
| `openfigi-security-isin` | OpenFIGI (ISIN asked) | ISIN | creates one (version 2026-10-23.1) | switched on 2026-10-24 19:27 ET ("switch on ticket 120"); version 2026-10-17.1 (waits) was on from 2026-10-18 13:22 ET |

- **Records that may create go first** in a batch, so a record that may only
  join finds the Security created in the same batch. One identifier
  value creates one Security per batch.
- **A record never binds when its identifiers disagree.** It opens a review
  instead, with one of these reasons:
  - `ambiguous_identifier`: one value held by two Securities;
  - `conflicting_identifiers`: its CUSIP and ISIN point at two Securities;
  - `incompatible_identifier_kind`: the value is held by a master of another kind;
  - `suspended_identifier`: the Security holding it is in review.
- **Each identifier's contract** (`identifiers.cusip`, `identifiers.isin`):
  - **Claim:** a value belongs to one Security (`forward: 1`); a Security may
    hold several values (`reverse: null`).
  - **Compatibility:** the holder must be a Security (`kind_equal@1`).
  - **Verification:** verified on ticket 79's Proving Run: 423,562 Securities,
    0 identifiers on two, a second pass changed nothing.
  - **Tolerance:** after 10,000 decisions, more than 5 violations per 10,000
    switch the rule off automatically, and its records go to review until a
    newly verified contract is registered (`docs/specs/mdm/policy-language.md`).
- **Which identifiers join** (`identifiers.<name>.sources`):
  - CUSIP joins from 13F, N-PORT and OpenFIGI;
  - ISIN joins from both N-PORT datasets and OpenFIGI's ISIN records.
  - FIGI and ticker are in neither list: they never join.

### 2. Survivorship: which value the Security shows

Every field any source supplies reaches the Security (a kind-level
`defaults` rule, operator 2026-09-24): a field only one source gives comes from
it; the priority decides only where several give it. For each field
(`edgar_warehouse/mdm/clean/survivorship.py`, ranked by the engine's
`survivorship::rank`):

1. **A steward's override wins.** A source that disagrees with it opens an
   `override_source_disagreement` review. Two overrides at once are refused.
2. **Otherwise the highest-priority source wins**, in the order of
   `defaults.sources`:
   1. `openfigi.security.v1`
   2. `openfigi.security_isin.v1`
   3. `sec.nport.security.v2`
   4. `sec.thirteenf.information_table.security.v1`

   (operator, 2026-10-18, ticket 84: "make openfigi priority 1 and 13f
   last", then "Name only (Recommended)").
3. **Within one source, the latest effective time wins.** Ties go to the
   source code, then the record key, then the assertion, so the result is
   always the same.
4. A record with no effective time still counts (`allow_unknown_effective:
   true`).
5. A source not in the list never fills a field. A source may blank a field
   ("clear") only when the rule names it in `clear_sources`. Securities name
   none, so a clear opens an `unauthorized_clear` review.
6. **The losing values that differ are kept beside the winner** as its
   `conflicts`. Nothing a source said is lost.
7. **A disagreement never blanks a field** (operator, 2026-10-23, ticket 131:
   "mastering is all about having good values not blanks, use priority").
   No field rule asks the sources to agree. To find a disagreement, read the
   `master_field` view where `conflict_count` is above 0. Within one source,
   filers that disagree on `share_class` still give no letter (ticket 130,
   `share_class_one_letter`). Both rulings are revisited once real examples exist.

What this gives today, measured (ticket 84): OpenFIGI fills the name: it
states one name for 99.7% of its 353,491 CUSIPs. OpenFIGI gives no title, so
N-PORT, then 13F, fill the title of class. A Security OpenFIGI did not find
takes N-PORT's filed name, else 13F's.

**Decided, built, not yet proved:** the one N-PORT dataset replaced the two
in this list and in the matching rules. A change to this list or to a rule
moves the Mastering Policy's digest, so it needs its test run and the
operator's approval of the new digest (data-onboarding, "a merge-rule change
moves pinned digests").

### 3. Held back

A record a contract sets aside never reaches matching. It waits with an open
review ("Held back, never dropped", below).

**An ISIN goes with a CUSIP only when OpenFIGI agrees** (operator,
2026-10-15: "Use FIGI to add pairs too"): the filed CUSIP and ISIN share a
FIGI, and neither is offered twice: the CUSIP is offered one ISIN and the
ISIN one CUSIP (`figi-agree.yaml`, `figi-offers.yaml`, `figi-attach.yaml`).

**OpenFIGI first: an ISIN answer finds its CUSIP's Security by a shared
listing FIGI** (switched on in the files 2026-10-24 19:27 ET, "switch on
ticket 120"; operator, 2026-10-23: "make the seurities run should
process openfigi first", then "agreed"). One CUSIP offered two ISINs stays
one Security when those answers share a FIGI (2026-10-24: "resolve using
figi"); both ISINs are kept. FIGI does not join two Securities. The ISIN target reads `figi_ids`
(each listing FIGI and the CUSIP asked) from every complete CUSIP run
(`figi-ids.yaml`, `isin-figi-cusips.yaml`, `isin-attach.yaml`); its record
carries the CUSIP when exactly one shares a FIGI, and the contract sets aside
two or more (`isin_shares_figi_with_several_cusips`). Every listing FIGI, not
only the ones a record keeps as cross-references: those would reach 349,761
of the 350,867 (2026-10-15 capture). The FIGI stays a cross-reference on the
Security; only the CUSIP it leads to is matched.

**An ISIN-only holding whose ISIN is already on a CUSIP's row is folded into
that row before MDM (decided)**, so no ISIN reaches MDM twice: `combine.yaml`
marks the row `folded_into` the CUSIP and `record.yaml` leaves it out;
`fold.yaml` keys the folded holdings' filed facts by that CUSIP, and the
CUSIP's record takes them where its own holdings state none. Not yet: an
earlier filing date of a folded holding does not move the "issued by" start
earlier, and its different LEI does not unsettle the issuer (the engine has no
"earliest of" yet; ticket 127).

**ISSUED_BY reaches an SEC filer's Securities only through GLEIF.** An N-PORT
holding names its issuer by LEI, and SEC filings almost never state one: 1 of
1,602 Form 4 issuers' submissions carries an LEI (2026-10-23, ticket 24). So
"ISSUED_BY" reaches an SEC Company only where its GLEIF record joined it by
the SEC-GLEIF name rules (the Companies-only proof: 2,764 issuers on their SEC
filer's Company, ticket 22). Measure that lookup through MDM's links, never
through the filing's own LEI. A Form 4 class attaches by the filed trading
symbol through OpenFIGI's ticker (ticket 24), not through this link.

**Share-class FIGI does not join records** (operator, 2026-10-20: "Lookup
only for now (Recommended)"). Before proposing it, count the ISIN-only
Securities that share a share-class FIGI with a CUSIP Security: 116 of
35,310 (2026 Q2).

## Every Security uniquely identifiable

Operator, 2026-10-20 08:24 ET: "Securities and funds must be uniquely
identifiable". A Security exists only for an identifier issued for it; a
fund's own label never makes one. 2026 Q2 N-PORT, 5,347,869 holdings:

| A holding identified by | Holdings | Becomes |
|---|---|---|
| CUSIP | 3,546,715 (66.3%) | a Security (live) |
| ISIN, no CUSIP | 812,952 (15.2%) | a Security (live) |
| SEDOL, CINS or LoanX in the "other" field | 7,718 | a Security, each by its verified Identifier Contract (decided: "SEDOL, CINS, LoanX (Recommended)"; ticket 125) |
| A Bloomberg ID or FIGI in the "other" field | 10,415 | a cross-reference only; never joins |
| A ticker only | 59,409 (mostly futures, forwards, options) | no Security: a ticker is not unique |
| The fund's own ID only | 909,030 (17%; loans 652,058, forwards, swaps) | **not a Security** (decided: "Not Securities (Recommended)"): a contract between two parties stays a holding under its fund |

## Share classes

- **A security's share class is a field, not a record** (operator,
  2026-10-20: "Field on the Security (Recommended)"). The share-class FIGI is
  a field and a cross-reference on each Security; it finds every Security of
  one class. No Share Class kind. Measured on 2026 Q2: 35,590 of 733,538 found
  identifiers (4.9%, mostly equities) carry one, in 26,509 classes; 25 classes
  span three or more identifiers.
- **A fund's share classes (Class A, Class I) are not Securities.** They
  belong to the fund series, not here. Operator, 2026-10-20: "Profile first
  (Recommended)" (ticket 124).

## Every OpenFIGI field (decided)

Operator, 2026-10-20: "all fields from open figi must be in the security
master figi pipeline is the closest to a real security master". An answer
gives, for each listing: name, FIGI, composite FIGI, share-class FIGI,
ticker, exchange code, security type, security type 2, market sector,
security description.

| Where | Fields |
|---|---|
| On the Security | name, security type, security type 2, market sector, share-class FIGI |
| In the listings detail table, one row per FIGI | FIGI, exchange code, ticker, composite FIGI, security description |
| Cross-references | every FIGI, composite FIGI, share-class FIGI and ticker |

**The primary listing** fills a security-level field the listings disagree
on (operator, 2026-10-20: "Use the primary exchange listing", then "US, else
the ISIN's country"). OpenFIGI marks no primary listing, so:

1. the one US composite (exchange code `US`, its own composite) decides,
   a blank value too;
2. only without one, the composite listing of the country in the ISIN's
   first two letters, from the RDM code set `openfigi-country-composite`
   version 1 (11 countries, approved 2026-10-20: "Only the 11 countries seen
   (Recommended)"), embedded in the answers reading as `read.references` and
   held equal to the published set by a test;
3. else blank: the listings table still holds every value.

Measured on 2026 Q2 (733,538 found Securities): 11,727 disagree on a
security-level field; the US composite settles 8,951, the country step 690,
and 2,086 stay blank. OpenFIGI's exchange-code list (1,109 codes) names no
countries, and for 25 of 36 countries tried the home composite never appears
in the answers, which is why the code set holds 11. A Security OpenFIGI did
not find (5%) keeps its N-PORT and 13F fields only.

## The listings detail table (decided)

Operator, 2026-10-20: "Maybe create a security detail table and keep it in
the mdm", then "Detail rows set in config (Recommended)".

- One MDM detail table for every kind: a Dataset Contract states its detail
  lists in configuration (OpenFIGI: `listings`, keyed by FIGI). No
  Security-only table, no Security-only code.
- A Security's CUSIP and ISIN answers make **one set of listings, joined by
  FIGI**; each row records which answer gave it ("One set, joined by FIGI").
- Each load replaces a Security's listings. **A listing a later answer drops
  is ended, its history kept** ("End it, keep history").

## Held back, never dropped (live)

| Reason | Means |
|---|---|
| `invalid_cusip_checksum`, `invalid_cusip` | The filed CUSIP fails its check digit or shape |
| `invalid_isin_checksum`, `invalid_isin` | The same for an ISIN |
| `missing_record_identity` | No usable CUSIP or ISIN |
| `placeholder_name_of_issuer` | A name such as NONE, NULL, UNKNOWN, TBD: withheld |
| `not_found_by_openfigi` | OpenFIGI found nothing for the identifier asked |

Each waits with an open review. 2026 Q2: 1,769 `invalid_cusip_checksum` and
1 `invalid_cusip` of 385,382 filed CUSIPs.

## Run order

OpenFIGI first (switched on in the files, ticket 120; operator, 2026-10-23):

1. N-PORT's read decides which identifiers OpenFIGI is asked (the capture).
2. GLEIF `umbrellas` (sub-fund pairs; read only).
3. OpenFIGI `answers_cusip`, `answers_isin` (the captured answers; read only).
4. N-PORT funds.
5. OpenFIGI `mastering_cusip`: creates a Security per CUSIP answer, and
   writes `figi_ids`.
6. OpenFIGI `mastering_isin`: joins each ISIN answer to its CUSIP's Security,
   or creates one. It reads every complete `mastering_cusip` run, so step 5
   completes first.
7. Securities `mastering` (N-PORT): one run over the quarter; joins what
   OpenFIGI made and creates the rest.
8. 13F.

`rules/source-sequence.yaml` holds the order; a source reads another
finished run by `{run: {source, target, step}}` (Bookkeeping SPEC).

## Securities known only from 13F

Operator, 2026-10-20: "13F us cusip, first then if not use ticker", then,
13F filing no ticker, "Ask by the filed FIGI (Recommended)": ask OpenFIGI by
CUSIP, then by the FIGI the 13F filer gave. A ticket, with counts; no request
until the operator permits it.

## Proving a change

Prove a Security contract or merge rule at the level [Choose the cheapest proof](../mdm-engineering/SKILL.md#choose-the-cheapest-proof) names. The whole quarter is that proof only when the claim is the quarter's totals or switch-on. When it is, 2026 Q2, one record per Security, takes about 3 h 10 min a pass on a laptop; keep it on power ("Make the Securities run faster", ticket 122).

OpenFIGI first was switched on from the completed figi-full store (2026-10-24). CUSIP answers created the Securities. ISIN bundle 1 held the new case, one CUSIP offered two ISINs that share a FIGI. Bundles 2–8 stayed unchecked. Its ISIN target reads the complete CUSIP runs' `figi_ids`, so those CUSIP runs finish first in the same store.
- Report counts only: Securities, held back by reason, identifiers on two
  Securities. Never an identifier or a name from the data.
