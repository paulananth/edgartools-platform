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
- [ ] Every gap in a skill found on the way: fixed in the skill, on its own branch
  - [x] ticket 81 (identifier types as configuration, #975 merged), ticket 82 (a reduction reads several source extracts, #978 merged), profiler reuse (#976 merged)
  - [x] ticket 83 (no output caps, #981), data-quality and identifier types (#982), profiler issued identifiers (#983): CI green, merged one by one on the operator's words "merge one by one" 2026-10-15 06:07 ET
- [ ] PR, CI green, merge on the operator's word
  - [x] #984, the 13F Security, switched on: CI green, merged by the operator 2026-10-15 06:55 ET
  - [ ] the N-PORT parts: their own PRs, after ticket 89 (a large CSV or TSV is read in pieces)
- [ ] Learning → skill
