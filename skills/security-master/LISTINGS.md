# OpenFIGI fields and the listings detail table

Part of the `security-master` skill: [SKILL.md](SKILL.md) says when to read this.

## Every OpenFIGI field (decided)

Operator: "all fields from open figi must be in the security
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
on (operator: "Use the primary exchange listing", then "US, else
the ISIN's country"). OpenFIGI marks no primary listing, so:

1. the one US composite (exchange code `US`, its own composite) decides,
   a blank value too;
2. only without one, the composite listing of the country in the ISIN's
   first two letters, from the RDM code set `openfigi-country-composite`
   version 1 (11 countries, approved: "Only the 11 countries seen
   (Recommended)"), embedded in the answers reading as `read.references` and
   held equal to the published set by a test;
3. else blank: the listings table still holds every value.

Few found Securities disagree on a security-level field; the US composite
settles most of those, the country step some, and the rest stay blank.
OpenFIGI's exchange-code list names no countries, and for most countries tried
the home composite never appears in the answers, which is why the code set is
short. A Security OpenFIGI did not find keeps its N-PORT and 13F fields only.

## The listings detail table (decided)

Operator: "changing my mind need a separate table for listing
ie figi, exchange, ticker, exchange" (replacing "we don't need this table").
One row per trading line, keyed by its listing FIGI, with its master id,
exchange code, currency, ticker and composite FIGI. A security is listed once
per exchange, but OpenFIGI gives a FIGI per trading line: on multi-currency
venues one stock has a line per currency, its ticker the same root plus a
currency code (most same-exchange groups). OpenFIGI states no
currency, so it is read from the ticker's suffix (blank where none); (master
id, exchange, currency) still repeats on some lines, so it is
an index, not the key ("Listing FIGI as key; exchange + currency as
columns"). The listing FIGI also matches through the
Cross-reference; ticker and ticker + exchange are lookup only there.

**The currency rule (built, part B3).** The codes are the RDM code set
`nport-filed-currencies` (the 80 three-letter codes N-PORT holdings file,
"N-PORT's filed codes (Recommended)"), embedded in OpenFIGI's
source extract. A line's code is its ticker's last three letters when they
are one of those codes and something is left before them; its root is the
rest, else the whole ticker. A line gets its code as its currency only where
its exchange gives the identifier two or more lines, one root and every
ticker different: so the root alone as a line beside coded lines gets none,
and a repeated code, two roots or a single line give none (a single line's
ticker often ends in a code by chance). Lines without an exchange
code form one group. Steps: `line-counts.yaml`, `lines.yaml`, `listing.yaml`.

**What listings are for: resolving a venue's key to its Security (decided;
being built).** Operator: "Listing table is
inside mdm primary use is the resolution of securities trading in different
exchanges or venues". So the lookups run from a venue's key to the Security,
never from a Security to its listings; the (master id, exchange, currency)
index is dropped.

- **Where they live** ("1", Index on the Security, 19:05 ET): the listings
  stay inside the Security's record; MDM keeps a lookup from (exchange code,
  ticker) and from (MIC, ticker) to the Security on every store (PostgreSQL, MySQL). It follows the
  Security's own history and merges: a merged-away or retired Security leaves
  it; a listing a later answer drops leaves it. No new kind of row. Built as
  configuration: `detail_lookups` in `rules/mastering/engine-v1.yaml` (kind
  `security`, detail `listings`, keys `mic` and `exchange`, each with
  `ticker`); the engine's `detail_lookups.py` names no kind or field and
  shares the name lookup's coverage and owner rebuild (`master_index.py`).
  A listing with a MIC is found by both keys, so a caller holding OpenFIGI's
  code needs no crosswalk.
- **The venue is its ISO 10383 MIC** (operator, 19:12 ET: "The exchange code
  is wrong why are we not using MIC codes"). OpenFIGI states only Bloomberg's
  exchange code (UN, UW, US), never a MIC, so each listing keeps that code as
  given and gets its MIC beside it from an RDM code set ("MIC beside, from
  RDM", 19:14 ET); the lookup is MIC + ticker. The code set is RDM's
  `iso-10383-mic` (every active MIC, segments under their operating MIC; its
  crosswalk gives 246 MICs their OpenFIGI code), embedded in OpenFIGI's
  source extract as `read.references.mic`; London's LN to XLON was set by
  hand (no code holds a majority of XLON's answers). A composite (US, GR, CN) is no
  venue and has no MIC; it is found by its exchange code. The code set is
  OpenFIGI's own: one filter request per active MIC, recording the exchange
  codes each answer gives ("Ask OpenFIGI by MIC", 19:20 ET); no vendor's
  table is used.
- **A listing FIGI** finds its Security through the identifier index, since
  every listing FIGI is the Security's identifier (part A2a); no second lookup.
- **Every match, never one picked.** Nearly every (exchange code, ticker) pair reaches
  one Security, but a few reach two or more (the market sector separates none
  of them), some reach two or more listings, and many listings have no
  exchange code or ticker. The answer names every Security a pair reaches.
- **Lookup only.** An exchange code and ticker never take part in matching:
  a reused ticker would merge two Securities.
- **Security-only, by decision.** Operator, 19:10 ET: "this is not generic
  anymore which is fine this must be added to security master skills". The
  venue lookup is the Security's own; it is documented here, not in the
  generic MDM skills.

Operator: "Maybe create a security detail table and keep it in
the mdm", then "Detail rows set in config (Recommended)".

- A Dataset Contract states its detail lists in configuration (OpenFIGI:
  `listings`, keyed by FIGI), and a master's record carries them. On
  installed stores no separate detail table is written (migration 028 retired
  what kept `mdm.detail_version`); the venue lookup above is the one
  Security-only part.
- A Security's CUSIP and ISIN answers make **one set of listings, joined by
  FIGI**; each row records which answer gave it ("One set, joined by FIGI").
- Each load replaces a Security's listings. **A listing a later answer drops
  is ended, its history kept** ("End it, keep history").
