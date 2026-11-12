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
in the files** are in `policy.yaml`; a new run uses them. OpenFIGI's earlier
rules (switched on; those switch-ons ended with them)
were replaced by one dataset,
`openfigi.security.v4`, and three rules that wait for their switch-on.

## The mastering process (decided; being built)

The operator replaced the per-kind design ("secutiy is the kind
cusip and isin are diffrant identifiers of the same securities", "there
should be one processing with all the identifier", "first lookup if not exists
then master", "mastering must create an unique id and the unique id joins with
all the other tables cross refrence and silver"). Built so far: a record
carries lists of identifiers (part A1), OpenFIGI's one load with every
listing FIGI as an identifier and one master id in silver (part B1),
N-PORT's pairing by FIGI removed (part B2), each listing's currency (part
B3), the merge by a shared FIGI (part A2a: the FIGI rule's `on_several:
merge`), the CUSIP-first bind (part A2b: N-PORT's CUSIP rule's
`on_conflict: first`); all switched on ("Do limited
testing and switch on"). The
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
| composite FIGI, share-class FIGI | lookup only: 9 composite and 2 share-class FIGIs are on CUSIPs whose names or types differ ("Lookup only") |
| SEDOL, CINS, LoanX | matching, each under its verified Identifier Contract |
| ticker (letters and digits, one to nine once a slash, dash or dot is dropped) | OpenFIGI issues it; only the Form 4 rule matches by it (operator, "Yes, Form 4 route only"): a few sit on two or more CUSIPs, at most 3, so its claim is 3 and a symbol reaching several Securities goes to review |
| ticker + exchange, Bloomberg ID | lookup only: many raw (ticker, exchange) pairs are on two or more CUSIPs, mostly a bond's description written in the ticker field |

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
other sources if not found in openfigi"), so an identifier never moves. A
few filed pairs lead to two Securities.

A wrong consolidation is split by a steward; both ids return and a Match
Exclusion stops the same records merging again. The Identifier Contract's
tolerance still switches automatic matching off when errors pass 5 per 10,000.
A new CUSIP whose listing FIGIs a Security holds joins it (one Security, both
CUSIPs, the old one with its last-seen date).

**Each source:**

- **OpenFIGI first, one load.** One target reads the CUSIP and the ISIN
  answers together; every bundle runs in parallel. Its record keeps the
  identifier asked and every listing's FIGI, ticker and ticker + exchange. Most
  ISIN answers share a listing FIGI with one CUSIP answer's Security; the
  rest mint their own, and a few consolidate. The ISIN target, `figi_ids`, `figi_cusips`, `attach` and
  `answers_cusip` / `answers_isin` go. Each listing
  stays in the Listing table ("need a separate table for listing").
- **13F adds fields, second**, the same way: look up first, then mint.
- **N-PORT adds fields.** A holding's record looks up its CUSIP, ISIN or other
  issued identifier; it mints only when none is found. Its seven pairing steps
  (`cusips_found` to `fold`) go.
- **Form 4** finds its Security by the issuer's trading symbol: the
  `security_symbols` target reads only each filing's issuer and symbol, and
  `form4-security-ticker` binds the symbol to the one Security OpenFIGI gave
  that ticker to. None held waits unbound, several go to review, and it makes
  nothing, so OpenFIGI is mastered first. The symbol is never an identifier of
  the Security it finds. A single-valued identifier that fails its shape refuses
  the whole record, so OpenFIGI's record rule leaves a bond's description in the
  ticker field empty instead.

**Load order and Field Survivorship:** OpenFIGI, then 13F, then N-PORT
(operator: "this should be second source", then "Load and
priority"; this replaces "make openfigi priority 1 and 13f last" when ticket
138 is built).

**The Security's fields** (Field Survivorship: OpenFIGI, then 13F, then N-PORT):

| Field | From |
|---|---|
| name | OpenFIGI, 13F, N-PORT |
| security type, security type 2, market sector, security description | OpenFIGI: the one value the listings state, else the US composite's, else the ISIN country's composite's (description is new to MDM, "Same rule as name") |
| title of class, share class, issuer | 13F, N-PORT; the issuer by N-PORT's issuer LEI |
| asset category, issuer type, investment country, currency, restricted, derivative category | N-PORT: the value the most holdings file; a tie keeps none ("Most-filed value"). Only on the Security in MDM; the holding row in silver does not repeat them (one system of record), except its currency code, the unit of its own value ("Keep it on the row"). **To build**: today they are in silver only |

The one Cross-reference serves every kind; Company, Person and Fund move onto
it in their own tickets ("Security now, others next tickets").

## Hard stops

| Never | Instead |
|---|---|
| Join two Securities on a ticker, a ticker and exchange, or a Bloomberg ID | Lookup only. Today FIGI is lookup only too; "The mastering process" makes it matching |
| Let one identifier sit on two Securities | Every proof counts `identifiers_on_two_masters`; it must be 0 |
| Let an OpenFIGI ISIN answer create a second Security for an issue its CUSIP answer already made | It joins that Security by a shared listing FIGI in MDM; FIGIs leading to two Securities merge them, the oldest surviving (built, A2a; a pair a steward split stays apart and goes to review) |
| Let a filed CUSIP and ISIN merge two Securities | Never: the record binds by its CUSIP, else an ISIN; an ISIN another Security holds is not added |
| Fill a security-level field by guessing between disagreeing listings | Take the primary listing's value, else leave it blank (decided) |
| Fold OpenFIGI's values into N-PORT's record | OpenFIGI keeps its own record on the same Security (decided) |
| Send a request to OpenFIGI or the SEC | Captured files only; a new request needs the operator's permission for that request |
| Load ISIN-only Securities in a second run over the same quarter | One run reads the quarter once (decided) |
| Pair a CUSIP with an ISIN in a source's own rules, or order one source's loads by kind of identifier | The Merge Stage pairs them through the Cross-reference (decided) |

## One Security, several sources

One Security is one issue (one CUSIP, or one ISIN when there is no usable
CUSIP). Each source keeps its own record on it; MDM merges them.

| Source | Dataset | Creates a Security? | Gives |
|---|---|---|---|
| SEC N-PORT | `sec.nport.security.v2` | Yes (decided) | CUSIP, every ISIN filed with it, issuer name as filed, title of class, issuer LEI, "issued by" link |
| SEC 13F | `sec.thirteenf.securities.v2` | Yes (live) | CUSIP, name and title as filed, a filed FIGI |
| OpenFIGI | `openfigi.security.v4` (both kinds asked) | Yes, and first (on) | All ten OpenFIGI fields and every listing; the CUSIP or ISIN asked and every listing's FIGI as identifiers |

The ranking that fills a field: OpenFIGI, then 13F, then N-PORT (operator: "this should be second source", then "Load and priority"; it
replaces "make openfigi priority 1 and 13f last").
Each of the three runs as a `mastering` target of Bookkeeping, and records its files in the
Change Journal: read, reduce, combine, record, prepare, merge, processed.
`rules/merge/kinds/security.yaml`, `defaults.sources`.

## Keys and identifiers

Today's keys and identifiers. "The mastering process" above replaces the
identifier part.

- **Record key (decided):** N-PORT gives one record per Security keyed by its
  CUSIP, else its ISIN (operator: "One master record ... why
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
  No rule matches on any of them. Every listing's FIGI is an identifier
  (OpenFIGI, part B1), and a listing's (exchange code, ticker) finds its
  Security through the venue lookup (the listings section).

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
| `security-cusip` | 13F | CUSIP | creates one | switched on |
| `nport-security-cusip` | N-PORT | CUSIP | creates one; a filed CUSIP and ISIN on two Securities bind by the CUSIP, the ISIN withheld from it (version 2026-10-26.2, "Filed CUSIP binds first") | switched on ("Do limited testing and switch on") |
| `nport-security-isin` | N-PORT | an ISIN (each filed with a CUSIP; the key of an ISIN-only one) | creates one | switched on ("Do limited testing and switch on") |
| `openfigi-security-cusip` | OpenFIGI (CUSIP asked) | CUSIP | creates one (version 2026-10-25.1) | switched on ("Do limited testing and switch on") |
| `openfigi-security-isin` | OpenFIGI (ISIN asked) | ISIN | creates one (version 2026-10-25.1) | switched on ("Do limited testing and switch on") |
| `openfigi-security-figi` | OpenFIGI | every listing FIGI | creates one; FIGIs reaching two or more Securities merge them (version 2026-10-26.1, "FIGI merges Securities") | switched on ("Do limited testing and switch on") |

- **Look up first, then create, in a batch**: every record that
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
  - **Verification:** verified on a Proving Run: no identifier
    on two Securities, a second pass changed nothing.
  - **Tolerance:** after 10,000 decisions, more than 5 violations per 10,000
    switch the rule off automatically, and its records go to review until a
    newly verified contract is registered (`docs/specs/mdm/policy-language.md`).
- **Which identifiers join** (`identifiers.<name>.sources`):
  - CUSIP joins from 13F, N-PORT and OpenFIGI;
  - ISIN joins from both N-PORT datasets and OpenFIGI's ISIN records.
  - FIGI and ticker are in neither list: they never join.

### 2. Survivorship: which value the Security shows

Every field any source supplies reaches the Security (a kind-level
`defaults` rule, operator): a field only one source gives comes from
it; the priority decides only where several give it. For each field
(`edgar_warehouse/mdm/survivorship.py`, ranked by the engine's
`survivorship::rank`):

1. **A steward's override wins.** A source that disagrees with it opens an
   `override_source_disagreement` review. Two overrides at once are refused.
2. **Otherwise the highest-priority source wins**, in the order of
   `defaults.sources`:
   1. `openfigi.security.v4`
   2. `sec.thirteenf.securities.v2`
   3. `sec.nport.security.v2`

   (operator: "make openfigi priority 1 and 13f
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
7. **A disagreement never blanks a field** (operator:
   "mastering is all about having good values not blanks, use priority").
   No field rule asks the sources to agree. To find a disagreement, read the
   `master_field` view where `conflict_count` is above 0. Within one source,
   filers that disagree on `share_class` still give no letter (`share_class_one_letter`). Both rulings are revisited once real examples exist.

What this gives today: OpenFIGI fills the name: it
states one name for nearly every CUSIP. OpenFIGI gives no title, so
N-PORT, then 13F, fill the title of class. A Security OpenFIGI did not find
takes N-PORT's filed name, else 13F's.

**Decided, built, not yet proved:** the one N-PORT dataset replaced the two
in this list and in the matching rules. A change to this list or to a rule
moves the Mastering Policy's digest, so it needs its test run and the
operator's approval of the new digest (data-onboarding, "a merge-rule change
moves pinned digests").

**The key of a Security is its CUSIP, else its ISIN, else its SEDOL, else its LoanX, and a holding with only a FIGI is a find-only record** (FIGI is the fourth class of the same path, a cross-reference that finds the Security OpenFIGI gave it to and never creates one; most FIGI-only FIGIs are not held yet and wait) (operator: "You can not build every make isin work for others", "Always build generic"). The no-CUSIP branch (`no_cusip_*` in the N-PORT rules) takes the first class a holding files, `key_kind` names it and `record.yaml` gives the identifier of that class. A SEDOL or LoanX filed beside a CUSIP or an ISIN is stored on the Security and never matches: funds often file one SEDOL on several Securities, and an unrestricted rule merged two CUSIP Securities. Their rules match only a record keyed by their class (`field_in_set@1` on `provenance.matching.key_class`), and the keyed records are published in the second target, `mastering_other_keys`, which reads the first run's combine with `record.yaml`'s `batch` context set to `other`. A new class is a lookup set, one line in each key coalesce (source.yaml, issuers.yaml, holding-rows.yaml) and one rule: the rules language has no list, so an engine key-class list waits for a fourth class.

### 3. Held back

A record a contract sets aside never reaches matching. It waits with an open
review ("Held back, never dropped", below).

**A Security has one issuer at a time** (relationship types version 3; operator). Two source records of one Security that name two issuers over overlapping periods set both ISSUED_BY links aside and open the review `conflicting_targets`; a changed issuer is two periods of history. This is the same answer inside one record (two issuers, no link).

**N-PORT carries every ISIN filed with a CUSIP** (it
replaces "Use FIGI to add pairs too" and its rules
`figi-agree.yaml`, `figi-offers.yaml`, `figi-attach.yaml`, all deleted). MDM
binds the record by its CUSIP, else an ISIN; a listed ISIN failing its check
digit is left out, the record kept.

**OpenFIGI: one load, every listing FIGI an identifier** (it replaces the earlier ISIN target, which joined an ISIN answer to its
CUSIP's Security through `figi-ids.yaml`, `isin-figi-cusips.yaml` and
`isin-attach.yaml`, all deleted). A CUSIP answer and an ISIN answer of one
security meet in MDM by a shared listing FIGI. Until part A2, an answer whose
FIGIs lead to two Securities waits for review, and the result can depend on
the order the bundles load.

**An ISIN-only holding keeps its own record, keyed by its ISIN** (the fold into a CUSIP's row by FIGI, `fold.yaml`, is deleted). It
meets the CUSIP's record filed with that ISIN in MDM, by the ISIN, and its
silver holding row is keyed by its ISIN.

**ISSUED_BY reaches an SEC filer's Securities only through GLEIF.** An N-PORT
holding names its issuer by LEI, and SEC filings almost never state one. So
"ISSUED_BY" reaches an SEC Company only where its GLEIF record joined it by
the SEC-GLEIF name rules. Measure that lookup through MDM's links, never
through the filing's own LEI. A Form 4 class attaches by the filed trading
symbol through OpenFIGI's ticker, not through this link.

**Share-class FIGI does not join records** (operator: "Lookup
only for now (Recommended)"). Before proposing it, count the ISIN-only
Securities that share a share-class FIGI with a CUSIP Security; they have been few.

## Every Security uniquely identifiable

Operator: "Securities and funds must be uniquely
identifiable". A Security exists only for an identifier issued for it; a
fund's own label never makes one:

| A holding identified by | Share of holdings | Becomes |
|---|---|---|
| CUSIP | about two thirds | a Security (live) |
| ISIN, no CUSIP | about one in seven | a Security (live) |
| SEDOL, CINS or LoanX in the "other" field | few | a Security, each by its verified Identifier Contract (decided: "SEDOL, CINS, LoanX (Recommended)") |
| A Bloomberg ID or FIGI in the "other" field | few | a cross-reference only; never joins |
| A ticker only | few (mostly futures, forwards, options) | no Security: a ticker is not unique |
| The fund's own ID only | about one in six (mostly loans, then forwards and swaps) | **not a Security** (decided: "Not Securities (Recommended)"): a contract between two parties stays a holding under its fund |

Live today: a SEDOL (seven characters, check digit) or a LoanX (LX and six digits),
told apart by the "other identifier" label and shape, **joins** the Security its holding already
keys by its CUSIP, else its ISIN; the label `CINS` is not read (nearly all such rows are CUSIPs
under the wrong label). A Security keyed by one of them alone, with no CUSIP or ISIN, is not made
yet. A fund that files without a series id is its registrant's Company, not a second
master keyed by the same CIK (operator: "the company is the fund").

## Share classes

- **A security's share class is a field, not a record** (operator: "Field on the Security (Recommended)"). The share-class FIGI is
  a field and a cross-reference on each Security; it finds every Security of
  one class. No Share Class kind. Few found
  identifiers carry one, mostly equities, and a class rarely spans three or
  more identifiers.
- **A fund's share classes (Class A, Class I) are not Securities.** They
  belong to the fund series, not here. Operator: "Profile first
  (Recommended)".

## Every OpenFIGI field (decided)

Read [LISTINGS.md](LISTINGS.md) before changing which OpenFIGI field lands where, or answering what a Security holds from OpenFIGI.

## The listings detail table (decided)

Read [LISTINGS.md](LISTINGS.md), "The listings detail table", before changing the listings table, the primary listing, or anything keyed by a listing FIGI.

## Held back, never dropped (live)

| Reason | Means |
|---|---|
| `invalid_cusip_checksum`, `invalid_cusip` | The filed CUSIP fails its check digit or shape |
| `invalid_isin_checksum`, `invalid_isin` | The same for an ISIN |
| `missing_record_identity` | No usable CUSIP or ISIN |
| `placeholder_name_of_issuer` | A name such as NONE, NULL, UNKNOWN, TBD: withheld |
| `not_found_by_openfigi` | OpenFIGI found nothing for the identifier asked |

Each waits with an open review.

## Run order

Built in the files; the OpenFIGI rules wait for their switch-on:

1. N-PORT's read decides which identifiers OpenFIGI is asked (the capture).
2. GLEIF `lei` (sub-fund pairs; read only).
3. N-PORT funds.
4. OpenFIGI `mastering`: one target over the CUSIP and the ISIN answers
   together, every bundle in parallel. Each record carries the identifier
   asked and every listing's FIGI; it joins the Security holding any of
   them, else creates one.
5. 13F, then Securities `mastering` (N-PORT): each looks up first, then
   creates.
6. Securities `mastering_other_keys` (N-PORT), then the Form 4
   `security_symbols` (ownership): the Securities keyed by a SEDOL
   or a LoanX, and the symbols a Form 4 files, each after the Securities they
   look up exist. Neither is in `rules/source-sequence.yaml`, which names one
   target a source.

Inside one batch the Merge Stage binds a record to a Security that is already
stored; a Security a record of the same batch creates is not found by another
record of it (a SEDOL-keyed record loaded with its CUSIP's record made a
second Security: 7 Securities, not 5). A record that must find another's
value is published in a later batch.

`rules/source-sequence.yaml` holds the order; a source reads another
finished run by `{run: {source, target, step}}` (Bookkeeping SPEC).

## Securities known only from 13F

Operator: "13F us cusip, first then if not use ticker", then,
13F filing no ticker, "Ask by the filed FIGI (Recommended)": ask OpenFIGI by
CUSIP, then by the FIGI the 13F filer gave. A ticket, with counts; no request
until the operator permits it.

## Proving a change

**Check the premise in the rules before measuring.** A count taken with code a ticket has since removed is not evidence (folded Securities were once counted with a FIGI fold that had already been ended, and the operator ruled on that number). Read the current rules for the step first, then measure the behaviour that runs, with a test.

Prove a Security contract or merge rule at the level [Choose the cheapest proof](../mdm-engineering/SKILL.md#choose-the-cheapest-proof) names. The whole quarter is that proof only when the claim is the quarter's totals or switch-on. When it is, a quarter, one record per Security, takes hours a pass on a laptop; keep it on power ("Make the Securities run faster").

OpenFIGI first was switched on from the completed figi-full store. CUSIP answers created the Securities. ISIN bundle 1 held the new case, one CUSIP offered two ISINs that share a FIGI. Bundles 2–8 stayed unchecked. Its ISIN target reads the complete CUSIP runs' `figi_ids`, so those CUSIP runs finish first in the same store.
- Report counts only: Securities, held back by reason, identifiers on two
  Securities. Never an identifier or a name from the data.

## RDM code sets and their sources

Reloaded from `rules/reference/published/` by `scripts/dev/reload_rdm.py`; the words of each are in
`WORDS` there.

| Code set | Source | Ticket |
|---|---|---|
| `openfigi-country-composite` | OpenFIGI mapping answers, measured on the local capture: the countries whose ISINs come back with the country's own composite exchange code | 120 |
| `iso-10383-mic` | ISO 10383 market identifier codes (every active MIC, ISO's market name as label), with OpenFIGI's exchange-code answers as a crosswalk for 246 MICs | 138 |
| `nport-filed-currencies` | the 80 three-letter currency codes the N-PORT 2026 Q2 holdings file, ISO 4217 names as labels | 138 |
