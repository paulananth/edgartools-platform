# Onboard funds and securities with the skills alone

Priority: 79, tier 1, in flight (raised by the operator, 2026-10-14). Map: [Rebuild priorities](../map.md).

Type: task (onboarding). Status: claimed (Claude, 2026-10-14 ET, branch `claude/nport-onboarding`). Blocked by: none.

## Why

Operator, 2026-10-14: "what is next on the goal must add a new source onboard using just the skills securities and funds funds hold securities", then "Tickers and cusips are attached to securities ie 13F", "You must use only the data onboarding skills nothing else" and "To build new source extract and mastering".

The data: the SEC's Form N-PORT quarterly data set for 2026q2, one zip downloaded once with the operator's permission ("One N-PORT quarter (Recommended)", 2026-10-14), kept locally. Securities carry their CUSIPs and tickers, as 13F states them; the local 13F information tables are the other source of securities. Earlier N-PORT tickets 26-30 are open design questions; this onboarding answers them from the data, through the skills.

## Checklist

- [x] The capture: `2026q2_nport.zip`, one request, 440,699,889 bytes, sha256 `077cc836…`, 32 members (30 TSV tables, a metadata file, a readme), 1.55 GB unpacked 2026-10-14 17:37 ET
- [x] discover: data-profiling over every table; the operator's answers; approved findings (13F 2026-10-14 20:54 ET; N-PORT 2026-10-15 06:29 ET)
- [x] plan-parts: one onboarding per part, in dependency order: N-PORT Security, registrant Company, Fund, HOLDS (onboarding log) 2026-10-15 06:29 ET
- [ ] For each part: identify, profile, map (the source extract and the Dataset Contract), quality, metadata, test, approve, switch-on
  - [x] Part 1, N-PORT Security with OpenFIGI deciding a CUSIP's ISIN: test run, quality (issuer name stand-in withheld), Proving Run (423,562 Securities, 0 CUSIPs and 0 ISINs on two, second pass changed nothing), rules approved under the standing words; #999 merged 2026-10-16 06:29 ET
  - [x] Part 2, the registrant as a Company: test run, Proving Run (1,947 Companies, 0 CIKs on two, second pass changed nothing), rules approved under the standing words; #1001 merged 2026-10-16 07:55 ET
  - [x] Part 3, the Fund (kind `fund_structure`): test run, Proving Run (12,937 Funds, 0 series ids and 0 LEIs on two, second pass changed nothing), rules approved under the standing words; #1003 merged on the operator's words "merge one by one" 2026-10-16 09:13 ET
  - [ ] ~~IS_SUBFUND_OF from a Fund to its registrant~~ deferred (operator, 2026-10-16: "Funds now, link later (Recommended)"): a profile needs a stated start date and no capture states when a series began; the registrant's CIK stays on each Fund, lookup only
  - [ ] Switch-on of parts 1-3's matching rules: waits for the operator's word
- [ ] Securities from 13F: CUSIP and ticker attached to the Security
  - [x] 13F findings approved: operator, "yes approve the 13F findings", 2026-10-14 20:54 ET
  - [x] map: `rules/sources/sec.thirteenf.information_table/` and `rules/merge/kinds/security.yaml` (matching rule `security-cusip`, declared, not switched on); tested on all 999 local files, 20,311 Securities accepted, 9,631 set aside (onboarding log) 2026-10-14 22:31 ET
  - [x] quality: 0 checks drafted, no `quality.yaml` (onboarding log; skill line in PR #982) 2026-10-15 05:30 ET
  - [x] Proving Run: 20,311 Securities, 0 CUSIPs on two Securities, second pass changed nothing (`proving-run.json`) 2026-10-14 22:51 ET
  - [x] approve and switch on the Security matching rule `security-cusip` and its CUSIP Identifier Contract: operator, 2026-10-15 06:27 ET, "merge 985 when green agreed for the rest"; recorded in `rules/merge/policy.yaml` (`automatic_rules`) and `rules/merge/kinds/security.yaml` (`identifiers.cusip.verification`, the Proving Run report's sha256) 2026-10-15 06:28 ET
  - [ ] ~~ticker on the Security~~ deferred to ticket 80 (Onboard OpenFIGI): the 13F files carry no ticker
  - [ ] ~~which filed name and title a Security keeps~~ deferred to ticket 84: filers disagree on 13% of holding rows
- [x] N-PORT findings answered from the rulings (`.scratch/onboarding/sec.nport/findings-answers.md`) and approved: operator, 2026-10-15 06:27 ET, "merge 985 when green agreed for the rest"; each answer in its question, `approval.status: approved` 2026-10-15 06:29 ET
- [ ] Funds hold securities: `HOLDS` from a fund to a Security
- [ ] The N-PORT Security run wiring (Bookkeeping) passes the quarter's `period` in the holdings reading's context and `effective_column: period` to `mdm.prepare` (ticket 100); from the second quarter on, `publication_key`, `revision` (one more each quarter) and `effective_at` instead (ticket 101, #1023); the issuer reading takes the same `isin` pair set as the holdings reading (ticket 102); no platform command builds the N-PORT run yet
  - [x] Measured (2026q2): 5,347,869 holding rows make 3,251,006 distinct Fund-to-Security links by CUSIP from 12,387 Funds; 830,315 rows come from registrants with no series (the link starts at the Company) 2026-10-16 08:21 ET
  - [ ] The Merge Stage made fast enough to apply them: ticket 96 merged (#1007, 2026-10-16 09:12 ET; a batch 4.4 s to 2.5 s); the rest is `mdm.save_batch` (1.3-1.5 s a batch), measured there
- [ ] Every gap in a skill found on the way: fixed in the skill, on its own branch
  - [x] ticket 81 (identifier types as configuration, #975 merged), ticket 82 (a reduction reads several source extracts, #978 merged), profiler reuse (#976 merged)
  - [x] ticket 83 (no output caps, #981), data-quality and identifier types (#982), profiler issued identifiers (#983): CI green, merged one by one on the operator's words "merge one by one" 2026-10-15 06:07 ET
- [ ] PR, CI green, merge on the operator's word
  - [x] #984, the 13F Security, switched on: CI green, merged by the operator 2026-10-15 06:55 ET
  - [x] the N-PORT parts 1 and 2: #999 and #1001, CI green, merged on the operator's words "merge one by one" 2026-10-16 07:55 ET
  - [x] part 3: #1003, CI green, merged on the operator's words "merge one by one" 2026-10-16 09:13 ET; main's CI green after it
- [ ] Learning → skill
