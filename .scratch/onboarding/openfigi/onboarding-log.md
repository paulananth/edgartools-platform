# OpenFIGI onboarding log (ticket 80)

Operator, 2026-10-17: "productionize figi source". This is ticket 80's onboarding of OpenFIGI as its own source, run through the data-onboarding skill. Branch `claude/openfigi-onboard`.

## The source

What is known before profiling. These are counts only; the values stay on this machine.

- **Provider and dataset.** This is OpenFIGI's mapping API (`POST /v3/mapping`). There is no bulk file. Each request holds up to 100 jobs `{idType, idValue}`. Each answer is a list in job order, and each item is `data` (the listings found), `warning` (nothing found) or `error` (identifier refused). Ticket 80, "What the source is", has the field list and the limits.
- **Capture.** The capture of 2026-10-15 is kept outside the repo. It was not run as a Bookkeeping capture.
  - 7,714 answer files with their 7,714 request files: 3,837 for CUSIPs and 3,877 for ISINs.
  - `receipts.jsonl`: one line per file, with `sha256`, `bytes`, `request_sha256` and `status`.
  - The operator's ruling: "Open figi rarely changes do not download again". No new request is made.
- **Outcomes**, counted over every answer:
  - 771,219 answers. 733,538 found listings and 37,681 found nothing. 0 refused: only CUSIPs that pass their check digit were sent.
  - 2,184,699 listings, with at most 301 for one answer.
- **Fields of a listing:** `figi`, `compositeFIGI`, `shareClassFIGI`, `ticker`, `exchCode`, `name`, `securityType`, `securityType2`, `marketSector`, `securityDescription`.
- **Known from the repo:**
  - An answer names no identifier; it is tied to its job by position. `rules/sources/sec.nport.security/figi-requests.yaml` and `figi-answers.yaml` do this tie: 771,219 answers tied, 0 differences from a direct match (#999).
  - Bonds and loans have no composite FIGI: Mtge, Muni, Corp and Govt listings never carry one, and every Equity listing does (onboarding log of `sec.nport`, 2026-10-15).
  - Identifier types already declared: `rules/identifiers/cusip.yaml` and `isin.yaml`. FIGI has none yet.
  - Rulings: FIGI, ticker and SEDOL are lookup only on a Security; CUSIP and ISIN join (operator, 2026-10-14, `rules/merge/kinds/security.yaml`). A ticker belongs to Security, not Company.
  - Existing kinds: company, person, security, fund_structure.
  - Today the capture is used only inside `sec.nport.security` (`figi-*.yaml`), to decide which ISIN a CUSIP carries.

## discover

Profiling input: two staging folders of links to the capture files (no copy), with the file names kept (`id_cusip/00000.json`):
- `answers`: 7,714 files, 559 MB;
- `requests`: 7,714 files, 60 MB.

The positional tie between them is known (above) and is not something profiling measures.

### The one profiling run (2026-10-17 08:48 ET, full scan, 176 s)

Findings: `~/edgar-local-tmp/t80/profile/findings.yaml` and `REPORT.md`, outside the repo.

- **Six parts:**
  - requests: 771,219 rows, keyed by `idValue`. Every asked identifier is distinct. Its ISINs pass their check digit.
  - answers: 771,219 rows. No column of its own is unique, because an answer is tied to its request by position.
  - listings (`answers.data`): 2,184,699 rows.
  - The three FIGI levels, found as entities carried inside the listings. Each value of a listing's fields depends on its FIGI, so these are measured, not guessed:
    - listing FIGI: 1,392,524;
    - composite FIGI: 271,051;
    - share-class FIGI: 26,509.
- **The FIGI hierarchy holds exactly.** A listing points at one composite, and a composite at one share class, with inclusion 1.0. Bonds and loans have no composite: 1,475,687 of the 2,184,699 listing rows carry one.
- **Values that disagree within one FIGI:**
  - Under one listing FIGI, 6 rows give another name and 4 another security type. These are steward items.
  - Under one composite, 22,059 listing rows give another name and 745 another security type.
  - Under one share class, 23,486 rows give another name.
  - So a composite's or share class's name varies across its listings, and the listing's own name is the one to keep.
- **Code lists:**
  - market sector: 9 codes;
  - security type: 34;
  - security type 2: 10;
  - exchange code: counted per part in `findings.yaml`.
- **"Hierarchies" from market sector to exchange code or security type** hold only 0.992 to 0.9998. They are code co-occurrence, not reference hierarchies, so they are not proposed.
- **Profiler questions 1–6, recorded in `findings.yaml` as following from rulings or repo facts, not as operator words:**
  - No new kinds: the three FIGI levels are lookup-only cross-references of a Security. Ruling of 2026-10-14: "FIGI, ticker and SEDOL are lookup only".
  - An answer's key is the identifier asked, through its request.
  - Requests and answers together are a crosswalk from a Security identifier to its listings.

## plan-parts and rulings

- **Q (2026-10-17, after findings):** how OpenFIGI attaches to a Security, given that a cross-reference holds one value per record and a CUSIP has up to 301 listings.
  **A:** "(c) MDM + silver listings (Recommended)". This means:
  - one MDM record per identifier asked, joining the Security that holds it and never creating one;
  - only single-valued levels go on the Security;
  - all listings land in silver, keyed by listing FIGI and linked to the Security.
- **Qualification on 10 sample answers** (explored, sample only):
  - Bonds: one listing, no composite.
  - Equities: 1 to 31 composites (one per country), 1 to 9 tickers, one share class, and exactly one composite whose exchange code is US.
- **Q:** which composite and ticker a Security carries.
  **A:** "US composite (Recommended)", at 08:56 ET. A Security carries:
  - the share-class FIGI when there is exactly one;
  - the US composite FIGI (the composite listing with exchange code US) and its ticker, when there is exactly one;
  - for an answer with one listing, that listing's FIGI and ticker.

  Everything else stays in silver only.
- **Parts, in order:**
  1. **MDM:** `openfigi.security.v1`, onto Security. It joins by the CUSIP or ISIN asked, with `on_no_match: wait`. Cross-references are lookup only. An identifier with nothing found is set aside.
  2. **RDM:** market sector, security type, security type 2 and exchange code. They are logged as code sets; the Security keeps the values as given until RDM publishes them.
  3. **Silver:** the listings, keyed by listing FIGI and linked to the Security.

## map: a gap in the reading grammar (2026-10-17 08:59 ET)

The rulings need each identifier's single share class, its US composite and ticker, and the FIGI of its only listing. These are counts and members over one row per listing that names its identifier.

An answer is tied to its identifier only by its position in the file. The grammar gives either one row per answer, with its position, or one row per listing, without it. The streamed form would carry the position into each listing, but it takes only a wrapped array, and OpenFIGI's files are bare arrays.

This is engine work, written as ticket 104 ("Stream a bare JSON array"), with a minimal failing example. Configuration only, so it waits for the operator's word to code.

## The full configured run (2026-10-17 12:45–12:54 ET, 9 min)

`openfigi_run.py`; report `openfigi-run.json` (counts only). It reads the kept capture only.

- **CUSIPs:** 353,491 records accepted, plus 30,121 OpenFIGI did not find, set aside.
  - 344,986 carry the FIGI and ticker of their only listing.
  - 9,482 carry a US composite and 10,058 a share class.
- **ISINs:** 380,047 records accepted, plus 7,560 not found.
  - 357,830 carry a single listing's FIGI.
  - 13,910 carry a US composite and 25,532 a share class.
- Every record equals a direct count from the raw answers: 0 differences, and every identifier prepared.
- **Faults found on the way, each fixed before this run:**
  - The stream bounds held the output of a whole reading, not of one file, so they were raised from measurements.
  - Each answer file's pair set was built from the whole group's requests, which is quadratic: about 6 minutes for a reading of 480 files. Each file now uses its own request file.
  - Putting the 8 readings together loaded several GB. The streamed reduce now gives each identifier's answer instead.
  - The 16 readings run at once, one process each: 91 s for all 7,714 files.
