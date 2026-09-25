# Ticket 12 handover to Codex: the Account hold-back (2026-09-25)

Claude hands ticket 12 to Codex because its session limit is running out
(operator, 2026-09-25). **Work on your own branch**
`codex/company-mastering-12-account-hold-back`, cut from the head of
`claude/company-mastering-12-prove-sec-classification` (PR #710, a draft).
Never commit to the Claude branch. Open your own PR, or ask the operator
whether to retarget #710.

Standing rules: CLAUDE.md, and the ticket file
`12-prove-and-switch-on-the-sec-company-classification-rule.md`, which
holds the live checklist, the decisions and the rule version names. Talk to
the operator in plain English and business terms. Give rule versions their
names (the "Account hold-back"), never ".13". Ask only for:
- digest approval;
- a kind question no ruling covers;
- merge.

## Where it stands

The **Account hold-back**, rule `sec-company-candidate` `2026-09-25.13`
(`edgar_warehouse/mdm/policies/company.json`), is measured and **passes**:
- sample 600 of 600, lower bound 0.9955;
- steps 8 and 10 each 300 of 300, lower bound 0.9911, against the 0.95 bar;
- adversarial 0 of 328.

Evidence is under `.scratch/company-mastering/research/12-13-*`:
- `12-13-summary.json` holds the scores and the file hashes;
- `12-13-label.py` holds the hand-read labels and every borderline note.

Built on this branch since #711 merged:
- The SEC contract reads the ticker catalog (`sec_company_ticker`) and the
  filing list (`sec_company_filing`) beside the Company member, through
  `_pin_evidence` in `clean/company_source.py`. Adapter
  `sec-company-landing-v4`.
- The primitive `values_overlap@1`.
- `token_match@2`: the ampersand fix. `@1` is restored unchanged.
- Rule steps `4`, `6b`, `7a` and `7b` with Probable Kinds.

The last commit writes the Account hold-back's `PROOF` and
`PENDING_ACTIVATION` in `clean/company_source.py`. The activation check
passes when test approval fields are filled in. `automatic_rules` is still
empty, so nothing acts alone.

## Next, in order

1. **Update the 6 tests that still pin the Legal-form rule (.8):**
   - `tests/mdm/test_clean_activation.py`:
     - `test_the_policy_is_the_pending_digest`: pin the new `digest(POLICY)`;
     - `test_the_proof_files_match_the_pinned_hashes`: read `12-13-summary.json`, not `12-summary.json`;
     - `test_the_measured_sec_rule_clears_the_bar_at_every_company_step`: steps `["8", "10"]`, not `["2", "4"]`;
     - the `proof()` helper's `by_step` covers `range(10)`: add `"10"`, and any other step id a test rule uses.
   - `tests/mdm/test_clean_company_source.py`:
     - `TEST_POLICY` rule_version becomes `2026-09-25.13`;
     - step asserts `"5"` → `"8"`;
     - the step-four test now concerns step `10`;
     - records need `tickers`/`forms` where a step reads them.
2. Run the MDM unit suite plus `tests/architecture`, and the PG16 clean suite (`tests/integration/test_clean_*.py`, Docker via Colima). Get CI green.
3. Run the three-axis `/code-review` (Standards, Spec, GoF) of the branch against `origin/main`, and fix the findings.
4. Write a plain-English approval brief that says what the rule does, the numbers, the borderline readings, and what the digest is. The operator approves the **exact digest**, then set `approved_by`/`approved_at` from the operator's real approval time, taken from `date`.
5. Activate (`POLICY["automatic_rules"] = [PENDING_ACTIVATION]` with approval), re-run the four-company PG16 test, get CI green, and merge only on the operator's word.

## Known caveats to carry into the brief

- Tickers come from the newest bronze catalog, 2026-09-02, which is three weeks old.
- The forms in the research come from each filer's recent submissions page. The contract reads `sec_company_filing`.
- Step 5's Probable Kind (Fund Structure) is an even split: 16 Funds against 18 Companies, of which 13 are BDCs.
- Borderline Companies are read by standing standards: S-11 non-traded REITs, listed royalty trusts, and government-owned corporations such as the TVA.
- 91.58% of SEC filers wait in the Stage, mostly persons, Form D filers and advisers.
- Re-reading a committed deferred publication after a Probable Kind change collides. This is the limit accepted on 2026-09-23.
- Two old research scripts (`12-options-10.py`, `12-ticker-sources.py`) patched the old `_tokens_found` signature and no longer rerun.
