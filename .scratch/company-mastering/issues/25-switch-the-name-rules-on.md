# Switch the two name matching rules on

Type: task
Status: in review (Claude, branch `claude/company-mastering-25-name-rules-on`)
Blocked by: nothing
Blocks: the completion gate's local run (one master per Company with CIK and LEI)

## Operator rulings

- "both i want to complete company master" (2026-09-29): switch on the two
  proven name rules first, then the cascade passes (ticket 20).
- Asked, with the rules and their proofs in plain words, "Do you approve
  switching on both name rules?": **"yes"** (2026-09-29, recorded 21:04 ET).

## Done

- `rules approve --merge platform --rule` (rules skill ticket 14) recorded the
  approval on each rule: `approved_by: operator`, `approved_words: yes`,
  `approved_at` 2026-09-30T01:04:15Z (name-and-state) and 01:04:24Z
  (postcode). Each proof in `merge/policy.yaml` is its measured proof from
  `pending-proofs.yaml`, unchanged, plus the approval.
- The Company policy is now `75bd2b67…33dbe`; peeling this ticket's layer
  (`tests/mdm/policy_layers.py`, `without_name_rules_on`) gives back
  `15e07b30…b6d6`, so every earlier approval still verifies.
- `company_source.name_matching_policy`, the test helper that switched the
  rules on artificially, is gone: the policy itself switches them on now.

## Next

- The local run of the completion gate: ticket 05's pinned 7,000 SEC
  submissions files (copied again from bronze, reads only, to
  `~/.local/share/edgartools/clean-mdm/captures/sec.submissions.company/cm05-7000/`,
  7,000 documents, 638 MB, ticker catalog `836140c5…`) and the pinned GLEIF
  Golden Copy, through the Merge Stage on a throwaway PostgreSQL 16.
