# What ADV Schedule A/B `OwnerID` is, tested against IAPD and across two monthly archives

Ticket: 16. Run 2026-09-20.
Primary sources plus a recorded empirical run. External quotes are verbatim from the cited URL.
Archive members, `IA_Schedule_A_B` columns, the original 4-row probe and the IAPD search endpoint are
already described in research [15](15-crd-vs-cik-identifier-semantics.md) F2 and F6; this file
reuses that endpoint and cites 15 rather than re-deriving. No Snowflake or AWS reads.
Reproducibility: seed `20260920`, every selection query, every request and every per-row result are
in the four sibling files listed under "Sources read"; `16-summary.json` carries the SHA-256 of
`16-sample.jsonl`, `16-results.jsonl` and `16-iapd-requests.jsonl` (computed last, after all writes).

## Sources read

External, reached:
- https://iard.com/iard-system-frequently-asked-questions-form-filing-ia-firms — IARD's own filing
  FAQ (general Question 14; Schedule A/B section Questions 2, 3, 4 and 6). This is the only page
  found that states how the Schedule A/B individual identifier is assigned. First read through
  WebFetch, then — because research 15 caught WebFetch inventing quotes — the raw HTML was fetched
  with `curl` (HTTP 200, 70,817 bytes, saved as scratchpad `r16/iard_faq.html`) and every quoted
  string below was located character-for-character in the tag-stripped text.
- https://iard.com/schedule-direct-owners-and-executive-officers — IARD's Schedule A page; carries the
  form instructions only (DE/FE/I rule), no identifier text.
- https://www.sec.gov/about/forms/formadv-part1a.pdf (text already extracted by research 15,
  scratchpad `adv1a.txt` lines 1301-1373) — Schedule A instructions 1-7 and the paper column set.
- https://reports.adviserinfo.sec.gov/reports/foia/reports_metadata.json — fetched once (twice in the
  log: the first fetch was not saved); lists `advFilingData` months Jan-Aug 2026; no key resembling a
  data dictionary, README, layout or description at any depth (walked programmatically).
- https://reports.adviserinfo.sec.gov/reports/foia/advFilingData/2026/ADV_Filing_Data_20260301_20260331.zip
  — the one earlier month permitted (32,782,706 bytes; March is the annual-amendment month, chosen
  for maximum firm overlap with August). Members: `IA_Schedule_A_B_20260301_20260331.csv` 95,452
  rows, `IA_ADV_Base_A_20260301_20260331.csv` 15,027 rows.
- The August 2026 archive already in the scratchpad (research 15): `IA_Schedule_A_B` 16,139 rows,
  `IA_ADV_Base_A` 2,386 rows. Neither ZIP contains any non-CSV member (100 CSVs + directory entry).
- IAPD JSON search endpoints (undocumented; research 15 F2 used the first):
  `https://api.adviserinfo.sec.gov/search/individual/<OwnerID>` and
  `https://api.adviserinfo.sec.gov/search/firm/<OwnerID>`. Response shape:
  `hits.total`, `hits.hits[]._source.iacontent` — a JSON *string* which parses to
  `basicInformation{individualId|firmId, firstName, middleName, lastName, otherNames[], bcScope,
  iaScope}` plus, for individuals, `currentEmployments[]`, `currentIAEmployments[]`,
  `previousEmployments[]`, `previousIAEmployments[]`, each element carrying `firmId` (the firm's
  CRD number: 105662 → "ON INVESTMENT MANAGEMENT CO", the filing firm of research 15's first probe).

Request accounting (all in `16-iapd-requests.jsonl`, one JSON line per request with UTC timestamp,
URL, status, bytes): **273 requests total**, first `2026-09-20T10:57:09Z` (06:57 ET), last
`2026-09-20T11:09:02Z` (07:09 ET); 270 to `api.adviserinfo.sec.gov` (235 `/search/individual/`,
35 `/search/firm/`; 267 of the 270 are the sampled lookups in `16-results.jsonl`, the other 3 were
the response-shape probes of 5637288, 2246558 and firm 105662 before the sample was drawn), 3 to
`reports.adviserinfo.sec.gov` (2× metadata, 1× March ZIP); **273 × HTTP
200, zero 403, zero 429**; `time.sleep(1.0)` before every request; User-Agent
`EdgarTools Platform research theananthfamily@gmail.com`; hard cap 300, not reached.

Sibling files (same directory):
- `16-sample.jsonl` — 248 sampled rows (204 main + 14 low-digit + 10 same-name-pair + 20 DE/FE),
  each with `FilingID`, filing firm CRD (`IA_ADV_Base_A.1E1` joined on `FilingID`), name, title,
  ownership code, control flag, `OwnerID`, stratum labels.
- `16-results.jsonl` — 267 per-request results (one row per `(OwnerID, endpoint)`), raw
  `hits_total`, returned ids, IAPD name, scopes, history firm ids, and the derived flags.
- `16-iapd-requests.jsonl` — the 273-line request log.
- `16-summary.json` — every count quoted below, all selection SQL, the same-name pair list, the
  archive-only analysis, and the three SHA-256s.

Repo: `edgar_warehouse/application/adv_bulk_fetch.py:26,151,173` (archive name pattern, metadata
URL, download URL — reused unchanged for the March fetch).

## Findings

### F1 — Documentation (item 1)

**No SEC document defines `OwnerID`.** Confirmed again: the ZIP has no README or dictionary member;
`reports_metadata.json` has no descriptive field; the SEC FOIA and IARD pages research 15 reached
have none. The paper form's column is "CRD No. If None: S.S. No. and Date of Birth, IRS Tax No. or
Employer ID No." (formadv-part1a.pdf, Schedule A, lines 1359-1367 of the extracted text), and
instruction 7(c) says "Complete each column."

**IARD's filing FAQ documents how that column is populated for individuals**, and it is the
system-assigned CRD number in every case:

> Question 14: How do I create a direct owner? — "… select the appropriate owner type - "New
> Individual" (a person) or "New Entity" (a company). If you select "New Individual," IARD will
> allow you to search to see if the individual already has a CRD record. If he or she does have a
> CRD record, his or her name will be displayed. Select the name to open the screen that allows you
> to enter the schedule information. If no CRD record is found, select the "Create Individual"
> button to assign the individual a CRD number and open the schedule information screen."

> Schedule A/B Question 2: "… Enter identifying information in the individual search screen. The
> system will search for matches to the search criteria provided. Make sure the Social Security
> Number, CRD Number, or Name you enter for the search is correct, so that you do not create a new
> individual record for an existing individual by mistake. If the individual doesn't already exist
> on the system, it will be created."

So for `I` rows the identifier behind the "CRD No." column is always a CRD-system individual
record id — either the person's pre-existing CRD record (a registered representative/IAR) or a
record IARD creates on the spot for an owner who has never registered. The same FAQ concedes that
duplicate records for one person can be created by the filer. For entities the path is different:
"Select the 'New Entity' button. Enter the required schedule information." — no CRD-record search;
and for a foreign entity without a tax id, "type 'Foreign Entity' in the data field box that
requests a CRD Number and select the 'Employer ID' radio button." The FAQ says nothing that
connects the FOIA CSV column name `OwnerID` to this field; that link is F2-F4's empirical result,
not a documented one.

### F2 — Empirical test of `I` rows against IAPD (item 2)

**Sample.** 204 distinct `OwnerID`s = 12 cells × 17 (magnitude quartile Q1 ≤ 2,894,234 / Q2 ≤
5,072,455 / Q3 ≤ 6,629,159 / Q4 above; × title class EXEC / GOVERNANCE / OWNER_ONLY by regex on
`Title or Status`, population 6,864 / 2,579 / 1,643), one row per `OwnerID`, ordered inside each
cell by `hash(concat_ws('|', FilingID, OwnerID, "Full Legal Name", '20260920'))`. Spread: 188
distinct `FilingID`s, 184 distinct filing-firm CRDs. Selection SQL (verbatim; the low-digit and
DE/FE queries are in `16-summary.json`):

```sql
WITH i_rows AS (
  SELECT a."FilingID" filing_id, b.firm_crd, b.firm_name, a."Schedule" schedule,
         a."Full Legal Name" full_legal_name, a."Title or Status" title, a."Ownership Code" ownership_code,
         a."Control Person" control_person, trim(a."OwnerID") owner_id, cast(trim(a."OwnerID") as bigint) owner_id_num
  FROM ab a JOIN base b ON a."FilingID" = b."FilingID"
  WHERE a."DE/FE/I" = 'I' AND nullif(trim(a."OwnerID"), '') IS NOT NULL
), classed AS (
  SELECT *,
    CASE WHEN owner_id_num <= 2894234.75 THEN 'Q1' WHEN owner_id_num <= 5072455 THEN 'Q2'
         WHEN owner_id_num <= 6629159 THEN 'Q3' ELSE 'Q4' END AS magnitude_quartile,
    CASE WHEN regexp_matches(upper(title), 'CHIEF|\bCEO\b|\bCFO\b|\bCCO\b|\bCOO\b|\bCIO\b|PRESIDENT|OFFICER|GENERAL COUNSEL|SECRETARY|TREASURER|MANAGING DIRECTOR|PRINCIPAL|CHAIRMAN|FOUNDER|\bHEAD\b|PORTFOLIO MANAGER|COUNSEL') THEN 'EXEC'
         WHEN regexp_matches(upper(title), 'DIRECTOR|TRUSTEE|MANAGER|MANAGING MEMBER|MANAGING PARTNER|GENERAL PARTNER|BOARD') THEN 'GOVERNANCE'
         ELSE 'OWNER_ONLY' END AS title_class,
    hash(concat_ws('|', filing_id, owner_id, full_legal_name, '20260920')) AS h
  FROM i_rows
), one_row_per_ownerid AS (
  SELECT * FROM (SELECT *, row_number() OVER (PARTITION BY owner_id ORDER BY h) rn FROM classed) WHERE rn = 1
), ranked AS (
  SELECT *, row_number() OVER (PARTITION BY magnitude_quartile, title_class ORDER BY h) cell_rank FROM one_row_per_ownerid
)
SELECT * FROM ranked WHERE cell_rank <= 17 ORDER BY magnitude_quartile, title_class, cell_rank
```
(`ab` = `IA_Schedule_A_B_20260801_20260831.csv`, `base` = `FilingID, trim("1E1") firm_crd, "1A"
firm_name` from `IA_ADV_Base_A_20260801_20260831.csv`; DuckDB, `all_varchar=true`.)

**Resolution.** `resolves` = at least one hit whose `basicInformation.individualId` equals the
queried `OwnerID`. **110/204 resolve (53.9%)**; `hits.total` was exactly 1 for all 110 and 0 for
the other 94 — **no request returned a hit with a different `individualId`**, so the endpoint is a
strict id lookup, not a fuzzy search.

**Name match, denominator = the 110 resolved.** Normalisation: lowercase, strip non-alphanumerics,
drop suffix tokens (jr, sr, ii, iii, iv, v, esq, cfa, cpa, cfp, phd, md, jd, mba); CSV name split as
`LAST, FIRST, MIDDLE` per the form instruction (the CSV also uses `LAST, FIRST MIDDLE` with one
comma — handled by keying on the first token of the first-name segment). **110/110 match (100%)**:
107 exact token-multiset equality against `firstName/middleName/lastName`, 3 exact equality against
an `otherNames` entry (4052029 SIZEMORE, STACY, LEIGH ↔ "STACY LEIGH SIZEMORE"; 4023880 GOODCHILD,
CHAD, WESTON ↔ "CHAD WESTON GOODCHILD"; 5239324 NAGELL, LUKE ↔ "LUKE  NAGELL"). Zero partial-only,
zero none.

**Filing firm in the individual's IAPD firm history, denominator = 110 resolved.** The filing firm's
CRD (`1E1`) appears among the `firmId`s of the four employment lists for **80/110 (72.7%)**: 66 in
`currentIAEmployments` only, 7 in both `currentEmployments` and `currentIAEmployments`, 5 in
current + previous IA, 2 in `previousIAEmployments` only. Of the 30 absent: 16 records have
**empty** employment lists altogether (all `iaScope: NotInScope`; `bcScope` Active 8 / InActive 8 —
IAPD/BrokerCheck records with no displayed IA employment), and 14 have a non-empty history that
omits the filing firm (6 of those 14 filing firms carry CRD ≥ 342,000, i.e. registered in the
weeks before the August archive). Restricted to `iaScope: Active` records: 78/87 (89.7%).

**By stratum** (resolve / name-match-among-resolved / filing-firm-in-history-among-resolved):

| Stratum | n | resolves | name match | filing firm in history |
|---|---|---|---|---|
| Q1 (≤ 2.89M) | 51 | 35 (68.6%) | 35/35 | 24/35 |
| Q2 (≤ 5.07M) | 51 | 36 (70.6%) | 36/36 | 27/36 |
| Q3 (≤ 6.63M) | 51 | 31 (60.8%) | 31/31 | 23/31 |
| Q4 (> 6.63M) | 51 | 8 (15.7%) | 8/8 | 6/8 |
| EXEC | 68 | 43 (63.2%) | 43/43 | 30/43 |
| GOVERNANCE | 68 | 30 (44.1%) | 30/30 | 19/30 |
| OWNER_ONLY | 68 | 37 (54.4%) | 37/37 | 31/37 |

By 1,000,000-bin: 0M 3/5, 1M 13/18, 2M 21/32, 3M 7/8, 4M 23/33, 5M 22/31, 6M 18/40, **7M 3/25, 8M
0/12**. Non-resolution concentrates in the *highest* (most recently issued) numbers, not the lowest;
every one of the 94 non-resolvers returned `hits.total: 0`. Q4's 43 non-resolvers split EXEC 12 /
GOVERNANCE 16 / OWNER_ONLY 15. Read with F1: numbers above ~7,000,000 are recent CRD-record
creations, and an individual whose record was created by "Create Individual" on Schedule A without
a Form U4 registration has nothing for IAPD to publish.

**Low-digit `I` rows** (5-6 digit `OwnerID`, 142 rows / 95 distinct in the archive): 14 probed on
the individual endpoint, **11/14 resolve, all 11 exact name matches, all 11 with the filing firm in
history**; the 3 zero-hit ids are 730326, 375675, 705211. The same 14 on the **firm** endpoint:
0/14.

**Archive-only: collisions (one `OwnerID` → different names).** Of 7,060 distinct `I` `OwnerID`s in
August, 2,273 appear on more than one row, 1,594 on more than one `FilingID`, 430 under more than
one filing-firm CRD. Names differ on the strict key (last-name tokens, or first token of the first
name) for **2** ids, both at one firm with identical first+middle names and a different surname
(5006680 "ALLEN, TAMARA, JEANNE" / "OLSZEWSKI, TAMARA, JEANNE" at 146385; 7437570 "Forman, Raquel" /
"TEICH, RAQUEL" at 119800); on a loose key (middle name, initial, suffix, case, one- vs two-comma
format only) for 23 more. **Zero** ids carry two unrelated names.

**Archive-only: the reverse (one person → more than one `OwnerID`).** 7,618 distinct (filing-firm
CRD, last|first) pairs; **21 carry two different `OwnerID`s at the same firm**. 12 are visibly
different people (different middle names: HAMM, WILLIAM, EUGENE 1227713 vs HAMM, WILLIAM,
CHRISTOPHER 5814331; FARRELL, NEIL, JOSEPH vs NEIL, VINCENT; …). **9 have identical full names**
(THOMPSON NIMROD G(ORDON) 4361188/5801517 at 106125; SIGHTS JERE MATTHEWS 6643761/6859158 at 106125;
FOLLETT RICHARD L(YNN) 2729084/4031384; MAROON MICHAEL ANTHONY 1611616/6954252; SMITH ERIC STEVEN
2894648/4390339; MARINICH DENNIS PAUL 1010011/2940858; GUIDA FRANK 1499368/7396287; LOPER CHARLES
A(LBERT) 1489450/4155205; TRAITEL II DAVID S/T 8314572/8314580). Five pairs were probed (10
requests):
- MARINICH, DENNIS, PAUL: **both** 1010011 and 2940858 resolve, both exact name, both list filing
  firm 291484 plus the same four other firms (11025, 19616, 10 — and 2940858 adds 35747, 628;
  `otherNames` "DENNY MARINICH II"). Two IAPD individual records with one name and overlapping
  five-firm histories.
- THOMPSON, NIMROD, GORDON/G.: **both** 4361188 and 5801517 resolve, both exact, both list 106125
  (5801517 also 615; `otherNames` "N. GORDON THOMPSON" / "ROD THOMPSON").
- SIGHTS, JERE, MATTHEWS: 6643761 resolves (history 106125); 6859158 zero hits.
- SMITH, ERIC, STEVEN: 2894648 resolves (history 108249); 4390339 zero hits.
- MAROON, MICHAEL, ANTHONY: neither resolves.
Across all firms, 71 of 6,990 distinct last|first keys map to more than one `OwnerID` — the
expected homonym rate, not evidence either way.

**Archive-only: stability across months.** (filing-firm CRD, last|first) pairs present in both
March and August 2026: **5,322 pairs across 1,227 firms; 5,322 (100%) carry the identical
`OwnerID` set, 0 differ, 0 are subset/superset.** `OwnerID`s present in both months: 5,107; 5,106
map to an overlapping name key, 1 does not (6121402: "brenner|megan" in March, "jewett|megan" in
August — a surname change on the same id). The test is well powered (n = 5,322) but tests
*persistence of an already-assigned id*, which F1 makes expected; it cannot see whether a new
record was created for an existing person at a *different* firm.

### F3 — `DE`/`FE` rows (item 3)

`OwnerID` is **blank for 4,917 of 5,013** DE/FE rows (DE 4,004/4,092; FE 913/921). The 96 non-blank
values are 5-6 digits (never 7), 63 distinct; **44 of the 63 equal a firm CRD** in the August or
March `IA_ADV_Base_A.1E1` column; only 4 rows equal their *own* filing firm's CRD. 20 distinct DE/FE
ids (19 DE, 1 FE; deterministic hash order) against the **firm** endpoint: **18/20 resolve with
`firmId` equal to the queried value, 18/18 exact name match** on `firmName` or `otherNames` (e.g.
144533 → "KOHLBERG KRAVIS ROBERTS & CO. L.P.", 107105 → "BLACKROCK FINANCIAL MANAGEMENT, INC",
116632 "VAN HULZEN ASSET MANAGEMENT" → otherNames match, 140195 "MARINER WEALTH" → "MARINER"); 16
`iaScope: ACTIVE`, 1 INACTIVE, 1 broker-dealer only (17917 BLACKSTONE SECURITIES PARTNERS L.P.,
`bcScope: ACTIVE`); 15 carry an 801- SEC number, 1 an 802- number; 2 return zero hits (292964 LONE
STAR AMERICAS ACQUISITIONS, LLC and 292963 LONE STAR GLOBAL ACQUISITIONS, LTD., consecutive numbers
in the firm CRD space). The first 5 of the same 20 against the **individual** endpoint: 0/5.
Consistent with F1's entity path: the filer types the owning entity's own CRD number when it has
one (a registered adviser or broker-dealer), and the FOIA export publishes that number as
`OwnerID`; tax ids / "Foreign Entity" are suppressed, leaving the column blank.

### F4 — Coverage and cross-type resolution (item 4)

- `I` rows with a non-null `OwnerID`: **11,086 / 11,126 = 99.64%** (August); 68,457 / 68,642 =
  99.73% (March). The 40 August nulls span 24 filings, 31 on Schedule A / 9 on B, 32 flagged
  `Control Person = Y`, with ordinary titles (CFO/CCO, LIMITED PARTNER, PRESIDENT - DIRECTOR,
  CHAIRMAN). Digit lengths of non-null `I` ids: 7 digits 10,944; 6 digits 133; 5 digits 9; min
  13,479, max 8,337,562; quartiles 2,894,235 / 5,072,455 / 6,629,159.
- Number spaces are disjoint in the archive: **0** `I` `OwnerID`s equal any firm CRD in either
  month's `Base_A` (firm CRDs run 70-344,307, 13,222 distinct in March); **0** `OwnerID` values
  appear under both `I` and `DE`/`FE`.
- Cross-type resolution: `I` ids on the firm endpoint **0/14**; `DE`/`FE` ids on the individual
  endpoint **0/5**. No `I` row resolved to a firm and no `DE`/`FE` row resolved to an individual.

### F5 — Conclusion, factual (item 5)

What the evidence establishes:
1. `OwnerID` for `I` rows is a CRD-system individual record id. IARD's FAQ says every Schedule A/B
   individual is either matched to an existing CRD record or has one created "to assign the
   individual a CRD number" (F1); 99.6-99.7% of `I` rows carry a value (F4); every resolving id
   (110 of 204 sampled, plus 11 of 14 low-digit, plus 6 pair members) returns an IAPD individual
   whose `individualId` equals it and whose name matches the row (F2); the id space never overlaps
   firm CRDs (F4); a resolving id's firm history contains the filing firm in 72.7% of cases, 89.7%
   among `iaScope: Active` (F2).
2. The id persists across monthly archives for the same firm+name: 5,322/5,322 (F2).
3. `DE`/`FE` `OwnerID` is the owning entity's own firm CRD when it has one, otherwise blank (F3).

What it does not establish:
4. **Unique per natural person — not shown, and counter-evidence exists.** IARD's own FAQ warns
   filers not to "create a new individual record for an existing individual by mistake"; the
   August archive has 9 same-firm, identical-full-name pairs with two `OwnerID`s, and for 2 of the
   5 probed pairs (MARINICH; THOMPSON) *both* ids resolve on IAPD to same-name records with
   overlapping multi-firm employment histories. Nothing public distinguishes "one person with two
   CRD records" from "two people with one name and one career", so the duplicate rate cannot be
   measured from these sources; only its lower bound (≥ 2 confirmed-both-resolving pairs among 7,060
   ids, ≥ 9 candidate pairs) is visible.
5. **Resolvable on IAPD — only for registered individuals.** 46.1% of the sample (94/204) returns
   nothing, rising to 84.3% of Q4 and 100% of ids ≥ 8,000,000 (F2). Read with F1, those are ids
   that exist in CRD but belong to individuals IAPD does not publish (never filed a Form U4, or out
   of display scope). The id still exists and is stable (F2 stability covers them: the 5,322 pairs
   hold 1,316 / 1,344 / 1,382 / 1,292 ids in Q1-Q4, 240 of them ≥ 8,000,000, all unchanged); it is
   just not externally verifiable.

## What this settles for ticket 02 Q2

- The paper form's "CRD No. If None: S.S. No. and Date of Birth …" column is published as
  `OwnerID`, and for individuals it is always a CRD individual id assigned or matched by IARD at
  filing time (F1), present on 99.6% of `I` rows (F4), disjoint from firm CRDs (F4), stable month to
  month for the same firm+name (F2), and — where IAPD publishes the person — a strict id lookup
  that returns the same name 110/110 times (F2). The research 15 "could not be determined" item on
  what `OwnerID` is, is closed: it is an individual CRD number — with the caveat that the
  documentary half (F1) describes the IARD field, and the link from that field to the FOIA column
  named `OwnerID` is empirical (F2, F4), since no SEC/IARD text names the column.
- The evidence **falls short of "unique per natural person."** The issuer's own FAQ says duplicates
  can be created, and the archive shows same-firm identical-name pairs with two ids, two of which
  resolve on IAPD as two records with overlapping histories (F2, F5.4). At the standard the repo
  applied to `owner_cik` (issuer-defined identifier of a filer account, one per account, no
  per-person guarantee — research 15 F4), `OwnerID` is the same kind of thing: one per CRD
  *record*, with records-per-person ≥ 1 and no published bound.
- `OwnerID` **binds deterministically** in the sense ticket 02 asked about — every `I` row carries
  a system-assigned id that the same person keeps across filings — but only ~54% of ids (15.7% in
  the newest quartile) can be corroborated against a public IAPD record; the rest are opaque
  numbers with a name (F2, F5.5).
- `DE`/`FE` rows do not carry a comparable identifier: 98% blank, and when present it is the owning
  entity's firm CRD (F3).

## Could not be determined

- Whether the MARINICH and THOMPSON pairs (and the other 7 identical-name pairs) are one person with
  two CRD records or two people: IAPD publishes no date of birth, and the SSN/DOB fallback is
  suppressed in the FOIA export, so no public field separates the two cases.
- The overall rate at which one person holds more than one `OwnerID`: only same-firm, same-name
  pairs are detectable from the archive; a duplicate created at a different firm under a name
  variant is invisible.
- Why 16 resolving records have empty employment lists while `bcScope` is Active/InActive — whether
  that is an IAPD display rule or a data gap; not documented on any page reached.
- Whether the 94 non-resolvers have CRD records that IAPD suppresses (never-registered owners) or
  ids that were later merged/retired: the endpoint returns `hits.total: 0` for both. The
  magnitude pattern (worst above 7,000,000) fits the former but does not prove it.
- Whether individual CRD ids issued by "Create Individual" on Schedule A are ever merged into a
  pre-existing record after the fact, and what happens to `OwnerID` in later archives if so — no
  such event was observable in the March→August comparison (0 changed ids in 5,322 pairs) and no
  page reached describes a merge process.
- Correlation between `OwnerID` magnitude and first registration date (which would confirm
  sequential issuance): the run stored firm ids only, not `registrationBeginDate`, and re-querying
  the 110 resolved records would exceed the 300-request cap.
- Whether the FOIA export's `OwnerID` column is populated from the same IARD field for ERA filers
  (`ERA_Schedule_A_B`, 1,235 rows): not sampled.
