# Research NAICS/GICS/alternative classification systems for MDM companies

Type: research
Status: resolved

## Question

Which industry classification system(s) beyond SIC should EdgarTools
Platform add for MDM companies -- NAICS, GICS, another candidate (e.g.
ISIC), or a combination -- and what does actually sourcing per-company
codes for that system look like?

Cover, for each candidate system (at minimum NAICS and GICS):

1. **Licensing.** Is the classification's structure/taxonomy itself
   freely usable and redistributable (NAICS: yes, US Census Bureau
   public standard), or does it require a data license (GICS: owned by
   S&P/MSCI -- confirm current licensing terms and whether a no-cost or
   low-cost tier exists for a project at this platform's scale)?
2. **Per-company data source.** A classification's TAXONOMY (the code
   list itself) is a separate question from actually knowing which code
   applies to a given company. For each system: does SEC/EDGAR already
   capture and expose a per-filer code anywhere (e.g. some forms have a
   NAICS field on their cover page -- confirm which forms, how populated
   coverage is), or would per-company codes require an external
   crosswalk/vendor dataset? A SIC-to-NAICS public crosswalk table
   exists (US Census Bureau) -- is deriving NAICS from the SIC code
   EdgarTools already has a viable path, and how lossy/ambiguous is that
   mapping (SIC and NAICS don't have a clean 1:1 correspondence)?
3. **Structure/hierarchy.** Is the system flat (like SIC's 4-digit code)
   or tiered (NAICS: 2-6 digit sector/subsector/industry-group/industry/
   national-industry; GICS: sector/industry-group/industry/
   sub-industry)? This affects the "where does it live" design question
   this map has deferred to fog.
4. **Real-world usage.** Which system(s) do peer financial-data platforms
   and typical downstream consumers (dashboards, screening tools,
   industry comparison) actually expect/use in practice -- does this
   favor one system over another for this platform's actual audience?

## Answer

### Recommendation

**Neither NAICS nor GICS is worth adding to MDM right now.** Add neither as
a second classification system. Instead, derive SIC's own native hierarchy
(Division letter, 2-digit Major Group, 3-digit Industry Group — all already
implicit in the `sic_code` value EdgarTools has for every company today) —
this is the cheapest possible way to get "industry grouping/rollup" and it
satisfies most of the motivation that would otherwise point at NAICS/GICS,
with none of the downsides below. This confirms and extends the note
already added to `map.md`'s "Not yet specified" section.

If a genuine appetite remains for a *second, independent* classification
system after that, rank the two candidates as:

1. **NAICS** — technically feasible, free taxonomy, but any per-company
   value would be a **derived approximation**, not authoritative source
   data, because SEC does not capture NAICS for the operating-company
   universe MDM tracks and the SIC→NAICS crosswalk is officially
   many-to-many, not 1:1. Worth doing only if the platform is comfortable
   labeling the column as "approximate, crosswalk-derived" rather than
   "SEC-sourced" the way `sic_code` is.
2. **GICS** — not viable at this platform's scale. It is the classification
   real equity-research/sector-dashboard users expect, but there is no free
   or low-cost path to per-company GICS data at all (proprietary
   end-to-end), and S&P/MSCI's licensing is enterprise-quote-only with
   real usage restrictions (no resale, no redistribution, no use to build
   "securities products or indices," GICS Direct "priced based on client
   type and size" with no published rate card). This isn't a "pay a modest
   fee" gap — it's "there is no self-serve tier to pay into."

The strongest single piece of evidence for the recommendation: SIC already
has the same 4-tier depth as GICS (Division → Major Group → Industry Group
→ Industry, vs. GICS's Sector → Industry Group → Industry → Sub-Industry),
and three of SIC's four tiers are free, zero-license, zero-new-source-data
prefix truncations of a code EdgarTools already has 100% coverage and
verified accuracy on — vs. NAICS/GICS, where either the license (GICS) or
the per-company data fidelity (NAICS) is a real, unresolved cost.

---

### 1. Licensing

**NAICS** — Public domain / free, confirmed. NAICS is developed and
published by the U.S. Census Bureau (with OMB/Statistical Policy
Directive backing) and, as a work of the U.S. federal government, carries
no copyright/license restriction — the code list, definitions, and
manual are freely usable and redistributable. Census Bureau data
generally is released under a CC0-equivalent public-domain dedication.
Source: [US Census Bureau NAICS](https://www.census.gov/naics/),
[Census Multimedia/Data Usage Policy](https://www.census.gov/library/multimedia-usage-policy.html).

**GICS** — Proprietary, jointly owned by S&P Global (formerly McGraw
Hill Financial / Standard & Poor's) and MSCI Inc., a registered
trademark of both. Two distinct things are restricted, not just one:
  - **The per-company classification dataset** ("GICS Direct" — the
    current classification for 44,000+ companies globally, delivered by
    FTP/data-vendor feed) is a commercial product. MSCI's own FAQ states
    pricing is "based on client type and size" with no public rate card.
    Source: [MSCI GICS FAQ](https://www.msci.com/documents/10199/5973a128-47f0-4317-b083-716a10207b50),
    [GICS Direct brochure](https://www.spglobal.com/content/dam/spglobal/mi/en/documents/general/GICS-Direct-Brochure.pdf).
  - **Redistribution/derivative use of GICS itself** is contractually
    restricted for licensees: sample third-party terms (FIS) explicitly
    prohibit using GICS "to create any securities products or indices,"
    altering/modifying/adapting any GICS component, or reselling/
    transferring GICS to other parties. Source:
    [FIS GICS Service Third Party Data Terms](https://www.fisglobal.com/-/media/fisglobal/files/pdf/policy/third-party-terms/gics-service-third-party-data-terms.pdf).
  - The **methodology/taxonomy document itself** (sector/industry-group/
    industry/sub-industry names and definitions) is publicly readable —
    S&P/MSCI publish the methodology PDF openly so index users understand
    constituent classifications — but that is not the same as a license
    to use "GICS" as a branded classification in a product, or to obtain
    the authoritative per-company assignments, both of which require a
    paid license.
  - No public no-cost or low-cost self-serve tier was found anywhere
    (S&P Global Marketplace, MSCI, or academic channels). Even academic
    access (Wharton Research Data Services / WRDS) requires an
    institutional subscription to Compustat/CRSP/IBES to reach GICS
    fields — individuals/small teams have no free path. Source:
    [WRDS](https://wrds-www.wharton.upenn.edu/), [S&P Global Academic
    Research Essentials](https://spre.wharton.upenn.edu/).

**Conclusion on licensing:** NAICS's taxonomy is unambiguously free.
GICS's taxonomy is publicly *readable* but not freely *usable* as a
branded classification, and the per-company data (the part that would
actually matter to MDM) is enterprise-priced with no small-project tier.

### 2. Per-company data source

**Does SEC/EDGAR capture NAICS anywhere for the operating-company
universe MDM tracks? No.** Confirmed via direct research (not assumed):
EDGAR's company/submissions metadata (the same `sec_company`
submissions-derived source `sic_code`/`sic_description` already comes
from) exposes only `sic`/`sicDescription` — there is no `naics` field in
the EDGAR submissions JSON, company-facts API, or full-text-search company
database. EDGAR was architecturally built around SIC in the late
1980s/early 1990s (the Division of Corporation Finance's office structure
is organized by SIC ranges) and has never switched, even though the
Census Bureau itself replaced SIC with NAICS in 1997 for its own
statistical purposes.

One narrow exception exists, worth noting but **not applicable to MDM's
company universe**: the SEC does publish and maintain its own NAICS XBRL
taxonomy (e.g. `https://xbrl.sec.gov/naics/2025/naics-2025.xsd`,
"created by staff of the U.S. Securities and Exchange Commission"). Based
on where NAICS-tagged SEC filings actually turn up in search (Form
ABS-15G and asset-backed-securities prospectus/reporting documents,
Regulation AB II's loan-level/obligor-industry disclosure regime for ABS
issuers), this appears scoped to asset-backed-securities structured
disclosure (classifying the industry of loan obligors/pool assets), not a
general per-filer classification field comparable to `sic_code` — it does
not cover the ordinary 10-K/10-Q-filing operating-company universe MDM
resolves. Treat this as a real but irrelevant-to-scope data point, not a
usable per-company NAICS source for MDM companies.

**Is there a free SIC→NAICS crosswalk? Yes, but it is explicitly
many-to-many, not 1:1.** The U.S. Census Bureau publishes official
concordance/correspondence tables between SIC and NAICS at
`https://www.census.gov/eos/www/naics/concordances/concordances.html`
(also referenced via BLS: https://www.bls.gov/emp/documentation/crosswalks.htm).
Multiple independent sources confirm the mapping is inherently ambiguous:
NAICS's real-world-driven splits and merges of old SIC industries mean a
single SIC code can map to several plausible NAICS codes and vice versa;
researchers describe having to "guess" the best 1:1 match, and academic
crosswalk projects (e.g. weighted crosswalks using employment/
establishment-count/payroll weights, per Princeton DSS/openICPSR) exist
*specifically because* an unweighted, deterministic mapping is not
possible for a meaningful fraction of codes. Source:
[Census concordances](https://www.census.gov/eos/www/naics/concordances/concordances.html),
[Weighted Crosswalks for NAICS and SIC Industry Codes (openICPSR/Princeton DSS)](https://dss.princeton.edu/catalog/resource5505).
**Conclusion:** a derived NAICS value from EdgarTools' existing `sic_code`
is possible but would be an approximation with real, quantifiable
ambiguity for a meaningful share of codes — not an authoritative,
SEC-sourced fact the way `sic_code` is today.

**Is there ANY free way to get per-company GICS classifications? No,
confirmed.** GICS is proprietary end-to-end — there is no public
crosswalk (unlike NAICS, which at least has a government-published
concordance from SIC), because GICS's per-company assignments are
themselves the commercial product S&P/MSCI sell (GICS Direct). The only
paths found are (a) pay for GICS Direct or a bundled data-vendor product,
or (b) independently re-derive a GICS-*like* classification from a
company's own public revenue-segment disclosures against S&P/MSCI's
openly-published methodology definitions — which is not "free access to
GICS data," it's building an unlicensed lookalike, with all the
trademark/accuracy risk that implies, and it does not scale the way a
crosswalk-derived NAICS approximation would.

### 3. Structure/hierarchy

**SIC (as EdgarTools/MDM has it today):** flat 4-digit code as stored
(`sic_code`), but SIC's *own manual* is 4 tiers: Division (a letter, A–J,
e.g. "D" = Manufacturing) → Major Group (2-digit) → Industry Group
(3-digit) → Industry (4-digit, the full code). EdgarTools captures only
the full 4-digit code today — no Division/Major-Group/Industry-Group
column exists (confirmed via grep, per `map.md`'s own note). Major Group
and Industry Group are trivial 2-digit/3-digit prefix truncations of the
existing code; Division is not a prefix and needs a small range-lookup
table (SIC Divisions are defined by *ranges* of Major Group codes, not a
digit position).

**NAICS:** confirmed 5-tier hierarchy, more granular than SIC's or GICS's
4 tiers — Sector (2-digit) → Subsector (3-digit) → Industry Group
(4-digit) → Industry (5-digit) → National Industry (6-digit, the full
code). Current NAICS (2022 revision) has 20 sectors (3 of which — 31-33
Manufacturing, 44-45 Retail, 48-49 Transportation & Warehousing — span a
range of 2-digit codes), 96 subsectors, 308 industry groups, 689
industries, 1,012 national industries. Source:
[NAICS Association](https://www.naics.com/search/),
[BEA NAICS FAQ](https://bea.gov/help/faq/19).

**GICS:** confirmed 4-tier hierarchy — Sector → Industry Group →
Industry → Sub-Industry, represented as a single 8-digit code where each
2-digit segment is one tier (e.g. `10` sector, `1010` industry group,
`101010` industry, `10101010` sub-industry). Current structure (post
March-2023 revision, still current as of this writing): **11 sectors, 25
industry groups, 74 industries, 163 sub-industries** — up from the
pre-2023 11/24/69/158 (a real, periodic revision cadence to be aware of:
GICS structure is not static, and any stored GICS code would need a
versioning/revision-date strategy). Source:
[Wikipedia — GICS](https://en.wikipedia.org/wiki/Global_Industry_Classification_Standard),
[GICS 2023 structural changes coverage](https://www.etftrends.com/etf-education-content-hub/what-advisors-need-to-know-about-the-gics-structure-changes-for-2023/).

**Comparison:** SIC and GICS are both 4-tier; NAICS is deeper (5-6
depending on how Sector's split ranges are counted). SIC's Division/Major
Group tiers are the cheapest of all three to obtain (already-owned data,
prefix/range derivation only) — no new licensing, no new source, no
crosswalk ambiguity.

### 4. Real-world usage

The two systems serve genuinely different audiences, and this cuts
against a one-size answer:

- **NAICS** is the standard for U.S. federal statistical/government data
  (Census, BLS, BEA) and general business classification (company
  registries, government contracting, sales/CRM/business-data-ops
  contexts) — free and ubiquitous in that world, but *not* what
  investment-facing sector dashboards typically show.
- **GICS** is the de facto standard specifically for **equity
  research/sector analysis** — S&P 500 sector breakdowns, index
  construction, and most retail-facing "sector/industry" stock-screening
  UIs are built around GICS-shaped categories (11 sectors, etc.), because
  it was purpose-built for investment analysis rather than statistical
  classification. Multiple sources converge on this split: "if you are
  comparing public companies and benchmarking sectors, GICS is usually
  the right framework; if you are segmenting companies for sales,
  marketing, CRM, or business-data operations, NAICS/SIC are the more
  practical standards." Source:
  [GICS vs. NAICS vs. SIC](https://learnfinanceterms.com/blog/gics-naics-sic-code-guide).

For a platform like EdgarTools (company/adviser *research*, not
institutional equity portfolio construction, but still competing for
attention against dashboards whose users are used to seeing GICS-shaped
sector buckets), this is the real tension: **the audience-expectation
system (GICS) is the one with no viable free per-company data path; the
freely-sourceable system (NAICS) is not what "sector dashboard" users are
used to seeing, and even NAICS would need per-company values labeled as
approximate/derived rather than authoritative.** This tension is exactly
why the recommendation above favors deriving SIC's own hierarchy first:
it doesn't resolve the GICS-shaped-expectation gap, but it's the only
option with zero cost and zero new data-quality caveats, and it can
coexist with a later, explicitly-labeled NAICS-approximation column if
demand still exists after that.

### Other alternatives considered

**ISIC** (UN International Standard Industrial Classification) — free,
public-domain-equivalent (maintained by UN Statistics Division,
freely published: https://unstats.un.org/unsd/classifications/Econ/isic),
but it is the *international* analog NAICS itself was harmonized against
— i.e. adopting it alongside NAICS would be redundant for a
US/EDGAR-centric company universe, and it has essentially zero mindshare
among the platform's likely users (US public company/adviser research),
unlike NAICS's federal-dataset ubiquity. Not recommended.

**ICB** (Industry Classification Benchmark, FTSE Russell) — a GICS-like,
also-proprietary competitor used in some non-US index contexts (e.g. LSE,
some European indices); doesn't solve the licensing or per-company-data
problem GICS has, and has less US-market mindshare than GICS. Not
recommended as a GICS substitute for this platform's audience.

Sources consulted (full list): US Census Bureau NAICS, MSCI GICS FAQ and
methodology docs, S&P Global GICS Direct brochure, FIS GICS third-party
data terms, T. Rowe Price GICS attribution page, Wikipedia GICS article,
Census Bureau SIC-NAICS concordances, Princeton DSS/openICPSR weighted
crosswalk documentation, BLS classifications/crosswalks page, SEC.gov
NAICS XBRL taxonomy schema and ABS-15G filing context, UN Statistics
Division ISIC page, learnfinanceterms.com GICS/NAICS/SIC comparison.
