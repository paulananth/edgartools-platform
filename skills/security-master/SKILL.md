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
in the files** are in `policy.yaml`; a new run uses them. Ticket 138 part B1
replaced OpenFIGI's ticket 120 rules (switched on 2026-10-24 19:27 ET,
"switch on ticket 120"; those switch-ons ended with them) with one dataset,
`openfigi.security.v3`, and three rules that wait for their switch-on.

## The mastering process (decided 2026-10-25, ticket 138; being built)

The operator replaced the per-kind design on 2026-10-25 ("secutiy is the kind
cusip and isin are diffrant identifiers of the same securities", "there
should be one processing with all the identifier", "first lookup if not exists
then master", "mastering must create an unique id and the unique id joins with
all the other tables cross refrence and silver"). Built so far: a record
carries lists of identifiers (part A1), OpenFIGI's one load with every
listing FIGI as an identifier and one master id in silver (part B1),
N-PORT's pairing by FIGI removed (part B2), each listing's currency (part
B3), the merge by a shared FIGI (part A2a: the FIGI rule's `on_several:
merge`), the CUSIP-first bind (part A2b: N-PORT's CUSIP rule's
`on_conflict: first`). Still to build: the switch-on. The
sections below say where 138 changes what runs.

**One master id.** Mastering mints one master id for each Security. The
Cross-reference, the Source Stage and every silver table join on it; silver
carries the master id only. When two Securities consolidate, the oldest id
survives and the other points to it; silver is re-pointed.

**The Cross-reference holds every identifier** ("cross_refrence table must
hold all the identifiers", "no need for identifier table"). No other
identifiers table; the Listing table (below) holds listings, not identifiers. Each row: the master id, the identifier kind,
the value, matching or lookup only, the source, first seen, last seen.

| Identifier | Role |
|---|---|
| CUSIP, ISIN, each listing FIGI | matching, from any source (a FIGI 13F or N-PORT files too) |
| composite FIGI, share-class FIGI | lookup only: 9 composite and 2 share-class FIGIs are on CUSIPs whose names or types differ ("Lookup only", 2026-10-25) |
| SEDOL, CINS, LoanX | matching, each under its verified Identifier Contract (ticket 125) |
| ticker, ticker + exchange, Bloomberg ID | lookup only: 17,941 (ticker, exchange) pairs are on two or more CUSIPs (55,057 CUSIPs, 2026-10-15 capture) |

**Each source does the same: look up, then master.** A source record carries
every identifier it has (a list where it has several, such as every listing
FIGI). The Merge Stage looks up each matching identifier:

| Found | Then |
|---|---|
| no Security | mint a new master id with all its identifiers |
| one Security | bind to it; its identifiers that no Security holds go into the Cross-reference |
| two Securities, by a listing FIGI | consolidate them automatically, the oldest id survives, then bind |

The same three steps for every source, in this order: look up CUSIP, then
ISIN, then FIGI; bind to the first Security found. A filed CUSIP and ISIN
never merge two Securities ("cusip is a seperate than isin it can never be
merges"): a holding whose CUSIP and ISIN lead to two Securities binds by the
CUSIP ("bind by CUSIP if matches if not then try isin"). Its other
identifiers are added only when no Security holds them ("add idintifiers from
other sources if not found in openfigi"), so an identifier never moves. On
2026 Q2, 154 filed pairs (241 holdings) lead to two Securities.

A wrong consolidation is split by a steward; both ids return and a Match
Exclusion stops the same records merging again. The Identifier Contract's
tolerance still switches automatic matching off when errors pass 5 per 10,000.
A new CUSIP whose listing FIGIs a Security holds joins it (one Security, both
CUSIPs, the old one with its last-seen date).

**Each source:**

- **OpenFIGI first, one load.** One target reads the CUSIP and the ISIN
  answers together; every bundle runs in parallel. Its record keeps the
  identifier asked and every listing's FIGI, ticker and ticker + exchange. On
  the 2026-10-15 capture, of 380,047 ISIN answers found, 350,867 share a
  listing FIGI with one CUSIP answer's Security, 29,169 mint their own and 11
  consolidate. The ISIN target, `figi_ids`, `figi_cusips`, `attach` and
  `answers_cusip` / `answers_isin` go. Each listing
  stays in the Listing table ("need a separate table for listing").
- **13F adds fields, second**, the same way: look up first, then mint.
- **N-PORT adds fields.** A holding's record looks up its CUSIP, ISIN or other
  issued identifier; it mints only when none is found. Its seven pairing steps
  (`cusips_found` to `fold`) go.
- **Form 4** finds a class by its trading symbol only among the Securities of
  the filing's issuer Company: one found attaches, none or two go to review
  (ticket 24). The ticker still joins nothing.

**Load order and Field Survivorship:** OpenFIGI, then 13F, then N-PORT
(operator, 2026-10-25: "this should be second source", then "Load and
priority"; this replaces "make openfigi priority 1 and 13f last" when ticket
138 is built).

**The Security's fields** (Field Survivorship: OpenFIGI, then 13F, then N-PORT):

| Field | From |
|---|---|
| name | OpenFIGI, 13F, N-PORT |
| security type, security type 2, market sector, security description | OpenFIGI: the one value the listings state, else the US composite's, else the ISIN country's composite's (description is new to MDM, "Same rule as name") |
| title of class, share class, issuer | 13F, N-PORT; the issuer by N-PORT's issuer LEI |
| asset category, issuer type, investment country, currency, restricted, derivative category | N-PORT: the value the most holdings file; a tie keeps none ("Most-filed value"); each holding keeps its own in silver |

The one Cross-reference serves every kind; Company, Person and Fund move onto
it in their own tickets ("Security now, others next tickets").

## Hard stops

| Never | Instead |
|---|---|
| Join two Securities on a ticker, a ticker and exchange, or a Bloomberg ID | Lookup only (2026-10-25, ticket 138). Today FIGI is lookup only too; ticket 138 makes it matching |
| Let one identifier sit on two Securities | Every proof counts `identifiers_on_two_masters`; it must be 0 |
| Let an OpenFIGI ISIN answer create a second Security for an issue its CUSIP answer already made | It joins that Security by a shared listing FIGI in MDM; FIGIs leading to two Securities merge them, the oldest surviving (built, A2a; a pair a steward split stays apart and goes to review) |
| Let a filed CUSIP and ISIN merge two Securities | Never: the record binds by its CUSIP, else an ISIN; an ISIN another Security holds is not added (2026-10-25, ticket 138) |
| Fill a security-level field by guessing between disagreeing listings | Take the primary listing's value, else leave it blank (decided) |
| Fold OpenFIGI's values into N-PORT's record | OpenFIGI keeps its own record on the same Security (decided) |
| Send a request to OpenFIGI or the SEC | Captured files only; a new request needs the operator's permission for that request |
| Load ISIN-only Securities in a second run over the same quarter | One run reads the quarter once (decided) |
| Pair a CUSIP with an ISIN in a source's own rules, or order one source's loads by kind of identifier | The Merge Stage pairs them through the Cross-reference (decided, ticket 138) |

## One Security, several sources

One Security is one issue (one CUSIP, or one ISIN when there is no usable
CUSIP). Each source keeps its own record on it; MDM merges them.

| Source | Dataset | Creates a Security? | Gives |
|---|---|---|---|
| SEC N-PORT | `sec.nport.security.v2` | Yes (decided) | CUSIP, every ISIN filed with it (ticket 138), issuer name as filed, title of class, issuer LEI, "issued by" link |
| SEC 13F | `sec.thirteenf.information_table.security.v1` | Yes (live) | CUSIP, name and title as filed, a filed FIGI |
| OpenFIGI | `openfigi.security.v3` (both kinds asked, ticket 138) | Yes, and first (waits for its switch-on) | All ten OpenFIGI fields and every listing; the CUSIP or ISIN asked and every listing's FIGI as identifiers |

The ranking that fills a field: OpenFIGI, then 13F, then N-PORT (operator,
2026-10-25: "this should be second source", then "Load and priority"; it
replaces "make openfigi priority 1 and 13f last", 2026-10-18).
`rules/merge/kinds/security.yaml`, `defaults.sources`.

## Keys and identifiers

Today's keys and identifiers. Ticket 138 replaces the identifier part with
"The mastering process" above.

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
`security-2026-10-24.isin-source-code`), one file of the Mastering Policy
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
| `nport-security-cusip` | N-PORT | CUSIP | creates one; a filed CUSIP and ISIN on two Securities bind by the CUSIP, the ISIN withheld from it (version 2026-10-26.2, "Filed CUSIP binds first") | waits for its switch-on (ticket 138); version 2026-10-20.1 was on from 2026-10-17 21:03 ET ("Switch on all six (Recommended)") |
| `nport-security-isin` | N-PORT | an ISIN (each filed with a CUSIP; the key of an ISIN-only one) | creates one | same; it replaces `nport-isin-security-isin` (retired with `sec.nport.security_isin.v1`) |
| `openfigi-security-cusip` | OpenFIGI (CUSIP asked) | CUSIP | creates one (version 2026-10-25.1) | waits for its switch-on (ticket 138); version 2026-10-23.1 was on from 2026-10-24 19:27 ET |
| `openfigi-security-isin` | OpenFIGI (ISIN asked) | ISIN | creates one (version 2026-10-25.1) | waits for its switch-on (ticket 138); version 2026-10-24.1 was on from 2026-10-24 19:27 ET |
| `openfigi-security-figi` | OpenFIGI | every listing FIGI | creates one; FIGIs reaching two or more Securities merge them (version 2026-10-26.1, "FIGI merges Securities") | waits for its switch-on and the FIGI contract's verification (ticket 138); it replaces `openfigi-isin-security-cusip` |

- **Look up first, then create, in a batch** (ticket 138): every record that
  finds a held Security binds first, then records that may create, then
  those that only join, so a value one record adds is found by the rest. One
  identifier value creates one Security per batch.
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
   1. `openfigi.security.v3`
   2. `sec.thirteenf.information_table.security.v1`
   3. `sec.nport.security.v2`

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

**N-PORT carries every ISIN filed with a CUSIP** (ticket 138 part B2; it
replaces "Use FIGI to add pairs too", 2026-10-15, and its rules
`figi-agree.yaml`, `figi-offers.yaml`, `figi-attach.yaml`, all deleted). MDM
binds the record by its CUSIP, else an ISIN; a listed ISIN failing its check
digit is left out, the record kept.

**OpenFIGI: one load, every listing FIGI an identifier** (ticket 138 part B1;
it replaces ticket 120's ISIN target, which joined an ISIN answer to its
CUSIP's Security through `figi-ids.yaml`, `isin-figi-cusips.yaml` and
`isin-attach.yaml`, all deleted). A CUSIP answer and an ISIN answer of one
security meet in MDM by a shared listing FIGI. Until part A2, an answer whose
FIGIs lead to two Securities waits for review, and the result can depend on
the order the bundles load.

**An ISIN-only holding keeps its own record, keyed by its ISIN** (ticket 138
part B2; the fold into a CUSIP's row by FIGI, `fold.yaml`, is deleted). It
meets the CUSIP's record filed with that ISIN in MDM, by the ISIN, and its
silver holding row is keyed by its ISIN.

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

## The listings detail table (decided; kept by ticket 138)

Operator, 2026-10-25: "changing my mind need a separate table for listing
ie figi, exchange, ticker, exchange" (replacing "we don't need this table").
One row per trading line, keyed by its listing FIGI, with its master id,
exchange code, currency, ticker and composite FIGI. A security is listed once
per exchange, but OpenFIGI gives a FIGI per trading line: on multi-currency
venues one stock has a line per currency, its ticker the same root plus a
currency code (90% of 292,567 same-exchange groups). OpenFIGI states no
currency, so it is read from the ticker's suffix (blank where none); (master
id, exchange, currency) still repeats on 71,974 of 2,184,699 lines, so it is
an index, not the key ("Listing FIGI as key; exchange + currency as
columns", 2026-10-25). The listing FIGI also matches through the
Cross-reference; ticker and ticker + exchange are lookup only there.

**The currency rule (built, part B3).** The codes are the RDM code set
`nport-filed-currencies` (the 80 three-letter codes N-PORT holdings file,
"N-PORT's filed codes (Recommended)", 2026-10-26), embedded in OpenFIGI's
source extract. A line's code is its ticker's last three letters when they
are one of those codes and something is left before them; its root is the
rest, else the whole ticker. A line gets its code as its currency only where
its exchange gives the identifier two or more lines, one root and every
ticker different: so the root alone as a line beside coded lines gets none,
and a repeated code, two roots or a single line give none (a single line's
ticker ends in a code by chance 121,414 times). Lines without an exchange
code form one group. Steps: `line-counts.yaml`, `lines.yaml`, `listing.yaml`.
The (master id, exchange, currency) index waits for its first reader.

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

Ticket 138 (built in the files, parts B1 and B2; its OpenFIGI rules wait
for their switch-on after the merge part A2):

1. N-PORT's read decides which identifiers OpenFIGI is asked (the capture).
2. GLEIF `umbrellas` (sub-fund pairs; read only).
3. N-PORT funds.
4. OpenFIGI `mastering`: one target over the CUSIP and the ISIN answers
   together, every bundle in parallel. Each record carries the identifier
   asked and every listing's FIGI; it joins the Security holding any of
   them, else creates one.
5. 13F, then Securities `mastering` (N-PORT): each looks up first, then
   creates.

Inside one batch the Merge Stage binds every record that finds a held
Security before any record creates one, so a value it adds is found by the
rest of the batch.

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
