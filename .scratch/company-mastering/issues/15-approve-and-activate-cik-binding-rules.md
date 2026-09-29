# Approve and activate the CIK binding rules

Type: task
Status: approved and switched on in the branch (Claude, `claude/company-mastering-15-activate-cik-rules`); merge on the operator's word
Blocked by: 04, 05, 06
Blocks: automatic SEC Company creation and SEC-to-GLEIF name-rule activation

## Outcome

Present the exact policy fingerprint and verified Identifier Contract for the
CIK binding rules already implemented by ticket 04. Obtain separate operator
approval, then activate only the approved rules and register that exact policy.
The approval of ticket 08's declared name rules does not activate these.

## Checklist

- [x] Close the ticket 04 safety items: suspended identifiers, recheck of an
  existing Company before saving, crash recovery of assessments, caller as-of
  publish time, and a real concurrent-run test. Built (Claude, 2026-09-26):
  ticket 04, "Closing the five open safety items". Merged in PR #721
  (`3ea3a6b1`, 2026-09-26 10:47 ET).
- [x] The operator answers two questions (ticket 04, "Suspended identifier"):
  1. When a Company is in review because its own records disagree on an
     identifier (for example two SEC records naming two CIKs), should the
     matching rules stop adding any record to it until the conflict is
     resolved? Built that way; the record waits in the Stage with a review.
     **Operator, 2026-09-29 06:58 ET: yes**, keep it as built: no rule adds a
     record to a Company in review until the conflict is resolved.
  2. Should an identifier stated by a source that does not issue it (a
     GLEIF record carrying a CIK) be able to put a Company in review at
     all? Today it can; it does not arise under today's adapters.
     **Operator, 2026-09-29 07:06 ET: agreed, no.** Only the issuer's own
     records count toward an identifier conflict; another source's stray
     value is ignored for it (Q14). It cannot arise today, so it is built
     when a feed first maps an identifier it does not issue:
     `tests/mdm/test_clean_cik_contract.py` fails at that moment.
- [x] Declare the rule and its Identifier Contract in `rules/`, switched off
  (2026-09-29 06:57 ET): `company-cik` and `identifiers.cik` in
  `merge/kinds/company.yaml`, byte for byte ticket 05's candidate
  (`research/05-candidate-policy.json`). The verification block is the corpus
  hash only (ticket 05's manifest, `3607ae6c…60cc`, re-hashed today); its
  counts stay in the ticket, so they do not move the digest. The Mapping
  Document words the rule. Two differences from ticket 05's body, neither a
  change in behaviour: the rule sits second in `rules` (the candidate put it
  last; binding rules are selected by family, not order), and the policy
  version stays `sec-company-local-v2` (the candidate named its own,
  `company-2026-09-26.cik-matching-rule`).
- [x] Verify CIK uniqueness, conflicting or stale identifiers, duplicate and
  reordered delivery, idempotent retry, and no unapproved consolidation on
  PostgreSQL 16, on the production policy with only the approval's changes
  (`tests/integration/test_clean_cik_rule.py`): the committed policy matches
  nothing; three records carrying one CIK, across two batches, make one
  Company; a Company whose records name two CIKs waits in review and gains no
  record (question 1); a redelivered batch returns its first result; a new
  revision creates nothing; reordered delivery ends in one Company; two
  filers with one name stay two Companies; a GLEIF record with the name waits.
  A *stale* identifier (one record's CIK changing) is the gap under Found,
  an xfail here. The concurrent run and the stale-proposal retry are proven
  on ticket 04's fixture rules (`test_clean_identifier_binding.py`), not on
  the production policy.
- [x] Record the operator-approved fingerprint, activation time, full proof, and
  resulting active fingerprint before shared registration.
  - **Approved:** `0d4d5cb0f190a4486c7cc65c7ba71b4dc173e3ce82eb2734261caea7c6c20702`,
    operator, **2026-09-29 07:27 ET** ("approved"), after the brief below.
  - **Switched on:** the contract's `approved_by`, `approved_at`
    (`2026-09-29T11:27:26Z`) and `reason` filled, and one `deterministic`
    activation for `company-cik` in `merge/policy.yaml`. Nothing else changed.
  - **Active fingerprint:** `15e07b302482bbbe191fd5b89855373f04f18db31a3c9caaa733f1bc87b9b6d6`.
    Peeling the approval gives back `0d4d5cb0…0702`, then `8bdc2f68…555d`,
    `3520e890…1e17` and `983352e8…4049` (`tests/mdm/policy_layers.py`).
  - **Full proof:** ticket 05 (the Proving Run), this ticket's PG16 suite on
    the approved policy, and ticket 04's fixture suite.
  - Not yet registered anywhere shared; that follows the merge.

## Found (2026-09-29 06:57 ET, Claude)

- **A bound record whose CIK changes re-keys its Company silently.** On
  PG16: an SEC record bound to Company A delivers a new revision naming
  another CIK; A now holds only the new CIK, stays accepted, and a real filer
  with that CIK then joins A. It is an `xfail(strict=True)` in
  `test_clean_cik_rule.py`, asserting the right outcome (review, no join).
- **Today's SEC reading cannot reach it:** its record key and its CIK are one
  column (`cik`) in one format (`sec_cik`), so a record's CIK never changes.
  `tests/mdm/test_clean_cik_contract.py` pins that; a mapping that separates
  them fails CI first.
- **The fix is not this ticket's:** Q9's "rebuild from remaining trusted
  evidence" for a CIK contradiction (ticket 04 noted it has no ticket). On the
  map's "Not yet specified".
- **Reversal:** none proven. A CIK bind carries its rule and version, so
  ticket 13's rerun would find it, but revoking a bind that *created* a
  Company is unbuilt and unproven (ticket 13 proves name-rule links only).

## The brief (Claude, 2026-09-29 06:57 ET)

- **The digest to approve:** `0d4d5cb0f190a4486c7cc65c7ba71b4dc173e3ce82eb2734261caea7c6c20702`,
  today's committed policy (`rules/`), with the CIK rule declared and off.
- **Why ticket 05's proof holds for it:** without the CIK rule and contract
  it is `8bdc2f68…555d` (ticket 21); without the cascade's seven passes too
  it is `3520e890…1e17`; without the place-code table too it is
  `983352e8…4049`, the policy ticket 05's candidate was built on. The rule
  and contract are ticket 05's, byte for byte. Everything else that differs
  is declared and switched off, or a table the CIK rule does not read.
- **What it may do / not do, numbers:** as ticket 06's brief (6,414 of 6,414
  Companies by their CIK, 0 controls, no CIK on two Companies, a second pass
  changed nothing).
- **The key invariant:** the rule relies on an SEC record's CIK being its
  key. If a later mapping let the two differ, a Company could silently take a
  new CIK and another filer could join it. Today they cannot differ; a test
  pins it.
- **Tolerance:** the spec's `sec.cik` row, written for a Person; with
  `kind_equal@1` its name-mismatch alarm may never fire for a Company.
- **After approval:** the contract's `approved_by`, `approved_at` and
  `reason`, and one `deterministic` activation in `merge/policy.yaml`; that
  final digest is shown before any shared registration.
