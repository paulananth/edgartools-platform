# Onboarding log: SEC Form N-PORT data set (funds, securities, holdings)

Skill: data-onboarding (with data-profiling and data-quality, which it calls). Ticket: rebuild priorities 79.

## 2026-10-14

- 17:37 ET. Capture: the 2026q2 N-PORT data set, one download with the operator's permission ("One N-PORT quarter (Recommended)"); 440,699,889 bytes, sha256 `077cc836a978a593b29012219395fbe9c303d5e930f5be3b5f4353c3b02296fc`; kept at `~/.local/share/edgartools/clean-mdm/captures/sec.nport-datasets/2026q2/`. No other provider request.
- Operator: "Tickers and cusips are attached to securities ie 13F". "You must use only the data onboarding skills nothing else". "To build new source extract and mastering".
- discover: the data-profiling skill is not installed as its own skill on this machine (`Unknown skill: data-profiling`); its instructions were read from `skills/data-profiling/SKILL.md` in the repo. Logged as a gap: `data-platform`'s `skill install` or each `link.sh` should link it.
- 17:39 ET. discover, first run: the profiler refused the whole zip before reading a table: "one part holds JSON, JSON Lines or XML records of one format, found ['csv', 'htm', 'json']". The 30 tables sit beside a readme (`nport_readme.htm`) and a metadata file (`nport_metadata.json`). Skill fix (operator, standing, and 2026-10-14: "Fix the skills as you find problems"): a zip's table members are read as tables and every other member is listed under `dataset.not_read` with its reason. Branch `claude/profile-zip-documents`, 223 profiling tests pass; this onboarding uses that branch's profiler until it merges.
- The linked skills on this machine pointed at a main checkout 30+ commits behind `origin/main`; fast-forwarded. data-profiling, data-quality and data-platform were never linked; linked. data-modeling had no `link.sh`: added on the same fix branch.
- 17:43 ET. discover, second run started with the fixed profiler; full read (1.55 GB, under the 5 GB limit).
- 18:06 ET. discover, second run (zip fix only): 30 parts read, 24 minutes. Findings not used for approval: they came from a profiler with the gaps below. Investigation for the skill fixes (DuckDB over three tables, counts only): of 5,347,869 holdings, 3,564,226 carry a real CUSIP (385,382 distinct); the rest are stand-ins: "N/A" 1,169,603, "000000000" 614,038, "999999999" 17,511. "N/A" stands in for the issuer LEI on 1,953,420 holdings. Only 61% of CUSIPs carry one issuer name (each fund writes it its own way). 12,944 fund series over 14,416 reports; 99.9% keep one name. ISIN on 64% of identifier rows, ticker on 10% (with values such as "USD"), SEDOL on 195,610.
- Profiler gaps found, each fixed in the skill (branch `claude/profile-identifiers`, stacked on #973): stand-ins hid identifier shapes and check digits; no check-digit family for letter-and-digit identifiers; an entity had to repeat on half its part's rows and have a name agreeing on 95% of all rows; one registrant came out as three parts (CIK, file number, LEI); a part's own extensions and lists counted as evidence it was master data (holdings classed master at 1.0); every table of a folder got the folder's hash; files with no suffix (the 13F tables) were refused. Trial B still scores 52 of 52.
- `#973` (zip with documents, data-modeling link) review: two defects fixed (records beside tables called documents; a readme split tables of one header).
- 18:23 ET. discover, third run: the N-PORT quarter and the 999 local 13F information tables in one run, with the fixed profiler.
- 19:38 ET. discover, third run (N-PORT and 13F, 36 minutes): Security by CUSIP (385,381, carrying issuer name and LEI), Fund by series LEI (13,545, carrying series id and name), registrant by CIK (1,947), issuer by LEI (28,430); holding ids are links, not entities. Holdings still class master (0.833): their lists keyed by a shared sequence cannot be told from other parts by tests; decided by the operator below. 13F CUSIPs pass their check digit on 70% of distinct values (options: issue number 90x/95x); no 13F-to-N-PORT link at the 90% bar. The 13F files carry no manager.
- Profiler gaps found in this run and fixed (`claude/profile-identifiers`): the check-digit test ran only when no name followed and a country code counted as a name; a column of another part's keys became an entity; a list pointing at its own entity counted as pointing elsewhere. The new-kind questions name the column, not the existing kinds: the data-modeling skill places the parts (a fund is a profile on `fund_structure`).
- Operator rulings (2026-10-14, AskUserQuestion, exact answers):
  - Holdings: "Silver + MDM link (Recommended)": each quarter's holdings land in silver with the fund's and the security's MDM ids; MDM keeps one HOLDS link per fund and security.
  - Security identity: "CUSIP and ISIN join (Recommended)": ticker, FIGI and SEDOL are cross-references, lookup only.
  - Fund identity: "Series id and LEI join (Recommended)".
  - 13F: "Securities only, options aside (Recommended)": CUSIP joins, FIGI lookup only; Put and Call rows set aside as options; a CUSIP failing its check digit is a data quality exception; 13F holdings wait for the manager filings.
  - Issuer and registrant: "Registrant yes, issuer later (Recommended)": the registrant joins the Company master by CIK and each Fund links to it with IS_SUBFUND_OF; issuer LEI and name stay on the Security until rebuild priorities 22.
- 19:52 ET. discover, final run started with the finished profiler; its findings go to the operator for approval.

## 13F findings approved (2026-10-14 20:54 ET)

- Findings: `~/.local/share/edgartools/clean-mdm/profiling/thirteenf-check/findings.yaml` (13F information tables profiled alone, 422 s, full scan: 2,953,581 holding rows; 31,071 CUSIPs; 19,997 FIGIs).
- Profiler fix first (branch `claude/profile-identifiers`): a check-digit family passing at least 50% and five times chance is still the column's family, its failures defects. 13F CUSIPs pass 70% (options carry invented issue numbers), so before the fix the Security was keyed by FIGI.
- The four questions answered from earlier rulings: no designed key for the holding rows (they wait for manager filings, bronze); the CUSIP entity is the kind `security`; FIGI a cross-reference, lookup only; Put/Call rows set aside.
- Operator's words: "yes approve the 13F findings".
- N-PORT findings: reuse `profiling/sec.nport-2026q2-final/` (operator, 2026-10-14: "why cant we reuse the already completed profiling"); its questions come later.
- CUSIP shape (operator asked "cusip is 9 digit with checkdigit"): nine characters, the ninth a check digit; 377,553 of 385,381 distinct N-PORT CUSIPs carry a letter in the first eight.

## 13F Security: map and test (2026-10-14 22:31 ET)

- Configuration (config only): `rules/sources/sec.thirteenf.information_table/` (`source.yaml`, `reduce.yaml`, `combine.yaml`) and the new kind's rules `rules/merge/kinds/security.yaml` (matching rule `security-cusip`: a CUSIP joins the one Security that holds it, or creates it; its Identifier Contract `normalize_identifier@cusip-v1`; declared, not switched on). Mapping Documents generated.
- The run: `source.read` (8 units of 999 files) → a reduction over all units (`securities` every CUSIP, `names`, `titles`, `figis`) → `source.combine` (one row per CUSIP, name, title and the lexically first FIGI joined) → `mdm.prepare` → the Dataset Contract.
- Size caps stopped the first trials (a 112 MB source extract refused by the reduction; FIGI dropped for a 100,000-row output cap). Operator: "i told you to not to have caps". Fixed in the engine, ticket 83 (PR #981, CI green): large outputs are written in pieces.
- A field's source path must be a plain path or a join for the Mapping Document, so the reading keeps the filed name, title and FIGI in their own tables of only the rows that carry them (`select`), instead of marking blanks.
- Tested locally, all 999 files, the ticket 83 engine: read 276 s, reduction 90 s, no refusals. 29,942 CUSIP records: 20,311 Securities accepted, all with issuer name and class title, 10,681 with a FIGI (lookup only); 9,603 set aside, check digit fails (options, ruled a data quality exception); 28 set aside, not CUSIP-shaped.
- Next: quality checks (data-quality skill), the Proving Run on MDM, approval, switch-on.
