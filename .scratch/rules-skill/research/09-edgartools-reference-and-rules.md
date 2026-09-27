# Research 09: edgartools reference data and rules, and the engine beyond Company

Ticket: [09](../issues/09-edgartools-reference-and-rules.md). Written 2026-09-27 (ET).
Source: edgartools 5.30.0 as installed in this worktree
(`.venv/lib/python3.12/site-packages/edgar`, below written `edgar/`). Only source
code and bundled files were read. **Zero SEC requests**: no edgartools function
that fetches was called; the data files were read with pandas.

Everything under "Recommendations" is a recommendation for the operator, **not a
decision**.

## Answer first

1. edgartools bundles only **7 data files** (`edgar/reference/data/`). Two matter
   for MDM: `place_codes.csv` (already taken, ticket 08) and `ct.pq`, a
   **CUSIP-to-ticker table of 67,679 CUSIPs**, every one with a valid check digit.
2. Its real value is **code-held lists and heuristics**, not files: the 9-signal
   individual-vs-company chain (`edgar/entity/constants.py:226`), business
   categories from SIC and forms (`edgar/entity/categorization.py`), form sets, and
   person-name suffixes (`edgar/display/formatting.py:167-181`).
3. No list in edgartools is a drop-in replacement for ours. Ours are measured and
   whole-token; edgartools' company keywords use **substring** matching and are
   smaller on foreign legal forms. Three edgartools entries are worth measuring as
   additions: `TRUST`, `FOUNDATION`/`ASSOCIATION`/`AUTHORITY`, and `NA` (bank).
4. Do **not** copy edgartools' person suffixes `MD` and `II/III/IV` into
   `person_suffix`: our conformed normalizer turns the state tag `/MD/` into the
   token `MD`, and `II` is common in fund names.
5. edgartools has **no SIC description table, no exchange/MIC table, no legal-form
   (ELF) table and no Form ADV parser**. SIC text comes from each filer's own
   submissions JSON.
6. edgartools **validates almost no identifier**: CUSIP by shape only
   (`edgar/thirteenf/parsers/infotable_txt/format_multiline.py:26`), series and
   class ids by "letter plus digits" (`edgar/funds/core.py:235-240`), ISIN, LEI and
   CRD not at all. Our `FORMATS` (with the LEI mod-97 check) is already stricter.
7. For Person, Security, Fund and Adviser the engine mostly needs **new `FORMATS`
   entries** (CUSIP, ISIN, SEC series, SEC class, CRD, EIN, SEC file number) and
   **one contract key for source placeholders** (`none_values`). Almost all of it
   is data or a few lines of code.
8. The five trial gaps each have a small fix: `none_values` (placeholders),
   `lookup_identifiers` (lookup-only ids), `aliases` (former names), a
   `kind_from` join key (kind from another file), and a `publication` section.
9. First, in order: `none_values`; `lookup_identifiers`; the CUSIP, ISIN, series,
   class and CRD formats; the `ct.pq` CUSIP-ticker table as a Security lookup;
   then measured proposals from edgartools' lists.
10. The BDC signal edgartools uses, an `814-` SEC file number
    (`edgar/entity/data.py:516-532`), is stronger than our `N-54A` list and is
    worth measuring for the Company rule.

## 1. Inventory of edgartools reference data and domain rules

### 1a. Bundled data files (`edgar/reference/data/`)

sha256 prefixes are of the 5.30.0 files.

| File | Holds | Rows | Origin (as stated) | How edgartools uses it | Refresh without SEC? |
|---|---|---|---|---|---|
| `place_codes.csv` (1daf0cc6…) | `Code, Place, Type` | 309: US 58, FOREIGN 238, CANADIAN 12, UNKNOWN 1 (`XX`) | SEC EDGAR state/country code list (not stated in file) | `edgar/reference/_codes.py:8-108`: place name, `US/CANADIAN/FOREIGN`, `get_filer_type` | Only by a new edgartools release. **Already taken** as `rules/reference/sec-place-codes.yaml` (branch `claude/rules-08-place-codes`) |
| `secforms.csv` (e46d71da…) | `Form, Description` | 311 | Not stated; SEC form descriptions | `edgar/reference/forms.py:5-27` `describe_form()`; `/A` is stripped and "Amendment" added | By release. No categories, only text |
| `exhibits.csv` (8ec4e466…) | `Exhibit No., Description, Form Types Involved, Regex` | 35 | Reg S-K Item 601 list (not stated) | exhibit labelling | By release. Not MDM |
| `company_tickers.parquet` (b6e976b2…) | `cik` (10-digit text), `ticker`, `exchange`, `name` | 10,769; 8,332 CIKs; 1,517 CIKs with >1 ticker; exchange Nasdaq 4,267, NYSE 3,322, OTC 2,817, CBOE 29, `NYS` 1, null 333 | A copy of SEC `company_tickers_exchange.json` ("edgar-storage format", `edgar/reference/tickers.py:66-80`) | Offline ticker/CIK lookup (`tickers.py:58-88`, first priority at `:157-190`) | By release only. We already capture the same SEC catalog into bronze (`reference_catalog`) |
| `ct.pq` (e3a74b2c…) | `Cusip`, `Ticker` | 67,679 CUSIPs, all unique, **all pass the CUSIP check digit** (checked here); 56,122 tickers; 8,776 tickers map to >1 CUSIP; includes test rows (`00006K018 TESTA`) | Not stated | 13F: `cusip_ticker_mapping()` and `get_ticker_from_cusip()` (`tickers.py:27-55`, `:514-523`) | By release only; origin unknown |
| `popular_us_stocks.csv` (421bf45f…) | `Ticker, Company, Cik` | 85 | Hand list | `popular_us_stocks()` (`tickers.py:578`) | Not MDM |
| `portfolio_managers.json` (3a779d94…) | `metadata`, `managers` (40 firms, 75 people) | 75 | Hand curation from websites and press (`metadata.sources`); `README_PORTFOLIO_MANAGERS.md` | `edgar/thirteenf/manager_lookup.py:14` | Not a governed source: no filing evidence per row |

### 1b. Code-held tables and heuristics

| Where | What | Size / examples | Origin |
|---|---|---|---|
| `edgar/entity/constants.py:12-71` | `COMPANY_FORMS` | ~110 forms: 10-K, 8-K, 20-F, S-1, DEF 14A, N-CSR, 485BPOS, X-17A-5… | Hand list |
| `constants.py:74-97` | `FUND_FORMS` | N-1A…N-6, N-CSR, N-CEN, **ADV/ADV-E/-H/-NR/-W**, PF, MA…, N-54A, NPORT-P | Hand list; overlaps `COMPANY_FORMS` (N-CSR is in both) |
| `constants.py:100-109` | `INDIVIDUAL_FORMS` | 3/4/5 and /A, SC 13D/G, SC TO-*, ADV-E | Hand list; companies file SC 13D too |
| `constants.py:118-154` | `FILER_TYPE_FOREIGN_FORMS` / `_DOMESTIC_FORMS` | F-6, 12G3-2B, 20FR12B, 18-K… / S-1, 10-12G, N-1A, C… | Hand list with a cited internal gap analysis |
| `constants.py:160-183` | `COMPANY_NAME_KEYWORDS` (substring) and `_STRICT` (whole word) | 29 + 14 words (see §2b) | Hand list |
| `constants.py:186-223` | `_name_suggests_company`: keywords, SEC tag `/ADR/`, `&` unless a joint filer (`MR & MRS`, repeated surname regex `:190`) | — | Heuristic |
| `constants.py:226-290` | `_classify_is_individual`: 9 ordered signals (issuer insider flag, tickers/exchanges, state of incorporation, entity type ≠ other, company form in the first 50 forms, EIN ≠ `000000000`, company name, owner insider flag, default individual). **Hard-coded CIK exceptions**: 1033331 (Reed Hastings, `:260`), 315090 (Warren Buffett, `:271`, `:277`) | — | Heuristic. **Our repo already runs it** in `edgar_warehouse/parsers/ownership.py:48,240-258` for name display only |
| `edgar/entity/categorization.py:62-161` | SIC sets: REIT {6798}, SPAC {6770}, bank {6021,6022,6029,6035,6036}, insurance {6311,6321,6331,6351,6361,6371}, investment manager {6211,6282}, holding {6719}; form sets: primary investment {N-CSR, N-CSRS, NPORT-P, NPORT-EX}, secondary {N-CEN, N-PX}, BDC {N-2, N-2ASR, N-23C-2}, 13F {13F-HR, 13F-HR/A}; ETF families (ISHARES, SPDR…); SPAC name patterns | — | Hand lists |
| `categorization.py:198-285` | `classify_business_category`: 10 ordered steps to 11 categories | — | Heuristic, the same shape as our step list |
| `categorization.py:288-...` | `sic_overrides_bdc`: SIC outside 6000–6999, or bank/insurance/REIT/SPAC/6211/6282, blocks BDC | — | Heuristic |
| `edgar/entity/data.py:516-532` | `is_bdc`: any filing with SEC file number `814-*` | — | Rule tied to the 1940 Act file-number prefix |
| `edgar/display/formatting.py:167-181` | Person name parts: surname prefixes (VAN, VON, DE, DEL… 20), suffixes (JR, SR, II, III, IV, MD, PHD, DDS, DR, ESQ, CPA, ET AL), title prefixes (DR, PROF, REV) | — | Hand lists, used by `reverse_name` (`:198`) |
| `edgar/reference/tickers.py:526-540` | `clean_company_name` (drops `/XX/` tag), `clean_company_suffix` (drops INC, CO, CORP, PLC, LTD, LIMITED, L.P., `& CO`) | — | Display helpers |
| `edgar/ownership/ownershipforms.py:160-190` | Form 4 transaction codes: 15 descriptions (A, C, D, E, F, G, H, I, M, O, P, S, U, X, Z) and 17 short types (adds J, W); `TRADES = ['P','S']` | — | SEC Form 4 instructions |
| `edgar/reference/_codes.py:118-221` | `INVESTMENT_CATEGORIES` (6), `ISO_STATES_AND_OUTLYING_AREAS` (9, truncated), `ISO_COUNTRY_CODES` (**truncated at GAMBIA and wrong: `CD` is "COOK ISLANDS"**, `:191`) | — | Unfinished; do not use |
| `edgar/reference/forms.py:30-33` | `PROSPECTUSES` | 30 forms | Hand list |
| `edgar/reference/company_subsets.py:96,150,738-800` | Industry subsets by SIC or SIC range (pharma 2834, biotech 2833–2836…) | — | Convenience filters |
| `edgar/entity/data/*.json`, `edgar/xbrl/standardization/*.json` | XBRL concept and statement mappings, 19 industry extension files | — | Financial statements, not MDM |
| `edgar/ai/skills/*.yaml` | Agent skill text | — | Not data |

Fetched at run time, **never bundled** (so not usable under our zero-SEC rule
except from our own bronze): the fund series/class list
(`edgar/funds/reference.py:460-515`, SEC "investment company" open data CSV),
`company_tickers.json`, `company_tickers_mf.json`, `ticker.txt`
(`edgar/urls.py:63-80`).

Missing from edgartools entirely: a SIC code table, an exchange/MIC table, a
GLEIF ELF legal-form table, CUSIP/ISIN/LEI/CRD validators, and a Form ADV parser
(no ADV class anywhere; `muniadvisors.py` is Form MA). Our repo has its own ADV
parser (`edgar_warehouse/parsers/adv.py`).

## 2. Mapping to the new build

Legend: **(a)** reference table for `rules/reference/`; **(b)** a better source
for a list in `rules/merge/kinds/company.yaml`; **(c)** logic to become a
primitive; **(d)** not useful.

| Item | Class | Reader / rule that would use it | Note |
|---|---|---|---|
| `place_codes.csv` | (a) done | name binding `jurisdiction_agrees@1`; later Person/Adviser addresses | Taken on `claude/rules-08-place-codes`. edgartools' `_codes.py` ISO table must **not** be used (truncated, `CD` wrong) |
| `ct.pq` | (a) | Security: a **lookup-only** CUSIP→ticker table; also a CUSIP check-digit test set | 1 CUSIP has 1 ticker here, but 8,776 tickers have several CUSIPs (history, reuse). A ticker must never key a Security (ADR 0015). Origin undocumented, so pin by sha256 and label it "edgartools 5.30.0", as ticket 08 did |
| `company_tickers.parquet` | (d) | — | Same content as the SEC catalog we already capture to bronze; bronze is dated and pinned, the bundle is not |
| `secforms.csv` | (a), low priority | Rule authoring and the Mapping Document: show a description beside each form a rule lists | All 9 forms in our lists have entries except the `/A` forms (by design, `forms.py:15-17`). No categories, so it cannot replace a list |
| `exhibits.csv` | (d) | — | Filing text, not MDM |
| `popular_us_stocks.csv`, `portfolio_managers.json` | (d) | — | Hand lists without filing evidence; the second could at most seed a Person test fixture |
| `COMPANY_NAME_KEYWORDS(_STRICT)` | (b) partial | `company_legal_form` (step 10) | See §2b |
| person suffixes (`formatting.py:173`) | (b) partial | `person_suffix` (step 9) | See §2b |
| `categorization.py` form sets | (b) partial | `fund_report` (step 7a), `bdc_election` (7b) | See §2b |
| `is_bdc` via `814-` | (c) | Company rule step 7b, later Fund profile | Needs file numbers on the reader's record and a prefix primitive (§3d) |
| `_classify_is_individual` | (c) as **candidate steps**, not a primitive | Person classification from SEC submissions | See §2c |
| `classify_business_category` | (c) later | A Company *field* (business category), not identity | Out of the identity path; would be a derived field with its own rule |
| Form 4 transaction codes | (a) | Person/Security holdings relationship properties | 17 codes; a small `rules/reference/sec-form4-transaction-codes.yaml` if a consumer needs the text |
| `FILER_TYPE_*_FORMS` | (d) for now | — | Our jurisdiction comes from state codes and GLEIF |
| `reverse_name` | (d) for MDM | Display only; our repo already keeps the raw name (`ownership.py` docstring) | Identity must use the raw SEC name |

### 2b. edgartools' lists against ours

**`company_legal_form`** (ours, `rules/merge/kinds/company.yaml:295-390`, 95
entries, whole-token after `edgar-conformed-v1`) vs edgartools keywords
(`constants.py:160-183`, 43 entries):

- In edgartools, not in ours: `TRUST`, `FUND`, `FUNDS`, `PORTFOLIO`,
  `FOUNDATION`, `ASSOCIATION`, `AUTHORITY`, `NA`.
  - `FUND`/`FUNDS` are ours on purpose in `fund_name` (step 5), which defers to
    Fund Structure. Adding them as Company evidence would undo that.
  - `TRUST` and `PORTFOLIO` point as often to a Fund Structure as to a Company.
  - `FOUNDATION`, `ASSOCIATION`, `AUTHORITY` (a non-profit or a government body)
    and `NA` (a US national bank, "JPMORGAN CHASE BANK NA") are real non-person
    signals. `AUTHORITY` may be a Government Entity, which we already defer
    (step 3, SIC 8888).
- In ours, not in edgartools: every foreign form (AB, AG, AS, BV, GMBH, KG, KK,
  NV, OY, PTE, PTY, SA, SARL, SAS, SE, SPA, SDN, BHD, LTDA,
  LIMITADA, KABUSHIKI), LLP, LLLP, GP, REIT, SPV, SPONSOR(S),
  and the business words (ASSET, EQUITY, ENERGY, INSURANCE, RESOURCES…).
- Matching differs: edgartools matches its long list as **substrings**
  (`constants.py:200`), so "CAPITAL" matches "CAPITALE" and "SERVICES" matches
  inside longer words. Ours is whole-token (`primitives.py:100-132`).
- Verdict: ours is the better list. `FOUNDATION`, `ASSOCIATION`, `NA` are worth
  a measured proposal; `AUTHORITY` should rather route to Government review.

**`person_suffix`** (ours `company.yaml:286-294`: CFA, CPA, DDS, ESQ, JR, MRS,
PHD, SR) vs edgartools (`formatting.py:173-178`: JR, SR, II, III, IV, MD, PHD,
DDS, DR, ESQ, CPA, ET AL):

- edgartools adds II, III, IV, MD, DR, ET AL; ours adds CFA and MRS.
- **Do not add `MD`**: `edgar-conformed-v1` turns `/` into a space
  (`primitives.py:66-71`), so "XYZ CORP /MD/" yields the token `MD` (Maryland).
  The same holds for other state tags, so any two-letter suffix is unsafe.
- **Do not add `II`/`III`/`IV`**: "ABC FUND II LP" and "…PARTNERS III" are common.
- `DR` and `ET AL` could be measured; `ET AL` marks joint individual filers.

**`fund_report`** (ours: N-CEN, N-CSR, N-CSRS, NPORT-P) vs edgartools
`PRIMARY_INVESTMENT_FORMS` {N-CSR, N-CSRS, NPORT-P, NPORT-EX} and secondary
{N-CEN, N-PX} (`categorization.py:108-122`): edgartools treats N-CEN as a
**weak** signal ("can be filed by companies with investment activities") and
adds NPORT-EX. Worth measuring: add `NPORT-EX`; check how many step-7a deferrals
hang on N-CEN alone.

**`bdc_election`** (ours: N-54A) vs edgartools `BDC_FORMS` {N-2, N-2ASR,
N-23C-2} (`categorization.py:126-130`) and the `814-` file number
(`data.py:516-532`). N-2 is also filed by closed-end funds, so it is not a BDC
signal by itself. `N-54A` (the election) and the `814-` file number are the two
exact ones; N-54C is the withdrawal.

**`form_10`, `private_offering`, `emerging_growth`**: edgartools has nothing better.
`COMPANY_FORMS` includes `10-12G` (`constants.py:20`) but not Form D.

### 2c. `_classify_is_individual` as rules

It is a first-match step list, exactly our rule shape. Each signal maps to an
existing primitive except two:

| edgartools signal (`constants.py`) | As our rule |
|---|---|
| 1 `insiderTransactionForIssuerExists` → company (`:249`) | `field_in_set@1` on a new reader field; **the reader does not carry it today** |
| 2 tickers/exchanges → company (`:253-256`) | `fields_all_empty@1` negated: needs a `fields_any_present` form, or `evidence_present@1` |
| 3 state of incorporation → company (`:259`) | `evidence_present@1` |
| 4 entity type ≠ other → company (`:265`) | `field_in_set@1` |
| 5 a company form in the first 50 forms (`:269`) | `values_overlap@1` with a declared list |
| 6 EIN ≠ `000000000` (`:276`) | needs the placeholder read as none (`none_values`, §3c), then `evidence_present@1` |
| 7 company name keyword (`:282`) | `token_match@2` |
| 8 `insiderTransactionForOwnerExists` → individual (`:286`) | `field_in_set@1`; reader field missing |
| CIK exceptions (1033331, 315090) | A declared exclusion list, never code: `field_in_set@1` on `cik` at the first step, with a stated reason |

The default "individual" (`:290`) is the part not to copy: our rule defers what
it cannot prove (`company.yaml:205-207`). As a Person rule, edgartools' chain is a
**candidate** to be measured by a Proving Run, not a proven rule; the repo already
ran it only for name display.

## 3. The engine beyond Company

### 3a. What each domain's sources carry, and what edgartools already does

| Domain | Source (bronze) | Identifiers the source carries | edgartools support (cited) |
|---|---|---|---|
| Person | Form 3/4/5 reporting owners; Form D related persons; N-CEN/N-PORT officers; ADV principals | owner CIK (Form 4), none on Form D persons, CRD (ADV individuals) | Owner parsing `edgar/ownership/ownershipforms.py`; transaction codes `:160-190`; name parts `formatting.py:167-181`; `_classify_is_individual` |
| Security | 13F info table; Form 4 (title only); N-PORT holdings | CUSIP (13F, N-PORT), ISIN, ticker, "other" ids (N-PORT `Identifiers` `funds/reports.py:307-320`), LEI of issuer (N-PORT) | CUSIP shape only `format_multiline.py:26,61-66`; `ct.pq` CUSIP→ticker; **no** check-digit or ISIN validation |
| Fund Structure / Fund Series | N-CEN, N-PORT, SEC series/class list, GLEIF FUND | SEC series `S000……`, class `C000……`, CIK, LEI, SEC file number `811-`/`814-` | Series/class detection by "letter + digits" (`funds/core.py:235-240`); header parsing `funds/data.py:76-79`; list fetched from SEC (`funds/reference.py:460-515`) |
| Adviser | Form ADV (repo parser), N-CEN adviser block, 13F other managers | CRD, SEC file number `801-`, LEI, CIK | N-CEN models carry `crd_number`, `lei`, `file_number` (`funds/ncen.py:61-135`); 13F `OtherManager(cik, name, file_number)` (`thirteenf/models.py:46-50`); Form D recipient CRD (`offerings/formd.py:122-124`); no ADV |

### 3b. Identifier formats to add to `FORMATS` (`adapters.py:56-59`)

Each is a pure function like `_lei` (`adapters.py:43-50`): return the canonical
value or raise `UnsupportedRecord`. None needs an edgartools import.

| Name | Shape and check | Who needs it | edgartools |
|---|---|---|---|
| `cusip` | 9 chars `[0-9A-Z*@#]`, Luhn-style mod-10 over the first 8 (odd positions doubled) | Security (13F, N-PORT) | Shape only; our check passed all 67,679 `ct.pq` rows, a ready test set |
| `isin` | 2-letter country + 9 alphanumerics + check digit (letters → numbers, then Luhn) | Security (N-PORT) | None |
| `sec_series` | `S` + 9 digits | Fund Series | "starts with S, rest digits" (`funds/core.py:235`) |
| `sec_class` | `C` + 9 digits | Fund share class (a Security or a class record) | same (`:239`) |
| `crd` | 1–8 digits, no check digit, leading zeros dropped | Adviser, Person (ADV) | None; our `normalize_identifier@crd-v1` (`primitives.py:79-81`) already exists for matching |
| `ein` | 9 digits, optional hyphen after 2; `000000000` is none (via `none_values`) | lookup only, Company and Fund | Only the `000000000` test (`constants.py:276`) |
| `sec_file_number` | `\d{2,3}-\d{1,6}` (e.g. `801-`, `811-`, `814-`, `028-`) | Adviser, Fund, BDC signal | Prefix test only (`data.py:530`) |
| `ticker` | not an identity; if kept, upper-case text, lookup only | Security (lookup) | None |
| `figi` | 12 chars, `BBG` prefix, mod-10 check | Only if a source carries it | None; no captured SEC source does |

### 3c. The trial gaps, and the smallest fix for each

From `claude/rules-07-skill:.scratch/rules-skill/trials/round-2/sec/rules-log.md:430-507`,
`…/round-2/gleif/rules-log.md:498-518,661-663` and `…/round-2/answer-key.md:57,76,89-102`.

| Gap | Smallest addition | Where | Also serves |
|---|---|---|---|
| A placeholder meaning "none" (EIN `000000000`, GLEIF `NULL`, ELF `8888`) | Contract key `none_values: {<field or identifier>: [values]}`; `normalize` treats a listed value as unknown before the format runs | `adapters.py` near `_blank` (`:70-71`) and the identifier loop (`:239-244`); a few lines | Person (Form D "N/A"), Fund (N-CEN "N/A"), `_classify_is_individual` signal 6 |
| Lookup-only identifiers (EIN, SEC's LEI, tickers) | Contract key `lookup_identifiers: {namespace: path}` stored beside `identifiers`, **outside** the merge's authoritative check | `adapters.py` (read) and `merge.py` near `:518` (`authoritative_identifier_conflict` skips them); binding already refuses them (`activation.py:326`) | Security tickers, Fund CIK-on-class, Adviser `801-` numbers |
| Former names as aliases | Contract key `aliases: {path: <list path>, name: name, from: from, to: to}` producing dated alias values | `adapters.py`; needs `value()` to read a list (today it cannot, `:119-125`) | Person name history, Fund Series renames |
| A kind taken from a record in another file (GLEIF relationship start node's category) | Contract key `kind_from: {source: gleif.level1.v1, key: [start]}` resolved in the Merge Stage, which holds both; until resolved the record waits | merge stage, not `normalize` (one record cannot see another) | 13F holdings (holder kind from the filer), N-PORT (series kind) |
| A publication-level contract (`native_contract`, `publication_contract`, `company_leis`) | A `publication:` section in `rules/sources/<source>/source.yaml`, read by a new `files.publication()`; the approved LEI list as its own pinned reference file | `edgar_warehouse/rules/files.py`; `gleif_source.dataset_contract()` must skip it | Any numbered release (SEC series/class list, N-CEN bulk) |

### 3d. Primitives the next domains need

Keep to the ones a measured rule would call. Each is a few lines in
`primitives.py` beside `_values_overlap` (`:174-187`).

| Primitive | What it tests | First use |
|---|---|---|
| `values_prefix_overlap@1` | how many list values start with a declared prefix | BDC by `814-` file number; adviser `801-` |
| `field_matches_format@1` | a field passes a named `FORMATS` entry (no regex in the document) | "has a valid CUSIP/CRD", Person vs Company by CRD shape |
| `fields_any_present@1` | at least one declared field is non-empty | edgartools signal 2 (tickers or exchanges) |
| `code_in_reference@1` | a field's code is in a named `rules/reference/` table, optionally with a column value (e.g. `type: US`) | place type (US/CANADIAN/FOREIGN), transaction codes |

Security title normalization already lives in code (`edgar_warehouse/mdm/clean/securities.py:7-8`);
its class and option words could move to a declared list, but only when a second
title rule appears.

## 4. Recommendations, in order (recommendations, not decisions)

| # | What | Cost | Unblocks |
|---|---|---|---|
| 1 | `none_values` contract key | Small code change in `adapters.normalize`; new mapping versions for SEC and GLEIF | EIN placeholder, GLEIF `NULL`, ELF `8888`; a clean EIN for lookup |
| 2 | `lookup_identifiers` contract key, exempt from the authoritative-conflict veto | Small code change (`adapters.py`, `merge.py`); a column or index for lookup is separate | The operator's EIN / SEC-LEI / ticker decision without a false veto |
| 3 | `FORMATS`: `cusip`, `isin`, `sec_series`, `sec_class`, `crd`, `ein`, `sec_file_number` | ~60 lines with tests; `ct.pq` is the CUSIP test set | Security, Fund, Adviser record keys and identifiers |
| 4 | `rules/reference/cusip-tickers.yaml` (or parquet) from `ct.pq`, pinned by sha256, lookup only | A data file | Security display ticker; a CUSIP cross-check for 13F |
| 5 | Measured proposals from edgartools' lists: `NPORT-EX` in `fund_report`; `FOUNDATION`, `ASSOCIATION`, `NA` in `company_legal_form`; `DR`, `ET AL` in `person_suffix`; **never** `MD`, `II`–`IV` | Data only, each needs a Proving Run and the operator's approval of the new digest | Fewer deferrals at steps 7a, 10, 9 |
| 6 | BDC by `814-` file number: reader carries file numbers; `values_prefix_overlap@1` | Reader change + one primitive + a Proving Run | A better step 7b and the future Fund profile |
| 7 | `aliases` contract key (former names) | Small code change; `value()` must read lists | Company renames (CONTEXT: "the old name is an alias"), Person and Fund later |
| 8 | Person classification: edgartools' 9 signals as candidate steps for a Person rule, with the two insider flags added to the reader | Reader change + a new rule file + a Proving Run | Person from SEC submissions |
| 9 | `publication:` section and `kind_from` | Moderate: loader, GLEIF reader, Merge Stage | GLEIF relationships beyond a Company-only scope; numbered releases |
| 10 | `secforms.csv` as a description table for the Mapping Document | A data file | Readable rules; no identity effect |

Not recommended: `company_tickers.parquet` (use our dated bronze), `_codes.py`
ISO tables (truncated and wrong), `portfolio_managers.json` and
`popular_us_stocks.csv` (hand lists without evidence), `reverse_name` for
identity, and edgartools' "default individual" and hard-coded CIK exceptions as
code.
