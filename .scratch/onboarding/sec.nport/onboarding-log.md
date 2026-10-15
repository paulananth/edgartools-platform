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

## 13F Security: Proving Run (2026-10-14 22:51 ET)

- Disposable PostgreSQL 16 (container removed), `.scratch/onboarding/sec.thirteenf.information_table/proving_run.py`; report `proving-run.json` (counts only). The matching rule `security-cusip` switched on only in the run's copy of the policy, stamped "proving-run".
- First pass 251 s, 62 batches, slowest 18 s: **20,311 Securities, one per CUSIP**; 20,311 bind decisions; every Security carries issuer name and class title. **0 CUSIPs on two Securities.** 9,631 records set aside, each an open review: 9,603 `invalid_cusip_checksum`, 28 `invalid_cusip`.
- Second pass (75 s) **changed nothing**.
- (The report's `read.assertions` 40,622 counts each assertion twice, once per apply loop; the stage counts are the measure.)
- Next: the operator's approval of the Security matching rule and its CUSIP Identifier Contract, then switch-on.

## 13F Security: quality (2026-10-15 05:30 ET)

- The data-quality helper drafts **0 checks** for part `thirteenf.cusip`. Of profiling's two items: the CUSIP check digit is the identifier type's (ticket 81: a failing CUSIP is set aside as `invalid_cusip_checksum`, 9,603 records); the class title disagreement (381,219 of 2,953,581 holding rows differ from their CUSIP's most common title) is between holding rows, and each Security record keeps one title after the reduction, so no record-level check can catch it.
- Decided (follows from the rulings, nothing for the operator to choose): **no `quality.yaml`** for this source. A file with no checks adds a quality version and changes every record id for nothing. The skill now says so (PR #982).
- The title disagreement, and the reduction keeping the lexically first filed word rather than the most common one, are ticket 84 (A Security's issuer name and class title: which filed words it keeps).

## Approvals (2026-10-15 06:27 ET)

- Operator's words: "merge 985 when green agreed for the rest". "The rest" were the two other questions asked: switch on the Security matching rule `security-cusip` with its CUSIP Identifier Contract, and approve the N-PORT findings answers.
- `security-cusip` switched on: `rules/merge/policy.yaml` (`automatic_rules`, deterministic) and `rules/merge/kinds/security.yaml` (`identifiers.cusip.verification`: the Proving Run report's sha256 `52cb4469...fc80`, approved 2026-10-15T10:27:01Z). The merge rules load; 367 tests that read them pass.
- N-PORT findings: the 25 answers written into the questions, then approved with data-profiling's `approve` (06:29 ET).

## plan-parts: N-PORT 2026q2, in dependency order (2026-10-15 06:29 ET)

From the approved findings (`profiling/sec.nport-2026q2-final/findings.yaml`). Reference parts: none ruled (code lists stay in bronze until RDM work picks them up). Metadata: SUBMISSION goes to Bookkeeping.

1. **Security from N-PORT holdings** (master, kind `security`, existing rules `rules/merge/kinds/security.yaml`): CUSIP (`FUND_REPORTED_HOLDING.ISSUER_CUSIP`) joins through `security-cusip`; ISIN (`IDENTIFIERS`) is a second joining identifier and needs its own matching rule, declared and proved before switch-on. Issuer name and issuer LEI as filed, on the Security. Source folder `rules/sources/sec.nport.security/`, code `sec.nport.security.v1`.
2. **Company: the registrant by CIK** (master, existing kind `company`, a new source for it): `REGISTRANT.CIK` joins through the Company CIK rule; folder `rules/sources/sec.nport.registrant/`.
3. **Fund** (master, kind `fund_structure`, `fund` profile, new merge rules): series id and series LEI join; IS_SUBFUND_OF its registrant, onboarded together with it.
4. **HOLDS and the holdings** (transaction, silver target, onboarded separately): each quarter's `FUND_REPORTED_HOLDING` rows land in silver with the Fund's and the Security's MDM ids; MDM keeps one HOLDS link per Fund and Security.

Holding details (`DEBT_SECURITY_REF_INSTRUMENT`, `REPURCHASE_AGREEMENT`, `DESC_REF_*`, `MONTHLY_RETURN_CAT_INSTRUMENT`, `FUND_VAR_INFO`, `NONFOREIGN_EXCHANGE_SWAP`, `EXPLANATORY_NOTE`) stay in bronze. Next: part 1, identify.

## 13F Security: Proving Run under the approved merge rules (2026-10-15 06:38 ET)

- Re-run with the repo's merge rules as switched on (no stand-in verification): **20,311 Securities, 0 CUSIPs on two Securities, 9,631 set aside, the second pass changed nothing**, as before. 9 min 40 s in all; first pass 271 s, second 295 s (75 s on the first run: not investigated, recorded).

## Part 1, Security from N-PORT: the source (2026-10-15 11:09 ET)

Known before any run (the run-once rule; no new scan of the data):
- `rules/identifiers/cusip.yaml`: nine characters, check digit `luhn over letter values`; `000000000` and `999999999` are filers' stand-ins for none, refused (`refuse_one_repeated_character`).
- `rules/identifiers/isin.yaml`: two-letter country, nine letters or digits, check digit `luhn over letter digits`; a US or Canadian ISIN holds the CUSIP as characters 3-11.
- Approved findings (`profiling/sec.nport-2026q2-final/`): 5,347,869 holdings, `ISSUER_CUSIP` always filled; 614,038 rows `000000000`, 17,511 `999999999`, 1,772 failing the check digit; 385,381 distinct CUSIPs. `IDENTIFIERS`: 6,749,116 rows linked by `HOLDING_ID`, ISIN filled on 64%, 397,025 distinct, 110 not ISINs (FIGI-shaped).
- Not in the findings: how CUSIP and ISIN pair. Ticket 90 adds it to profiling for the next source; here the one test run counts it.

## Part 1: rulings (2026-10-15, recorded 11:09 ET)

- Security key, operator: "Two contracts (Recommended)": `sec.nport.security.v1`, one record per CUSIP, carrying its ISIN as a second joining identifier when the pair is one to one; `sec.nport.security_isin.v1`, one record per ISIN, for holdings with no usable CUSIP. Both join through `security-cusip` and a new `security-isin` matching rule, proved and brought for approval.
- Engine facts that block the ISIN join in configuration: a reading's lookup set answers membership only (at most 1,000,000 values per set); a `select` cannot split rows by a pattern; a reduction holds its output rows in Python (about 5.3 million holdings). Ticket 91 written: a reading looks up a value in a large set.
- Operator: "Code 91 first": both contracts are built after ticket 91 merges, so the Security is onboarded once, with ISIN from the start.

## Part 1: OpenFIGI order (2026-10-15)

- Operator, asked whether OpenFIGI comes before the N-PORT Security: "Both, in parallel". The N-PORT Security test run goes ahead now (no provider requests); ticket 80's capture is set up beside it, and its requests wait for the operator's word for them and a key in their own terminal. FIGI's evidence is compared with the filed CUSIP and ISIN pairs before the ISIN matching rule is brought for approval.

## Part 1: the one test run, planned (2026-10-15 12:00 ET)

Configuration: `rules/sources/sec.nport.security/` (`identifiers.yaml`, `source.yaml`, `reduce.yaml`, `combine-pairs.yaml`, `combine.yaml`). Checked first on invented rows only: ISIN cleaning, and which table each holding goes to.

Stages, each run once, on `2026q2_nport.zip` (440,699,889 bytes, read in place by hash):
1. `identifiers.yaml`: IDENTIFIERS.tsv streamed into pieces (about 2 min).
2. The pair set `isin`, derived from step 1 (about 4.3 million pairs; ticket 91 measured 1.5 GB peak at this size).
3. `source.yaml`: FUND_REPORTED_HOLDING.tsv streamed once, each holding given its ISIN (about 6 min).
4. `reduce.yaml`, `combine-pairs.yaml`, `combine.yaml` (about 4 min together).
5. `mdm.prepare` for `security` and `security_isin`, then each record through its Dataset Contract (counts only).

Expected: about 15 minutes in all; peak memory 2 to 3 GB. Reported: records per contract, set-aside reasons, ISINs attached, pairs one to one, CUSIPs with several ISINs, ISINs with several CUSIPs, holdings with no usable CUSIP and no single ISIN.

## Part 1: the one test run (2026-10-15 12:01-12:27 ET, tested locally)

`security_test_run.py` beside this log; report `security-test-run.json` (counts only). Run once, 26 min 3 s, peak resident 3.6 GB (planned 15 min, 2-3 GB: the reduction took 480 s at 3.38 GB). First checked on an invented 6-holding ZIP (every stage, each case as designed).

| Stage | Time | Peak |
|---|---|---|
| identifiers reading (IDENTIFIERS.tsv) | 205 s | 0.11 GB |
| pair set + holdings reading | 460 s | 1.42 GB |
| reduce | 480 s | 3.38 GB |
| combine-pairs + combine | 155 s | 3.38 GB |
| prepare + contract, by CUSIP | 227 s | |
| prepare + contract, by ISIN | 35 s | |

- Holdings: 4,716,318 with a usable CUSIP, 417,552 with none but one ISIN; the rest (stand-in CUSIP and no single ISIN) make no record.
- `sec.nport.security.v1`: 385,382 records; **383,595 accepted**, every one with issuer name, class title and issuer LEI as filed; **354,274 carry their one-to-one ISIN**. Set aside: 1,769 `invalid_cusip_checksum`, 1 `invalid_cusip`, 17 `invalid_isin_checksum` (a FIGI filed as the CUSIP's one ISIN: the Security is set aside for its secondary ISIN).
- `sec.nport.security_isin.v1`: **35,309 accepted**, none set aside.
- Pairs: 414,777 distinct CUSIP and ISIN pairs; 354,373 one to one; 353,329 pairs where the ISIN holds the CUSIP (the US/CA rule); 520 CUSIPs filed with several ISINs; **17,219 ISINs filed with several CUSIPs** (attached to none). The OpenFIGI comparison (operator: "Both, in parallel") says which.
- Open for the operator before the Proving Run: the 17 Securities set aside for a bad secondary ISIN; adding N-PORT to the Security kind's sources (`defaults.sources`, a merge-rule change); the ISIN matching rule.

## Part 1: rules, metadata and quality (2026-10-15 12:58 ET)

- Merge rules (declared, not switched on): `nport-security-cusip`, `nport-security-isin` (both on `sec.nport.security.v1`) and `nport-isin-security-isin` (on `sec.nport.security_isin.v1`), each an identifier match with its cardinality, minting when nothing holds it. A record whose CUSIP and ISIN point at two Securities goes to review (binding.py). The ISIN Identifier Contract (`normalize_identifier@isin-v1`) has no verification yet. N-PORT's two codes added after 13F to `defaults.sources` (13F wins each field until ticket 84 rules) and to the CUSIP contract's `sources`: both merge-rule changes for the operator, with the Proving Run.
- Mapping Documents: `rules/sources/sec.nport.security/MAPPING.xlsx`, `rules/merge/kinds/security.xlsx` and 13F's (its "who wins" rows name N-PORT now); `rules mapdoc check` passes; `rules catalog plan` shows the new source.
- Quality (data-quality `draft`, then `measure` on the test run's normalized records, rebuilt from its prepared batches in 4 min, not a new read): one engine check drafted, an issuer name filed as a stand-in (`placeholder@1`, proposed `withhold`): **0 of 383,595 CUSIP and 0 of 35,309 ISIN Securities**, since each keeps its lexically first filed name. Not written yet: its `on_fail` is the operator's, asked with the approval. New code, logged not written: issuer LEI check digit (179,389 holdings; the LEI is a filed word, ruled); filed words differing between a key's holdings (ticket 84).
- The Proving Run waits for the OpenFIGI comparison (operator: "Both, in parallel"), so a rule FIGI changes is proved once, not twice. Ticket 92 (#994) is the capture; its first request waits for `OPENFIGI_API_KEY` in the operator's environment.

## Part 1: OpenFIGI's evidence on the filed pairs (2026-10-15 13:45 ET, explored)

Capture (operator: "Yes, run it (Recommended)"; key kept outside the repository, operator: "Reuse the OPENFIGI_API_KEY"): 7,714 mapping requests of 100 (383,612 CUSIPs, 387,607 ISINs; every accepted N-PORT one), 13:04-13:42 ET, 0 retries, through the capture's transport (ticket 92), each answer kept whole on this machine with its request and a receipt line (621 MB; `captures/openfigi/2026q2-nport/receipts.jsonl`). Not run as a Bookkeeping capture (no Journal, no leases): that is the scheduled feed's, later.

`security_figi_comparison.py` beside this log; result `security-figi-comparison.json` (counts only). Two securities are the same when any FIGI of one's listings (its own, composite or share class) is one of the other's: a bond or loan has no composite FIGI (all Mtge, Muni, Corp, Govt listings; every Equity listing has one), so composites alone called 337,521 agreeing pairs "different" (caught, rerun).
- Found: 353,491 of 383,612 CUSIPs; 380,047 of 387,607 ISINs.
- **The filed one-to-one pairs: 346,535 the same security, 128 different, 7,710 not both found.** Where FIGI can judge, the rule "ISIN joins when the pair is one to one in the quarter" is right on 99.96%.
- The 17,219 ISINs filed with several CUSIPs: FIGI names exactly one of them for 4,338, none for 12,880, several for 1.
- ISIN-only Securities (35,309): 5,395 share a FIGI with an N-PORT CUSIP; 27,438 share none; 2,476 not found.

## Part 1: the ISIN rule, with OpenFIGI (2026-10-15 14:07 ET)

- Operator, asked which ISIN rule goes into the one Proving Run (filed one to one; filed and FIGI agree; FIGI adds pairs too): **"Use FIGI to add pairs too"**. Read as the option said: it decides which ISIN a CUSIP Security carries; FIGI is not made an MDM identifier. OpenFIGI is now part of how Securities are identified (the earlier "FIGI lookup only" ruling is changed for this decision).
- Counted from the captured answers only (`security_figi_attachment.py`, `security-figi-attachment.json`), under "share a listing or composite FIGI" and again with share class: identical. The narrower meaning is used.
- **350,873 CUSIP Securities carry an ISIN**: 346,535 filed one to one and FIGI agrees; 4,338 where FIGI names the one CUSIP among several filed. Dropped: 7,838 filed pairs (128 FIGI disagrees, 7,710 cannot judge); 12,881 ISINs FIGI ties to none or several of their CUSIPs. Refused, counted: 1 CUSIP offered two ISINs; 1 ISIN FIGI ties to several CUSIPs. The 5,394 ISIN-only holdings FIGI ties to a CUSIP are all one-to-one pairs of that CUSIP already.
- The engine cannot tell whether two lists share a value: ticket 93 (a generic `overlap` expression), waiting for the operator's word. Then: OpenFIGI's reading (ticket 80), re-run only the stages after the reduction, then the one Proving Run.

## Part 1: matching OpenFIGI's answers to their identifiers (2026-10-15 14:22 ET)

- An answer names no identifier: it is matched to its request by position. Probed on an invented two-job request and answer (no data, no request): one row per job works (`each: item`), its position works, its FIGIs only as one text; two gaps: no number turned into text for a key (batch and position), and no list of one field from a list of objects (each job's FIGIs as a list for `overlap`).
- Operator, asked whether to code tickets 94 and 95 for them: **"Open figi rarely changes do not download again fix engine"**. So: tickets 94 and 95 are coded; the capture of 2026-10-15 is kept and reused, and a later quarter asks OpenFIGI only for identifiers it has not been asked (ticket 80, Refresh).

## Standing approval of rules (2026-10-15 18:56 ET)

- Operator: **"Approved the rules always"**. Read as: each rules approval for this onboarding (Rules versions, quality checks and their `on_fail`, merge-rule declarations) is recorded with these words and its test evidence, without a question. Still needs a passing test first. Not covered: switch-on, merges, provider requests; each keeps its own word.
