# Ticket 08 handoff to Codex: SEC-to-GLEIF matching rules (2026-09-25)

The operator asked Claude to write this note and give the Company mastering
work to Codex to continue. Claude's branch is
`claude/company-mastering-08-sec-gleif-matching`, PR
[#713](https://github.com/paulananth/edgartools-platform/pull/713); the
Claude worktree is
`/Users/aneenaananth/projects/edgartools-platform-worktrees/claude-cm-08`.
Do not commit to the Claude branch from Codex. The operator authorised the
merge of #713 (2026-09-25 15:21 ET); Claude merges it once all seven CI
checks are green on its final head. Check `gh pr view 713` first. Then cut a
new `codex/<topic>` branch off `origin/main` in its own worktree.

## Exact approval: declared, not active

The operator approved the policy fingerprint
`983352e81d295a165a1391e82fa8a24a710e6f638361a577f18f541917fd4049`
(2026-09-25 15:21 ET). It is the live Company policy: `digest(POLICY)` in
`edgar_warehouse/mdm/clean/company_source.py`. It replaced ticket 12's
`35250dad…1321`, which the tests no longer pin as live.

- The two matching rules are **declared** in `policies/company.json`, with the
  `name_binding` bar (95% one-sided lower bound at 95% confidence):
  - **Name-and-state rule**, `sec-gleif-name-jurisdiction` 2026-09-25.1;
  - **Postcode rule with state veto**, `sec-gleif-name-postal` 2026-09-25.2.
- Neither is **active**. `automatic_rules` names only the Account hold-back
  (classification .13). `NAME_PROOFS` keep `approved_by`/`approved_at` as
  `None`: switching a rule on is a separate operator decision, not given.
  `test_no_matching_rule_is_active` holds this.
- Any change to the policy body changes the fingerprint. Compute it, explain
  it in plain English, and get the operator's approval before registering or
  merging. Say rule names, never ".1"/".2", to the operator.

## What the rules do and what was proved

An SEC Company and a GLEIF record link when their names are equal **with the
legal form kept** (WAYFAIR INC is not WAYFAIR LLC), no other SEC filer and no
other GLEIF legal entity carries that name, and the place agrees (state or
country of incorporation; or headquarters postcode with no conflicting places
of incorporation). A rule only **joins** a waiting GLEIF record to the
Company its SEC record already holds by CIK; it never creates a Company.

- Name-and-state rule: 300/300, lower bound 0.9911, 0 of 257 adversarial
  pairs wrong. Postcode rule with state veto: 300/300, 0.9911, 0 of 315. The
  first postcode version failed (19 of 162; AAON, Inc.) and is not declared.
- 3,050 of the 6,414 Account hold-back Companies match. The production census
  and rule tests reproduce the research exactly (`research/08-parity.py`).
- CI re-hashes the frozen research files and re-scores the labels
  (`TestTheNameMatchingRules` in `tests/mdm/test_clean_activation.py`).
- One person designed the rules and labelled the pairs; the draws were held
  back from the design.

Full detail: `08-qualify-sec-to-gleif-fuzzy-binding.md` (checklist, Design,
"Decisions made while building"); operation: `docs/specs/clean-mdm/local-operations.md`
(the `mdm name-census` command, the `--name-census` bundle input).

## Limits Codex inherits

1. **No undo for a wrong link.** The Stage cannot reverse or move an
   established binding ("requires a correction contract"), and a Match
   Exclusion is Company-to-Company only. Identity correction is a new ticket
   and must land before either rule is switched on.
2. **Silver drops SEC's `countryCode`.** `sec_company_address` keeps
   `stateOrCountry` only, so 10 postcode matches wait in production, Shell
   (`0001306965`) among them. A warehouse change fixes it.
3. **No SEC record holds a Company automatically yet.** Ticket 04's identifier
   rules are not active in the live policy; they need their own approval. The
   matching rules depend on them.
4. **The census must be rebuilt for each full GLEIF Golden Copy.** The rule
   checks each record's `gleif_last_update` against the census; it cannot see
   a new entity that took a matched name later. A delta is refused.
5. Below-the-bar routing to a Steward is not built; an unmatched pair waits.

## Local data (not in the repo)

- `~/.local/share/edgartools/clean-mdm/research/gleif-20260911-1600/`: the
  pinned Golden Copy (sha256 `1b6cd9cd…a36a6a`).
- `~/.local/share/edgartools/clean-mdm/research/cm08-gleif-all.jsonl`: the
  extract `08-extract-gleif-all.py` writes.
- The SEC bronze scan, Company list and coverage files (`cm08-sec-scan.jsonl`,
  `cm08-companies.jsonl`, `cm08-coverage*.jsonl`) were in Claude's session
  scratchpad and may be gone. Their hashes are in `research/08-draft-rule.md`
  ("Files and hashes") and the proofs (`3b51d0ac…`, `97e5d118…`);
  `08-companies.py` and `08-coverage.py` rebuild the last two from the scan.
  CI does not need them.

Zero SEC requests: bronze only.

## Open operator decision

Claude asked the operator whether to open three follow-up tickets: identity
correction (undo a wrong link), SEC `countryCode` in silver, and approval of
ticket 04's identifier rules. **The operator has not answered.** Ask before
writing them; do not record them as decided.

## Codex's next steps

1. Confirm #713 is merged and `main`'s `digest(POLICY)` is `983352e8…4049`.
2. Put the open decision above to the operator.
3. Continue the Company milestone from `.scratch/company-mastering/remaining-work.md`
   and `docs/specs/clean-mdm/company-completion.md`: the dated Company table
   (ticket 09), latest-only Stage (10), ticket 04's safety items, then the
   whole Proving Run and final approval (05, 06).
