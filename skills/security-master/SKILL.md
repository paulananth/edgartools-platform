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

Rules marked **live** are in `rules/` and proved. Rules marked **decided** are
ruled and being built (ticket 120); do not describe them to anyone as
running until the ticket ticks them.

## Hard stops

| Never | Instead |
|---|---|
| Join two Securities on a FIGI or a ticker | They are cross-references: lookup only (operator, 2026-10-20: "Lookup only for now") |
| Let one identifier sit on two Securities | Every proof counts `identifiers_on_two_masters`; it must be 0 |
| Let OpenFIGI create a Security | OpenFIGI's records join the Security holding their CUSIP or ISIN, or wait (live) |
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
| SEC N-PORT | `sec.nport.security.v1` | Yes (live) | CUSIP, ISIN (FIGI-agreed), issuer name as filed, title of class, issuer LEI, "issued by" link |
| SEC 13F | `sec.thirteenf.information_table.security.v1` | Yes (live) | CUSIP, name and title as filed, a filed FIGI |
| OpenFIGI | `openfigi.security.v1` (CUSIP), `openfigi.security_isin.v1` (ISIN) | Never: joins or waits (live) | All ten OpenFIGI fields (decided; today name, FIGIs, ticker) |

The ranking that fills a field: OpenFIGI first, then N-PORT, then 13F
(operator, 2026-10-18: "make openfigi priority 1 and 13f last"; ticket 84).
`rules/merge/kinds/security.yaml`, `defaults.sources`.

## Keys and identifiers

- **Record key (decided):** N-PORT gives one record per Security keyed by its
  CUSIP, else its ISIN (operator, 2026-10-20: "One master record ... why
  can't one run captures all attributes and builds the cross reference").
  The key has no fixed format; CUSIP and ISIN are each checked as
  identifiers. Live today: two N-PORT datasets, one keyed by CUSIP, one by
  ISIN.
- **Identifiers (match):** `cusip` and `isin`, each verified by its check
  digit (`rules/identifiers/`).
- **Cross-references (lookup only):** listing FIGI, composite FIGI,
  share-class FIGI, ticker. `mdm.cross_reference_lookup` finds a Security by
  them; no rule matches on them.

## Matching (live, `rules/merge/kinds/security.yaml`)

1. A record joins the one Security holding its CUSIP, or creates one (13F,
   N-PORT).
2. An N-PORT record also joins by the ISIN it carries; its CUSIP and ISIN
   pointing at two Securities goes to review, never binds.
3. An ISIN-only record joins the Security holding its ISIN, or creates one.
4. OpenFIGI records join by CUSIP or ISIN and wait otherwise.

**An ISIN goes with a CUSIP only when OpenFIGI agrees** (operator,
2026-10-15: "Use FIGI to add pairs too"): the filed CUSIP and ISIN share a
FIGI, and neither is offered twice: the CUSIP is offered one ISIN and the
ISIN one CUSIP (`figi-agree.yaml`, `figi-offers.yaml`, `figi-attach.yaml`).

**An ISIN-only holding whose ISIN is already on a CUSIP's row is folded into
that row before MDM (decided)**, so no ISIN reaches MDM twice.

**Share-class FIGI does not join records** (operator, 2026-10-20: "Lookup
only for now (Recommended)"). Before proposing it, count the ISIN-only
Securities that share a share-class FIGI with a CUSIP Security.

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

1. the one listing with exchange code `US`;
2. else the composite listing of the country in the ISIN's first two letters,
   from the RDM code set country → OpenFIGI composite exchange code (approved
   by the operator before use);
3. else blank: the listings table still holds every value.

Measured on 2026 Q2 (733,538 found Securities): 30,722 have several
listings; 11,680 disagree on name or share-class FIGI; 8,928 of those have one
US listing, 2,706 none, 46 two. A Security OpenFIGI did not find (5%) keeps
its N-PORT and 13F fields only.

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

1. GLEIF `umbrellas` (sub-fund pairs; read only).
2. OpenFIGI `answers_cusip`, `answers_isin` (the captured answers; read only).
3. N-PORT funds.
4. Securities `mastering`: one run over the quarter (decided: CUSIP and ISIN
   Securities together).
5. OpenFIGI's Security records, which join what N-PORT made.

`rules/source-sequence.yaml` holds the order; a source reads another
finished run by `{run: {source, target, step}}` (Bookkeeping SPEC).

## Securities known only from 13F

Operator, 2026-10-20: "13F us cusip, first then if not use ticker", then,
13F filing no ticker, "Ask by the filed FIGI (Recommended)": ask OpenFIGI by
CUSIP, then by the FIGI the 13F filer gave. A ticket, with counts; no request
until the operator permits it.

## Proving a change

- A change to a Security contract or merge rule needs the full two-pass test
  (`rules test`): records reach MDM, no identifier on two Securities, and the
  second pass changes nothing. 2026 Q2 takes about 2 h 20 min a pass on a
  laptop; keep it on power ("Make the Securities run faster", ticket 122).
- Report counts only: Securities, held back by reason, identifiers on two
  Securities. Never an identifier or a name from the data.
