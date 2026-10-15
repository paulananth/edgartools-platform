# Onboard funds and securities with the skills alone

Priority: 79, tier 1, in flight (raised by the operator, 2026-10-14). Map: [Rebuild priorities](../map.md).

Type: task (onboarding). Status: claimed (Claude, 2026-10-14 ET, branch `claude/nport-onboarding`). Blocked by: none.

## Why

Operator, 2026-10-14: "what is next on the goal must add a new source onboard using just the skills securities and funds funds hold securities", then "Tickers and cusips are attached to securities ie 13F", "You must use only the data onboarding skills nothing else" and "To build new source extract and mastering".

The data: the SEC's Form N-PORT quarterly data set for 2026q2, one zip downloaded once with the operator's permission ("One N-PORT quarter (Recommended)", 2026-10-14), kept locally. Securities carry their CUSIPs and tickers, as 13F states them; the local 13F information tables are the other source of securities. Earlier N-PORT tickets 26-30 are open design questions; this onboarding answers them from the data, through the skills.

## Checklist

- [x] The capture: `2026q2_nport.zip`, one request, 440,699,889 bytes, sha256 `077cc836…`, 32 members (30 TSV tables, a metadata file, a readme), 1.55 GB unpacked 2026-10-14 17:37 ET
- [ ] discover: data-profiling over every table; the operator's answers; approved findings
- [ ] plan-parts: one onboarding per part, in dependency order
- [ ] For each part: identify, profile, map (the source extract and the Dataset Contract), quality, metadata, test, approve, switch-on
- [ ] Securities from 13F: CUSIP and ticker attached to the Security
  - [x] 13F findings approved: operator, "yes approve the 13F findings", 2026-10-14 20:54 ET
  - [x] map: `rules/sources/sec.thirteenf.information_table/` and `rules/merge/kinds/security.yaml` (matching rule `security-cusip`, declared, not switched on); tested on all 999 local files, 20,311 Securities accepted, 9,631 set aside (onboarding log) 2026-10-14 22:31 ET
  - [x] quality: 0 checks drafted, no `quality.yaml` (onboarding log; skill line in PR #982) 2026-10-15 05:30 ET
  - [x] Proving Run: 20,311 Securities, 0 CUSIPs on two Securities, second pass changed nothing (`proving-run.json`) 2026-10-14 22:51 ET
  - [ ] approve and switch on the Security matching rule `security-cusip` and its CUSIP Identifier Contract: waiting for the operator's words
  - [ ] ~~ticker on the Security~~ deferred to ticket 80 (Onboard OpenFIGI): the 13F files carry no ticker
  - [ ] ~~which filed name and title a Security keeps~~ deferred to ticket 84: filers disagree on 13% of holding rows
- [ ] N-PORT findings answered from the rulings (`.scratch/onboarding/sec.nport/findings-answers.md`): waiting for the operator's approval
- [ ] Funds hold securities: `HOLDS` from a fund to a Security
- [ ] Every gap in a skill found on the way: fixed in the skill, on its own branch
  - [x] ticket 81 (identifier types as configuration, #975 merged), ticket 82 (a reduction reads several source extracts, #978 merged), profiler reuse (#976 merged)
  - [ ] ticket 83 (no output caps, #981), data-quality and identifier types (#982), profiler issued identifiers (#983): CI green, waiting for the merge word
- [ ] PR, CI green, merge on the operator's word
- [ ] Learning → skill
